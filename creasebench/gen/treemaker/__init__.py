"""Optional offline crease-pattern generator backed by TreeMaker 5.

TreeMaker 5 (c) Robert J. Lang is GPL v2+; it is *not* vendored here. Run
``creasebench/gen/treemaker/build.sh`` once to fetch/compile it into
``~/.cache/creasebench/treemaker`` together with our driver ``tm_driver.cpp``
(GPL-2.0-or-later). This module only shells out to the resulting
``tm_generate`` binary, so importing it never requires the build; check
:func:`available` first. Crease patterns produced are program output and not
covered by the GPL.

Example::

    from creasebench.gen import treemaker
    if treemaker.available():
        r = treemaker.generate([("body", "a", 1), ("body", "b", 1),
                                ("body", "c", 1), ("body", "d", 1)])
        r["ok"], r["scale"], r["creases"][:3]
"""

from __future__ import annotations

import itertools
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Iterable, Sequence

__all__ = ["available", "binary_path", "build", "generate", "TreeMakerError"]

_HERE = Path(__file__).resolve().parent
_SNAP = 1e-4  # TreeMaker DistTol: coords this close to 0 or 1 are snapped onto the border


class TreeMakerError(RuntimeError):
    pass


def _cache_dir() -> Path:
    root = os.environ.get("CREASEBENCH_CACHE")
    if root:
        return Path(root) / "treemaker"
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "creasebench" / "treemaker"


def binary_path() -> Path:
    """Location of ``tm_generate`` (override with ``CREASEBENCH_TM_GENERATE``)."""
    env = os.environ.get("CREASEBENCH_TM_GENERATE")
    if env:
        return Path(env)
    return _cache_dir() / "bin" / "tm_generate"


def available() -> bool:
    """True if the compiled ``tm_generate`` binary exists and is executable."""
    p = binary_path()
    return p.is_file() and os.access(p, os.X_OK)


def build(tm_src: str | None = None, quiet: bool = True) -> Path:
    """Run build.sh (fetches TreeMaker at the pinned commit unless ``tm_src``)."""
    env = dict(os.environ)
    if tm_src:
        env["TM_SRC"] = str(tm_src)
    r = subprocess.run(["bash", str(_HERE / "build.sh")], env=env,
                       capture_output=quiet, text=True)
    if r.returncode != 0:
        raise TreeMakerError(f"build.sh failed:\n{r.stdout}\n{r.stderr}")
    return binary_path()


def _tok(x: Any) -> str:
    s = str(x)
    if not s or any(c.isspace() for c in s) or "#" in s:
        raise ValueError(f"node id {x!r} must be non-empty without whitespace/'#'")
    return s


def _snap(v: float) -> float:
    r = round(v)
    return float(r) if abs(v - r) < _SNAP else float(v)


def _area(pts: Sequence[Sequence[float]]) -> float:
    a = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2


def _on_square_border(x1: float, y1: float, x2: float, y2: float,
                      eps: float = 1e-5) -> bool:
    return any(abs(a) < eps and abs(b) < eps for a, b in
               ((x1, x2), (y1, y2), (x1 - 1, x2 - 1), (y1 - 1, y2 - 1)))


def _leaf_edges(edges: list) -> list[tuple[float, str]]:
    """(leaf-edge length, leaf id) for every leaf, longest first."""
    deg: dict = {}
    for a, b, _ in edges:
        deg[str(a)] = deg.get(str(a), 0) + 1
        deg[str(b)] = deg.get(str(b), 0) + 1
    out = [(float(length), str(leaf)) for a, b, length in edges
           for leaf in (a, b) if deg[str(leaf)] == 1]
    out.sort(key=lambda t: (-t[0], t[1]))
    return out


def _corner_candidates(edges: list, max_sets: int) -> list[list[str]]:
    """4-subsets of the (up to 7) longest-flap leaves, by total length desc."""
    le = _leaf_edges(edges)
    if len(le) < 4:
        return []
    top = le[:7]
    combos = sorted(itertools.combinations(top, 4),
                    key=lambda c: (-sum(t[0] for t in c), [t[1] for t in c]))
    return [[t[1] for t in c] for c in combos[:max_sets]]


def _quality(r: dict) -> tuple:
    clean = r["ok"] and r["raw"].get("interior_violations") == 0
    return (r["ok"], clean, r["covers_square"], r["scale"] or 0.0)


def generate(edges: Iterable[Sequence[Any]], timeout: float = 60, *,
             corners: Iterable[Any] | str = (), borders: Iterable[Any] = (),
             locs: dict[Any, Sequence[float]] | None = None,
             solver: str = "auto", restarts: int = 8, seed: int = 1,
             stubs: int = 1, pin: bool = True, first: bool = False,
             max_corner_sets: int = 6,
             binary: str | os.PathLike | None = None) -> dict:
    """Run TreeMaker headless on a tree and return a normalized crease pattern.

    Args:
        edges: ``(a, b, length)`` triples; node ids are any whitespace-free
            str/int. Must form a tree with >= 3 leaves.
        timeout: total seconds budget; raises TreeMakerError if exceeded
            (with ``corners="auto"``, the best result so far is returned).
        corners / borders: leaf ids to condition onto a paper corner / edge.
            ``corners="auto"``: run unconditioned, then try up to
            ``max_corner_sets`` choices of 4 long-flap leaves pinned to the 4
            corners (until one gives a clean square-covering CP; without
            corner leaves TreeMaker usually only creases the leaves' convex
            hull) and return the best by (ok, local_ok, covers_square,
            scale). Trees with < 4 leaves run unconditioned only.
        locs: optional initial positions ``{id: (x, y)}`` in [0,1]^2.
        solver: ``"auto"`` (default: ALM on even restart attempts, wnlib on
            odd ones), ``"alm"`` or ``"wnlib"``.
        restarts: random-restart attempts (random initial layouts); the
            full-CP attempt with the largest scale is returned (attempts that
            also pass the interior Maekawa/Kawasaki check are preferred).
        first: stop at the first attempt that yields a clean full CP.
        stubs: 0 never, 1 triangulate with tmStubFinder if the first CP build
            fails, 2 always triangulate.
        pin: stretch unpinned leaf flaps (edge optimizer) until all are pinned.

    Returns a dict with keys:
        ok (bool, full CP with facet ordering & M/V; when False the crease
        lists may be partial or empty), status (TreeMaker CPStatus or failure
        stage), scale (TreeMaker scale factor m: unit tree length -> paper
        length, square side = 1), creases ([x1, y1, x2, y2, assignment, kind]
        with assignment in M/V/F/B/U: F = unfolded hinge (flat), B = on the
        square's border, U = boundary of the leaf hull inside the square, no
        assignment), leaves ({id: [x, y]}), nodes (all tree nodes incl. stubs),
        vertices ([{x, y, tree_node, elevation, depth, border}]), facets,
        covers_square, hull_area, local_ok (interior Maekawa/Kawasaki pass),
        corners (leaf ids pinned to corners), seconds, raw (driver JSON).
    """
    exe = Path(binary) if binary else binary_path()
    if not (exe.is_file() and os.access(exe, os.X_OK)):
        raise TreeMakerError(f"tm_generate not built at {exe}; run build.sh")
    edges = [tuple(e) for e in edges]
    kw = dict(borders=list(borders), locs=locs, solver=solver,
              restarts=restarts, seed=seed, stubs=stubs, pin=pin, first=first)
    if not isinstance(corners, str):
        return _run_once(exe, edges, list(corners), timeout=timeout, **kw)
    if corners != "auto":
        raise ValueError("corners must be an iterable of ids or 'auto'")
    t0 = time.monotonic()
    best = None
    last_err: Exception | None = None
    for cset in [[]] + _corner_candidates(edges, max_corner_sets):
        left = timeout - (time.monotonic() - t0)
        if left <= 0:
            break
        try:
            r = _run_once(exe, edges, cset, timeout=left, **kw)
        except TreeMakerError as ex:
            last_err = ex
            continue
        if best is None or _quality(r) > _quality(best):
            best = r
        if cset and r["ok"] and r["local_ok"] and r["covers_square"]:
            break  # candidates are ordered by flap length; good enough
    if best is None:
        raise TreeMakerError(f"no result within {timeout}s: {last_err}")
    best["seconds"] = time.monotonic() - t0
    return best


def _run_once(exe: Path, edges: list, corners: list, *, timeout: float,
              borders: list, locs, solver: str, restarts: int, seed: int,
              stubs: int, pin: bool, first: bool) -> dict:
    lines = []
    for e in edges:
        a, b, length = e[0], e[1], float(e[2])
        lines.append(f"edge {_tok(a)} {_tok(b)} {length!r}")
    for n in corners:
        lines.append(f"corner {_tok(n)}")
    for n in borders:
        lines.append(f"border {_tok(n)}")
    for n, (x, y) in (locs or {}).items():
        lines.append(f"loc {_tok(n)} {float(x)!r} {float(y)!r}")
    lines += [f"option solver {solver}", f"option restarts {int(restarts)}",
              f"option seed {int(seed)}", f"option stubs {int(stubs)}",
              f"option pin {1 if pin else 0}",
              f"option first {1 if first else 0}",
              f"option attempt_timeout {max(1, min(10, int(timeout / 4)))}"]
    try:
        r = subprocess.run([str(exe)], input="\n".join(lines) + "\n",
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as ex:
        raise TreeMakerError(f"tm_generate timed out after {timeout:.1f}s") from ex
    try:
        raw = json.loads(r.stdout)
    except json.JSONDecodeError as ex:
        raise TreeMakerError(
            f"tm_generate rc={r.returncode} produced no JSON: "
            f"{r.stdout[:200]!r} {r.stderr[:500]!r}") from ex
    out = _normalize(raw)
    out["corners"] = [str(c) for c in corners]
    return out


def _normalize(raw: dict) -> dict:
    if raw.get("status") == "INPUT_ERROR":
        raise ValueError(raw.get("error", "bad input"))
    W, H = raw.get("paper", [1.0, 1.0])
    s = max(W, H)  # TreeMaker default paper is 1x1; scale into unit square
    verts = [{**v, "x": _snap(v["x"] / s), "y": _snap(v["y"] / s)}
             for v in raw.get("vertices", [])]
    creases = []
    for c in raw.get("creases", []):
        a, b = verts[c["v"][0]], verts[c["v"][1]]
        x1, y1, x2, y2 = a["x"], a["y"], b["x"], b["y"]
        fold = c["fold"]
        if fold == "B":
            fold = "B" if _on_square_border(x1, y1, x2, y2) else "U"
        creases.append([x1, y1, x2, y2, fold, c["kind"]])
    nodes = [{**n, "x": _snap(n["x"] / s), "y": _snap(n["y"] / s)}
             for n in raw.get("nodes", [])]
    leaves = {n["id"]: [n["x"], n["y"]] for n in nodes if n["leaf"]}
    facets = raw.get("facets", [])
    hull = sum(_area([(verts[i]["x"], verts[i]["y"]) for i in f["v"]])
               for f in facets)
    return {
        "ok": bool(raw.get("ok")),
        "status": raw.get("status"),
        "scale": raw.get("scale"),
        "creases": creases,
        "leaves": leaves,
        "nodes": nodes,
        "vertices": [{k: v[k] for k in ("x", "y", "tree_node", "elevation",
                                        "depth", "border")} for v in verts],
        "facets": facets,
        "edges": raw.get("edges", []),
        "hull_area": hull,
        "covers_square": bool(raw.get("ok")) and abs(hull - W * H / s / s) < 1e-5,
        "local_ok": bool(raw.get("ok")) and raw.get("interior_violations") == 0,
        "num_stubs_added": raw.get("num_stubs_added", 0),
        "seconds": raw.get("seconds"),
        "raw": raw,
    }


def reference_designs(names=("lizard", "bird", "beetle", "deer", "spider"), timeout: float = 120.0) -> list[dict]:
    """Certified tree-method crease patterns for semantic target trees (used by the task builder).

    Only patterns that cover the whole square and pass the full flat-foldability check
    (flat-folder) are returned; M/V comes from TreeMaker's facet ordering, with any
    leftover unassigned creases completed by the solver."""
    from ...cp import CreasePattern
    from ...trees import SEMANTIC_TREES
    from ...verify import complete_assignment

    out = []
    if not available():
        return out
    for name in names:
        spec = SEMANTIC_TREES[name]
        try:
            r = generate(spec["edges"], timeout=timeout, corners="auto")
        except Exception:  # noqa: BLE001
            continue
        if not (r.get("ok") and r.get("local_ok") and r.get("covers_square")):
            continue
        segs = [s[:5] for s in r["creases"] if s[4] != "F"]
        cp = CreasePattern.from_segments(segs, tol=1e-5)
        cp = complete_assignment(cp, timeout=timeout)
        if cp is None:
            continue
        out.append({"name": f"tm-{name}", "cp": cp,
                    "meta": {"generator": "TreeMaker 5 (headless)", "tree": name, "tm_scale": r.get("scale")}})
    return out
