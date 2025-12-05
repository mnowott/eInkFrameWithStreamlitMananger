#!/usr/bin/env python3
import os
import sys
import time
import subprocess
import signal
import json
from datetime import datetime, time as dtime
import gpiozero
# from lib.waveshare_epd import epdconfig

USERNAME = os.getenv("SUDO_USER") or os.getenv("USER")
SD_MOUNT_BASE = f"/media/{USERNAME}"  # Adjust as needed
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_PROCESSING_SCRIPT = os.path.join(SCRIPT_DIR, "frame_manager.py")
process = None  # Holds the subprocess running frame_manager.py
sd_was_removed = False  # Track if SD card was removed

# ---------------------------------------------------------
# Settings handling
# ---------------------------------------------------------

DEFAULT_SETTINGS = {
    "picture_mode": "local",          # local | online | both
    "change_interval_minutes": 15,    # integer minutes
    "stop_rotation_between": None,    # or {"evening": "HH:MM", "morning": "HH:MM"}
    "s3_folder": "s3_folder"          # folder name on SD card for "online" images
}

SETTINGS_LOCATIONS = [
    "/etc/epaper_frame/settings.json",
    os.path.expanduser("~/.config/epaper_frame/settings.json"),
    os.path.join(SCRIPT_DIR, "settings.json"),
]


def load_settings():
    """Load settings.json from one of the predefined locations, shallow-merging into DEFAULT_SETTINGS."""
    settings = DEFAULT_SETTINGS.copy()
    for path in SETTINGS_LOCATIONS:
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    for key in DEFAULT_SETTINGS.keys():
                        if key in data:
                            settings[key] = data[key]
                print(f"[sd_monitor] Loaded settings from {path}")
                break
            except Exception as e:
                print(f"[sd_monitor] Error reading settings from {path}: {e}")
    return settings


# ---------------------------------------------------------
# Refresh time handling
# ---------------------------------------------------------

def get_refresh_time(sd_path, filename="refresh_time.txt", settings=None):
    """Determine refresh time in seconds, preferring settings.json, falling back to SD card file, then default."""
    if settings is None:
        settings = DEFAULT_SETTINGS

    # 1) Try settings.json (change_interval_minutes)
    change_interval = settings.get("change_interval_minutes")
    try:
        if change_interval is not None:
            minutes = int(change_interval)
            if minutes > 0:
                return minutes * 60
    except Exception as e:
        print(f"[sd_monitor] Invalid change_interval_minutes in settings: {e}")

    # 2) Fallback to refresh_time.txt on SD card
    file_path = os.path.join(sd_path, filename)
    if os.path.exists(file_path):
        try:
            with open(file_path, "r") as f:
                number = f.read().strip()
                if number.isdigit():
                    return int(number)
                else:
                    print(f"[sd_monitor] Invalid number in {filename}, defaulting to 600")
                    return 600
        except Exception as e:
            print(f"[sd_monitor] Error reading {filename}: {e}")
            return 600
    else:
        print(f"[sd_monitor] {filename} not found, defaulting to 600")
        return 600


# ---------------------------------------------------------
# Quiet hours handling
# ---------------------------------------------------------

def parse_hhmm(value: str) -> dtime | None:
    try:
        parts = value.split(":")
        h = int(parts[0])
        m = int(parts[1])
        return dtime(hour=h, minute=m)
    except Exception:
        return None


def parse_stop_rotation_between(cfg) -> tuple[dtime, dtime] | None:
    """Return (evening_time, morning_time) or None."""
    if not cfg or not isinstance(cfg, dict):
        return None

    evening_str = cfg.get("evening")
    morning_str = cfg.get("morning")
    if not evening_str or not morning_str:
        return None

    evening = parse_hhmm(evening_str)
    morning = parse_hhmm(morning_str)
    if not evening or not morning:
        return None

    return (evening, morning)


def in_quiet_hours(now: datetime, evening: dtime, morning: dtime) -> bool:
    """
    Returns True if current time is within the "stop_rotation_between" interval.

    If evening < morning:
        - Quiet between same-day times, e.g. 20:00 -> 23:00
    If evening > morning (typical overnight):
        - Quiet between evening and next day's morning, e.g. 22:00 -> 07:00
    """
    current = now.time()

    if evening < morning:
        # same-day window
        return evening <= current < morning
    else:
        # crosses midnight
        return current >= evening or current < morning


# ---------------------------------------------------------
# Process handling
# ---------------------------------------------------------

def start_frame_manager(sd_path, settings):
    """Start the image processing script as a separate process."""
    global process
    if process is not None and process.poll() is None:
        print("[sd_monitor] Stopping existing frame_manager process...")
        process.send_signal(signal.SIGTERM)  # Gracefully terminate the process
        process.wait()
        print("[sd_monitor] Existing frame_manager process stopped.")
    
    # Compute refresh time
    refresh_time_sec = get_refresh_time(sd_path, settings=settings)
    
    print(f"[sd_monitor] Starting frame_manager with path {sd_path} and refresh_time_sec={refresh_time_sec}...")
    process = subprocess.Popen(
        ["python3", IMAGE_PROCESSING_SCRIPT, sd_path, str(refresh_time_sec)], 
        stdout=sys.stdout, 
        stderr=sys.stderr,
        text=True)
    print("[sd_monitor] frame_manager started.")


def stop_frame_manager(reason: str = ""):
    """Stop the running frame_manager process, if any."""
    global process
    if process is not None and process.poll() is None:
        msg = f"[sd_monitor] Stopping frame_manager process. Reason: {reason}" if reason else "[sd_monitor] Stopping frame_manager process."
        print(msg)
        try:
            process.send_signal(signal.SIGTERM)
            process.wait()
        except Exception as e:
            print(f"[sd_monitor] Error stopping frame_manager: {e}")
    process = None


def monitor_sd_card():
    """Continuously monitor the SD card and restart frame_manager if reinserted or quiet hours end."""
    global sd_was_removed
    sd_inserted = False

    settings = load_settings()
    quiet_cfg = parse_stop_rotation_between(settings.get("stop_rotation_between"))
    was_in_quiet = False

    if quiet_cfg:
        print(f"[sd_monitor] Quiet hours configured: {settings.get('stop_rotation_between')} (parsed={quiet_cfg})")
    else:
        print("[sd_monitor] No quiet hours configured.")

    while True:
        try:
            now = datetime.now()
            in_quiet = False
            if quiet_cfg:
                in_quiet = in_quiet_hours(now, quiet_cfg[0], quiet_cfg[1])

            items = os.listdir(SD_MOUNT_BASE)
            valid_dirs = [item for item in items if os.path.isdir(os.path.join(SD_MOUNT_BASE, item))]
            
            if valid_dirs:
                sd_path = os.path.join(SD_MOUNT_BASE, valid_dirs[0])

                if in_quiet:
                    # SD is present but within quiet hours -> stop rotation
                    if process is not None and process.poll() is None:
                        stop_frame_manager(reason="entering quiet hours")
                    sd_inserted = True
                    sd_was_removed = False
                    was_in_quiet = True
                else:
                    # Not in quiet hours, SD present
                    need_start = False

                    if not sd_inserted:
                        print("[sd_monitor] SD card inserted. Starting frame_manager...")
                        need_start = True
                    elif sd_was_removed:
                        print("[sd_monitor] SD card reinserted. Restarting frame_manager...")
                        need_start = True
                    elif process is None or process.poll() is not None:
                        print("[sd_monitor] frame_manager not running, starting...")
                        need_start = True
                    elif was_in_quiet:
                        print("[sd_monitor] Quiet hours ended, restarting frame_manager...")
                        need_start = True

                    if need_start:
                        start_frame_manager(sd_path, settings)
                        sd_inserted = True
                        sd_was_removed = False
                        was_in_quiet = False

            else:
                # No SD card mounted under SD_MOUNT_BASE
                if sd_inserted:
                    print("[sd_monitor] SD card removed.")
                    sd_inserted = False
                    sd_was_removed = True
                    stop_frame_manager(reason="SD card removed")

        except Exception as e:
            print(f"[sd_monitor] Error monitoring SD card: {e}")

        time.sleep(2)  # Check every 2 seconds


def cleanup_stale_mounts():
    for folder in os.listdir(SD_MOUNT_BASE):
        full_path = os.path.join(SD_MOUNT_BASE, folder)

        # Skip non-directories
        if not os.path.isdir(full_path):
            continue

        # Try to access the folder (read + execute)
        if not os.access(full_path, os.R_OK | os.X_OK):
            print(f"[sd_monitor] Stale or inaccessible mount detected: {full_path}, attempting to remove...")

            # Try to remove it
            try:
                subprocess.run(["sudo", "rm", "-r", full_path], check=True)
                print(f"[sd_monitor] Removed stale mount folder: {full_path}")
            except subprocess.CalledProcessError as e:
                print(f"[sd_monitor] Failed to remove {full_path} (subprocess error): {e}")
            except Exception as e:
                print(f"[sd_monitor] Unexpected error removing {full_path}: {e}")


if __name__ == "__main__":
    cleanup_stale_mounts()
    monitor_sd_card()
