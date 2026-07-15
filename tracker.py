"""
tracker.py - IoU-based persistent tracker.

FIX: Previously used positional index matching which caused velocity
mis-assignment whenever detections reordered or appeared/disappeared.
Now uses IoU overlap to match new detections to existing tracks so
track IDs survive partial occlusion, brief disappearances, and
reordering in the detection list.
"""

import numpy as np


def _iou(a, b):
    """Compute IoU between two bboxes (x1,y1,x2,y2)."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    inter_w = max(0, ix2 - ix1)
    inter_h = max(0, iy2 - iy1)
    inter   = inter_w * inter_h

    if inter == 0:
        return 0.0

    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union  = area_a + area_b - inter

    return inter / union if union > 0 else 0.0


class SimpleTracker:
    """
    Lightweight centroid + IoU tracker.

    Assigns a persistent integer track_id to each detection and
    computes frame-to-frame velocity (vx, vy) in pixels/frame.

    Returns:
        velocities  : dict  {track_id: (vx, vy)}
        track_ids   : list  of track_id per detection (same order as detections)
    """

    IOU_THRESHOLD  = 0.25   # min IoU to consider a match
    MAX_LOST_FRAMES = 10    # frames to keep a lost track before dropping it

    def __init__(self):
        # track_id → {"bbox": ..., "center": ..., "lost": int}
        self._tracks: dict = {}
        self._next_id: int = 0

    # ------------------------------------------------------------------

    def _center(self, bbox):
        x1, y1, x2, y2 = bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    # ------------------------------------------------------------------

    def update(self, detections: list) -> tuple:
        """
        Match detections to existing tracks via IoU, update positions,
        assign new IDs to unmatched detections.

        Returns
        -------
        velocities : dict {track_id: (vx, vy)}
        track_ids  : list of track_id in the same order as `detections`
        """
        velocities: dict = {}
        assigned_track_ids: list = [-1] * len(detections)

        if not detections:
            # Age all tracks
            for tid in list(self._tracks):
                self._tracks[tid]["lost"] += 1
                if self._tracks[tid]["lost"] > self.MAX_LOST_FRAMES:
                    del self._tracks[tid]
            return velocities, assigned_track_ids

        # ── Greedy IoU matching ──────────────────────────────────────
        unmatched_dets = list(range(len(detections)))
        matched_track_ids = set()

        for det_idx in list(unmatched_dets):
            det_bbox = detections[det_idx]["bbox"]
            best_iou = self.IOU_THRESHOLD
            best_tid = None

            for tid, track in self._tracks.items():
                if tid in matched_track_ids:
                    continue
                iou = _iou(det_bbox, track["bbox"])
                if iou > best_iou:
                    best_iou = iou
                    best_tid = tid

            if best_tid is not None:
                # Match found — compute velocity
                prev_cx, prev_cy = self._tracks[best_tid]["center"]
                new_cx, new_cy   = self._center(det_bbox)

                velocities[best_tid] = (new_cx - prev_cx, new_cy - prev_cy)

                self._tracks[best_tid].update({
                    "bbox":   det_bbox,
                    "center": (new_cx, new_cy),
                    "lost":   0,
                })

                assigned_track_ids[det_idx] = best_tid
                matched_track_ids.add(best_tid)
                unmatched_dets.remove(det_idx)

        # ── Spawn new tracks for unmatched detections ────────────────
        for det_idx in unmatched_dets:
            det_bbox = detections[det_idx]["bbox"]
            tid = self._next_id
            self._next_id += 1

            self._tracks[tid] = {
                "bbox":   det_bbox,
                "center": self._center(det_bbox),
                "lost":   0,
            }
            velocities[tid]           = (0.0, 0.0)   # no history yet
            assigned_track_ids[det_idx] = tid

        # ── Age unmatched existing tracks ────────────────────────────
        for tid in list(self._tracks):
            if tid not in matched_track_ids and tid not in {
                assigned_track_ids[i] for i in range(len(detections))
                if assigned_track_ids[i] != -1
            }:
                self._tracks[tid]["lost"] += 1
                if self._tracks[tid]["lost"] > self.MAX_LOST_FRAMES:
                    del self._tracks[tid]

        return velocities, assigned_track_ids