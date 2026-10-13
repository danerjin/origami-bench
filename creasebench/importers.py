"""Import crease patterns from other tools: ORIPA ``.cp`` / ``.opx`` and FOLD.

ORIPA ``.cp`` is one line per segment: ``type x1 y1 x2 y2`` with type 1 = paper edge (cut),
2 = mountain, 3 = valley, anything else (0, 4) = auxiliary line (dropped). ``.opx`` is ORIPA's XML
format with ``<oripa.OriLineProxy>`` records (type, x0, y0, x1, y1). Coordinates are normalized so
the paper square becomes the unit square (y up).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .cp import CreasePattern

_KIND = {1: "B", 2: "M", 3: "V"}


def _normalize(segs: list[tuple[float, float, float, float, str]]) -> list[list]:
    xs = [v for s in segs for v in (s[0], s[2])]
    ys = [v for s in segs for v in (s[1], s[3])]
    x0, y0 = min(xs), min(ys)
    side = max(max(xs) - x0, max(ys) - y0)
    if side <= 0:
        raise ValueError("degenerate crease pattern")
    return [[(a - x0) / side, (b - y0) / side, (c - x0) / side, (d - y0) / side, k] for a, b, c, d, k in segs]


def read_cp_text(text: str) -> list[list]:
    segs = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 5:
            continue
        t = int(float(parts[0]))
        if t not in _KIND:
            continue
        x1, y1, x2, y2 = map(float, parts[1:])
        segs.append((x1, -y1, x2, -y2, _KIND[t]))  # ORIPA's y axis points down
    return _normalize(segs)


def read_opx_text(text: str) -> list[list]:
    segs = []
    for rec in re.findall(r"<object class=\"oripa\.OriLineProxy\">(.*?)</object>", text, re.S):
        vals = dict(re.findall(r"<void property=\"(\w+)\">\s*<\w+>([^<]*)</\w+>", rec, re.S))
        t = int(float(vals.get("type", 0)))
        if t not in _KIND:
            continue
        x0, y0, x1, y1 = (float(vals.get(k, 0)) for k in ("x0", "y0", "x1", "y1"))
        segs.append((x0, -y0, x1, -y1, _KIND[t]))
    return _normalize(segs)


def load_crease_pattern(path: str | Path, tol: float = 1e-7) -> CreasePattern:
    """Load ``.cp``, ``.opx`` or ``.fold`` into a planar :class:`CreasePattern` on the unit square."""
    p = Path(path)
    suf = p.suffix.lower()
    if suf == ".fold":
        return CreasePattern.from_fold(json.loads(p.read_text()), rebuild=True)
    text = p.read_text(errors="replace")
    segs = read_opx_text(text) if suf == ".opx" else read_cp_text(text)
    return CreasePattern.from_segments(segs, tol=tol)
