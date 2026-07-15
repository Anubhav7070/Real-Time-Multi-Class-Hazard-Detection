"""
main.py
=======
Hazard Detection & Risk Assessment System v2
Entry point — handles CLI arguments and interactive source selection.

Supports:
  [1] Webcam / Camera  (live feed)
  [2] Video file       (mp4, avi, mov, mkv …)
  [3] Image file       (jpg, jpeg, png, bmp, webp, tiff)
  [4] Image folder     (batch-process all images in a directory)
"""

import argparse
import os
import sys
from detector import WildlifeDetector
from config import SystemConfig

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".m4v"}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _list_cameras(max_test: int = 5) -> list:
    import cv2
    available = []
    for idx in range(max_test):
        cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            available.append(idx)
            cap.release()
    return available


def _is_image(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in IMAGE_EXTENSIONS


def _is_video(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in VIDEO_EXTENSIONS


# ─────────────────────────────────────────────────────────────────────────────
# Interactive source picker
# ─────────────────────────────────────────────────────────────────────────────

def interactive_source_picker() -> tuple:
    """Returns (source, mode) where mode is 'camera'|'video'|'image'|'folder'."""
    print("\n" + "─" * 55)
    print("    Hazard Detection — Select Input Source")
    print("─" * 55)
    print("  [1]  Webcam / Camera      (live detection)")
    print("  [2]  Video file           (.mp4, .avi, .mov …)")
    print("  [3]  Image file           (.jpg, .png, .bmp …)")
    print("  [4]  Image folder         (batch all images)")
    print("─" * 55)

    while True:
        choice = input("  Enter choice (1-4): ").strip()
        if choice in ("1", "2", "3", "4"):
            break
        print("  ⚠  Please enter 1, 2, 3, or 4.")

    # ── Camera ──────────────────────────────────────────────────
    if choice == "1":
        cameras = _list_cameras()
        if not cameras:
            print("  ⚠  No cameras detected — defaulting to index 0.")
            return "0", "camera"
        if len(cameras) == 1:
            print(f"  ✓  Using camera index {cameras[0]}")
            return str(cameras[0]), "camera"

        print("\n  Available cameras:")
        for idx in cameras:
            print(f"    [{idx}]  Camera {idx}")
        while True:
            cam_input = input(f"  Select camera index [{cameras[0]}]: ").strip()
            if cam_input == "":
                return str(cameras[0]), "camera"
            if cam_input.isdigit() and int(cam_input) in cameras:
                return cam_input, "camera"
            print(f"  ⚠  Please enter one of: {cameras}")

    # ── Video file ───────────────────────────────────────────────
    elif choice == "2":
        while True:
            path = input("  Enter path to video file: ").strip().strip('"').strip("'")
            if os.path.isfile(path) and _is_video(path):
                print(f"  ✓  Video: {path}")
                return path, "video"
            elif os.path.isfile(path):
                print(f"  ⚠  Not a recognised video format: {path}")
                print(f"     Supported: {', '.join(sorted(VIDEO_EXTENSIONS))}")
            else:
                print(f"  ⚠  File not found: '{path}'")
            retry = input("  Try again? (y/n): ").strip().lower()
            if retry != "y":
                sys.exit(0)

    # ── Image file ───────────────────────────────────────────────
    elif choice == "3":
        while True:
            path = input("  Enter path to image file: ").strip().strip('"').strip("'")
            if os.path.isfile(path) and _is_image(path):
                print(f"  ✓  Image: {path}")
                return path, "image"
            elif os.path.isfile(path):
                print(f"  ⚠  Not a recognised image format: {path}")
                print(f"     Supported: {', '.join(sorted(IMAGE_EXTENSIONS))}")
            else:
                print(f"  ⚠  File not found: '{path}'")
            retry = input("  Try again? (y/n): ").strip().lower()
            if retry != "y":
                sys.exit(0)

    # ── Image folder ─────────────────────────────────────────────
    else:
        while True:
            path = input("  Enter path to image folder: ").strip().strip('"').strip("'")
            if os.path.isdir(path):
                images = [
                    f for f in os.listdir(path)
                    if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS
                ]
                if images:
                    print(f"  ✓  Found {len(images)} images in: {path}")
                    return path, "folder"
                else:
                    print(f"  ⚠  No images found in: {path}")
            else:
                print(f"  ⚠  Folder not found: '{path}'")
            retry = input("  Try again? (y/n): ").strip().lower()
            if retry != "y":
                sys.exit(0)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description=(
            "Hazard Detection & Risk Assessment System v2\n"
            "Detects: venomous animals, dangerous insects, toxic plants\n\n"
            "Input modes:\n"
            "  Camera  : --source 0\n"
            "  Video   : --source path/to/video.mp4\n"
            "  Image   : --source path/to/image.jpg\n"
            "  Folder  : --source path/to/folder/"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--source",             type=str,   default=None,
                   help="Input: camera index / video path / image path / folder path")
    p.add_argument("--conf",               type=float, default=0.35,
                   help="Detection confidence threshold (default: 0.35)")
    p.add_argument("--model",              type=str,   default="best.pt",
                   help="Path to trained YOLO model weights (default: best.pt)")
    p.add_argument("--distance-threshold", type=int,   default=200,
                   help="Pixel distance for HIGH risk (default: 200)")
    p.add_argument("--medium-distance",    type=int,   default=400,
                   help="Pixel distance for MEDIUM risk (default: 400)")
    p.add_argument("--no-sound",           action="store_true",
                   help="Disable alarm sounds")
    p.add_argument("--no-notify",          action="store_true",
                   help="Disable desktop notifications")
    p.add_argument("--no-phone",           action="store_true",
                   help="Disable phone push notifications")
    p.add_argument("--notify-port",        type=int,   default=8765,
                   help="Port for the Hazard Alert Notification Server (default: 8765)")
    p.add_argument("--save",               type=str,   default=None,
                   help="Save annotated output to this path")
    return p.parse_args()


def _resolve_mode(source_str: str) -> str:
    if source_str.isdigit():
        return "camera"
    if os.path.isdir(source_str):
        return "folder"
    ext = os.path.splitext(source_str)[1].lower()
    if ext in IMAGE_EXTENSIONS:
        return "image"
    return "video"


def main():
    args = parse_args()

    # Resolve source + mode
    if args.source is not None:
        source_str = args.source
        mode       = _resolve_mode(source_str)
    else:
        source_str, mode = interactive_source_picker()

    source = int(source_str) if source_str.isdigit() else source_str

    # Validate model
    if not os.path.isfile(args.model):
        print(f"[ERROR] Model file not found: {args.model}")
        print(f"        Specify: python main.py --model path/to/best.pt")
        sys.exit(1)

    # Build config
    config = SystemConfig(
        model_path           = args.model,
        confidence_threshold = args.conf,
        distance_threshold   = args.distance_threshold,
        medium_risk_distance = args.medium_distance,
        sound_enabled        = not args.no_sound,
        notify_enabled       = not args.no_notify,
        phone_notify_enabled = not args.no_phone,
        notify_server_port   = args.notify_port,
        save_path            = args.save,
    )

    mode_icons = {
        "camera": "", "video": "", "image": " ", "folder": ""
    }

    # Banner
    print("\n" + "═" * 62)
    print("  Hazard Detection & Risk Assessment System  v2")
    print("  Categories:  ANIMALS |  INSECTS |  PLANTS")
    print("═" * 62)
    print(f"  Mode            : {mode_icons.get(mode,'?')} {mode.upper()}")
    print(f"  Source          : {source_str}")
    print(f"  Model           : {config.model_path}")
    print(f"  Confidence      : {config.confidence_threshold}")
    print(f"  HIGH risk dist  : {config.distance_threshold}px")
    print(f"  MEDIUM risk dist: {config.medium_risk_distance}px")
    print(f"  Sound Alerts    : {'ON' if config.sound_enabled  else 'OFF'}")
    print(f"  Desktop Notify  : {'ON' if config.notify_enabled else 'OFF'}")

    if config.phone_notify_enabled:
        phone_status = f"ON  (server port: {config.notify_server_port})"
    else:
        phone_status = "OFF"
    print(f"  Phone Notify    : {phone_status}")

    if config.save_path:
        print(f"  Saving output   : {config.save_path}")

    if mode in ("image", "folder"):
        print("  Controls        : any key = next  |  Q/ESC = quit")
    else:
        print("  Controls        : Q/ESC = quit    |  S = screenshot")
    print("═" * 62 + "\n")

    if config.phone_notify_enabled:
        print(f"    Open alert app : http://localhost:{config.notify_server_port}/app")
        print(f"      (start first)  : python notification_server.py\n")

    detector = WildlifeDetector(config)

    if mode == "image":
        detector.run_image(source)
    elif mode == "folder":
        detector.run_folder(source)
    else:
        detector.run(source)   # camera or video


if __name__ == "__main__":
    main()