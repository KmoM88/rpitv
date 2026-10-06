#!/usr/bin/env bash
set -e

if [ "$EUID" -ne 0 ]; then
  echo "[-] Please run as root (e.g. sudo ./install.sh)"
  exit 1
fi

echo "[+] Installing system dependencies..."
apt-get update
apt-get install -y --no-install-recommends \
  ffmpeg \
  pmount \
  usbmount \
  exfat-fuse \
  exfatprogs \
  ntfs-3g

echo "[+] Configuring USB automounting..."
mkdir -p /etc/systemd/system/systemd-udevd.service.d
cat << 'EOF' > /etc/systemd/system/systemd-udevd.service.d/00-my-custom-mountflags.conf
[Service]
PrivateMounts=no
EOF

if [ -f /etc/usbmount/usbmount.conf ]; then
  sed -i 's/FILESYSTEMS=.*/FILESYSTEMS="vfat ext2 ext3 ext4 hfsplus ntfs exfat fuseblk"/' /etc/usbmount/usbmount.conf
  sed -i 's/FS_MOUNTOPTIONS=.*/FS_MOUNTOPTIONS="-fstype=vfat,iocharset=utf8,umask=000 -fstype=ntfs,iocharset=utf8,umask=000 -fstype=exfat,iocharset=utf8,umask=000"/' /etc/usbmount/usbmount.conf
fi

echo "[+] Installing Waveshare 3.5\" overlay..."
mkdir -p /boot/firmware/overlays
if [ -f overlays/waveshare35a.dtbo ]; then
  cp overlays/waveshare35a.dtbo /boot/firmware/overlays/waveshare35a.dtbo
fi

echo "[+] Updating boot configuration (/boot/firmware/config.txt)..."
if [ -f /boot/firmware/config.txt ] && ! grep -q "waveshare35a" /boot/firmware/config.txt; then
  cp /boot/firmware/config.txt /boot/firmware/config.txt.bak
  cat << 'EOF' >> /boot/firmware/config.txt

# --- RPi TV Settings ---
dtparam=i2c_arm=on
dtparam=spi=on
dtparam=audio=on
camera_auto_detect=0
display_auto_detect=0
auto_initramfs=1
disable_fw_kms_setup=1
disable_overscan=1
arm_boost=1
gpu_mem=128

# Waveshare 3.5inch 480x320 LCD (A) v3 (rotate=90 or rotate=270 for 180° inversion)
dtoverlay=waveshare35a:rotate=90:speed=24000000

# Video timing configuration for 480x320
hdmi_force_hotplug=1
hdmi_group=2
hdmi_mode=87
hdmi_cvt 480 320 60 6 0 0 0
hdmi_drive=2
EOF
fi

# Ensure conflicting KMS driver is disabled if present
sed -i 's/^dtoverlay=vc4-kms-v3d/#dtoverlay=vc4-kms-v3d/' /boot/firmware/config.txt || true
sed -i 's/^max_framebuffers=2/#max_framebuffers=2/' /boot/firmware/config.txt || true

echo "[+] Updating boot cmdline (/boot/firmware/cmdline.txt)..."
grep -q "fbcon=map:10" /boot/firmware/cmdline.txt || sed -i "s/$/ fbcon=map:10/" /boot/firmware/cmdline.txt
grep -q "vt.global_cursor_default=0" /boot/firmware/cmdline.txt || sed -i "s/$/ vt.global_cursor_default=0/" /boot/firmware/cmdline.txt

echo "[+] Configuring udev rules for framebuffers..."
cat << 'EOF' > /etc/udev/rules.d/99-tft.rules
KERNEL=="fb*", GROUP="video", MODE="0660"
KERNEL=="tty[0-9]*", GROUP="tty", MODE="0660"
EOF

echo "[+] Disabling login prompt cursor on display..."
systemctl disable getty@tty1.service 2>/dev/null || true
systemctl stop getty@tty1.service 2>/dev/null || true

echo "[+] Installing player script and configuration..."
cp rpi-tv-player.py /usr/local/bin/rpi-tv-player.py
chmod +x /usr/local/bin/rpi-tv-player.py

if [ ! -f /etc/rpi-tv.conf ]; then
  cp rpi-tv.conf /etc/rpi-tv.conf
fi

echo "[+] Installing systemd services..."
cp rpi-tv.service /etc/systemd/system/rpi-tv.service
cp systemd/daily-reboot.service /etc/systemd/system/daily-reboot.service
cp systemd/daily-reboot.timer /etc/systemd/system/daily-reboot.timer

systemctl daemon-reload
systemctl enable rpi-tv.service
systemctl enable --now daily-reboot.timer

echo "[+] Installation complete! Please reboot the Pi: sudo reboot"
