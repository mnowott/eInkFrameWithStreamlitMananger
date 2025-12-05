#!/usr/bin/env python3
from image_converter import ImageConverter
from display_manager import DisplayManager
import os
import shutil
import sys
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PIC_PATH = os.path.join(SCRIPT_DIR, 'pic')
# Optional temp directory used when picture_mode == "local"
FILTERED_SD_PATH = os.path.join(SCRIPT_DIR, "sd_filtered")

# ---------------------------------------------------------
# Settings handling
# ---------------------------------------------------------

DEFAULT_SETTINGS = {
    "picture_mode": "local",          # local | online | both
    "change_interval_minutes": 15,    # NOT used directly here (sd_monitor handles refresh time)
    "stop_rotation_between": None,    # handled in sd_monitor, not here
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
                print(f"[frame_manager] Loaded settings from {path}")
                break
            except Exception as e:
                print(f"[frame_manager] Error reading settings from {path}: {e}")
    return settings


def build_local_only_source(sd_path: str, s3_folder_name: str) -> str:
    """
    Build a temporary directory that mirrors sd_path but EXCLUDES the s3_folder subtree.
    Returns the path to the filtered directory.
    """
    sd_path = os.path.abspath(sd_path)
    s3_full = os.path.join(sd_path, s3_folder_name)
    s3_full = os.path.abspath(s3_full)

    # Clean / recreate filtered dir
    if os.path.exists(FILTERED_SD_PATH):
        shutil.rmtree(FILTERED_SD_PATH)
    os.makedirs(FILTERED_SD_PATH, exist_ok=True)

    print(f"[frame_manager] Building local-only source in {FILTERED_SD_PATH}, excluding {s3_full}")

    for root, dirs, files in os.walk(sd_path):
        root_abs = os.path.abspath(root)

        # Do not descend into s3_folder subtree
        dirs[:] = [d for d in dirs if os.path.abspath(os.path.join(root_abs, d)) != s3_full]

        # If we're inside s3_folder anyway, skip (defensive)
        if root_abs.startswith(s3_full + os.sep) or root_abs == s3_full:
            continue

        rel_root = os.path.relpath(root_abs, sd_path)
        if rel_root == ".":
            dest_root = FILTERED_SD_PATH
        else:
            dest_root = os.path.join(FILTERED_SD_PATH, rel_root)

        os.makedirs(dest_root, exist_ok=True)

        for filename in files:
            src_file = os.path.join(root_abs, filename)
            dest_file = os.path.join(dest_root, filename)
            try:
                shutil.copy2(src_file, dest_file)
            except Exception as e:
                print(f"[frame_manager] Failed to copy {src_file} -> {dest_file}: {e}")

    return FILTERED_SD_PATH


def get_effective_source_dir(sd_path: str, settings: dict) -> str:
    """
    Decide which part of the SD card to use based on picture_mode and s3_folder.

    - both  -> entire sd_path
    - online -> only <sd_path>/<s3_folder>
    - local  -> sd_path excluding <sd_path>/<s3_folder> (via a filtered copy)
    """
    picture_mode = settings.get("picture_mode", "local")
    s3_folder = settings.get("s3_folder", "s3_folder")
    sd_path = os.path.abspath(sd_path)

    print(f"[frame_manager] picture_mode={picture_mode}, s3_folder={s3_folder}")

    if picture_mode == "online":
        online_path = os.path.join(sd_path, s3_folder)
        print(f"[frame_manager] Using online-only images from: {online_path}")
        return online_path

    if picture_mode == "local":
        filtered_path = build_local_only_source(sd_path, s3_folder)
        print(f"[frame_manager] Using local-only images from filtered path: {filtered_path}")
        return filtered_path

    # "both" or any unknown value -> entire SD card
    print(f"[frame_manager] Using all images from SD path: {sd_path}")
    return sd_path


if __name__ == "__main__":

    # Collect arguments from the command line
    if len(sys.argv) < 3:
        print("Usage: frame_manager.py <sd_path> <refresh_time_sec>")
        sys.exit(1)

    sd_path = sys.argv[1]
    refresh_time = int(sys.argv[2])
    print(f"[frame_manager] Received SD path: {sd_path}")
    print(f"[frame_manager] Received refresh time: {refresh_time} seconds")

    # Load settings (picture_mode, s3_folder, etc.)
    settings = load_settings()

    # Decide which source directory to feed into ImageConverter based on picture_mode
    effective_source_dir = get_effective_source_dir(sd_path, settings)

    # Delete existing directory and create a new one
    # This is where the converted images will be stored & read by DisplayManager
    if os.path.exists(PIC_PATH):
        shutil.rmtree(PIC_PATH)
    os.makedirs(PIC_PATH, exist_ok=True)

    # Set up DisplayManager using the converted images folder
    display_manager = DisplayManager(image_folder=PIC_PATH, refresh_time=refresh_time)
    print("[frame_manager] DisplayManager created")

    # ImageConverter will process images from the effective source dir into PIC_PATH
    image_converter = ImageConverter(source_dir=effective_source_dir, output_dir=PIC_PATH)
    print("[frame_manager] ImageConverter created")

    # ------------------------------------------------------------------
    # Boot picture: separate from SD content
    #
    # display_message('start.jpg') is treated as the boot screen.
    # This image is NOT part of the rotating SD images converted into PIC_PATH.
    # You can replace the underlying 'start.jpg' asset with a placeholder text image.
    # ------------------------------------------------------------------
    try:
        display_manager.display_message('start.jpg')
        print("[frame_manager] Boot image (start.jpg) displayed")
    except Exception as e:
        print(f"[frame_manager] Error displaying boot image: {e}")

    # Process images from the SD card
    try:
        print("[frame_manager] Processing images from SD card, please wait...")
        image_converter.process_images()
        print("[frame_manager] Image processing finished")
    except Exception as e:
        print(f"[frame_manager] Error during image processing: {e}")

    # Start displaying images
    try:
        print("[frame_manager] Starting image rotation...")
        display_manager.display_images()
    except Exception as e:
        print(f"[frame_manager] Error during image display: {e}")
