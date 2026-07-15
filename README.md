# 🐍 Wildlife Detection & Human Risk Assessment System

Real-time computer vision system using **YOLOv8** + **OpenCV** that detects animals and humans, classifies venomous species, calculates proximity, and triggers tiered risk alerts.

---

## 🗂 Project Structure

```
wildlife_detection_system/
├── main.py           # Entry point & CLI argument parsing
├── config.py         # Configuration, class labels, risk constants
├── detector.py       # YOLOv8 inference + main video loop
├── risk_engine.py    # Distance calculation & risk classification
├── alert_manager.py  # Desktop notifications & alarm sounds
├── renderer.py       # OpenCV overlay drawing (HUD, boxes, labels)
├── requirements.txt  # Dependencies
└── README.md
```

---

## ⚙️ Installation

```bash
# 1. Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows

# 2. Install dependencies
pip install -r requirements.txt
```

### Weights
By default the system downloads `yolov8n.pt` (YOLOv8 Nano — trained on COCO) automatically on first run. For custom species (snakes, spiders, scorpions) pass your own weights:

```bash
python main.py --model path/to/your_custom_model.pt
```

---

## 🚀 Usage

### Webcam (default)
```bash
python main.py
```

### Video file
```bash
python main.py --source /path/to/video.mp4
```

### Full options
```bash
python main.py \
  --source 0 \               # 0=webcam, or video path
  --model yolov8n.pt \       # model weights
  --conf 0.35 \              # confidence threshold
  --distance-threshold 200 \ # HIGH risk pixel distance
  --no-sound \               # disable alarm
  --no-notify \              # disable desktop notifications
  --save output.mp4          # save annotated video
```

### Keyboard shortcuts
| Key | Action              |
|-----|---------------------|
| Q / ESC | Quit           |
| S   | Save screenshot     |

---

## 🔬 How It Works

### 1. Detection
YOLOv8 runs on every frame and returns bounding boxes + class labels. The system filters to keep only **animals** and **humans** (everything else is ignored).

### 2. Animal Classification
Each detected animal is classified as:

| Category       | Examples                                          |
|----------------|---------------------------------------------------|
| **Venomous**   | cobra, rattlesnake, black widow, scorpion, viper  |
| **Non-venomous** | corn snake, garden spider, emperor scorpion     |
| **Unknown**    | generic "snake" / "spider" labels → treated as venomous (safe default) |

### 3. Distance Calculation
Uses **edge-to-edge bounding box distance** (not center-to-center) for accuracy. If boxes overlap the distance is 0.

### 4. Risk Classification

| Risk Level | Condition                                                  |
|------------|------------------------------------------------------------|
| 🟢 **LOW** | Non-venomous animal, or venomous animal far from human (> medium threshold) |
| 🟡 **MEDIUM** | Venomous animal within medium zone (200–400 px by default) |
| 🔴 **HIGH** | Venomous animal within danger zone (< 200 px by default)  |

### 5. Alerts

| Risk Level | Alert                                    |
|------------|------------------------------------------|
| HIGH       | Desktop notification + alarm sound beeps |
| MEDIUM     | Desktop notification (single beep)       |
| LOW        | On-screen display only                  |

All alerts have a **5-second cooldown** to prevent spam.

---

## 🎯 Custom Model Training

To detect specific species (cobra, black widow, etc.) train a custom YOLOv8 model:

```bash
# 1. Prepare dataset in YOLO format (images + labels)
# 2. Create data.yaml:
#    train: /data/train/images
#    val:   /data/val/images
#    nc: 10
#    names: ['cobra', 'rattlesnake', 'viper', 'black_widow', ...]

# 3. Train
yolo train model=yolov8n.pt data=data.yaml epochs=100 imgsz=640

# 4. Use your trained weights
python main.py --model runs/detect/train/weights/best.pt
```

Add your new class names to `config.py` → `VENOMOUS_CLASSES` or `NON_VENOMOUS_CLASSES`.

---

## 🔧 Tuning Parameters

Edit `config.py` or pass CLI flags:

| Parameter             | Default | Description                              |
|-----------------------|---------|------------------------------------------|
| `confidence_threshold`| 0.35    | Min detection confidence (0–1)           |
| `distance_threshold`  | 200 px  | HIGH risk trigger distance               |
| `medium_risk_distance`| 400 px  | MEDIUM risk trigger distance             |
| `alert_cooldown`      | 5.0 s   | Seconds between repeat alerts            |

For low-resolution cameras, decrease thresholds. For high-res, increase them.

---

## 📦 Dependencies

| Library        | Purpose                           |
|----------------|-----------------------------------|
| `ultralytics`  | YOLOv8 model inference            |
| `opencv-python`| Video capture & rendering         |
| `numpy`        | Numerical operations              |
| `plyer`        | Cross-platform desktop notifications |
| `pygame`       | Alarm sound generation            |

`plyer` and `pygame` are **optional** — the system runs without them (alerts fall back to terminal bell / OS-level notifications).

---

## 🖥 Display Legend

```
┌──────────────────────────────────────────────────────────────────┐
│ [HIGH RISK]  ⚠ cobra within 95px of a person!         FPS: 28.3 │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ╔══════════╗          ╔═══════════╗                             │
│  ║  HUMAN   ║──95px────║  cobra    ║                             │
│  ║ [HUMAN]  ║          ║[VENOMOUS] ║                             │
│  ╚══════════╝          ╚═══════════╝                             │
│                                                                  │
│  Flashing red border = HIGH risk active                          │
├──────────────────────────────────────────────────────────────────┤
│ Q: Quit  |  S: Screenshot                                        │
└──────────────────────────────────────────────────────────────────┘
```

**Bounding box colors:**
- 🔵 Cyan — Human
- 🔴 Red — Venomous animal
- 🟢 Green — Non-venomous animal
- 🟠 Orange — Unknown/ambiguous

---

## 📄 License
MIT
