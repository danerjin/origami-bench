"""Graders for the three tracks. Each returns a dict with ``score`` in [0, 1],
``solved`` (bool) and diagnostic details."""

from __future__ import annotations

import json
import re
from typing import Any

import numpy as np
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

from .compare import (as_geometry, extent, geometry_score, mirror_symmetry, normalized_iou,
                      sharp_points, silhouette_iou)
from .cp import CPError, CreasePattern
from .layers import build_problem, solve_layers
from .simulate import FoldedState, fold
from .tasks import Task
from .verify import verify

ANSWER_SNAP_TOL = 1e-4
GEOM_TOL = 0.01
SOLVED_IOU = 0.95


# ------------------------------------------------------------------ parsing
def extract_json(text: str) -> Any:
    """Parse the last ```json block (or, failing that, the last {...} object) in a reply."""
    if text is None:
        raise ValueError("empty response")
    blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
    for b in reversed(blocks):
        try:
            return json.loads(b)
        except json.JSONDecodeError:
            continue
    # fall back to the last balanced {...}
    end = text.rfind("}")
    while end != -1:
        depth = 0
        for i in range(end, -1, -1):
            depth += {"}": 1, "{": -1}.get(text[i], 0)
            if depth == 0:
                try:
                    return json.loads(text[i:end + 1])
                except json.JSONDecodeError:
                    break
        end = text.rfind("}", 0, end)
    raise ValueError("no JSON answer found")


def _fail(reason: str, **kw) -> dict:
    return {"score": 0.0, "solved": False, "error": reason, **kw}


def grade(task: Task, response_text: str) -> dict:
    try:
        answer = extract_json(response_text)
    except ValueError as e:
        return _fail(f"unparseable answer: {e}")
    if not isinstance(answer, dict):
        return _fail("answer is not a JSON object")
    try:
        out = grade_analytic(task, answer) if task.track == "analytic" else grade_design(task, answer)
    except (CPError, ValueError, TypeError, KeyError, IndexError) as e:
        return _fail(f"invalid answer: {type(e).__name__}: {e}")
    # Rescale so that the trivial baseline (paper left unfolded / a single book fold) scores 0.
    base = task.reference.get("baseline_score")
    if base is not None and base < 1:
        out["raw_score"] = out["score"]
        out["score"] = max(0.0, (out["score"] - base) / (1 - base))
    return out


# ------------------------------------------------------------------ analytic
def task_cp(task: Task) -> CreasePattern:
    return CreasePattern.from_fold(task.inputs["crease_pattern"], rebuild=False)


def grade_analytic(task: Task, ans: dict) -> dict:
    ref = task.reference
    claims_foldable = bool(ans.get("foldable", True))
    if not ref["foldable"]:
        if claims_foldable:
            return {"score": 0.0, "solved": False, "detail": "CP is not flat-foldable but answer folded it"}
        gt_bad = set(ref.get("violation_vertices", []))
        pred_bad = set(int(v) for v in ans.get("violation_vertices", []) or [])
        if gt_bad or pred_bad:
            jac = len(gt_bad & pred_bad) / len(gt_bad | pred_bad)
        else:
            jac = 1.0
        return {"score": 0.6 + 0.4 * jac, "solved": jac == 1.0, "violation_jaccard": jac}
    if not claims_foldable:
        return {"score": 0.0, "solved": False, "detail": "answered not foldable, but it is"}

    cp = task_cp(task)
    folded = fold(cp)
    # Ground truth is recomputed from the CP exactly as shown to the model, so that the
    # alignment's mirror flag refers to the same frame as the layer-order constraints.
    gt_vertices = folded.vertices
    target_sil = as_geometry(ref["silhouette"])
    out: dict[str, Any] = {}
    geom_frac = 0.0
    reflected = None
    iou = 0.0
    if ans.get("folded_vertices") is not None:
        pred = np.array(ans["folded_vertices"], dtype=float)
        g = geometry_score(pred, gt_vertices, tol=GEOM_TOL)
        out["geometry"] = g
        geom_frac = g["fraction_correct"]
        reflected = g.get("reflected")
        if pred.shape == gt_vertices.shape:
            pred_sil = unary_union([Polygon(pred[f]).buffer(1e-9) for f in cp.faces
                                    if Polygon(pred[f]).is_valid])
            if not pred_sil.is_empty:
                iou = silhouette_iou(pred_sil, target_sil)["iou"]
    elif ans.get("silhouette"):
        iou = silhouette_iou(as_geometry(ans["silhouette"]), target_sil)["iou"]
    out["silhouette_iou"] = iou
    shape = max(geom_frac, 0.75 * iou)

    layer = 0.0
    claims = ans.get("face_above") or []
    if claims:
        prob = build_problem(folded)
        pairs = [(int(a), int(b)) for a, b in claims]
        variants = [pairs] if reflected is not None else [pairs, [(b, a) for a, b in pairs]]
        if reflected:
            variants = [[(b, a) for a, b in pairs]]
        covered = {tuple(sorted(p)) for p in pairs} & set(prob.pair_var)
        coverage = len(covered) / max(1, len(prob.pair_var))
        consistent = any(solve_layers(folded, budget=20_000, extra_above=v, problem=prob).status == "found"
                         for v in variants)
        layer = coverage if consistent else 0.0
        out.update(layer_coverage=coverage, layer_consistent=consistent)
    out["layer_score"] = layer
    out["shape_score"] = shape
    out["score"] = 0.8 * shape + 0.2 * layer
    out["solved"] = geom_frac == 1.0
    return out


# ------------------------------------------------------------------ design
def answer_cp(ans: dict) -> CreasePattern:
    if "creases" in ans:
        return CreasePattern.from_segments(ans["creases"], tol=ANSWER_SNAP_TOL)
    if "fold" in ans:
        fold_obj = ans["fold"]
        segs = []
        for (u, v), a in zip(fold_obj["edges_vertices"], fold_obj.get("edges_assignment") or []):
            p, q = fold_obj["vertices_coords"][u], fold_obj["vertices_coords"][v]
            segs.append(((p[0], p[1]), (q[0], q[1]), a))
        return CreasePattern.from_segments(segs, tol=ANSWER_SNAP_TOL)
    raise KeyError("answer needs a 'creases' list")


def folded_point(folded: FoldedState, p) -> np.ndarray | None:
    """Folded position of a point of the paper."""
    pt = Point(p)
    for fi, face in enumerate(folded.cp.faces):
        if Polygon(folded.cp.vertices[face]).buffer(1e-7).contains(pt):
            return folded.transform(fi, np.array([p], float))[0]
    return None


def grade_design(task: Task, ans: dict) -> dict:
    cp = answer_cp(ans)
    if cp.num_creases() == 0:
        return _fail("no creases", num_creases=0)
    rep = verify(cp, budget=50_000)
    out: dict[str, Any] = {"verify": rep.summary(), "num_creases": cp.num_creases()}
    if not rep.foldable:
        out.update(score=0.0, solved=False, error=f"not flat-foldable: {rep.reason}")
        return out
    sil = rep.folded.silhouette()
    checks = task.reference["checks"]
    results = []
    for chk in checks:
        s, info = run_check(chk, sil, rep.folded)
        results.append({"type": chk["type"], "score": s, "weight": chk.get("weight", 1.0), **info})
    wsum = sum(r["weight"] for r in results)
    score = sum(r["score"] * r["weight"] for r in results) / wsum
    used_u = "U" in cp.assignments
    if used_u:
        score *= 0.9
    out.update(checks=results, score=score, used_unassigned=used_u,
               solved=all(r.get("passed", r["score"] >= 0.999) for r in results))
    return out


def run_check(chk: dict, sil, folded: FoldedState) -> tuple[float, dict]:
    t = chk["type"]
    if t == "iou":
        target = as_geometry(chk["target"])
        iou = silhouette_iou(sil, target)["iou"]
        base = silhouette_iou(box(0, 0, 1, 1), target)["iou"]
        thr = chk.get("threshold", SOLVED_IOU)
        return normalized_iou(iou, base), {"iou": iou, "passed": iou >= thr}
    if t == "regular_polygon":
        n = chk["n"]
        iou = _regular_polygon_iou(sil, n)
        thr = chk.get("threshold", SOLVED_IOU)
        ok_area = sil.area >= chk.get("min_area", 0.0)
        return (iou if ok_area else 0.0), {"iou": iou, "area": sil.area, "passed": iou >= thr and ok_area}
    if t == "area":
        a = sil.area
        ok = chk.get("min", 0) - 1e-6 <= a <= chk.get("max", 1) + 1e-6
        return float(ok), {"area": a, "passed": ok}
    if t == "sharp_points":
        n = sharp_points(sil, chk.get("max_angle", 60.0))
        ok = chk.get("min", 0) <= n <= chk.get("max", 10**6)
        return float(ok), {"sharp_points": n, "passed": ok}
    if t == "symmetry":
        s = mirror_symmetry(sil)
        ok = s >= chk.get("min", 0.95)
        return float(ok), {"symmetry_iou": s, "passed": ok}
    if t == "extent":
        length, width = extent(sil)
        ok = (chk.get("min_length", 0) - 1e-6 <= length <= chk.get("max_length", 10) + 1e-6
              and width <= chk.get("max_width", 10) + 1e-6
              and length / max(width, 1e-9) >= chk.get("min_aspect", 0))
        return float(ok), {"length": length, "width": width, "passed": ok}
    if t == "rectangularity":
        r = sil.area / sil.minimum_rotated_rectangle.area
        ok = r >= chk.get("min", 0.98)
        return float(ok), {"rectangularity": r, "passed": ok}
    if t == "convexity":
        r = sil.area / sil.convex_hull.area
        ok = chk.get("min", 0) <= r <= chk.get("max", 1) + 1e-9
        return float(ok), {"convexity": r, "passed": ok}
    if t == "vertex_count":
        g = sil.simplify(chk.get("simplify", 0.01))
        n = len(g.exterior.coords) - 1 if g.geom_type == "Polygon" else -1
        ok = chk.get("min", 0) <= n <= chk.get("max", 10**6)
        return float(ok), {"vertex_count": n, "passed": ok}
    if t == "coincident":
        pts = [folded_point(folded, p) for p in chk["points"]]
        if any(p is None for p in pts):
            return 0.0, {"passed": False}
        spread = max(float(np.linalg.norm(a - b)) for a in pts for b in pts)
        ok = spread <= chk.get("tol", 0.01)
        return float(ok), {"spread": spread, "passed": ok}
    raise ValueError(f"unknown check type {t}")


def _regular_polygon_iou(sil, n: int) -> float:
    """IoU against the best-aligned regular n-gon of equal area."""
    area = sil.area
    r = np.sqrt(2 * area / (n * np.sin(2 * np.pi / n)))
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    reg = Polygon(np.c_[r * np.cos(ang), r * np.sin(ang)])
    return silhouette_iou(sil, reg, rot_step_deg=1.0)["iou"]
