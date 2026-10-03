#!/usr/bin/env python3
import os
import sys
import glob
import time
import secrets
import signal
import subprocess

CONF_FILE = "/etc/rpi-tv.conf"
current_process = None
FRAME_SIZE = 480 * 320 * 2  # 307,200 bytes for 480x320 RGB565

def load_config():
    config = {
        "ROTATE_180": "false",
        "SHUFFLE": "true",
        "BALANCE_FOLDERS": "true",
        "LOOP_FOREVER": "true",
        "VIDEO_EXTENSIONS": ".mp4,.mkv,.avi,.mov,.m4v,.webm,.mpg,.mpeg,.ts,.flv,.3gp",
        "SCAN_DIRS": "/media,/mnt"
    }
    if os.path.exists(CONF_FILE):
        try:
            with open(CONF_FILE, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        config[k.strip()] = v.strip().strip("\"'")
        except Exception as e:
            print("[RPi-TV] Error reading config: " + str(e), flush=True)
    return config

def signal_handler(signum, frame):
    global current_process
    print("[RPi-TV] Terminating playback...", flush=True)
    if current_process and current_process.poll() is None:
        current_process.terminate()
        try:
            current_process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            current_process.kill()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def try_automount_usb():
    """Mount any unmounted USB partition under /media."""
    try:
        with open("/proc/mounts", "r") as f:
            mounts = f.read()
        partitions = sorted(glob.glob("/dev/sd[a-z][0-9]*"))
        for part in partitions:
            if part not in mounts:
                name = os.path.basename(part)
                mount_point = "/media/" + name
                os.makedirs(mount_point, exist_ok=True)
                subprocess.run(
                    ["mount", "-o", "ro,umask=000", part, mount_point],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
    except Exception:
        pass

def find_videos(scan_dirs, extensions):
    videos = []
    ext_tuple = tuple(ext.lower().strip() for ext in extensions.split(",") if ext.strip())
    for d in scan_dirs.split(","):
        d = d.strip()
        if os.path.exists(d):
            try:
                for root, dirs, files in os.walk(d, onerror=None):
                    # Exclude hidden directories like .Trash, .git, etc.
                    dirs[:] = [x for x in dirs if not x.startswith(".")]
                    for f in files:
                        if f.lower().endswith(ext_tuple) and not f.startswith("."):
                            videos.append(os.path.join(root, f))
            except Exception as e:
                print(f"[RPi-TV] Scan error in {d}: {e}", flush=True)
    return sorted(list(set(videos)))

def build_playlist(videos, balance_folders=True):
    rng = secrets.SystemRandom()
    if not balance_folders:
        pl = list(videos)
        rng.shuffle(pl)
        return pl

    # Group by parent folder so smaller shows (e.g. on sdb1) get fair screen time
    folders = {}
    for v in videos:
        parent = os.path.basename(os.path.dirname(v))
        folders.setdefault(parent, []).append(v)

    for k in folders:
        rng.shuffle(folders[k])

    playlist = []
    folder_names = list(folders.keys())
    while any(folders.values()):
        rng.shuffle(folder_names)
        for fn in folder_names:
            if folders[fn]:
                playlist.append(folders[fn].pop())

    return playlist

def get_fbdev():
    if os.path.exists("/dev/fb1"):
        return "/dev/fb1"
    if os.path.exists("/dev/fb0"):
        return "/dev/fb0"
    return "/dev/fb1"

def play_video(video_path, config):
    global current_process
    fbdev = get_fbdev()
    rotate = config.get("ROTATE_180", "false").lower() in ("true", "1", "yes")

    print("[RPi-TV] Playing: " + os.path.basename(video_path) + " (" + os.path.basename(os.path.dirname(video_path)) + ")", flush=True)

    cmd = [
        "ffmpeg",
        "-re",
        "-i", video_path,
        "-pix_fmt", "rgb565le",
        "-s", "480x320",
        "-f", "rawvideo",
        "-an"
    ]
    if rotate:
        cmd.extend(["-vf", "hflip,vflip"])
    cmd.append("-")

    start_time = time.time()
    try:
        current_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=FRAME_SIZE * 4
        )

        with open(fbdev, "r+b") as fb:
            while current_process.poll() is None:
                chunk = current_process.stdout.read(FRAME_SIZE)
                if not chunk or len(chunk) < FRAME_SIZE:
                    break
                fb.seek(0)
                fb.write(chunk)

        current_process.wait()
    except Exception as e:
        print("[RPi-TV] Playback exception: " + str(e), flush=True)
    finally:
        if current_process and current_process.poll() is None:
            current_process.terminate()
        current_process = None

    elapsed = time.time() - start_time
    print("[RPi-TV] Finished video in " + str(round(elapsed, 1)) + "s", flush=True)
    if elapsed < 2.0:
        time.sleep(3.0)

def main():
    print("[RPi-TV] Starting RPi-TV Video Service...", flush=True)
    while True:
        config = load_config()
        try_automount_usb()
        videos = find_videos(config.get("SCAN_DIRS", "/media,/mnt"), config.get("VIDEO_EXTENSIONS", ""))

        if not videos:
            print("[RPi-TV] No videos found on USB storage. Waiting...", flush=True)
            time.sleep(3)
            continue

        # Per-drive statistics
        sda = sum(1 for v in videos if "sda" in v)
        sdb = sum(1 for v in videos if "sdb" in v)
        print(f"[RPi-TV] Found {len(videos)} videos total (Drive 1: {sda}, Drive 2: {sdb})", flush=True)

        balance = config.get("BALANCE_FOLDERS", "true").lower() in ("true", "1", "yes")
        playlist = build_playlist(videos, balance_folders=balance)

        # Log first 5 upcoming tracks to confirm randomness
        upcoming = [os.path.basename(x) for x in playlist[:5]]
        print(f"[RPi-TV] Playlist randomized (Balance={balance}). Next up: {upcoming}", flush=True)

        for vid in playlist:
            if not os.path.exists(vid):
                print("[RPi-TV] File missing: " + vid, flush=True)
                break
            play_video(vid, config)
            time.sleep(0.5)

        if config.get("LOOP_FOREVER", "true").lower() not in ("true", "1", "yes"):
            break

if __name__ == "__main__":
    main()
