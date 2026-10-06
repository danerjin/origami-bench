"""Crease completion for BP Studio output: add the missing elevation pleats.

BP Studio exports hinges (flap/river contours), ridges and gadget
axis-parallels, but not the pleats that make every flap and river collapse.
In a box-pleated uniaxial base the paper carries a piecewise-linear
*elevation* function whose gradient is parallel to the hinges.
Ridges are where the gradient turns, and the missing pleats are its integer
level sets. The level sets are
  * axis-aligned grid lines in ordinary BP regions, and
  * lines parallel to the gadget's axis-parallels inside a stretch, at the
    same phase and unit spacing.

Algorithm (exact rational arithmetic throughout):

1. Planarize BP Studio's lines.
2. Excess paper and river corners (faces that see hinges in two directions):
   cast the bisector "corner ridge" from every hinge corner of such a face, a
   straight-skeleton step (``_split_excess``).
3. Extract the faces. For every face, choose a *family* of level lines:
   - if the face is bounded by gadget axis-parallels, use their direction
     (Pythagorean directions get exact unit spacing at the gadget's phase);
   - otherwise use the direction perpendicular to the face's hinges, or to its
     border edges when the face has no hinge (a flap square clipped by the
     sheet);
   - faces that are still ambiguous get these candidates: a full orthogonal
     grid, each axis family, then nothing.
4. Clip each chosen family to its face. This is the COrigami F.1 idea
   ("keep grid segments perpendicular to an intersecting hinge"), applied
   face by face.
5. Local search: re-pick the families of ambiguous faces to minimise the
   number of interior vertices that violate even degree or Kawasaki. Then,
   inside full-grid faces, greedily add 45-degree ridges from the vertices
   that still violate.
6. Prune pleats that end in the interior of the paper.

The result is a list of ``[x1, y1, x2, y2, kind]`` segments in grid units,
where kind is one of border, hinge, ridge, axis-parallel or pleat.
"""

from __future__ import annotations

import math
from fractions import Fraction
from itertools import combinations, product
from math import gcd, isqrt

__all__ = ["complete_pleats"]

Pt = tuple[Fraction, Fraction]
GRID = "grid"  # pseudo-family: both axis-aligned families
VORONOI = "voronoi"  # pseudo-family: nearest-hinge partition of an excess face


def _fr(x) -> Fraction:
    return Fraction(x).limit_denominator(10**4)


# ---------------------------------------------------------------- planarize
def _planarize(segs):
    """segs: [(p, q, kind)] with Fraction points -> set of (a, b, kind) elementary edges."""
    cuts = [{s[0], s[1]} for s in segs]

    def on(pt, p, d):
        if (pt[0] - p[0]) * d[1] - (pt[1] - p[1]) * d[0] != 0:
            return False
        t = ((pt[0] - p[0]) * d[0] + (pt[1] - p[1]) * d[1]) / (d[0] ** 2 + d[1] ** 2)
        return 0 < t < 1

    # bucket by bounding boxes to avoid hopeless pairs
    boxes = [(min(p[0], q[0]), max(p[0], q[0]), min(p[1], q[1]), max(p[1], q[1])) for p, q, _ in segs]
    order = sorted(range(len(segs)), key=lambda i: boxes[i][0])
    for ii, i in enumerate(order):
        bi = boxes[i]
        for j in order[ii + 1:]:
            bj = boxes[j]
            if bj[0] > bi[1]:
                break
            if bj[3] < bi[2] or bj[2] > bi[3]:
                continue
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
    prio = {"border": 0, "hinge": 1, "ridge": 2, "axis-parallel": 3, "pleat": 4, "other": 5}
    edges: dict[tuple[Pt, Pt], str] = {}
    for (p, q, k), pts in zip(segs, cuts):
        d = (q[0] - p[0], q[1] - p[1])
        o = sorted(pts, key=lambda z: (z[0] - p[0]) * d[0] + (z[1] - p[1]) * d[1])
        for a, b in zip(o, o[1:]):
            if a == b:
                continue
            key = (min(a, b), max(a, b))
            old = edges.get(key)
            if old is None or prio.get(k, 9) < prio.get(old, 9):
                edges[key] = k
    return edges


def _add_segment(edges, seg):
    """Insert one segment into an already planar edge dict (returns a new dict)."""
    p, q, kind = seg
    d = (q[0] - p[0], q[1] - p[1])
    lo_x, hi_x = min(p[0], q[0]), max(p[0], q[0])
    lo_y, hi_y = min(p[1], q[1]), max(p[1], q[1])
    out = dict(edges)
    cuts = {p, q}
    for (a, b), k in edges.items():
        if max(a[0], b[0]) < lo_x or min(a[0], b[0]) > hi_x or max(a[1], b[1]) < lo_y or min(a[1], b[1]) > hi_y:
            continue
        e = (b[0] - a[0], b[1] - a[1])
        den = d[0] * e[1] - d[1] * e[0]
        if den == 0:
            continue  # collinear overlaps are not expected for inserted diagonals
        w = (a[0] - p[0], a[1] - p[1])
        t = (w[0] * e[1] - w[1] * e[0]) / den
        u = (w[0] * d[1] - w[1] * d[0]) / den
        if 0 <= t <= 1 and 0 <= u <= 1:
            x = (p[0] + t * d[0], p[1] + t * d[1])
            cuts.add(x)
            if x != a and x != b:
                del out[(a, b)]
                out[(min(a, x), max(a, x))] = k
                out[(min(x, b), max(x, b))] = k
    o = sorted(cuts, key=lambda z: (z[0] - p[0]) * d[0] + (z[1] - p[1]) * d[1])
    for a, b in zip(o, o[1:]):
        if a != b:
            out.setdefault((min(a, b), max(a, b)), kind)
    return out


def _faces(edges):
    """Bounded faces of a planar straight-line graph: list of (vertex loop, [edge kinds])."""
    out: dict[Pt, list[Pt]] = {}
    for a, b in edges:
        out.setdefault(a, []).append(b)
        out.setdefault(b, []).append(a)
    for v, nb in out.items():
        nb.sort(key=lambda w: math.atan2(float(w[1] - v[1]), float(w[0] - v[0])))
    pos = {v: {w: i for i, w in enumerate(nb)} for v, nb in out.items()}
    seen = set()
    faces = []
    for a in out:
        for b in out[a]:
            if (a, b) in seen:
                continue
            loop = []
            u, v = a, b
            while (u, v) not in seen:
                seen.add((u, v))
                loop.append(u)
                nb = out[v]
                i = pos[v][u]
                w = nb[(i - 1) % len(nb)]  # next edge clockwise -> walks the face on the left
                u, v = v, w
            area = sum(loop[i][0] * loop[(i + 1) % len(loop)][1] - loop[(i + 1) % len(loop)][0] * loop[i][1]
                       for i in range(len(loop)))
            if area > 0:
                faces.append(loop)
    return faces


# ---------------------------------------------------------------- families
def _prim(dx: Fraction, dy: Fraction) -> tuple[int, int]:
    """Primitive integer vector parallel to (dx, dy), canonical sign."""
    den = math.lcm(dx.denominator, dy.denominator)
    a, b = int(dx * den), int(dy * den)
    g = gcd(a, b)
    a, b = a // g, b // g
    if a < 0 or (a == 0 and b < 0):
        a, b = -a, -b
    return a, b


class _Family:
    """Level lines n.p = c0 + k*L (n primitive integer normal, L = |n| when rational)."""

    def __init__(self, n, offsets=None, phase=None, spacing=None):
        self.n = n
        self.offsets = set(offsets or ())
        self.phase = phase
        self.spacing = spacing

    def values(self, lo: Fraction, hi: Fraction):
        """Offsets c with lo < c < hi."""
        vals = {c for c in self.offsets if lo < c < hi}
        if self.spacing:
            k0 = math.ceil((lo - self.phase) / self.spacing)
            c = self.phase + k0 * self.spacing
            while c < hi:
                if c > lo:
                    vals.add(c)
                c += self.spacing
        return sorted(vals)

    def key(self):
        return self.n


def _build_families(lines):
    """Families from gadget axis-parallels, keyed by normal, plus the two axis families."""
    fams: dict[tuple[int, int], _Family] = {
        (1, 0): _Family((1, 0), phase=Fraction(0), spacing=Fraction(1)),
        (0, 1): _Family((0, 1), phase=Fraction(0), spacing=Fraction(1)),
    }
    for p, q, k in lines:
        if k != "axis-parallel":
            continue
        d = _prim(q[0] - p[0], q[1] - p[1])
        n = _prim(Fraction(-d[1]), Fraction(d[0]))
        c = n[0] * p[0] + n[1] * p[1]
        f = fams.get(n)
        if f is None:
            L2 = n[0] ** 2 + n[1] ** 2
            L = isqrt(L2)
            if L * L == L2:  # Pythagorean direction: exact unit spacing
                f = _Family(n, phase=c - L * math.floor(c / L), spacing=Fraction(L))
            else:
                f = _Family(n)
            fams[n] = f
        f.offsets.add(c)
    return fams


def _clip_family(poly, fam: _Family):
    """Segments of the family's lines inside polygon `poly` (list of Fraction points)."""
    a, b = fam.n
    vals = [a * x + b * y for x, y in poly]
    out = []
    m = len(poly)
    for c in fam.values(min(vals), max(vals)):
        # intersections of line a x + b y = c with polygon edges
        hits = []
        for i in range(m):
            p, q = poly[i], poly[(i + 1) % m]
            vp, vq = vals[i], vals[(i + 1) % m]
            if (vp - c) * (vq - c) < 0:
                t = (c - vp) / (vq - vp)
                hits.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
            elif vp == c:
                hits.append(p)
        if len(hits) < 2:
            continue
        d = (-b, a)
        hits = sorted(set(hits), key=lambda z: z[0] * d[0] + z[1] * d[1])
        for s, e in zip(hits, hits[1:]):
            mid = ((s[0] + e[0]) / 2, (s[1] + e[1]) / 2)
            if _inside(mid, poly):
                out.append((s, e, "pleat"))
    return out


def _near(poly, pts) -> bool:
    """True if any point of `pts` lies inside or on the boundary of `poly`."""
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    lo_x, hi_x, lo_y, hi_y = min(xs), max(xs), min(ys), max(ys)
    m = len(poly)
    for v in pts:
        if not (lo_x <= v[0] <= hi_x and lo_y <= v[1] <= hi_y):
            continue
        if _inside(v, poly):
            return True
        for i in range(m):
            (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % m]
            if (x2 - x1) * (v[1] - y1) - (y2 - y1) * (v[0] - x1) == 0 and \
                    min(x1, x2) <= v[0] <= max(x1, x2) and min(y1, y2) <= v[1] <= max(y1, y2):
                return True
    return False


def _inside(pt, poly) -> bool:
    """Strict point-in-polygon (points on the boundary count as outside)."""
    x, y = pt
    inside = False
    m = len(poly)
    for i in range(m):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % m]
        if (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1) == 0 and \
                min(x1, x2) <= x <= max(x1, x2) and min(y1, y2) <= y <= max(y1, y2):
            return False
        if (y1 > y) != (y2 > y):
            xi = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if xi > x:
                inside = not inside
    return inside


# ---------------------------------------------------------------- vertex check
def _violations(edges, W, H, only=None):
    adj: dict[Pt, set[Pt]] = {}
    for (a, b), k in edges.items():
        if k == "border":
            continue
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    bad = []
    for v, nb in adj.items():
        if only is not None and v not in only:
            continue
        if v[0] in (0, W) or v[1] in (0, H):
            continue
        n = len(nb)
        if n % 2:
            bad.append(v)
            continue
        angs = sorted(math.atan2(float(w[1] - v[1]), float(w[0] - v[0])) for w in nb)
        gaps = [(angs[(i + 1) % n] - angs[i]) % (2 * math.pi) for i in range(n)]
        if abs(sum(gaps[0::2]) - math.pi) > 1e-9:
            bad.append(v)
    return bad


def _prune_dangling(edges, W, H):
    """Repeatedly drop pleat edges that end at an interior degree-1 vertex."""
    while True:
        deg: dict[Pt, int] = {}
        for a, b in edges:
            deg[a] = deg.get(a, 0) + 1
            deg[b] = deg.get(b, 0) + 1

        def interior(v):
            return 0 < v[0] < W and 0 < v[1] < H

        drop = [e for e, k in edges.items() if k == "pleat" and
                any(deg[v] == 1 and interior(v) for v in e)]
        if not drop:
            return edges
        for e in drop:
            del edges[e]


# ---------------------------------------------------------------- excess paper
def _voronoi_fill(loop, kinds):
    """Pleats for an axis-aligned excess face from a nearest-hinge (L-inf) partition.

    The face is cut into unit cells, and each cell into four quarter
    triangles. Each triangle takes the pleat family perpendicular to its
    L-inf-nearest hinge of the face. A triangle emits its cell edge when that
    edge is a level line of its family. A half-diagonal between triangles of
    different families becomes a ridge. Returns None if the face is not an
    integer, axis-aligned polygon.
    """
    m = len(loop)
    if any(v[0].denominator != 1 or v[1].denominator != 1 for v in loop):
        return None
    hinges = []
    for i in range(m):
        a, b = loop[i], loop[(i + 1) % m]
        if a[0] != b[0] and a[1] != b[1]:
            return None
        if kinds[i] == "hinge":
            hinges.append((a, b))
    if not hinges:
        return None

    def family(c):
        best = None
        for a, b in hinges:
            if a[1] == b[1]:  # horizontal hinge -> vertical pleats (normal (1,0))
                lo, hi = min(a[0], b[0]), max(a[0], b[0])
                d = max(abs(c[1] - a[1]), lo - c[0], c[0] - hi)
                f = (1, 0)
            else:
                lo, hi = min(a[1], b[1]), max(a[1], b[1])
                d = max(abs(c[0] - a[0]), lo - c[1], c[1] - hi)
                f = (0, 1)
            if best is None or d < best[0]:
                best = (d, f)
        return best[1]

    xs = [int(v[0]) for v in loop]
    ys = [int(v[1]) for v in loop]
    segs = []
    sixth, half = Fraction(1, 6), Fraction(1, 2)
    for i in range(min(xs), max(xs)):
        for j in range(min(ys), max(ys)):
            cen = (i + half, j + half)
            if not _inside(cen, loop):
                continue
            q = {"W": (i + sixth, j + half), "E": (i + 1 - sixth, j + half),
                 "S": (i + half, j + sixth), "N": (i + half, j + 1 - sixth)}
            fam = {k: family(c) for k, c in q.items()}
            F = Fraction
            if fam["W"] == (1, 0):
                segs.append(((F(i), F(j)), (F(i), F(j + 1)), "pleat"))
            if fam["E"] == (1, 0):
                segs.append(((F(i + 1), F(j)), (F(i + 1), F(j + 1)), "pleat"))
            if fam["S"] == (0, 1):
                segs.append(((F(i), F(j)), (F(i + 1), F(j)), "pleat"))
            if fam["N"] == (0, 1):
                segs.append(((F(i), F(j + 1)), (F(i + 1), F(j + 1)), "pleat"))
            corners = {("S", "E"): (i + 1, j), ("E", "N"): (i + 1, j + 1),
                       ("N", "W"): (i, j + 1), ("W", "S"): (i, j)}
            for (t1, t2), cpt in corners.items():
                if fam[t1] != fam[t2]:
                    segs.append((cen, (F(cpt[0]), F(cpt[1])), "ridge"))
    return segs


def _unit_rational(d):
    """d / |d| as Fractions if |d| is rational, else None."""
    a, b = _prim(Fraction(d[0]), Fraction(d[1]))
    L2 = a * a + b * b
    L = isqrt(L2)
    if L * L != L2:
        return None
    s = 1 if (d[0] * a + d[1] * b) > 0 else -1
    return (Fraction(s * a, L), Fraction(s * b, L))


def _split_excess(base, W, H, max_iter=6):
    """Straight-skeleton style split of faces that see hinges in two directions.

    Such faces are typically excess paper outside every contour, or the corner
    of a river. At every vertex where two non-parallel hinge edges of the face
    meet, cast the bisector of the face's interior angle (a 45-degree ridge for
    axis-aligned hinges) until it hits an existing line. This is the corner
    ridge that lets the pleats arriving from one hinge turn into the other
    family. Returns (new base, number of rays added).
    """
    added = 0
    for _ in range(max_iter):
        edges = _planarize(base)
        faces = _faces(edges)
        new = []
        seen_v = set()
        for loop in faces:
            m = len(loop)
            ks = [edges[(min(loop[i], loop[(i + 1) % m]), max(loop[i], loop[(i + 1) % m]))] for i in range(m)]
            hdirs = {_prim(loop[(i + 1) % m][0] - loop[i][0], loop[(i + 1) % m][1] - loop[i][1])
                     for i in range(m) if ks[i] == "hinge"}
            if len(hdirs) < 2 or any(k == "axis-parallel" for k in ks):
                continue
            for i in range(m):
                k_in, k_out = ks[i - 1], ks[i]
                if k_in != "hinge" or k_out != "hinge":
                    continue
                v, a, b = loop[i], loop[i - 1], loop[(i + 1) % m]
                u1 = _unit_rational((a[0] - v[0], a[1] - v[1]))
                u2 = _unit_rational((b[0] - v[0], b[1] - v[1]))
                if u1 is None or u2 is None or u1 == u2 or (u1[0] == -u2[0] and u1[1] == -u2[1]):
                    continue
                d = (u1[0] + u2[0], u1[1] + u2[1])
                # interior angle > 180 (face is left of a->v->b walk): flip the bisector
                cross = (v[0] - a[0]) * (b[1] - v[1]) - (v[1] - a[1]) * (b[0] - v[0])
                if cross < 0:
                    d = (-d[0], -d[1])
                probe = (v[0] + d[0] / 1000, v[1] + d[1] / 1000)
                if not _inside(probe, loop) or (v, d) in seen_v:
                    continue
                seen_v.add((v, d))
                end = _ray_hit(v, d, list(edges.keys()) + [(p, q) for p, q, _ in new])
                if end is not None:
                    new.append((v, end, "ridge"))
        if not new:
            break
        base = base + new
        added += len(new)
    return base, added


def _crossings(p, q, edges):
    """Points strictly between p and q where segment pq meets existing edges, ordered from p."""
    d = (q[0] - p[0], q[1] - p[1])
    pts = set()
    for (a, b) in edges:
        e = (b[0] - a[0], b[1] - a[1])
        den = d[0] * e[1] - d[1] * e[0]
        if den == 0:
            continue
        w = (a[0] - p[0], a[1] - p[1])
        t = (w[0] * e[1] - w[1] * e[0]) / den
        u = (w[0] * d[1] - w[1] * d[0]) / den
        if 0 < t < 1 and 0 <= u <= 1:
            pts.add((t, (p[0] + t * d[0], p[1] + t * d[1])))
    return [pt for _, pt in sorted(pts)]


def _ray_hit(v, d, segs):
    best_t, best_pt = None, None
    for a, b in segs:
        e = (b[0] - a[0], b[1] - a[1])
        den = d[0] * e[1] - d[1] * e[0]
        if den == 0:
            continue
        w = (a[0] - v[0], a[1] - v[1])
        t = (w[0] * e[1] - w[1] * e[0]) / den
        u = (w[0] * d[1] - w[1] * d[0]) / den
        if t > 0 and 0 <= u <= 1 and (best_t is None or t < best_t):
            best_t, best_pt = t, (v[0] + t * d[0], v[1] + t * d[1])
    return best_pt


# ---------------------------------------------------------------- main entry
def complete_pleats(result: dict, max_rounds: int = 6, return_info: bool = False,
                    split_excess: bool | None = None, grid_fallback: bool = True):
    """Add elevation pleats to a BP Studio result (output of ``generate``).

    Returns a list of ``[x1, y1, x2, y2, kind]`` (floats, grid units). With
    ``return_info=True`` it returns ``(segments, info)`` where info has the
    remaining vertex violations and the face/family statistics.

    ``split_excess``: True uses corner-bisector rays (a straight-skeleton step)
    for excess paper; False uses the nearest-hinge Voronoi fill only. The
    default None tries the skeleton first, since it gives fewer creases and
    flat-folder handles it much faster. It falls back to the Voronoi fill if
    local violations remain, and keeps whichever result has fewer.
    """
    if split_excess is None:
        best = None
        for se in (True, False):
            segs, info = _complete_once(result, max_rounds, se, grid_fallback)
            info["strategy"] = "skeleton" if se else "voronoi"
            score = (len(info["violations"]), len(segs))
            if best is None or score < best[0]:
                best = (score, segs, info)
            if not info["violations"]:
                break
        _, segs, info = best
    else:
        segs, info = _complete_once(result, max_rounds, split_excess, grid_fallback)
        info["strategy"] = "skeleton" if split_excess else "voronoi"
    return (segs, info) if return_info else segs


def _complete_once(result: dict, max_rounds: int, split_excess: bool, grid_fallback: bool):
    sheet = result.get("sheet") or {}
    W = _fr(sheet.get("width", result.get("grid")))
    H = _fr(sheet.get("height", result.get("grid")))
    base = []
    for x1, y1, x2, y2, k in result["lines"]:
        p, q = (_fr(x1), _fr(y1)), (_fr(x2), _fr(y2))
        if p != q:
            base.append((p, q, k))
    base, skeleton_rays = (_split_excess(base, W, H) if split_excess else (base, 0))
    base_edges = _planarize(base)
    fams = _build_families(base)
    faces = _faces(base_edges)

    # per-face candidate families
    def kinds_of(loop):
        out = []
        for i in range(len(loop)):
            a, b = loop[i], loop[(i + 1) % len(loop)]
            out.append((a, b, base_edges[(min(a, b), max(a, b))]))
        return out

    face_cands = []
    for loop in faces:
        ks = kinds_of(loop)
        ap = {_prim(b[0] - a[0], b[1] - a[1]) for a, b, k in ks if k == "axis-parallel"}
        hinge_dirs = {_prim(b[0] - a[0], b[1] - a[1]) for a, b, k in ks if k == "hinge"}
        if not hinge_dirs and not ap:
            # A flap square clipped by the sheet: its contour side lies on the border.
            hinge_dirs = {_prim(b[0] - a[0], b[1] - a[1]) for a, b, k in ks if k == "border"}
        cands = []
        if ap:
            for d in ap:
                n = _prim(Fraction(-d[1]), Fraction(d[0]))
                cands.append(n)
        for d in hinge_dirs:
            # level lines perpendicular to a hinge => normal parallel to the hinge
            if d in fams and d not in cands:
                cands.append(d)
        ambiguous = len(cands) != 1
        if ambiguous:
            # Excess paper / corner faces: a full orthogonal grid (every vertex is a
            # right-angle cross) first, then single families, then nothing.
            alts = [VORONOI] + ([GRID] if grid_fallback else []) + [(1, 0), (0, 1)] + [c for c in cands if c not in ((1, 0), (0, 1))]
            cands = alts + [None]
        face_cands.append(cands)

    clipped_cache: dict[tuple[int, object], list] = {}

    def face_segs(fi, n):
        if n is None:
            return []
        if n == GRID:
            return face_segs(fi, (1, 0)) + face_segs(fi, (0, 1))
        if n == VORONOI:
            key = (fi, n)
            if key not in clipped_cache:
                loop = faces[fi]
                ks = [base_edges[(min(loop[i], loop[(i + 1) % len(loop)]), max(loop[i], loop[(i + 1) % len(loop)]))]
                      for i in range(len(loop))]
                clipped_cache[key] = _voronoi_fill(loop, ks) or []
            return clipped_cache[key]
        key = (fi, n)
        if key not in clipped_cache:
            clipped_cache[key] = _clip_family(faces[fi], fams[n])
        return clipped_cache[key]

    choice = [c[0] for c in face_cands]

    def assemble(ch):
        segs = list(base)
        for fi, n in enumerate(ch):
            segs.extend(face_segs(fi, n))
        return _planarize(segs)

    edges = assemble(choice)
    bad = _violations(edges, W, H)
    ambiguous = [fi for fi, c in enumerate(face_cands) if len(c) > 1]

    # Local search over ambiguous faces (coordinate descent, then pairs).
    rounds = 0
    improved = True
    while bad and improved and rounds < max_rounds:
        rounds += 1
        improved = False
        badset = set(bad)
        touch = [fi for fi in ambiguous if _near(faces[fi], badset)]
        for fi in touch:
            best = (len(bad), choice[fi])
            for n in face_cands[fi]:
                if n == choice[fi]:
                    continue
                trial = list(choice)
                trial[fi] = n
                b2 = _violations(assemble(trial), W, H)
                if len(b2) < best[0]:
                    best = (len(b2), n)
            if best[1] != choice[fi]:
                choice[fi] = best[1]
                edges = assemble(choice)
                bad = _violations(edges, W, H)
                improved = True
        if not improved and len(touch) <= 8:
            for f1, f2 in combinations(touch, 2):
                for n1, n2 in product(face_cands[f1], face_cands[f2]):
                    trial = list(choice)
                    trial[f1], trial[f2] = n1, n2
                    b2 = _violations(assemble(trial), W, H)
                    if len(b2) < len(bad):
                        choice, bad = trial, b2
                        edges = assemble(choice)
                        improved = True
                        break
                if improved:
                    break

    # Ray repair: at a vertex that still violates, try a straight crease in one of
    # the 8 compass directions or continuing an incident crease, running to the
    # first hinge/ridge/border line of the BP layout. Keep it greedily if it lowers
    # the violation count. Typical fixes: the 45-degree corner ridge in excess
    # paper, and the midline of a gap between two parallel hinges.
    added_rays = 0
    if bad:
        stops = list(base_edges.keys())
        compass = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
        for _ in range(4 * len(bad) + 4):
            if not bad:
                break
            adj: dict[Pt, set] = {}
            for (a, b) in edges:
                adj.setdefault(a, set()).add(b)
                adj.setdefault(b, set()).add(a)
            best = (len(bad), None)
            for v in bad:
                inc = set()
                for w in adj.get(v, ()):
                    a_, b_ = _prim(w[0] - v[0], w[1] - v[1])
                    dx, dy = w[0] - v[0], w[1] - v[1]
                    sx = 1 if (dx * a_ + dy * b_) > 0 else -1
                    inc.add((sx * a_, sx * b_))
                dirs = list(compass) + [(-a_, -b_) for a_, b_ in inc]
                for d in dict.fromkeys(dirs):
                    if d in inc:
                        continue
                    end = _ray_hit(v, d, stops)
                    if end is None:
                        continue
                    kind = "pleat" if d[0] == 0 or d[1] == 0 else "ridge"
                    # candidate endpoints: every existing vertex/crossing on the way, then the stop
                    ends = _crossings(v, end, edges)[:12] + [end]
                    for e_ in dict.fromkeys(ends):
                        trial = _add_segment(edges, (v, e_, kind))
                        nb = len(_violations(trial, W, H))
                        if nb < best[0]:
                            best = (nb, (v, e_, kind), trial)
            if best[1] is None:
                break
            edges = best[2]
            bad = _violations(edges, W, H)
            added_rays += 1

    edges = _prune_dangling(edges, W, H)
    bad = _violations(edges, W, H)
    segs = [[float(a[0]), float(a[1]), float(b[0]), float(b[1]), k] for (a, b), k in edges.items()]
    info = {
        "faces": len(faces),
        "ambiguous_faces": len(ambiguous),
        "families": [list(n) for n in fams],
        "pleat_edges": sum(1 for k in edges.values() if k == "pleat"),
        "violations": [[float(v[0]), float(v[1])] for v in bad],
        "search_rounds": rounds,
        "repair_rays_added": added_rays,
        "skeleton_rays": skeleton_rays,
    }
    return segs, info
