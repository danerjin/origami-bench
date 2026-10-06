"""Headless Box Pleating Studio crease-pattern generator.

Thin wrapper around ``bp_core.bundle.mjs`` (a self-contained Node bundle of
Box Pleating Studio v0.7.17's core, MIT, (c) Mu-Tsun Tsai). Only ``node``
(>= 18) is required at runtime. See README.md in this folder.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

__all__ = ["generate", "diagnose", "certified_cp", "BUNDLE_PATH", "BPStudioError"]

BUNDLE_PATH = Path(__file__).resolve().parent / "bp_core.bundle.mjs"


class BPStudioError(RuntimeError):
    """Raised when node is missing or the bundle crashes / returns non-JSON."""


def _node_exe() -> str:
    exe = os.environ.get("BPSTUDIO_NODE") or shutil.which("node")
    if not exe:
        raise BPStudioError("node executable not found (set BPSTUDIO_NODE or put node on PATH)")
    return exe


def _norm_flap(f: Any) -> dict:
    if isinstance(f, Mapping):
        return {
            "id": int(f["id"]),
            "x": int(f["x"]),
            "y": int(f["y"]),
            "width": int(f.get("width", 0)),
            "height": int(f.get("height", 0)),
        }
    # tuple form: (id, x, y[, width, height])
    f = list(f)
    return {"id": int(f[0]), "x": int(f[1]), "y": int(f[2]),
            "width": int(f[3]) if len(f) > 3 else 0,
            "height": int(f[4]) if len(f) > 4 else 0}


def generate(
    tree_edges: Iterable[Sequence[int]],
    flaps: Iterable[Any],
    grid: int | tuple[int, int],
    timeout: float = 60,
    pattern_choice: int | Mapping[str, int] | None = None,
    config_choice: Mapping[str, int] | None = None,
    diagnose_foldability: bool = False,
) -> dict:
    """Generate a box-pleated crease pattern with BP Studio's core.

    Args:
        tree_edges: ``[(parent, child, length), ...]`` with integer ids/lengths.
        flaps: leaf placements, dicts ``{"id","x","y","width"=0,"height"=0}`` or
            tuples ``(id, x, y[, w, h])`` in integer grid units.
        grid: sheet size in grid units (int for a square, or ``(width, height)``).
        timeout: seconds before the node subprocess is killed.
        pattern_choice: pattern index applied to every stretch (int) or
            ``{stretch_id: index}``; default is BP Studio's first (best) pattern.
        config_choice: ``{stretch_id: configuration index}``.
        diagnose_foldability: if True, add ``result["diagnostics"]`` from
            :func:`diagnose` (even-degree / Kawasaki check of interior vertices).

    Returns:
        The bundle's JSON (see README) plus ``lines_unit``: the lines as
        ``[x1, y1, x2, y2, kind]`` divided by the sheet width (and height),
        i.e. normalized to the unit square for a square sheet.
    """
    if isinstance(grid, (tuple, list)):
        w, h = int(grid[0]), int(grid[1])
    else:
        w = h = int(grid)
    payload: dict[str, Any] = {
        "tree": [[int(a), int(b), int(c)] for a, b, c in tree_edges],
        "flaps": [_norm_flap(f) for f in flaps],
        "sheet": {"width": w, "height": h},
    }
    if pattern_choice is not None:
        payload["pattern_choice"] = pattern_choice if isinstance(pattern_choice, int) else dict(pattern_choice)
    if config_choice is not None:
        payload["config_choice"] = dict(config_choice)

    try:
        proc = subprocess.run(
            [_node_exe(), str(BUNDLE_PATH)],
            input=json.dumps(payload).encode(),
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        return {"status": "error", "errors": [f"timeout after {timeout}s"], "lines": [],
                "lines_unit": [], "warnings": []}
    out = proc.stdout.decode().strip()
    try:
        result = json.loads(out.splitlines()[-1]) if out else None
    except json.JSONDecodeError:
        result = None
    if result is None:
        raise BPStudioError(
            f"bp_core bundle failed (exit {proc.returncode}): {proc.stderr.decode()[-2000:]}")
    sw = result.get("sheet", {}).get("width", w) or w
    sh = result.get("sheet", {}).get("height", h) or h
    result["lines_unit"] = [[x1 / sw, y1 / sh, x2 / sw, y2 / sh, k]
                            for x1, y1, x2, y2, k in result.get("lines", [])]
    if proc.stderr:
        result.setdefault("warnings", []).append("node stderr: " + proc.stderr.decode()[-1000:])
    if diagnose_foldability:
        result["diagnostics"] = diagnose(result)
    return result


def _planar_edges(lines):
    """Split segments at all intersections (exact rational arithmetic)."""
    from fractions import Fraction
    from itertools import combinations

    def fr(x):
        return Fraction(x).limit_denominator(10**6)

    segs = [((fr(a), fr(b)), (fr(c), fr(d)), k) for a, b, c, d, k in lines]
    cuts = [{s[0], s[1]} for s in segs]

    def on(pt, p, d):
        if (pt[0] - p[0]) * d[1] - (pt[1] - p[1]) * d[0] != 0:
            return False
        t = ((pt[0] - p[0]) * d[0] + (pt[1] - p[1]) * d[1]) / (d[0] ** 2 + d[1] ** 2)
        return 0 < t < 1

    for i, j in combinations(range(len(segs)), 2):
        (p, q, _), (r, s, _) = segs[i], segs[j]
        d1 = (q[0] - p[0], q[1] - p[1])
        d2 = (s[0] - r[0], s[1] - r[1])
        den = d1[0] * d2[1] - d1[1] * d2[0]
        if den == 0:
            cuts[i].update(pt for pt in (r, s) if on(pt, p, d1))
            cuts[j].update(pt for pt in (p, q) if on(pt, r, d2))
            continue
        t = ((r[0] - p[0]) * d2[1] - (r[1] - p[1]) * d2[0]) / den
        u = ((r[0] - p[0]) * d1[1] - (r[1] - p[1]) * d1[0]) / den
        if 0 <= t <= 1 and 0 <= u <= 1:
            x = (p[0] + t * d1[0], p[1] + t * d1[1])
            cuts[i].add(x)
            cuts[j].add(x)
    edges = set()
    for (p, q, k), pts in zip(segs, cuts):
        d = (q[0] - p[0], q[1] - p[1])
        order = sorted(pts, key=lambda z: (z[0] - p[0]) * d[0] + (z[1] - p[1]) * d[1])
        for a, b in zip(order, order[1:]):
            if a != b:
                edges.add((min(a, b), max(a, b), k))
    return edges


def diagnose(result: dict) -> dict:
    """Necessary flat-foldability checks on the *unassigned* line set.

    For every interior vertex of the planarized CP, checks even degree and
    Kawasaki's theorem. BP Studio's exported CP omits the axial/elevation
    pleats, so violations are expected; they mark where crease completion is
    needed before an M/V solver can succeed.
    """
    import math

    sheet = result.get("sheet") or {}
    W, H = sheet.get("width", result.get("grid")), sheet.get("height", result.get("grid"))
    edges = _planar_edges(result.get("lines", []))
    adj: dict = {}
    for a, b, k in edges:
        if k == "border":
            continue
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    violations = []
    n = 0
    for v, nb in adj.items():
        if v[0] in (0, W) or v[1] in (0, H):
            continue
        n += 1
        angs = sorted(math.atan2(float(w[1] - v[1]), float(w[0] - v[0])) for w in nb)
        if len(angs) % 2:
            violations.append([float(v[0]), float(v[1]), f"odd degree {len(angs)}"])
            continue
        gaps = [(angs[(i + 1) % len(angs)] - angs[i]) % (2 * math.pi) for i in range(len(angs))]
        s = sum(gaps[0::2])
        if abs(s - math.pi) > 1e-7:
            violations.append([float(v[0]), float(v[1]), f"kawasaki alt-sum {math.degrees(s):.3f} deg"])
    return {"planar_edges": len(edges), "interior_vertices": n,
            "violations": violations, "locally_flat_foldable": not violations}


def certified_cp(tree_edges, flaps, grid, timeout: float = 120.0, gen_timeout: float = 60.0,
                 pattern_choice=None, config_choice=None, pleat_options: Mapping | None = None,
                 fallback_budget: int = 20_000, skip_heuristic: bool = True):
    """generate -> complete_pleats -> flat-folder M/V completion.

    Returns ``(cp, info)``. ``cp`` is a :class:`creasebench.cp.CreasePattern` on
    the unit square with every crease assigned M or V, or ``None`` if
    certification failed. ``info`` holds:

    * ``stage``: one of generate, pleats, local, verify or ok. This is the
      stage that failed, or ok.
    * ``reason`` and ``bp``: the generate() result without its lines.
    * ``pleats``: the info returned by complete_pleats.
    * ``verify``: the summary of creasebench.verify.verify.
    * ``n_creases`` and the timings.

    ``skip_heuristic`` (default True): if the pleat completion needed its
    heuristic fallbacks (the Voronoi excess fill or greedy repair rays), stop
    with ``stage="pleats"`` and do not verify. In the benchmark runs none of
    those cases certified (see README), and verifying them costs 1-5 minutes each.

    ``fallback_budget`` is the decision budget of the pure-Python layer solver.
    ``verify`` only uses that solver when flat-folder errors; a small budget keeps
    those cases from running for many minutes.

    Note: this calls ``verify(cp)`` once and derives the M/V assignment from
    its layer order exactly as ``creasebench.verify.complete_assignment``
    does. That avoids running the flat-folder twice.
    """
    import time

    from creasebench.cp import CreasePattern
    from creasebench.verify import verify

    from .pleats import complete_pleats

    info: dict[str, Any] = {"timings": {}}
    t0 = time.perf_counter()
    res = generate(tree_edges, flaps, grid, timeout=gen_timeout,
                   pattern_choice=pattern_choice, config_choice=config_choice)
    info["timings"]["generate"] = round(time.perf_counter() - t0, 3)
    info["bp"] = {k: v for k, v in res.items() if k not in ("lines", "lines_unit", "assignment", "bp_assignment")}
    if res.get("status") != "ok":
        info.update(stage="generate", reason="; ".join(res.get("errors", [])))
        return None, info

    t0 = time.perf_counter()
    segs, pinfo = complete_pleats(res, return_info=True, **dict(pleat_options or {}))
    info["timings"]["pleats"] = round(time.perf_counter() - t0, 3)
    info["pleats"] = pinfo
    if pinfo["violations"]:
        info.update(stage="pleats", reason=f"{len(pinfo['violations'])} interior vertices still violate "
                                           f"even-degree/Kawasaki after completion")
        return None, info
    pinfo["heuristic"] = pinfo["strategy"] == "voronoi" or pinfo.get("repair_rays_added", 0) > 0
    if skip_heuristic and pinfo["heuristic"]:
        info.update(stage="pleats", reason="completion needed heuristic excess-paper repair "
                                           "(Voronoi fill / repair rays); not verified (skip_heuristic=True)")
        return None, info

    W, H = res["sheet"]["width"], res["sheet"]["height"]
    unit = [[x1 / W, y1 / H, x2 / W, y2 / H, "B" if k == "border" else "U"] for x1, y1, x2, y2, k in segs]
    cp = CreasePattern.from_segments(unit, tol=1e-9)
    info["n_creases"] = cp.num_creases()
    info["cp_warnings"] = list(cp.warnings)

    t0 = time.perf_counter()
    rep = verify(cp, timeout=timeout, budget=fallback_budget)
    info["timings"]["verify"] = round(time.perf_counter() - t0, 3)
    info["verify"] = rep.summary()
    if not rep.foldable or rep.layers is None or rep.layers.assignments is None:
        info.update(stage="local" if rep.local is not None and not rep.local.ok else "verify",
                    reason=rep.reason)
        return None, info
    out = CreasePattern(cp.vertices.copy(), list(cp.edges), list(rep.layers.assignments),
                        [list(f) for f in cp.faces])
    out.warnings = list(cp.warnings)
    info.update(stage="ok", reason="flat-foldable")
    return out, info


REFERENCE_SAMPLES = ("lizard_32", "star4_16", "three_flap_16", "star4_r6_16", "stretch_gops_13",
                     "stretch_gops_14", "stretch_kamiya_13", "tight_0_00", "tight_0_05", "random_0_02")


def reference_designs(names=REFERENCE_SAMPLES) -> list[dict]:
    """Certified box-pleated crease patterns shipped in samples/certified (generated with
    certified_cp; regenerate with ``python -m creasebench.gen.bpstudio.certify_samples``).
    They are re-verified on load."""
    import json

    from ...cp import CreasePattern
    from ...verify import verify

    out = []
    root = Path(__file__).with_name("samples") / "certified"
    for name in names:
        p = root / f"{name}.fold"
        if not p.exists():
            continue
        d = json.loads(p.read_text())
        cp = CreasePattern.from_fold(d, rebuild=False)
        if not verify(cp, timeout=120).foldable:
            continue
        out.append({"name": f"bp-{name}".replace("_", "-"), "cp": cp,
                    "meta": {"generator": "Box Pleating Studio core + pleat completion",
                             **d.get("creasebench_source", {})}})
    return out
