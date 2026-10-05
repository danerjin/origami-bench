"""Crease pattern data structure, planar arrangement and face extraction.

Conventions
-----------
* The paper is the unit square [0, 1] x [0, 1], viewed from its top (+z) side.
* Edge assignments follow FOLD: "M" mountain, "V" valley, "B" boundary,
  "F" flat (not folded) and "U" unassigned (folded, direction unknown).
* Faces are vertex loops in counter-clockwise order.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

FOLDED_ASSIGNMENTS = ("M", "V", "U")
VALID_ASSIGNMENTS = ("M", "V", "B", "F", "U")

Segment = tuple[tuple[float, float], tuple[float, float], str]


class CPError(ValueError):
    """Raised when a crease pattern cannot be interpreted."""


@dataclass
class CreasePattern:
    vertices: np.ndarray  # (n, 2)
    edges: list[tuple[int, int]]
    assignments: list[str]
    faces: list[list[int]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.vertices = np.asarray(self.vertices, dtype=float).reshape(-1, 2)
        if not self.faces:
            self.faces = compute_faces(self.vertices, self.edges)
        self._edge_faces: dict[tuple[int, int], list[int]] | None = None

    # ------------------------------------------------------------------ queries
    @property
    def num_vertices(self) -> int:
        return len(self.vertices)

    def edge_index(self) -> dict[tuple[int, int], int]:
        return {_key(u, v): i for i, (u, v) in enumerate(self.edges)}

    def edge_faces(self) -> dict[tuple[int, int], list[int]]:
        """Map undirected edge key -> faces (1 for boundary, 2 for interior)."""
        if self._edge_faces is None:
            ef: dict[tuple[int, int], list[int]] = {}
            for fi, face in enumerate(self.faces):
                for a, b in zip(face, face[1:] + face[:1]):
                    ef.setdefault(_key(a, b), []).append(fi)
            self._edge_faces = ef
        return self._edge_faces

    def crease_indices(self) -> list[int]:
        return [i for i, a in enumerate(self.assignments) if a in FOLDED_ASSIGNMENTS]

    def num_creases(self) -> int:
        return len(self.crease_indices())

    def segments(self, include_border: bool = False) -> list[Segment]:
        out = []
        for (u, v), a in zip(self.edges, self.assignments):
            if a == "B" and not include_border:
                continue
            p, q = self.vertices[u], self.vertices[v]
            out.append(((float(p[0]), float(p[1])), (float(q[0]), float(q[1])), a))
        return out

    # ------------------------------------------------------------------ FOLD io
    def to_fold(self, precision: int = 8, **meta) -> dict:
        d = {
            "file_spec": 1.1,
            "file_creator": "origami-bench",
            "frame_classes": ["creasePattern"],
            "frame_attributes": ["2D"],
            "vertices_coords": [[round(float(x), precision), round(float(y), precision)]
                                for x, y in self.vertices],
            "edges_vertices": [[int(u), int(v)] for u, v in self.edges],
            "edges_assignment": list(self.assignments),
            "faces_vertices": [[int(v) for v in f] for f in self.faces],
        }
        d.update(meta)
        return d

    @classmethod
    def from_fold(cls, d: dict | str | Path, rebuild: bool = True) -> "CreasePattern":
        """Load a FOLD dict/file.

        With ``rebuild`` (default) the edges are re-run through the planar
        arrangement, which tolerates sloppy input (crossing edges, missing
        border, duplicate vertices). Without it the graph is trusted as-is.
        """
        if not isinstance(d, dict):
            d = json.loads(Path(d).read_text())
        try:
            coords = d["vertices_coords"]
            ev = d["edges_vertices"]
        except KeyError as e:
            raise CPError(f"FOLD object missing {e}") from None
        asg = d.get("edges_assignment") or ["U"] * len(ev)
        if len(asg) != len(ev):
            raise CPError("edges_assignment length does not match edges_vertices")
        if rebuild:
            segs = []
            for (u, v), a in zip(ev, asg):
                p, q = coords[u], coords[v]
                segs.append(((p[0], p[1]), (q[0], q[1]), a))
            return cls.from_segments(segs)
        faces = d.get("faces_vertices") or []
        return cls(np.array(coords, dtype=float)[:, :2],
                   [tuple(e) for e in ev], [_norm_assignment(a) for a in asg], faces)

    @classmethod
    def from_segments(cls, segments: Iterable[Sequence], tol: float = 1e-7,
                      add_border: bool = True) -> "CreasePattern":
        """Build a crease pattern from loose line segments.

        Each segment is ``((x1, y1), (x2, y2), assignment)`` or
        ``[x1, y1, x2, y2, assignment]``. Segments are clipped to the unit
        square, split at all intersections and merged; dangling creases that end
        in the interior of the paper are pruned with a warning.
        """
        segs, warnings = _normalize_segments(segments)
        if add_border:
            corners = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
            for i in range(4):
                segs.append((corners[i], corners[(i + 1) % 4], "B"))
        verts, edges, asg, w2 = _arrangement(segs, tol)
        warnings += w2
        verts, edges, asg, w3 = _prune_dangling(verts, edges, asg)
        warnings += w3
        cp = cls(verts, edges, asg)
        cp.warnings = warnings
        return cp

    def save(self, path: str | Path, **meta) -> None:
        Path(path).write_text(json.dumps(self.to_fold(**meta)))


# ---------------------------------------------------------------------- helpers
def _key(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def _norm_assignment(a: str) -> str:
    a = str(a).strip().upper()[:1]
    if a not in VALID_ASSIGNMENTS:
        raise CPError(f"unknown edge assignment {a!r}")
    return a


def _normalize_segments(segments: Iterable[Sequence]) -> tuple[list[Segment], list[str]]:
    out: list[Segment] = []
    warnings: list[str] = []
    for s in segments:
        if isinstance(s, dict):
            p, q, a = s["p"], s["q"], s.get("assignment", "U")
        elif len(s) == 3:
            p, q, a = s
        elif len(s) == 5:
            p, q, a = (s[0], s[1]), (s[2], s[3]), s[4]
        else:
            raise CPError(f"cannot parse segment {s!r}")
        a = _norm_assignment(a)
        if a in ("B", "F"):
            continue  # border is added explicitly; flat edges are not creases
        p = (float(p[0]), float(p[1]))
        q = (float(q[0]), float(q[1]))
        if not all(map(math.isfinite, p + q)):
            raise CPError("non-finite coordinate")
        clipped = _clip_unit_square(p, q)
        if clipped is None:
            warnings.append(f"segment {p}-{q} lies outside the paper; ignored")
            continue
        p2, q2 = clipped
        if math.dist(p2, q2) < 1e-9:
            continue
        out.append((p2, q2, a))
    return out, warnings


def _clip_unit_square(p, q):
    """Liang-Barsky clip of segment pq to [0,1]^2."""
    x0, y0 = p
    dx, dy = q[0] - x0, q[1] - y0
    t0, t1 = 0.0, 1.0
    for pk, qk in ((-dx, x0), (dx, 1 - x0), (-dy, y0), (dy, 1 - y0)):
        if abs(pk) < 1e-15:
            if qk < -1e-12:
                return None
        else:
            r = qk / pk
            if pk < 0:
                t0 = max(t0, r)
            else:
                t1 = min(t1, r)
    if t0 > t1:
        return None
    return ((x0 + t0 * dx, y0 + t0 * dy), (x0 + t1 * dx, y0 + t1 * dy))


class _VertexPool:
    def __init__(self, tol: float):
        self.tol = tol
        self.pts: list[tuple[float, float]] = []
        self.grid: dict[tuple[int, int], list[int]] = {}

    def add(self, p) -> int:
        x, y = float(p[0]), float(p[1])
        # snap near-boundary values exactly onto the boundary
        x = 0.0 if abs(x) < self.tol else 1.0 if abs(x - 1) < self.tol else x
        y = 0.0 if abs(y) < self.tol else 1.0 if abs(y - 1) < self.tol else y
        cx, cy = int(math.floor(x / self.tol)), int(math.floor(y / self.tol))
        for i in range(cx - 1, cx + 2):
            for j in range(cy - 1, cy + 2):
                for idx in self.grid.get((i, j), ()):
                    q = self.pts[idx]
                    if abs(q[0] - x) <= self.tol and abs(q[1] - y) <= self.tol:
                        return idx
        self.pts.append((x, y))
        self.grid.setdefault((cx, cy), []).append(len(self.pts) - 1)
        return len(self.pts) - 1


def _arrangement(segs: list[Segment], tol: float):
    n = len(segs)
    P = np.array([s[0] for s in segs], dtype=float)
    Q = np.array([s[1] for s in segs], dtype=float)
    D = Q - P
    L2 = np.einsum("ij,ij->i", D, D)
    params: list[list[float]] = [[0.0, 1.0] for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            d1, d2 = D[i], D[j]
            denom = d1[0] * d2[1] - d1[1] * d2[0]
            r = P[j] - P[i]
            if abs(denom) > 1e-12 * math.sqrt(L2[i] * L2[j]):
                t = (r[0] * d2[1] - r[1] * d2[0]) / denom
                u = (r[0] * d1[1] - r[1] * d1[0]) / denom
                ti, tj = tol / math.sqrt(L2[i]), tol / math.sqrt(L2[j])
                if -ti <= t <= 1 + ti and -tj <= u <= 1 + tj:
                    params[i].append(min(max(t, 0.0), 1.0))
                    params[j].append(min(max(u, 0.0), 1.0))
            else:
                # parallel: if collinear, project endpoints onto each other
                cross = abs(r[0] * d1[1] - r[1] * d1[0]) / math.sqrt(L2[i])
                if cross > tol:
                    continue
                for a, b in ((i, j), (j, i)):
                    for pt in (P[b], Q[b]):
                        t = float(np.dot(pt - P[a], D[a]) / L2[a])
                        if -1e-12 < t < 1 + 1e-12:
                            params[a].append(min(max(t, 0.0), 1.0))
    pool = _VertexPool(tol)
    edge_map: dict[tuple[int, int], str] = {}
    warnings: list[str] = []
    priority = {"B": 3, "M": 2, "V": 2, "U": 1}
    for i, (p, q, a) in enumerate(segs):
        ts = sorted(set(params[i]))
        ids = [pool.add(P[i] + t * D[i]) for t in ts]
        for u, v in zip(ids, ids[1:]):
            if u == v:
                continue
            k = _key(u, v)
            old = edge_map.get(k)
            if old is None or priority[a] > priority[old]:
                edge_map[k] = a
            elif old != a and priority[a] == priority[old]:
                warnings.append(f"conflicting assignments {old}/{a} on overlapping creases; kept {old}")
    verts = np.array(pool.pts, dtype=float)
    edges = list(edge_map.keys())
    asg = [edge_map[e] for e in edges]
    return verts, edges, asg, warnings


def _prune_dangling(verts, edges, asg):
    warnings = []
    edges = list(edges)
    asg = list(asg)
    while True:
        deg = np.zeros(len(verts), dtype=int)
        for u, v in edges:
            deg[u] += 1
            deg[v] += 1
        bad = [i for i, (u, v) in enumerate(edges) if deg[u] == 1 or deg[v] == 1]
        if not bad:
            break
        bad_set = set(bad)
        warnings.append(f"pruned {len(bad)} dangling crease edge(s) that end inside the paper")
        edges = [e for i, e in enumerate(edges) if i not in bad_set]
        asg = [a for i, a in enumerate(asg) if i not in bad_set]
    # drop isolated vertices and reindex
    used = sorted({v for e in edges for v in e})
    remap = {old: new for new, old in enumerate(used)}
    verts = verts[used] if used else np.zeros((0, 2))
    edges = [(remap[u], remap[v]) for u, v in edges]
    return verts, edges, asg, warnings


def compute_faces(vertices: np.ndarray, edges: Sequence[tuple[int, int]]) -> list[list[int]]:
    """Extract bounded faces (CCW vertex loops) of a planar straight-line graph."""
    nbrs: dict[int, list[int]] = {}
    for u, v in edges:
        nbrs.setdefault(u, []).append(v)
        nbrs.setdefault(v, []).append(u)
    order: dict[int, list[int]] = {}
    pos: dict[int, dict[int, int]] = {}
    for v, ns in nbrs.items():
        ang = [math.atan2(vertices[w][1] - vertices[v][1], vertices[w][0] - vertices[v][0]) for w in ns]
        srt = [w for _, w in sorted(zip(ang, ns))]
        order[v] = srt
        pos[v] = {w: i for i, w in enumerate(srt)}
    visited: set[tuple[int, int]] = set()
    faces = []
    for u, v in edges:
        for a, b in ((u, v), (v, u)):
            if (a, b) in visited:
                continue
            loop = []
            x, y = a, b
            while (x, y) not in visited:
                visited.add((x, y))
                loop.append(x)
                ring = order[y]
                k = pos[y][x]
                x, y = y, ring[(k - 1) % len(ring)]
            if _signed_area(vertices, loop) > 1e-14:
                faces.append(loop)
    return faces


def _signed_area(vertices, loop) -> float:
    pts = vertices[loop]
    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def face_area(cp: CreasePattern, fi: int) -> float:
    return _signed_area(cp.vertices, cp.faces[fi])


def is_boundary_vertex(p, tol: float = 1e-9) -> bool:
    x, y = p
    return abs(x) < tol or abs(y) < tol or abs(x - 1) < tol or abs(y - 1) < tol
