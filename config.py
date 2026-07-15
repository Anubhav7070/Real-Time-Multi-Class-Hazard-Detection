"""
config.py
=========
System configuration for Wildlife + Insects + Plants Detection System.

Classes matched EXACTLY to trained model output:
  ['snake', 'venomous_snake', 'non_venomous_snake', 'scorpion', 'spider',
   'wasp', 'bee', 'beehive', 'datura', 'deadly_nightshade', 'hemlock',
   'calotropis', 'parthenium', 'person']

Three detection categories:
  ANIMAL  — snakes, scorpions
  INSECT  — spiders, wasps, bees
  PLANT   — toxic plants
"""

from dataclasses import dataclass
from typing import Optional, Set

# ─────────────────────────────────────────────────────────────────────────────
# ── CATEGORY: ANIMAL  ────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

VENOMOUS_ANIMAL_CLASSES: Set[str] = {
    "snake",
    "venomous_snake",
    "scorpion",
}

NON_VENOMOUS_ANIMAL_CLASSES: Set[str] = {
    "non_venomous_snake",
}

# ─────────────────────────────────────────────────────────────────────────────
# ── CATEGORY: INSECT  ────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

VENOMOUS_INSECT_CLASSES: Set[str] = {
    "spider",
    "wasp",
}

NON_VENOMOUS_INSECT_CLASSES: Set[str] = {
    "bee",
    "beehive",
}

# ─────────────────────────────────────────────────────────────────────────────
# ── CATEGORY: PLANT  ─────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

TOXIC_PLANT_CLASSES: Set[str] = {
    "datura",
    "deadly_nightshade",
    "hemlock",
    "calotropis",
    "parthenium",
}

NON_TOXIC_PLANT_CLASSES: Set[str] = set()

# ─────────────────────────────────────────────────────────────────────────────
# ── HUMAN ────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

HUMAN_CLASSES: Set[str] = {"person"}

# ─────────────────────────────────────────────────────────────────────────────
# ── Convenience unions ───────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

ALL_VENOMOUS_CLASSES: Set[str] = (
    VENOMOUS_ANIMAL_CLASSES | VENOMOUS_INSECT_CLASSES | TOXIC_PLANT_CLASSES
)

ALL_NONVENOMOUS_CLASSES: Set[str] = (
    NON_VENOMOUS_ANIMAL_CLASSES | NON_VENOMOUS_INSECT_CLASSES | NON_TOXIC_PLANT_CLASSES
)

ALL_ANIMAL_CLASSES: Set[str] = VENOMOUS_ANIMAL_CLASSES | NON_VENOMOUS_ANIMAL_CLASSES
ALL_INSECT_CLASSES: Set[str] = VENOMOUS_INSECT_CLASSES | NON_VENOMOUS_INSECT_CLASSES
ALL_PLANT_CLASSES:  Set[str] = TOXIC_PLANT_CLASSES | NON_TOXIC_PLANT_CLASSES

ALL_DETECTION_CLASSES: Set[str] = (
    ALL_ANIMAL_CLASSES | ALL_INSECT_CLASSES | ALL_PLANT_CLASSES | HUMAN_CLASSES
)

# ─────────────────────────────────────────────────────────────────────────────
# ── Risk levels ──────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

class RiskLevel:
    LOW    = "LOW"
    MEDIUM = "MEDIUM"
    HIGH   = "HIGH"
    NONE   = "NONE"

RISK_COLORS = {
    RiskLevel.LOW    : (0, 200, 0),      # green  (BGR)
    RiskLevel.MEDIUM : (0, 165, 255),    # orange
    RiskLevel.HIGH   : (0, 0, 220),      # red
    RiskLevel.NONE   : (200, 200, 200),  # grey
}

# Category tag → bbox outline colour (BGR)
BBOX_COLORS = {
    "human"          : (255, 200, 0),    # gold
    "venomous_animal": (0, 0, 255),      # red
    "venomous_insect": (0, 60, 255),     # deep-red
    "toxic_plant"    : (0, 100, 0),      # dark green
    "safe_animal"    : (0, 200, 50),     # green
    "safe_insect"    : (120, 220, 0),    # lime
    "safe_plant"     : (0, 180, 0),      # medium green
    "unknown"        : (0, 165, 255),    # orange
}

# ─────────────────────────────────────────────────────────────────────────────
# ── SystemConfig ─────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SystemConfig:
    model_path            : str           = "best.pt"
    confidence_threshold  : float         = 0.35
    distance_threshold    : int           = 200      # px — HIGH risk
    medium_risk_distance  : int           = 400      # px — MEDIUM risk
    sound_enabled         : bool          = True     # sound on ALL detections
    notify_enabled        : bool          = True     # desktop popup on ALL detections
    save_path             : Optional[str] = None
    display_fps           : bool          = True
    font_scale            : float         = 0.55
    font_thickness        : int           = 1
    box_thickness         : int           = 2
    alert_cooldown        : float         = 3.0      # seconds between desktop/sound alerts
    phone_notify_enabled  : bool          = True     # phone push on ALL detections
    notify_server_port    : int           = 8765     # port for Wildlife Alert Notification Server

    def __post_init__(self):
        if self.distance_threshold >= self.medium_risk_distance:
            raise ValueError(
                f"distance_threshold ({self.distance_threshold}) must be < "
                f"medium_risk_distance ({self.medium_risk_distance})."
            )