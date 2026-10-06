"""Scoring primitives: rigid alignment of folded geometry and silhouette IoU."""

from __future__ import annotations

import math

import numpy as np
from shapely import affinity
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry


# ------------------------------------------------------------- point alignment
def kabsch(P: np.ndarray, Q: np.ndarray, allow_reflection: bool = True):
    """Best rigid (optionally improper) transform mapping P onto Q.

    Returns (R, t, reflected) minimising sum ||R p + t - q||^2.
    """
    pc, qc = P.mean(0), Q.mean(0)
    H = (P - pc).T @ (Q - qc)
    U, _, Vt = np.linalg.svd(H)
    best = None
    for refl in ((False, True) if allow_reflection else (False,)):
        D = np.diag([1.0, -1.0 if (np.linalg.det(Vt.T @ U.T) > 0) == refl else 1.0])
        R = Vt.T @ D @ U.T
        t = qc - R @ pc
        err = float(np.sum((P @ R.T + t - Q) ** 2))
        if best is None or err < best[0]:
            best = (err, R, t, bool(np.linalg.det(R) < 0))
    return best[1], best[2], best[3]


def geometry_score(pred: np.ndarray, gt: np.ndarray, tol: float = 0.01) -> dict:
    """Compare vertex-indexed folded coordinates up to rigid motion + reflection.

    Robust to a minority of wrong vertices: alignment is refit on inliers.
    """
    pred = np.asarray(pred, float)
    gt = np.asarray(gt, float)
    if pred.shape != gt.shape:
        return {"fraction_correct": 0.0, "max_error": math.inf, "reflected": False,
                "error": f"expected {gt.shape[0]} vertices, got {pred.shape[0]}"}
    mask = np.ones(len(gt), bool)
    R = t = None
    reflected = False
    for _ in range(4):
        R, t, reflected = kabsch(pred[mask], gt[mask])
        err = np.linalg.norm(pred @ R.T + t - gt, axis=1)
        new = err <= max(tol, np.quantile(err, 0.5) * 3)
        if new.sum() < 3 or (new == mask).all():
            break
        mask = new
    err = np.linalg.norm(pred @ R.T + t - gt, axis=1)
    return {"fraction_correct": float(np.mean(err <= tol)), "max_error": float(err.max()),
            "mean_error": float(err.mean()), "reflected": reflected}


# ------------------------------------------------------------- silhouettes
def as_geometry(poly) -> BaseGeometry:
    """Accept a shapely geometry, a list of (x, y) or a list of rings/polygons."""
    if isinstance(poly, BaseGeometry):
        return poly
    arr = poly
    if len(arr) and isinstance(arr[0][0], (list, tuple)):
        return MultiPolygon([Polygon(p).buffer(0) for p in arr]).buffer(0)
    return Polygon(arr).buffer(0)


def _iou(a: BaseGeometry, b: BaseGeometry) -> float:
    u = a.union(b).area
    return a.intersection(b).area / u if u > 0 else 0.0


def silhouette_iou(pred, target, rot_step_deg: float = 2.0) -> dict:
    """IoU after the best rigid alignment (rotation, reflection, translation).

    Scale is *not* normalised: the paper size is fixed, so size matters.
    """
    A = as_geometry(pred)
    B = as_geometry(target)
    if A.is_empty or B.is_empty:
        return {"iou": 0.0}
    bc = B.centroid
    best = (-1.0, 0.0, False, 0.0, 0.0)
    for refl in (False, True):
        A0 = affinity.scale(A, xfact=-1, origin=(0, 0)) if refl else A
        ac = A0.centroid
        A0 = affinity.translate(A0, bc.x - ac.x, bc.y - ac.y)
        for k in range(int(360 / rot_step_deg)):
            ang = k * rot_step_deg
            v = _iou(affinity.rotate(A0, ang, origin=bc), B)
            if v > best[0]:
                best = (v, ang, refl, 0.0, 0.0)
    # local refinement over (angle, dx, dy)
    v, ang, refl, dx, dy = best
    A0 = affinity.scale(A, xfact=-1, origin=(0, 0)) if refl else A
    ac = A0.centroid
    A0 = affinity.translate(A0, bc.x - ac.x, bc.y - ac.y)
    steps = [rot_step_deg / 2, 0.01]
    for _ in range(30):
        improved = False
        for dang, ddx, ddy in ((steps[0], 0, 0), (-steps[0], 0, 0), (0, steps[1], 0),
                               (0, -steps[1], 0), (0, 0, steps[1]), (0, 0, -steps[1])):
            cand = affinity.translate(affinity.rotate(A0, ang + dang, origin=bc), dx + ddx, dy + ddy)
            c = _iou(cand, B)
            if c > v + 1e-12:
                v, ang, dx, dy = c, ang + dang, dx + ddx, dy + ddy
                improved = True
        if not improved:
            steps = [s / 2 for s in steps]
            if steps[0] < 1e-3:
                break
    return {"iou": float(v), "rotation_deg": float(ang), "reflected": refl}


def normalized_iou(iou: float, baseline: float) -> float:
    """Rescale IoU so that the trivial answer (unfolded paper) scores 0."""
    if baseline >= 1:
        return iou
    return max(0.0, (iou - baseline) / (1 - baseline))


# ------------------------------------------------------------- shape features
def sharp_points(poly, max_angle_deg: float = 60.0, min_edge: float = 0.02) -> int:
    """Count convex silhouette corners sharper than ``max_angle_deg`` (a proxy for flaps/points)."""
    g = as_geometry(poly)
    polys = list(g.geoms) if isinstance(g, MultiPolygon) else [g]
    count = 0
    for p in polys:
        ring = p.simplify(min_edge / 4).exterior
        pts = np.array(ring.coords[:-1])
        if not ring.is_ccw:
            pts = pts[::-1]
        n = len(pts)
        for i in range(n):
            a, b, c = pts[i - 1], pts[i], pts[(i + 1) % n]
            u, w = a - b, c - b
            cross = (b - a)[0] * (c - b)[1] - (b - a)[1] * (c - b)[0]
            if cross <= 0:
                continue  # reflex
            ang = math.degrees(math.acos(np.clip(np.dot(u, w) / (np.linalg.norm(u) * np.linalg.norm(w)), -1, 1)))
            if ang < max_angle_deg:
                count += 1
    return count


def mirror_symmetry(poly, step_deg: float = 1.0) -> float:
    """Best IoU between the shape and its mirror image over all mirror axes through the centroid."""
    g = as_geometry(poly)
    c = g.centroid
    best = 0.0
    for k in range(int(180 / step_deg)):
        ang = k * step_deg
        m = affinity.rotate(affinity.scale(affinity.rotate(g, -ang, origin=c), yfact=-1, origin=c), ang, origin=c)
        best = max(best, _iou(g, m))
    return best


def extent(poly) -> tuple[float, float]:
    """(length, width) of the minimum rotated bounding rectangle."""
    g = as_geometry(poly)
    rect = g.minimum_rotated_rectangle
    pts = np.array(rect.exterior.coords)
    e1 = np.linalg.norm(pts[1] - pts[0])
    e2 = np.linalg.norm(pts[2] - pts[1])
    return float(max(e1, e2)), float(min(e1, e2))
