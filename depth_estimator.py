"""
depth_estimator.py - MiDaS-based monocular depth estimation.

FIXES vs original:
  1. get_depth_at: added bounds clamping so out-of-range bbox centers
     (e.g. when detection is right at the frame edge) no longer raise
     an IndexError on the depth_map array.
  2. __init__: torch.hub.load failures (network errors, missing model)
     now raise a clear RuntimeError with an actionable message instead
     of crashing with an opaque torch exception.
  3. estimate: added a guard so a broken frame (wrong shape) doesn't
     silently produce a garbage depth map.
"""

import cv2
import numpy as np

try:
    import torch
    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False


class DepthEstimator:

    def __init__(self):
        if not _TORCH_AVAILABLE:
            raise RuntimeError(
                "[DepthEstimator] PyTorch is not installed. "
                "Run: pip install torch torchvision"
            )

        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        # FIX: wrap hub.load in try/except so a transient network error or
        # corrupted cache gives a readable message instead of a traceback dump
        try:
            self.model = torch.hub.load("intel-isl/MiDaS", "MiDaS_small")
            self.model.to(self.device)
            self.model.eval()

            transforms = torch.hub.load("intel-isl/MiDaS", "transforms")
            self.transform = transforms.small_transform
        except Exception as exc:
            raise RuntimeError(
                f"[DepthEstimator] Failed to load MiDaS model: {exc}\n"
                "  • Check your internet connection (first run downloads weights).\n"
                "  • Try clearing the torch hub cache: "
                "torch.hub.set_dir('/tmp/hub') then retry."
            ) from exc

    # ------------------------------------------------------------------

    def estimate(self, frame: np.ndarray) -> np.ndarray:
        """
        Run MiDaS on `frame` (BGR, HxWx3) and return a normalized
        depth map (float32, HxW, values in [0, 1]).
        """
        # FIX: guard against frames with wrong number of channels
        if frame.ndim != 3 or frame.shape[2] != 3:
            h, w = frame.shape[:2]
            return np.zeros((h, w), dtype=np.float32)

        img         = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        input_batch = self.transform(img).to(self.device)

        with torch.no_grad():
            prediction = self.model(input_batch)
            prediction = torch.nn.functional.interpolate(
                prediction.unsqueeze(1),
                size=frame.shape[:2],
                mode="bicubic",
                align_corners=False,
            ).squeeze()

        depth_map = prediction.cpu().numpy()
        depth_map = cv2.normalize(depth_map, None, 0, 1, cv2.NORM_MINMAX)
        return depth_map.astype(np.float32)

    # ------------------------------------------------------------------

    def get_depth_at(self, depth_map: np.ndarray, bbox: tuple) -> float:
        """
        Sample the depth value at the centre of `bbox`.

        FIX: original had no bounds check — a detection whose centre
        landed outside the depth map (possible when detections are
        clipped to frame edges) would raise an IndexError.
        Now the coordinates are clamped to valid array bounds.
        """
        x1, y1, x2, y2 = bbox
        h, w = depth_map.shape[:2]

        # Clamp centre to valid pixel range
        cx = int(max(0, min((x1 + x2) / 2, w - 1)))
        cy = int(max(0, min((y1 + y2) / 2, h - 1)))

        return float(depth_map[cy, cx])