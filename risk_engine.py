"""
risk_engine.py
==============
Risk assessment engine for Animals, Insects, and Plants.

Each category has its own danger classification and distance thresholds.
Plants have special logic: proximity triggers risk even without motion.
"""

import math
from typing import List, Tuple, Optional
from config import (
    RiskLevel, SystemConfig,
    VENOMOUS_ANIMAL_CLASSES, NON_VENOMOUS_ANIMAL_CLASSES,
    VENOMOUS_INSECT_CLASSES, NON_VENOMOUS_INSECT_CLASSES,
    TOXIC_PLANT_CLASSES, NON_TOXIC_PLANT_CLASSES,
    HUMAN_CLASSES,
)


# ─────────────────────────────────────────────────────────────────────────────
# Geometry helpers
# ─────────────────────────────────────────────────────────────────────────────

def bbox_center(bbox: Tuple) -> Tuple[float, float]:
    x1, y1, x2, y2 = bbox
    return (x1 + x2) / 2.0, (y1 + y2) / 2.0


def closest_edge_distance(a: Tuple, b: Tuple) -> float:
    """Shortest edge-to-edge distance; 0 if overlapping."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    dx = max(0, max(ax1, bx1) - min(ax2, bx2))
    dy = max(0, max(ay1, by1) - min(ay2, by2))
    return math.sqrt(dx * dx + dy * dy)


def euclidean_distance(p1: Tuple, p2: Tuple) -> float:
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)


# ─────────────────────────────────────────────────────────────────────────────
# Classification helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_category(label: str) -> str:
    """Return 'animal', 'insect', 'plant', 'human', or 'unknown'."""
    lbl = label.lower()
    if lbl in HUMAN_CLASSES:
        return "human"
    if lbl in (VENOMOUS_ANIMAL_CLASSES | NON_VENOMOUS_ANIMAL_CLASSES):
        return "animal"
    if lbl in (VENOMOUS_INSECT_CLASSES | NON_VENOMOUS_INSECT_CLASSES):
        return "insect"
    if lbl in (TOXIC_PLANT_CLASSES | NON_TOXIC_PLANT_CLASSES):
        return "plant"
    # fallback: try to guess from label name
    if any(k in lbl for k in ("snake", "scorpion")):
        return "animal"
    if any(k in lbl for k in ("spider", "wasp", "bee", "insect")):
        return "insect"
    if any(k in lbl for k in ("plant", "datura", "hemlock", "nightshade",
                               "calotropis", "parthenium")):
        return "plant"
    return "unknown"


def classify_threat(label: str) -> str:
    """
    Return one of:
      'venomous_animal', 'safe_animal',
      'venomous_insect', 'safe_insect',
      'toxic_plant',     'safe_plant',
      'human',           'unknown'
    """
    lbl = label.lower()
    if lbl in HUMAN_CLASSES:
        return "human"
    if lbl in VENOMOUS_ANIMAL_CLASSES:
        return "venomous_animal"
    if lbl in NON_VENOMOUS_ANIMAL_CLASSES:
        return "safe_animal"
    if lbl in VENOMOUS_INSECT_CLASSES:
        return "venomous_insect"
    if lbl in NON_VENOMOUS_INSECT_CLASSES:
        return "safe_insect"
    if lbl in TOXIC_PLANT_CLASSES:
        return "toxic_plant"
    if lbl in NON_TOXIC_PLANT_CLASSES:
        return "safe_plant"
    # fallback guesses so model detections aren't all "unknown"
    if "venomous" in lbl and "snake" in lbl:
        return "venomous_animal"
    if "non_venomous" in lbl or "nonvenomous" in lbl:
        return "safe_animal"
    if any(k in lbl for k in ("snake", "scorpion")):
        return "venomous_animal"
    if any(k in lbl for k in ("spider", "wasp")):
        return "venomous_insect"
    if any(k in lbl for k in ("bee", "beehive")):
        return "safe_insect"
    if any(k in lbl for k in ("datura", "hemlock", "nightshade",
                               "calotropis", "parthenium")):
        return "toxic_plant"
    return "unknown"


def is_human(label: str) -> bool:
    return label.lower() in HUMAN_CLASSES


def is_dangerous(threat_type: str) -> bool:
    return threat_type in (
        "venomous_animal", "venomous_insect", "toxic_plant", "unknown"
    )


# ─────────────────────────────────────────────────────────────────────────────
# RiskAssessment result object
# ─────────────────────────────────────────────────────────────────────────────

class RiskAssessment:
    def __init__(self):
        self.risk_level       : str             = RiskLevel.NONE
        self.closest_distance : Optional[float] = None
        self.dangerous_label  : Optional[str]   = None
        self.threat_type      : Optional[str]   = None
        self.category         : Optional[str]   = None
        self.human_bbox       : Optional[Tuple] = None
        self.threat_bbox      : Optional[Tuple] = None
        self.message          : str             = ""

    @property
    def dangerous_animal(self) -> Optional[str]:
        return self.dangerous_label

    @property
    def animal_bbox(self) -> Optional[Tuple]:
        return self.threat_bbox

    def __repr__(self):
        dist_str = (f"{self.closest_distance:.1f}px"
                    if self.closest_distance is not None else "N/A")
        return (f"RiskAssessment(risk={self.risk_level}, "
                f"dist={dist_str}, label={self.dangerous_label}, "
                f"cat={self.category})")


# ─────────────────────────────────────────────────────────────────────────────
# Main assessment
# ─────────────────────────────────────────────────────────────────────────────

RISK_ORDER = {
    RiskLevel.NONE: 0, RiskLevel.LOW: 1,
    RiskLevel.MEDIUM: 2, RiskLevel.HIGH: 3
}


def _risk_from_dist(dist: float, threat_type: str, config: SystemConfig) -> str:
    if threat_type in ("safe_animal", "safe_insect", "safe_plant"):
        if dist <= config.distance_threshold:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    if threat_type == "toxic_plant":
        if dist <= config.distance_threshold:
            return RiskLevel.HIGH
        if dist <= config.medium_risk_distance:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    # venomous_animal, venomous_insect, unknown
    if dist <= config.distance_threshold:
        return RiskLevel.HIGH
    if dist <= config.medium_risk_distance:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def assess_frame(detections: List[dict], config: SystemConfig) -> RiskAssessment:
    result  = RiskAssessment()
    humans  = [d for d in detections if is_human(d["label"])]
    threats = [d for d in detections if not is_human(d["label"])]

    if not threats:
        result.message = "No threats detected."
        return result

    if not humans:
        for t in threats:
            tt = classify_threat(t["label"])
            if is_dangerous(tt):
                result.risk_level      = RiskLevel.LOW
                result.dangerous_label = t["label"]
                result.threat_type     = tt
                result.category        = get_category(t["label"])
                result.threat_bbox     = t["bbox"]
                cat_str                = (result.category or "entity").capitalize()
                result.message = (
                    f"⚠ {cat_str} detected — no human nearby: "
                    f"{t['label'].replace('_',' ').title()}"
                )
                return result
        result.risk_level = RiskLevel.LOW
        result.message = "Non-dangerous entity detected — no human nearby."
        return result

    # Both humans and threats present
    worst_risk   = RiskLevel.NONE
    worst_dist   = float("inf")
    worst_human  = None
    worst_threat = None

    for human in humans:
        for threat in threats:
            tt   = classify_threat(threat["label"])
            dist = closest_edge_distance(human["bbox"], threat["bbox"])
            risk = _risk_from_dist(dist, tt, config)

            if (RISK_ORDER[risk] > RISK_ORDER[worst_risk] or
                    (RISK_ORDER[risk] == RISK_ORDER[worst_risk] and dist < worst_dist)):
                worst_risk   = risk
                worst_dist   = dist
                worst_human  = human
                worst_threat = threat

    result.risk_level       = worst_risk
    result.closest_distance = worst_dist
    result.dangerous_label  = worst_threat["label"] if worst_threat else None
    result.threat_type      = classify_threat(worst_threat["label"]) if worst_threat else None
    result.category         = get_category(worst_threat["label"])    if worst_threat else None
    result.human_bbox       = worst_human["bbox"]  if worst_human  else None
    result.threat_bbox      = worst_threat["bbox"] if worst_threat else None

    name     = (result.dangerous_label or "Entity").replace("_", " ").title()
    cat_str  = (result.category or "").capitalize()
    dist_str = f"{worst_dist:.0f}px"

    if worst_risk == RiskLevel.HIGH:
        result.message = f"⚠ HIGH RISK [{cat_str}]: {name} within {dist_str} of a person!"
    elif worst_risk == RiskLevel.MEDIUM:
        result.message = f"⚡ MEDIUM RISK [{cat_str}]: {name} {dist_str} from a person."
    else:
        result.message = f"✓ LOW RISK [{cat_str}]: {name} {dist_str} — safe distance."

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Collision prediction
# ─────────────────────────────────────────────────────────────────────────────

def predict_collision(
    human_bbox,
    threat_bbox,
    threat_velocity,
    human_velocity=(0.0, 0.0),
    steps: int = 10,
):
    hx1, hy1, hx2, hy2 = human_bbox
    ax1, ay1, ax2, ay2 = threat_bbox

    hcx = (hx1 + hx2) / 2.0
    hcy = (hy1 + hy2) / 2.0
    acx = (ax1 + ax2) / 2.0
    acy = (ay1 + ay2) / 2.0

    rel_vx = threat_velocity[0] - human_velocity[0]
    rel_vy = threat_velocity[1] - human_velocity[1]

    THRESHOLD = 50

    for t in range(1, steps + 1):
        dist = math.sqrt(
            (acx + rel_vx * t - hcx) ** 2 +
            (acy + rel_vy * t - hcy) ** 2
        )
        if dist < THRESHOLD:
            return True, t

    return False, None