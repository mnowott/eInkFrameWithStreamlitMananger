# eInkFrame — An eInk Digital Picture Frame Powered by Raspberry Pi and Python

![Screenshot 2025-05-01 201531](https://github.com/user-attachments/assets/5bd552d1-ae64-4cdf-9b72-edce30af698a)

### The **eInkFrame** is a robust digital picture frame powered by Raspberry Pi that utilizes a [Waveshare 7.3 inch 7-Color ePaper Display](https://www.waveshare.com/7.3inch-e-paper-hat-f.htm) for a natural look. Simply upload images in a supported format to a micro SD card, and the display will automatically cycle through them at a customizable interval!

---

## Contents

- [Required Hardware](#required-hardware)
- [Pi Setup](#pi-setup)
- [Assembly](#assembly)
- [Using the Frame](#using-the-frame)
- [Video Demo](#video-demo)

---

## Required Hardware

| Item | Link |
|------|------|
| Raspberry Pi Zero 2 W | [Amazon](https://amzn.to/3YBvaBV) |
| Pi Power Supply | [Amazon](https://amzn.to/42dMak0) |
| Waveshare 7.3" 7-Color ePaper Display | [Amazon](https://amzn.to/42fzjOk) |
| Picture Frame 3D Print Files | [Printables](https://www.printables.com/model/1287334-eink-picture-frame) |
| 2x Micro SD Cards (for OS & images) | [Amazon](https://amzn.to/3EoRUhC) |
| Micro USB to Micro SD Card Reader | [Option 1](https://amzn.to/4iNaMVC), [Option 2](https://ebay.us/pmuPZh) |
| Screws/Nuts (if using 3D prints) | 2x M3x20mm screws and nuts |

---

## Pi Setup

**Before starting**, ensure that your Pi is running Raspberry Pi OS 32 or 64-bit (Lite not supported), and is connected to your home network.  
If you need help installing Raspberry Pi OS, follow the [official guide](https://www.raspberrypi.com/documentation/computers/getting-started.html#installing-the-operating-system).

Once your Pi has booted, open Command Prompt (Windows) or Terminal (Mac), and SSH into the Pi:

```bash
ssh pi@pi.local
```

Then run the following to clone the project and begin setup:

```bash
git clone https://github.com/EnriqueNeyra/eInkFrame.git
cd eInkFrame
sudo bash setup.sh
```

Be sure to **reboot** the Pi after the setup script completes.

---

## Assembly

### 1. Attach the Pi and driver board, ensuring the pin headers are fully inserted.
<p align="center"><img src="https://github.com/user-attachments/assets/6a8b445e-f5aa-4209-9d59-1f44771c8c97" width="700"></p>

### 2. Insert the Pi and driver board into the enclosure.
<p align="center"><img src="https://github.com/user-attachments/assets/e239cbd2-ec13-4ce6-b5a3-7ec788c9c889" width="700"></p>

### 3. Insert the M3 nuts into the slots at the bottom of the frame.
<p align="center"><img src="https://github.com/user-attachments/assets/1424cc05-c8ca-4eee-a023-0ed3894e8e58" width="700"></p>

### 4. Carefully slide the eInk display into the frame, ensuring it's secured under the notch at the top.
<p align="center"><img src="https://github.com/user-attachments/assets/0aa116d8-0ff4-4fcd-921d-744f1de8a531" width="700"></p>

### 5. Tuck the ribbon cables into the Pi enclosure and connect to the display cable.
<p align="center"><img src="https://github.com/user-attachments/assets/1f097542-2afd-4506-b957-2a9bd27435b7" width="700"><br>
<img src="https://github.com/user-attachments/assets/05a9b906-0a23-47dd-a1ed-2d7c4fdf8e96" width="700"></p>

### 6. Align the enclosure holes with the display, and secure the stand using 2 M3x20mm screws.
<p align="center"><img src="https://github.com/user-attachments/assets/280c1f53-32ee-486b-861c-43cb786ad754" width="700"></p>

Assembly is now complete!

---

## Using the Frame

Upload any images you want displayed to a clean Micro SD card. Recommended and tested formats include: JPG/JPEG, PNG, TIFF, and BMP.

The default image cycle time is 600 seconds (10 minutes), and new images are chosen randomly while avoiding repeats. Optionally, the default timing can be customized by adding a `.txt` file to the SD card that specifies the refresh time **in seconds**:

**Requirements for `refresh_time.txt`:**
1. Must be named `refresh_time.txt`
2. Must be placed at the root of the SD card (not in a folder)
3. The text file should contain **only a single number**

Use the Micro USB to Micro SD card adapter to plug the SD card into the Pi, then connect power.
After a few moments, a “Beginning Setup...” message will appear. Setup time depends on the number of images on the SD card.

### SD + Power Connections & Setup Screen
<table>
<tr>
<td><img src="https://github.com/user-attachments/assets/1a624bbd-fe04-43ba-9848-4d6f9a4e9256" width="500"></td>
<td><img src="https://github.com/user-attachments/assets/0caeab3e-0e62-4c46-a58e-45cc1a4e156e" width="500"></td>
</tr>
</table>

Your first image should appear shortly!

---

## Video Demo

> ⚠️ Note: The video was shortened due to upload size constraints.  
> Actual setup can take several minutes. Image display/refresh time is ~30 seconds.

<video src="https://github.com/user-attachments/assets/c6cf8acc-d6ac-4012-bf26-b0e4b8fefe73">

---

## Questions?

Open an issue or reach out via GitHub!

## NEW

1. Updated sd_monitor.py

Changes vs your original:

Reads settings.json from these locations (first found wins):

/etc/epaper_frame/settings.json

~/.config/epaper_frame/settings.json

settings.json next to the scripts

Uses change_interval_minutes from settings for refresh time (fallback to refresh_time.txt on SD, then 600s).

Uses stop_rotation_between to pause/stop frame_manager.py during quiet hours, so the display keeps the last image (no updates between times).

2. New frame_manager.py (using your original structure)

Goals implemented here:

Keeps your structure with ImageConverter and DisplayManager.

Uses settings.json to:

Decide which SD card images to process based on picture_mode and s3_folder.

"both" → all files on the SD card

"local" → all files except in <sd_root>/<s3_folder>/

"online" → only files in <sd_root>/<s3_folder>/

Keeps a boot picture separated from the rotation:

Boot picture is shown via display_manager.display_message('start.jpg') (like before).

Rotation uses only the converted SD images (from ImageConverter into PIC_PATH), so the boot picture is not part of the rotation.

You can use any placeholder text image as start.jpg inside whatever location DisplayManager uses for that.

To enforce local / online / both without touching ImageConverter, we:

Optionally build a temporary filtered copy of the SD contents (excluding s3_folder) for picture_mode="local".
