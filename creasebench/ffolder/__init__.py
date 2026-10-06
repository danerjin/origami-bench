"""Python bridge to the vendored flat-folder solver (Jason S. Ku, MIT license).

flat-folder decides global flat-foldability (layer order) for crease patterns
with thousands of creases. It runs under Node.js; when Node is missing,
``available()`` is False and callers fall back to the pure-Python solver.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ..cp import CreasePattern

DRIVER = Path(__file__).with_name("ff_solve.mjs")


def available() -> bool:
    return shutil.which("node") is not None


@dataclass
class FFResult:
    status: str  # "found" | "none" | "budget" | "error"
    face_above: list[tuple[int, int]] = field(default_factory=list)  # global frame of our simulator
    states: str | None = None  # number of folded states (as a string; may be huge) up to the limit
    reason: str | None = None
    stats: dict = field(default_factory=dict)
    seconds: float = 0.0


def solve(cp: CreasePattern, flipped: list[bool], limit: int = 1, timeout: float = 120.0) -> FFResult:
    """Run flat-folder on ``cp``.

    ``flipped`` is our simulator's per-face flip state; it is used to express the
    returned layer order in our frame (flat-folder may fold from a different root face).
    """
    fold = {
        "vertices_coords": cp.vertices.tolist(),
        "edges_vertices": [list(map(int, e)) for e in cp.edges],
        "edges_assignment": list(cp.assignments),
        "faces_vertices": [list(map(int, f)) for f in cp.faces],
    }
    try:
        proc = subprocess.run(["node", str(DRIVER), str(limit)], input=json.dumps(fold), text=True,
                              capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return FFResult("budget", reason=f"timed out after {timeout:.0f}s", seconds=timeout)
    if proc.returncode != 0 or not proc.stdout:
        return FFResult("error", reason=(proc.stderr or "no output")[-2000:])
    d = json.loads(proc.stdout)
    res = FFResult(d["status"], reason=d.get("reason") or d.get("error"), stats=d.get("stats", {}),
                   seconds=d.get("seconds", 0.0), states=d.get("states"))
    ff = d.get("Ff")
    if ff is not None and len(ff) == len(flipped) and flipped:
        same = sum(bool(a) == bool(b) for a, b in zip(ff, flipped))
        mirrored = same < len(flipped) / 2
    else:
        mirrored = False
    if d["status"] == "found":
        res.face_above = [(b, a) if mirrored else (a, b) for a, b in d["above"]]
    return res
