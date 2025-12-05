#!/bin/bash

echo "Enabling SPI interface..."
sudo sed -i 's/^dtparam=spi=.*/dtparam=spi=on/' /boot/config.txt
sudo sed -i 's/^#dtparam=spi=.*/dtparam=spi=on/' /boot/config.txt
sudo raspi-config nonint do_spi 0

echo "Enabling I2C interface..."
sudo sed -i 's/^dtparam=i2c_arm=.*/dtparam=i2c_arm=on/' /boot/config.txt
sudo sed -i 's/^#dtparam=i2c_arm=.*/dtparam=i2c_arm=on/' /boot/config.txt
sudo raspi-config nonint do_i2c 0

echo "Setting up python script epaper service..."
SERVICE_NAME="epaper.service"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}"
CURRENT_USER=${SUDO_USER:-$(whoami)}
CURRENT_HOME=$(eval echo "~$CURRENT_USER")

sudo tee "$SERVICE_PATH" > /dev/null <<EOF
[Unit]
Description=ePaper Display Service
After=network.target

[Service]
ExecStart=/usr/bin/python3 $(pwd)/sd_monitor.py
WorkingDirectory=$(pwd)
Restart=always
User=$CURRENT_USER

[Install]
WantedBy=multi-user.target
EOF

echo "Creating default settings.json (if not present)..."
CONFIG_DIR="${CURRENT_HOME}/.config/epaper_frame"
CONFIG_PATH="${CONFIG_DIR}/settings.json"

sudo -u "$CURRENT_USER" mkdir -p "$CONFIG_DIR"

if [ ! -f "$CONFIG_PATH" ]; then
    sudo -u "$CURRENT_USER" tee "$CONFIG_PATH" > /dev/null <<EOF
{
  "picture_mode": "both",
  "change_interval_minutes": 15,
  "stop_rotation_between": null,
  "s3_folder": "s3_folder"
}
EOF
    echo "Created default settings at $CONFIG_PATH"
else
    echo "settings.json already exists at $CONFIG_PATH, leaving it unchanged."
fi

echo "Enabling service..."
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"

echo "Setup complete!"
read -p "Reboot required. Reboot now? (y/n): " REBOOT_CHOICE
if [[ "$REBOOT_CHOICE" == "y" || "$REBOOT_CHOICE" == "Y" ]]; then
    echo "Rebooting now..."
    sudo reboot
else
    echo "Reboot skipped. Please remember to reboot at a later time."
fi
