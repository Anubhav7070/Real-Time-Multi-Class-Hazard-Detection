"""
detector.py
===========
Main detection + inference loop.

Modes supported:
  run(source)        — camera index or video file path
  run_image(path)    — single image file
  run_folder(folder) — all images in a directory (batch)

Fixes:
  - Classes now matched to actual trained model (14 classes)
  - ALL_DETECTION_CLASSES check uses model.names directly as fallback
  - Plants treated as static (velocity = 0) in collision prediction
  - Image mode: shows annotated result, saves if --save specified
  - Folder mode: iterates all images, press any key for next, Q to quit
"""

import cv2
import sys
import time
import os
from pathlib import Path
from typing import List, Union

from depth_estimator import DepthEstimator
from tracker import SimpleTracker

from config import (
    SystemConfig, ALL_DETECTION_CLASSES, HUMAN_CLASSES, ALL_PLANT_CLASSES
)
from risk_engine import assess_frame, predict_collision, get_category, classify_threat
from alert_manager import AlertManager
from renderer import Renderer

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif"}


class WildlifeDetector:

    def __init__(self, config: SystemConfig):
        self.config  = config
        self.alert   = AlertManager(config)
        self.render  = Renderer(config)
        self.model   = self._load_model()
        self.depth   = DepthEstimator()
        self.tracker = SimpleTracker()
        self._screenshot_count = 0

        # Build detection class set from model names (guarantees correctness
        # even if config.py classes diverge from actual model output)
        self._model_classes = set(self.model.names.values())

    # ── Model loading ────────────────────────────────────────────

    def _load_model(self):
        try:
            from ultralytics import YOLO
        except ImportError:
            print("[ERROR] ultralytics not installed. Run: pip install ultralytics")
            sys.exit(1)

        if not os.path.isfile(self.config.model_path):
            print(f"[ERROR] Model not found: {self.config.model_path}")
            sys.exit(1)

        model = YOLO(self.config.model_path)
        print(f"[INFO]  Model loaded — {len(model.names)} classes")
        print(f"[INFO]  Classes: {list(model.names.values())}")
        return model

    # ── Inference ────────────────────────────────────────────────

    def _infer(self, frame) -> List[dict]:
        results = self.model(
            frame,
            conf=self.config.confidence_threshold,
            verbose=False,
        )
        detections = []
        for r in results:
            for box in r.boxes:
                cls_id = int(box.cls[0])
                label  = self.model.names[cls_id].lower().replace(" ", "_")
                conf   = float(box.conf[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                # Accept any class the model produces
                detections.append({
                    "label":      label,
                    "confidence": conf,
                    "bbox":       (x1, y1, x2, y2),
                    "category":   get_category(label),
                })
        return detections

    # ── Screenshot ───────────────────────────────────────────────

    def _save_screenshot(self, frame):
        ts   = time.strftime("%Y%m%d_%H%M%S")
        path = f"screenshot_{ts}_{self._screenshot_count:03d}.png"
        cv2.imwrite(path, frame)
        self._screenshot_count += 1
        print(f"[INFO]  Screenshot saved: {path}")

    # ── Shared processing for one frame ─────────────────────────

    def _process_frame(self, frame, use_tracker: bool = True):
        """
        Run detection → tracking → risk assessment → depth → alerts → render.
        Returns annotated frame and RiskAssessment.
        """
        # STEP 1: Detection
        detections = self._infer(frame)

        # STEP 2: Tracking (skip for static images)
        if use_tracker:
            velocities, track_ids = self.tracker.update(detections)
        else:
            velocities  = {i: (0.0, 0.0) for i in range(len(detections))}
            track_ids   = list(range(len(detections)))

        # STEP 3: Risk assessment
        assessment = assess_frame(detections, self.config)

        # STEP 4: Depth + collision (only if human-threat pair exists)
        if assessment.human_bbox and assessment.threat_bbox:
            depth_map = self.depth.estimate(frame)

            threat_velocity = (0.0, 0.0)
            human_velocity  = (0.0, 0.0)

            for i, det in enumerate(detections):
                tid = track_ids[i] if i < len(track_ids) else -1
                if det["bbox"] == assessment.threat_bbox:
                    if det["category"] != "plant":
                        threat_velocity = velocities.get(tid, (0.0, 0.0))
                if det["bbox"] == assessment.human_bbox:
                    human_velocity = velocities.get(tid, (0.0, 0.0))

            collision, t = predict_collision(
                assessment.human_bbox,
                assessment.threat_bbox,
                threat_velocity,
                human_velocity,
            )

            if collision:
                assessment.message   += f" | ⚠ Collision in {t} frames"
                assessment.risk_level = "HIGH"

            h_depth    = self.depth.get_depth_at(depth_map, assessment.human_bbox)
            a_depth    = self.depth.get_depth_at(depth_map, assessment.threat_bbox)
            depth_diff = abs(h_depth - a_depth)
            assessment.message += f" | DepthΔ: {depth_diff:.2f}"

        # STEP 5: Alerts
        self.alert.handle(
            assessment.risk_level,
            assessment.dangerous_label or "entity",
            category=assessment.category or "animal",
        )

        # STEP 6: Render
        annotated = self.render.render(frame, detections, assessment)

        return annotated, assessment

    # ── MODE 1: Camera / Video ───────────────────────────────────

    def run(self, source: Union[int, str]):
        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            print(f"[ERROR] Cannot open source: {source}")
            sys.exit(1)

        writer = None
        if self.config.save_path:
            fps    = cap.get(cv2.CAP_PROP_FPS) or 25.0
            width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(
                self.config.save_path, fourcc, fps, (width, height)
            )
            print(f"[INFO]  Saving video to: {self.config.save_path}")

        window_name = "Wildlife Detection v2 | Q: Quit  S: Screenshot"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    print("[INFO]  End of stream.")
                    break

                annotated, _ = self._process_frame(frame, use_tracker=True)

                if writer is not None:
                    writer.write(annotated)

                cv2.imshow(window_name, annotated)

                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    break
                elif key in (ord("s"), ord("S")):
                    self._save_screenshot(annotated)

        finally:
            cap.release()
            if writer is not None:
                writer.release()
                print(f"[INFO]  Video saved: {self.config.save_path}")
            cv2.destroyAllWindows()

    # ── MODE 2: Single Image ─────────────────────────────────────

    def run_image(self, image_path: str):
        frame = cv2.imread(image_path)
        if frame is None:
            print(f"[ERROR] Cannot read image: {image_path}")
            sys.exit(1)

        print(f"[INFO]  Processing image: {image_path}")
        print(f"[INFO]  Size: {frame.shape[1]}x{frame.shape[0]}")

        annotated, assessment = self._process_frame(frame, use_tracker=False)

        # Print result summary
        print(f"\n{'─'*50}")
        print(f"  Risk Level : {assessment.risk_level}")
        print(f"  Message    : {assessment.message}")
        if assessment.dangerous_label:
            print(f"  Detected   : {assessment.dangerous_label}")
            print(f"  Category   : {assessment.category}")
        print(f"{'─'*50}\n")

        # Save if requested
        if self.config.save_path:
            save_path = self.config.save_path
            # If save_path has no image extension, add one
            if os.path.splitext(save_path)[1].lower() not in IMAGE_EXTENSIONS:
                save_path += ".jpg"
            cv2.imwrite(save_path, annotated)
            print(f"[INFO]  Annotated image saved: {save_path}")
        else:
            # Auto-save next to original with _detected suffix
            stem = Path(image_path).stem
            folder = Path(image_path).parent
            auto_save = str(folder / f"{stem}_detected.jpg")
            cv2.imwrite(auto_save, annotated)
            print(f"[INFO]  Result saved: {auto_save}")

        # Display
        window_name = f"Wildlife Detection | {Path(image_path).name} | any key: close"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

        # Resize window to fit screen (max 1280x720)
        h, w = annotated.shape[:2]
        max_w, max_h = 1280, 720
        scale = min(max_w / w, max_h / h, 1.0)
        cv2.resizeWindow(window_name, int(w * scale), int(h * scale))

        cv2.imshow(window_name, annotated)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    # ── MODE 3: Image Folder ─────────────────────────────────────

    def run_folder(self, folder_path: str):
        images = sorted([
            os.path.join(folder_path, f)
            for f in os.listdir(folder_path)
            if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS
        ])

        if not images:
            print(f"[ERROR] No images found in: {folder_path}")
            sys.exit(1)

        print(f"[INFO]  Found {len(images)} images in: {folder_path}")
        print(f"[INFO]  Controls: any key = next image | Q/ESC = quit\n")

        # Create output folder for saved results
        out_folder = None
        if self.config.save_path:
            out_folder = self.config.save_path
            os.makedirs(out_folder, exist_ok=True)
            print(f"[INFO]  Saving results to: {out_folder}")
        else:
            out_folder = os.path.join(folder_path, "detected_results")
            os.makedirs(out_folder, exist_ok=True)
            print(f"[INFO]  Auto-saving results to: {out_folder}")

        window_name = "Wildlife Detection v2 | any key: next  Q/ESC: quit"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

        results_summary = []

        for idx, img_path in enumerate(images):
            frame = cv2.imread(img_path)
            if frame is None:
                print(f"[WARN]  Cannot read: {img_path} — skipping")
                continue

            print(f"[{idx+1}/{len(images)}] {os.path.basename(img_path)}", end=" … ")

            annotated, assessment = self._process_frame(frame, use_tracker=False)

            print(f"{assessment.risk_level:6s} | {assessment.message[:60]}")

            # Save annotated image
            out_name = f"{Path(img_path).stem}_detected.jpg"
            out_path = os.path.join(out_folder, out_name)
            cv2.imwrite(out_path, annotated)

            results_summary.append({
                "file":  os.path.basename(img_path),
                "risk":  assessment.risk_level,
                "label": assessment.dangerous_label,
                "msg":   assessment.message,
            })

            # Show image, resize to fit screen
            h, w = annotated.shape[:2]
            max_w, max_h = 1280, 720
            scale = min(max_w / w, max_h / h, 1.0)
            cv2.resizeWindow(window_name, int(w * scale), int(h * scale))
            cv2.imshow(window_name, annotated)

            key = cv2.waitKey(0) & 0xFF
            if key in (ord("q"), 27):
                print("\n[INFO]  Quit by user.")
                break

        cv2.destroyAllWindows()

        # Final summary
        print(f"\n{'═'*55}")
        print(f"  📊 Batch Summary — {len(results_summary)} images processed")
        print(f"{'═'*55}")
        high   = sum(1 for r in results_summary if r["risk"] == "HIGH")
        medium = sum(1 for r in results_summary if r["risk"] == "MEDIUM")
        low    = sum(1 for r in results_summary if r["risk"] == "LOW")
        none_  = sum(1 for r in results_summary if r["risk"] == "NONE")
        print(f"  HIGH   : {high}")
        print(f"  MEDIUM : {medium}")
        print(f"  LOW    : {low}")
        print(f"  NONE   : {none_}")
        print(f"  Results saved → {out_folder}")
        print(f"{'═'*55}\n")