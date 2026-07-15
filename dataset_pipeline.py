"""
dataset_pipeline.py
====================
Complete pipeline to:
  1. Download all 3 datasets (toxidsnake, Lucas Lins Animals, COCO-person)
  2. Merge them into one unified YOLOv8 dataset
  3. Remap / normalise class names
  4. Generate a unified data.yaml
  5. Launch YOLOv8 training

Usage:
    python dataset_pipeline.py --api-key YOUR_ROBOFLOW_API_KEY

Get a FREE Roboflow API key at: https://app.roboflow.com  (no credit card)

FIXES vs original:
  1. _export_coco_to_yolo: used `i` after the for-loop — crashes with
     UnboundLocalError when the dataset is empty. Now guarded with a
     count variable initialised to 0.
  2. copy_dataset: when Roboflow uses a flat split directory (all files
     in train/), the original code set BOTH img_src and lbl_src to the
     same directory — but labels are .txt files mixed in with images.
     Fixed to properly separate image extensions from label .txt files
     when working in flat directories.
  3. Added a simple progress counter so large downloads don't look frozen.
"""

import os
import sys
import shutil
import argparse
import yaml
import random
from pathlib import Path

# ---------------------------------------------------------------------------
# Dataset catalogue
# ---------------------------------------------------------------------------

DATASETS = {
    # ── Dataset 1: toxidsnake (most complete venomous species labels) ──────
    "toxidsnake": {
        "workspace": "toxidsnake",
        "project":   "venomous-species-detection",
        "version":   1,
        "url":       "https://universe.roboflow.com/toxidsnake/venomous-species-detection",
        "images":    361,
        "note":      "Primary venomous-species dataset — snakes, spiders, scorpions",
    },

    # ── Dataset 2: Lucas Lins Souza – Animals (Bee/Scorpion/Snake/Spider) ──
    "lucas_animals": {
        "workspace": "lucas-lins-souza",
        "project":   "animals-uu2j9",
        "version":   2,
        "url":       "https://universe.roboflow.com/lucas-lins-souza/animals-uu2j9",
        "images":    7108,
        "note":      "7k-image multi-class: Scorpion, Snake, Spider",
    },

    # ── Dataset 3: Lucas Lins – Animals-train (Scorpion/Spider/Snake) ──────
    "lucas_train": {
        "workspace": "lucas-lins-souza",
        "project":   "animals-train-yruka",
        "version":   1,
        "url":       "https://universe.roboflow.com/lucas-lins-souza/animals-train-yruka",
        "images":    3029,
        "note":      "Supplementary 3k dataset with scorpion/spider/snake",
    },
}

# ---------------------------------------------------------------------------
# Class remapping
# ---------------------------------------------------------------------------

CLASS_REMAP = {
    "snake":                "snake",
    "black_mamba":          "black_mamba",
    "black mamba":          "black_mamba",
    "boomslang":            "boomslang",
    "coastal_taipan":       "coastal_taipan",
    "coastal taipan":       "coastal_taipan",
    "common_krait":         "common_krait",
    "common krait":         "common_krait",
    "coral_snake":          "coral_snake",
    "coral snake":          "coral_snake",
    "eastern_brown_snake":  "eastern_brown_snake",
    "eastern brown snake":  "eastern_brown_snake",
    "scorpion":                     "scorpion",
    "arizona_bark_scorpion":        "arizona_bark_scorpion",
    "arizona bark scorpion":        "arizona_bark_scorpion",
    "brazilian_yellow_scorpion":    "brazilian_yellow_scorpion",
    "brazilian yellow scorpion":    "brazilian_yellow_scorpion",
    "deathstalker_scorpion":        "deathstalker_scorpion",
    "deathstalker scorpion":        "deathstalker_scorpion",
    "spider":           "spider",
    "black_widow":      "black_widow",
    "black widow":      "black_widow",
    "black_window":     "black_widow",   # common typo in dataset
    "black window":     "black_widow",
    "brown_recluse":    "brown_recluse",
    "brown recluse":    "brown_recluse",
    "daddy_long_legs":  "daddy_long_legs",
    "daddy long legs":  "daddy_long_legs",
    "brown_widow":      "brown_widow",
    "brown widow":      "brown_widow",
    "bee":              "bee",
    "beehive":          "beehive",
    "person":           "person",
}

FINAL_CLASSES = [
    # ── VENOMOUS ────────────────────────────────
    "black_mamba",
    "boomslang",
    "coastal_taipan",
    "common_krait",
    "coral_snake",
    "eastern_brown_snake",
    "snake",
    "arizona_bark_scorpion",
    "brazilian_yellow_scorpion",
    "deathstalker_scorpion",
    "scorpion",
    "black_widow",
    "brown_recluse",
    "brown_widow",
    "spider",
    # ── NON-VENOMOUS ────────────────────────────
    "daddy_long_legs",
    "bee",
    "beehive",
    # ── HUMAN ───────────────────────────────────
    "person",
]

CLASS2ID = {cls: i for i, cls in enumerate(FINAL_CLASSES)}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def install(pkg):
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])


def ensure_deps():
    try:
        import roboflow  # noqa
    except ImportError:
        print("[SETUP] Installing roboflow...")
        install("roboflow")
    try:
        import yaml      # noqa
    except ImportError:
        install("pyyaml")


def make_dirs(base: Path):
    for split in ("train", "val", "test"):
        (base / "images" / split).mkdir(parents=True, exist_ok=True)
        (base / "labels" / split).mkdir(parents=True, exist_ok=True)
    print(f"[DIR]   Created dataset structure at: {base}")


def remap_label_file(src: Path, dst: Path, src_classes: list):
    """
    Read a YOLO .txt label file, remap class IDs to the global FINAL_CLASSES
    list, and write to dst. Lines whose class doesn't map are dropped.
    """
    lines_out = []
    with open(src) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            old_id = int(parts[0])
            if old_id >= len(src_classes):
                continue
            raw_name = src_classes[old_id].lower().replace(" ", "_")
            canonical = CLASS_REMAP.get(raw_name)
            if canonical is None or canonical not in CLASS2ID:
                continue
            new_id = CLASS2ID[canonical]
            lines_out.append(f"{new_id} " + " ".join(parts[1:]))

    if lines_out:
        dst.write_text("\n".join(lines_out) + "\n")


def copy_dataset(src_root: Path, dst_root: Path, src_classes: list, tag: str):
    """
    Walk a downloaded Roboflow dataset and copy + remap everything into dst_root.

    FIX: when Roboflow uses a flat split directory (images and labels mixed
    together), the original code set img_src == lbl_src to the same flat dir.
    This meant label .txt files were treated as images. Now the label file is
    always looked up by stem regardless of directory layout.
    """
    copied = 0
    for split in ("train", "valid", "test"):
        dst_split = "val" if split == "valid" else split

        # ── Structured layout: split/images/ and split/labels/ ──────────
        img_src = src_root / split / "images"
        lbl_src = src_root / split / "labels"

        flat_mode = False
        if not img_src.exists():
            # ── Flat layout: split/ contains both images and .txt files ─
            flat_dir = src_root / split
            if flat_dir.exists():
                img_src   = flat_dir
                lbl_src   = flat_dir   # labels are co-located
                flat_mode = True
            else:
                continue

        img_dst = dst_root / "images" / dst_split
        lbl_dst = dst_root / "labels" / dst_split

        image_files = [
            f for f in img_src.iterdir()
            if f.suffix.lower() in IMAGE_EXTENSIONS
        ]

        for img_file in image_files:
            new_stem = f"{tag}_{img_file.stem}"
            shutil.copy2(img_file, img_dst / (new_stem + img_file.suffix))

            # FIX: in flat mode labels live alongside images; find by stem
            lbl_file = lbl_src / (img_file.stem + ".txt")
            if lbl_file.exists():
                remap_label_file(lbl_file, lbl_dst / (new_stem + ".txt"), src_classes)
            else:
                # No annotation = background image
                (lbl_dst / (new_stem + ".txt")).write_text("")

            copied += 1
            # FIX: progress counter so large datasets don't look frozen
            if copied % 500 == 0:
                print(f"[MERGE] {tag}: {copied} images processed so far...")

    print(f"[MERGE] {tag}: {copied} images merged total")
    return copied


def write_data_yaml(dst_root: Path):
    data = {
        "path":  str(dst_root.resolve()),
        "train": "images/train",
        "val":   "images/val",
        "test":  "images/test",
        "nc":    len(FINAL_CLASSES),
        "names": FINAL_CLASSES,
    }
    out = dst_root / "data.yaml"
    with open(out, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    print(f"[YAML]  Written: {out}")
    return out


def download_coco_person(dst_root: Path, max_images: int = 3000):
    """
    Download COCO person images + annotations using fiftyone.
    """
    print("\n[COCO]  Attempting COCO person subset download via fiftyone...")
    try:
        import fiftyone as fo
        import fiftyone.zoo as foz
    except ImportError:
        print("[COCO]  fiftyone not found. Installing (this takes ~1 min)...")
        install("fiftyone")
        try:
            import fiftyone as fo
            import fiftyone.zoo as foz
        except Exception:
            _print_coco_manual_instructions()
            return 0

    try:
        dataset = foz.load_zoo_dataset(
            "coco-2017",
            split="train",
            label_types=["detections"],
            classes=["person"],
            max_samples=max_images,
            dataset_name="coco_person_subset",
            overwrite=True,
        )
        return _export_coco_to_yolo(dataset, dst_root)
    except Exception as e:
        print(f"[COCO]  fiftyone download failed: {e}")
        _print_coco_manual_instructions()
        return 0


def _export_coco_to_yolo(dataset, dst_root: Path) -> int:
    """Export fiftyone detections to YOLO format."""
    person_id = CLASS2ID["person"]
    img_dst   = dst_root / "images" / "train"
    lbl_dst   = dst_root / "labels" / "train"

    # FIX: use explicit count instead of relying on loop variable `i`
    # which is undefined if dataset is empty (raises UnboundLocalError)
    count = 0
    for sample in dataset:
        img_path = Path(sample.filepath)
        new_stem = f"coco_person_{count:06d}"
        shutil.copy2(img_path, img_dst / (new_stem + img_path.suffix))

        w, h = sample.metadata.width, sample.metadata.height
        lines = []
        if sample.ground_truth:
            for det in sample.ground_truth.detections:
                if det.label.lower() != "person":
                    continue
                bx, by, bw, bh = det.bounding_box
                cx = bx + bw / 2
                cy = by + bh / 2
                lines.append(f"{person_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
        (lbl_dst / (new_stem + ".txt")).write_text("\n".join(lines))
        count += 1

        if count % 500 == 0:
            print(f"[COCO]  {count} images exported so far...")

    print(f"[COCO]  {count} person images exported to {img_dst}")
    return count


def _print_coco_manual_instructions():
    print("""
[COCO]  ── MANUAL DOWNLOAD INSTRUCTIONS ─────────────────────────────
    If automatic download failed, get COCO person images manually:

    Option A — Roboflow (easiest, pre-converted to YOLO format):
        https://universe.roboflow.com/joseph-nelson/coco-128
        Then add 'person' images to:  merged_dataset/images/train/

    Option B — Official COCO:
        http://images.cocodataset.org/zips/train2017.zip  (~18GB)
        http://images.cocodataset.org/annotations/annotations_trainval2017.zip
        Then run: python dataset_pipeline.py --coco-only path/to/coco
──────────────────────────────────────────────────────────────────────
""")


# ---------------------------------------------------------------------------
# Main download + merge
# ---------------------------------------------------------------------------

def download_roboflow_datasets(api_key: str, dst_root: Path):
    from roboflow import Roboflow

    rf    = Roboflow(api_key=api_key)
    total = 0

    for name, info in DATASETS.items():
        print(f"\n[DLOAD] Downloading: {name}  ({info['images']} images)")
        print(f"        URL: {info['url']}")
        try:
            project = rf.workspace(info["workspace"]).project(info["project"])
            version = project.version(info["version"])
            dl_path = Path(f"./downloads/{name}")
            version.download("yolov8", location=str(dl_path), overwrite=True)

            data_yaml = dl_path / "data.yaml"
            if not data_yaml.exists():
                yamls = list(dl_path.rglob("data.yaml"))
                if yamls:
                    data_yaml = yamls[0]
                    dl_path   = data_yaml.parent

            with open(data_yaml) as f:
                meta = yaml.safe_load(f)
            src_classes = meta.get("names", [])
            print(f"        Source classes: {src_classes}")

            n      = copy_dataset(dl_path, dst_root, src_classes, tag=name)
            total += n

        except Exception as e:
            print(f"[ERROR] Failed to download {name}: {e}")
            print(f"        Please download manually from: {info['url']}")

    return total


def train(data_yaml: Path, model: str = "yolov8n.pt", epochs: int = 100):
    print("\n" + "=" * 60)
    print("  Starting YOLOv8 Training")
    print("=" * 60)
    try:
        from ultralytics import YOLO
        mdl     = YOLO(model)
        results = mdl.train(
            data    = str(data_yaml),
            epochs  = epochs,
            imgsz   = 640,
            batch   = 16,
            workers = 4,
            project = "wildlife_runs",
            name    = "venomous_detector",
            patience= 20,
            save    = True,
            plots   = True,
        )
        best = Path("wildlife_runs/venomous_detector/weights/best.pt")
        print(f"\n[DONE]  Best weights: {best.resolve()}")
        print(f"        Use in main.py: python main.py --model {best}")
        return best
    except ImportError:
        print("[ERROR] ultralytics not installed. Run: pip install ultralytics")
    except Exception as e:
        print(f"[ERROR] Training failed: {e}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="Download, merge, and train wildlife dataset")
    p.add_argument("--api-key",        required=True, help="Roboflow API key")
    p.add_argument("--output",         default="merged_dataset", help="Output folder")
    p.add_argument("--coco",           action="store_true", help="Include COCO person subset")
    p.add_argument("--coco-max",       type=int, default=3000, help="Max COCO person images")
    p.add_argument("--train",          action="store_true", help="Train after download")
    p.add_argument("--model",          default="yolov8n.pt", help="Base model for training")
    p.add_argument("--epochs",         type=int, default=100)
    p.add_argument("--skip-download",  action="store_true", help="Skip download, only merge/train")
    return p.parse_args()


def main():
    args = parse_args()
    ensure_deps()

    dst = Path(args.output)
    make_dirs(dst)

    total_images = 0

    if not args.skip_download:
        total_images += download_roboflow_datasets(args.api_key, dst)
    else:
        print("[SKIP]  Skipping download (--skip-download set)")

    if args.coco:
        total_images += download_coco_person(dst, max_images=args.coco_max)
    else:
        print("\n[INFO]  Skipping COCO person (pass --coco to include it)")

    data_yaml = write_data_yaml(dst)

    print(f"\n{'='*60}")
    print(f"  Dataset summary")
    print(f"{'='*60}")
    print(f"  Output folder  : {dst.resolve()}")
    print(f"  Total images   : {total_images}")
    print(f"  Classes        : {len(FINAL_CLASSES)}")
    for i, cls in enumerate(FINAL_CLASSES):
        print(f"    {i:2d}  {cls}")
    print(f"  data.yaml      : {data_yaml.resolve()}")
    print(f"{'='*60}\n")

    if args.train:
        train(data_yaml, model=args.model, epochs=args.epochs)
    else:
        print("  To train now, run:")
        print(f"    python dataset_pipeline.py --api-key YOUR_KEY --train")
        print(f"  Or train manually:")
        print(f"    yolo train model=yolov8n.pt data={data_yaml} epochs=100 imgsz=640")


if __name__ == "__main__":
    main()