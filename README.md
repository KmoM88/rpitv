# RPi TV (Simpsons TV for Raspberry Pi 1 B+)

A lightweight, dedicated video player appliance built for the **Raspberry Pi 1 Model B+** (ARMv6 single-core, 512 MB RAM) with a **Waveshare 3.5" TFT LCD (A) v3** (480x320) connected via GPIO.

Automatically detects attached USB flash drives, indexes video files across multiple drives, balances playback between folders/shows with cryptographic randomness, and streams video smoothly to the SPI display in an endless loop.

---

## Hardware Specifications
- **Board**: Raspberry Pi 1 Model B+ (BCM2835 ARMv6 @ 700MHz, 512 MB RAM)
- **Display**: Waveshare 3.5inch RPi LCD (A) v3 (480x320, ILI9486 SPI controller)
- **Audio**: Disabled by default (`-an`) to save CPU on ARMv6
- **Storage**: MicroSD Card (OS) + One or more USB Flash Drives (FAT32, exFAT, or NTFS)

---

## Features
- **Ultra-Lightweight**: Built on **Raspberry Pi OS Lite** (no X11, no Wayland, no desktop overhead). Uses ~110 MB of RAM with zero swap.
- **Direct Framebuffer Streaming**: Bypasses heavy desktop layers and renders raw video frames directly to `/dev/fb1` via `ffmpeg rawvideo` with hardware color formatting.
- **Multi-Drive USB Auto-Mount**: Automatically detects, mounts, and reads video files from all attached USB partitions (e.g. `/dev/sda1`, `/dev/sdb1`).
- **Balanced Random Playlist**: Interleaves shows evenly across folders (e.g. Futurama, Evangelion, Rick & Morty, Cowboy Bebop) using cryptographically secure random seeding (`secrets.SystemRandom`), ensuring smaller folders get fair screen time.
- **Auto-Boot & Recovery**: Boots directly into playback without terminal or blinking cursor overlays.
- **Automated 24h Reboot**: Systemd timer schedules daily maintenance reboots (default: 04:00 AM) to maintain long-term stability.

---

## Quick Automated Installation

On your freshly flashed Raspberry Pi OS Lite:

```bash
# 1. Clone this repository
git clone git@github.com:KmoM88/rpitv.git
cd rpitv

# 2. Run the automated installer
sudo chmod +x install.sh
sudo ./install.sh

# 3. Reboot the Pi
sudo reboot
```

---

## Step-by-Step Manual Setup Guide

If you prefer to configure the system manually from a fresh Raspberry Pi OS Lite installation, follow these steps:

### 1. Flash Raspberry Pi OS Lite
1. Flash **Raspberry Pi OS Lite (32-bit)** to your MicroSD card using the official Raspberry Pi Imager.
2. In the Imager settings (gear icon):
   - Set hostname (e.g. `simpsonstv`).
   - Create a user (e.g. `pi`).
   - Enable SSH with password or public key authentication.

### 2. Configure Passwordless Sudo
Log into the Pi via SSH and enable passwordless `sudo`:

```bash
echo "pi ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/010_pi-nopasswd
sudo chmod 0440 /etc/sudoers.d/010_pi-nopasswd
```

### 3. Install System Dependencies
Install the required video decoder and filesystem utilities:

```bash
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  ffmpeg \
  pmount \
  usbmount \
  exfat-fuse \
  exfatprogs \
  ntfs-3g
```

### 4. Enable USB Auto-Mounting
Configure `usbmount` and systemd mount sharing:

```bash
sudo mkdir -p /etc/systemd/system/systemd-udevd.service.d
printf "[Service]\nPrivateMounts=no\n" | sudo tee /etc/systemd/system/systemd-udevd.service.d/00-my-custom-mountflags.conf

sudo sed -i 's/FILESYSTEMS=.*/FILESYSTEMS="vfat ext2 ext3 ext4 hfsplus ntfs exfat fuseblk"/' /etc/usbmount/usbmount.conf
sudo sed -i 's/FS_MOUNTOPTIONS=.*/FS_MOUNTOPTIONS="-fstype=vfat,iocharset=utf8,umask=000 -fstype=ntfs,iocharset=utf8,umask=000 -fstype=exfat,iocharset=utf8,umask=000"/' /etc/usbmount/usbmount.conf
```

### 5. Install the Waveshare 3.5" Device Tree Overlay
Copy the verified device tree overlay to `/boot/firmware/overlays/`:

```bash
sudo cp overlays/waveshare35a.dtbo /boot/firmware/overlays/waveshare35a.dtbo
```

### 6. Configure Boot Settings (`/boot/firmware/config.txt`)
Edit `/boot/firmware/config.txt`:

```ini
# Hardware interfaces
dtparam=i2c_arm=on
dtparam=spi=on
dtparam=audio=on

# Auto detection settings
camera_auto_detect=0
display_auto_detect=0
auto_initramfs=1

# Disable vc4-kms-v3d so the TFT SPI display operates as primary framebuffer
#dtoverlay=vc4-kms-v3d
#max_framebuffers=2

disable_fw_kms_setup=1
disable_overscan=1

# Safe performance settings for Raspberry Pi 1 B+
arm_boost=1

# Allocate 128MB to GPU for hardware video decoding
gpu_mem=128

# Waveshare 3.5inch 480x320 LCD (A) v3
# rotate=270 is landscape rotated 180 degrees from default 90
dtoverlay=waveshare35a:rotate=270:speed=24000000

# Video timing configuration for 480x320
hdmi_force_hotplug=1
hdmi_group=2
hdmi_mode=87
hdmi_cvt 480 320 60 6 0 0 0
hdmi_drive=2

[all]
enable_uart=1
```

> [!IMPORTANT]
> Do **not** set high `core_freq` (e.g. 450MHz) on a Pi 1 B+ with low over-voltage, as the GPU/SDRAM PLL clock will fail to lock on boot and leave the green LED dark.

### 7. Configure Kernel Boot Parameters (`/boot/firmware/cmdline.txt`)
Append `fbcon=map:10` and `vt.global_cursor_default=0` to the single line in `/boot/firmware/cmdline.txt`:

```bash
sudo bash -c 'sed -i "s/$/ fbcon=map:10 vt.global_cursor_default=0/" /boot/firmware/cmdline.txt'
```

- `fbcon=map:10`: Maps the console to the SPI display `/dev/fb1`.
- `vt.global_cursor_default=0`: Permanently hides the blinking white text cursor.

### 8. Set Framebuffer Permissions & Suppress TTY Login
```bash
sudo tee /etc/udev/rules.d/99-tft.rules > /dev/null << 'EOF'
KERNEL=="fb*", GROUP="video", MODE="0660"
KERNEL=="tty[0-9]*", GROUP="tty", MODE="0660"
EOF

sudo systemctl disable getty@tty1.service
```

### 9. Install the Player Daemon and Configuration
```bash
sudo cp rpi-tv-player.py /usr/local/bin/rpi-tv-player.py
sudo chmod +x /usr/local/bin/rpi-tv-player.py

sudo cp rpi-tv.conf /etc/rpi-tv.conf
sudo cp rpi-tv.service /etc/systemd/system/rpi-tv.service

sudo systemctl daemon-reload
sudo systemctl enable rpi-tv.service
```

### 10. Enable 24-Hour Maintenance Reboot
```bash
sudo cp systemd/daily-reboot.service /etc/systemd/system/daily-reboot.service
sudo cp systemd/daily-reboot.timer /etc/systemd/system/daily-reboot.timer

sudo systemctl daemon-reload
sudo systemctl enable --now daily-reboot.timer
```

---

## Configuration (`/etc/rpi-tv.conf`)

You can customize playback behavior anytime by editing `/etc/rpi-tv.conf`:

```ini
# Player backend
PLAYER=ffmpeg

# Additional software 180° rotation (true/false)
ROTATE_180=false

# Video playback behavior
SHUFFLE=true
BALANCE_FOLDERS=true
LOOP_FOREVER=true

# Supported video extensions
VIDEO_EXTENSIONS=.mp4,.mkv,.avi,.mov,.m4v,.webm,.mpg,.mpeg,.ts,.flv,.3gp

# Directories to search for video files
SCAN_DIRS=/media,/mnt
```

Restart the service after making changes:
```bash
sudo systemctl restart rpi-tv.service
```

---

## Helpful Commands

- **Check live playback logs**:
  ```bash
  journalctl -u rpi-tv -f
  ```
- **Check service status**:
  ```bash
  systemctl status rpi-tv.service
  ```
- **Check mounted USB drives**:
  ```bash
  lsblk
  ```
- **Check scheduled daily reboot timer**:
  ```bash
  systemctl list-timers daily-reboot.timer
  ```

---

## License
MIT
