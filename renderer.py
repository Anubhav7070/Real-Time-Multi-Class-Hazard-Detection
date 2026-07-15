"""
renderer.py
===========
Draws bounding boxes, category badges, HUD, and risk overlays onto frames.

Updated for 3-category system: ANIMAL / INSECT / PLANT.
Each category has distinct visual styling.
"""

import cv2
import time
import numpy as np
from typing import List, Tuple
from config import (
    SystemConfig, RiskLevel, RISK_COLORS, BBOX_COLORS,
)
from risk_engine import RiskAssessment, classify_threat, is_human, get_category

# Category icons (unicode fallback to text)
CATEGORY_ICON = {
    "animal": "🐍",
    "insect": "🕷",
    "plant":  "🌿",
    "human":  "👤",
    "unknown":"?",
}

CATEGORY_LABEL = {
    "animal": "ANIMAL",
    "insect": "INSECT",
    "plant":  "PLANT",
    "human":  "HUMAN",
    "unknown":"UNKNWN",
}


# ─────────────────────────────────────────────────────────────────────────────
# Drawing helpers
# ─────────────────────────────────────────────────────────────────────────────

def _put_text_with_bg(
    frame,
    text: str,
    pos: Tuple[int, int],
    font=cv2.FONT_HERSHEY_SIMPLEX,
    scale: float = 0.55,
    thickness: int = 1,
    text_color=(255, 255, 255),
    bg_color=(0, 0, 0),
    padding: int = 4,
):
    (w, h), baseline = cv2.getTextSize(text, font, scale, thickness)
    x, y = pos
    cv2.rectangle(
        frame,
        (x - padding, y - h - padding),
        (x + w + padding, y + baseline + padding),
        bg_color, -1,
    )
    cv2.putText(frame, text, (x, y), font, scale, text_color, thickness, cv2.LINE_AA)


def _draw_corner_box(frame, x1, y1, x2, y2, color, thickness=2, corner_len=15):
    """Draw only box corners for a clean look."""
    pts = [
        ((x1, y1), (x1 + corner_len, y1)),
        ((x1, y1), (x1, y1 + corner_len)),
        ((x2, y1), (x2 - corner_len, y1)),
        ((x2, y1), (x2, y1 + corner_len)),
        ((x1, y2), (x1 + corner_len, y2)),
        ((x1, y2), (x1, y2 - corner_len)),
        ((x2, y2), (x2 - corner_len, y2)),
        ((x2, y2), (x2, y2 - corner_len)),
    ]
    for p1, p2 in pts:
        cv2.line(frame, p1, p2, color, thickness)


# ─────────────────────────────────────────────────────────────────────────────
# Renderer
# ─────────────────────────────────────────────────────────────────────────────

class Renderer:

    FONT = cv2.FONT_HERSHEY_SIMPLEX

    def __init__(self, config: SystemConfig):
        self.config   = config
        self._fps_buf = []
        self._last_ts = time.time()

    def _update_fps(self):
        now = time.time()
        self._fps_buf.append(1.0 / max(now - self._last_ts, 1e-6))
        self._last_ts = now
        if len(self._fps_buf) > 30:
            self._fps_buf.pop(0)

    def _get_fps(self) -> float:
        return sum(self._fps_buf) / len(self._fps_buf) if self._fps_buf else 0.0

    # ── Main render entry point ──────────────────────────────────

    def render(self, frame, detections: List[dict], assessment: RiskAssessment):
        self._update_fps()

        for det in detections:
            self._draw_detection(frame, det)

        if assessment.human_bbox and assessment.threat_bbox:
            self._draw_distance_line(frame, assessment)

        self._draw_hud(frame, assessment)
        self._draw_category_legend(frame)

        if assessment.risk_level == RiskLevel.HIGH:
            self._draw_alert_border(frame)

        return frame

    # ── Per-detection drawing ────────────────────────────────────

    def _draw_detection(self, frame, det: dict):
        x1, y1, x2, y2 = det["bbox"]
        label = det["label"]
        conf  = det["confidence"]

        threat_type = classify_threat(label)
        category    = get_category(label)
        color       = BBOX_COLORS.get(threat_type, BBOX_COLORS["unknown"])
        cat_tag     = CATEGORY_LABEL.get(category, "UNKNWN")

        # thin full box + thick corners
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 1)
        _draw_corner_box(frame, x1, y1, x2, y2, color,
                         thickness=self.config.box_thickness)

        # category chip above label
        chip_text = f"[{cat_tag}]"
        _put_text_with_bg(
            frame, chip_text,
            pos=(x1, max(y1 - 24, 14)),
            scale=0.38,
            text_color=(255, 255, 255),
            bg_color=color,
            padding=3,
        )

        # main label + confidence
        display_name = label.replace("_", " ").title()
        label_text   = f"{display_name}  {conf:.0%}"
        _put_text_with_bg(
            frame, label_text,
            pos=(x1, max(y1 - 6, 22)),
            scale=self.config.font_scale,
            thickness=self.config.font_thickness,
            text_color=(255, 255, 255),
            bg_color=color,
        )

    # ── Distance line ────────────────────────────────────────────

    def _draw_distance_line(self, frame, assessment: RiskAssessment):
        hx1, hy1, hx2, hy2 = assessment.human_bbox
        ax1, ay1, ax2, ay2 = assessment.threat_bbox
        hcx = int((hx1 + hx2) / 2)
        hcy = int((hy1 + hy2) / 2)
        acx = int((ax1 + ax2) / 2)
        acy = int((ay1 + ay2) / 2)

        risk_color = RISK_COLORS[assessment.risk_level]
        cv2.line(frame, (hcx, hcy), (acx, acy), risk_color, 1, cv2.LINE_AA)

        mid_x = (hcx + acx) // 2
        mid_y = (hcy + acy) // 2
        _put_text_with_bg(
            frame,
            f"{assessment.closest_distance:.0f}px",
            pos=(mid_x - 20, mid_y),
            scale=0.48,
            text_color=(255, 255, 255),
            bg_color=risk_color,
        )

    # ── HUD (top bar) ────────────────────────────────────────────

    def _draw_hud(self, frame, assessment: RiskAssessment):
        h, w  = frame.shape[:2]
        risk  = assessment.risk_level
        color = RISK_COLORS.get(risk, RISK_COLORS[RiskLevel.NONE])

        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 56), (20, 20, 20), -1)
        cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)

        _put_text_with_bg(
            frame, f" {risk} RISK ",
            pos=(10, 38),
            scale=0.75,
            thickness=2,
            text_color=(255, 255, 255),
            bg_color=color,
            padding=6,
        )

        _put_text_with_bg(
            frame, assessment.message,
            pos=(165, 38),
            scale=0.50,
            text_color=(230, 230, 230),
            bg_color=(30, 30, 30),
        )

        if self.config.display_fps:
            _put_text_with_bg(
                frame, f"FPS: {self._get_fps():.1f}",
                pos=(w - 110, 38),
                scale=0.50,
                text_color=(200, 230, 200),
                bg_color=(30, 30, 30),
            )

        _put_text_with_bg(
            frame, "Q: Quit  |  S: Screenshot",
            pos=(10, h - 12),
            scale=0.42,
            text_color=(180, 180, 180),
            bg_color=(20, 20, 20),
        )

    # ── Category legend (bottom-right) ───────────────────────────

    def _draw_category_legend(self, frame):
        h, w = frame.shape[:2]
        legend_items = [
            ("ANIMAL",  BBOX_COLORS["venomous_animal"]),
            ("INSECT",  BBOX_COLORS["venomous_insect"]),
            ("PLANT",   BBOX_COLORS["toxic_plant"]),
            ("HUMAN",   BBOX_COLORS["human"]),
        ]
        x_start = w - 110
        y_start = h - 12 - len(legend_items) * 20

        for i, (label, color) in enumerate(legend_items):
            y = y_start + i * 20
            cv2.rectangle(frame, (x_start, y - 10), (x_start + 12, y + 2), color, -1)
            _put_text_with_bg(
                frame, label,
                pos=(x_start + 16, y),
                scale=0.38,
                text_color=(200, 200, 200),
                bg_color=(20, 20, 20),
                padding=2,
            )

    # ── Flashing red border (HIGH risk) ──────────────────────────

    def _draw_alert_border(self, frame):
        h, w  = frame.shape[:2]
        pulse = int(abs(np.sin(time.time() * 6)) * 255)
        cv2.rectangle(frame, (0, 0), (w - 1, h - 1), (0, 0, pulse), 6) 