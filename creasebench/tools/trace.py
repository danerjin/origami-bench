"""Trace a box-pleated crease pattern from a raster image (red = mountain, blue = valley).

The paper square is located from its dark border, then every unit step between lattice points of an
N x N lattice in the box-pleating directions (0, 45, 90, 135 degrees) is classified by sampling the
pixels along it. Steps are merged into segments and returned in unit-square coordinates (y up).
The trace is only as good as the image: check it with ``check_local`` and fix what it reports.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

DIRS = [(1, 0), (0, 1), (1, 1), (1, -1)]


def load(path):
    a = np.asarray(Image.open(path).convert("RGB")).astype(int)
    dark = a.sum(2) < 200
    rows = np.where(dark.sum(1) > 0.5 * a.shape[1])[0]
    cols = np.where(dark.sum(0) > 0.5 * a.shape[0])[0]
    return a, (int(cols.min()), int(rows.min()), int(cols.max()), int(rows.max()))


def classify(a, p, q, samples=9, margin=0.2):
    """'M', 'V' or None for the straight pixel path p -> q (pixel coords)."""
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    red = blue = 0
    for t in np.linspace(margin, 1 - margin, samples):
        x, y = p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])
        xi, yi = int(round(x)), int(round(y))
        win_r = win_b = 0
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                R, G, B = r[yi + dy, xi + dx], g[yi + dy, xi + dx], b[yi + dy, xi + dx]
                if min(R, G, B) > 205:
                    continue  # paper or a pale grid line
                if R - B > 22 and R - G > 15:
                    win_r = 1
                if B - R > 22:
                    win_b = 1
        red += win_r
        blue += win_b
    if red >= samples - 1 and red > blue:
        return "M"
    if blue >= samples - 1 and blue > red:
        return "V"
    return None


def trace(path, n: int, samples: int = 9):
    a, (x0, y0, x1, y1) = load(path)
    sx, sy = (x1 - x0) / n, (y1 - y0) / n

    def px(i, j):  # lattice (i, j) with j counted from the bottom
        return (x0 + i * sx, y1 - j * sy)

    steps = []
    for i in range(n + 1):
        for j in range(n + 1):
            for di, dj in DIRS:
                i2, j2 = i + di, j + dj
                if not (0 <= i2 <= n and 0 <= j2 <= n):
                    continue
                if (di, dj) in ((1, 0), (0, 1)) and ((j in (0, n) and dj == 0) or (i in (0, n) and di == 0)):
                    continue  # on the paper border
                k = classify(a, px(i, j), px(i2, j2), samples)
                if k:
                    steps.append(((i, j), (i2, j2), k))
    return steps


def merge(steps, n):
    """Merge collinear unit steps of the same kind into maximal segments (unit-square coords)."""
    from collections import defaultdict

    by = defaultdict(set)
    for p, q, k in steps:
        d = (q[0] - p[0], q[1] - p[1])
        by[(d, k)].add(p)
    segs = []
    for (d, k), starts in by.items():
        for p in sorted(starts):
            prev = (p[0] - d[0], p[1] - d[1])
            if prev in starts:
                continue
            q = p
            while q in starts:
                q = (q[0] + d[0], q[1] + d[1])
            segs.append([p[0] / n, p[1] / n, q[0] / n, q[1] / n, k])
    return segs


def _pixel_class(a, x, y):
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    xi, yi = int(round(x)), int(round(y))
    best = None
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            R, G, B = r[yi + dy, xi + dx], g[yi + dy, xi + dx], b[yi + dy, xi + dx]
            if min(R, G, B) > 205:
                continue
            if R - B > 22 and R - G > 15:
                best = "M" if best in (None, "M") else "X"
            elif B - R > 22:
                best = "V" if best in (None, "V") else "X"
    return best


def trace_lines(path, n: int = 96, snap: int = 192, gap_px: float = 4.0, min_px: float = 3.5, perp: float = 3.5):
    """Scan every lattice line (rows, columns, both diagonals through 1/n lattice points) pixel by
    pixel; runs of one colour become segments (gaps up to ``gap_px`` bridged, e.g. where other creases
    cross), with endpoints snapped to the 1/``snap`` lattice."""
    a, (x0, y0, x1, y1) = load(path)
    W, H = x1 - x0, y1 - y0
    px = lambda u, v: (x0 + u * W, y1 - v * H)  # noqa: E731
    lines = []
    for k in range(1, n):
        lines.append(((0.0, k / n), (1.0, k / n)))
        lines.append(((k / n, 0.0), (k / n, 1.0)))
    for k in range(-n + 1, n):  # x - y = k/n  and  x + y = k/n (+1 offset)
        c = k / n
        p, q = (max(0.0, c), max(0.0, -c)), (min(1.0, 1 + c), min(1.0, 1 - c))
        lines.append((p, q))
        c2 = 1 + c
        p2, q2 = (max(0.0, c2 - 1), min(1.0, c2)), (min(1.0, c2), max(0.0, c2 - 1))
        lines.append((p2, q2))
    segs = []
    for p, q in lines:
        P, Q = px(*p), px(*q)
        L = float(np.hypot(Q[0] - P[0], Q[1] - P[1]))
        if L < 2:
            continue
        m = int(L)
        cls = []
        for i in range(m + 1):
            t = i / m
            x, y = P[0] + t * (Q[0] - P[0]), P[1] + t * (Q[1] - P[1])
            if not (2 <= x < a.shape[1] - 2 and 2 <= y < a.shape[0] - 2):
                cls.append(None)
                continue
            c = _pixel_class(a, x, y)
            if c in ("M", "V"):
                # a stroke running along this line is thin across it; a crossing stroke is not
                nx_, ny_ = -(Q[1] - P[1]) / L, (Q[0] - P[0]) / L
                side = [_pixel_class(a, x + s * perp * nx_, y + s * perp * ny_) for s in (-1, 1)]
                if all(sc == c for sc in side):
                    c = "X"
            cls.append(c)
        # bridge short gaps (crossings, antialiasing) between runs of the same colour
        runs = []
        i = 0
        while i <= m:
            c = cls[i]
            if c in ("M", "V"):
                j = i
                while j + 1 <= m and cls[j + 1] in (c, "X"):
                    j += 1
                runs.append([i, j, c])
                i = j + 1
            else:
                i += 1
        merged = []
        for r in runs:
            if merged and merged[-1][2] == r[2] and (r[0] - merged[-1][1]) * (L / m) <= gap_px:
                merged[-1][1] = r[1]
            else:
                merged.append(r)
        for i0, i1, c in merged:
            if (i1 - i0) * (L / m) < min_px:
                continue
            t0, t1 = i0 / m, i1 / m
            u0 = [p[0] + t0 * (q[0] - p[0]), p[1] + t0 * (q[1] - p[1])]
            u1 = [p[0] + t1 * (q[0] - p[0]), p[1] + t1 * (q[1] - p[1])]
            s = lambda v: round(v * snap) / snap  # noqa: E731
            u0, u1 = [s(v) for v in u0], [s(v) for v in u1]
            if u0 != u1:
                segs.append([u0[0], u0[1], u1[0], u1[1], c])
    return segs


def refine(path, segs, rounds: int = 2, perp: float = 3.0, keep: float = 0.7):
    """Planarize an over-complete trace, then re-classify every edge from the pixels in its middle 60%
    (a stroke must run along the edge and be thin across it). Edges without enough colour are dropped,
    dangling edges are pruned by the planarizer, and the whole thing is repeated."""
    from ..cp import CreasePattern

    a, (x0, y0, x1, y1) = load(path)
    W, H = x1 - x0, y1 - y0
    px = lambda u: (x0 + u[0] * W, y1 - u[1] * H)  # noqa: E731
    cp = CreasePattern.from_segments(segs, tol=1e-9)
    for _ in range(rounds):
        out = []
        for (u, v), asg in zip(cp.edges, cp.assignments):
            if asg == "B":
                continue
            P, Q = px(cp.vertices[u]), px(cp.vertices[v])
            L = float(np.hypot(Q[0] - P[0], Q[1] - P[1]))
            nx_, ny_ = -(Q[1] - P[1]) / L, (Q[0] - P[0]) / L
            votes = {"M": 0, "V": 0}
            m = max(3, int(0.6 * L))
            for t in np.linspace(0.2, 0.8, m):
                x, y = P[0] + t * (Q[0] - P[0]), P[1] + t * (Q[1] - P[1])
                c = _pixel_class(a, x, y)
                if c in votes:
                    side = [_pixel_class(a, x + s * perp * nx_, y + s * perp * ny_) for s in (-1, 1)]
                    if not all(sc == c for sc in side):
                        votes[c] += 1
            k = max(votes, key=votes.get)
            if votes[k] >= keep * m:
                p, q = cp.vertices[u], cp.vertices[v]
                out.append([float(p[0]), float(p[1]), float(q[0]), float(q[1]), k])
        cp = CreasePattern.from_segments(out, tol=1e-9)
    return cp


def edge_evidence(a, box, p, q, perp: float = 3.0):
    """(fraction of red, fraction of blue) of pixels in the middle 60% of p -> q (unit coords)."""
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    P = (x0 + p[0] * W, y1 - p[1] * H)
    Q = (x0 + q[0] * W, y1 - q[1] * H)
    L = float(np.hypot(Q[0] - P[0], Q[1] - P[1]))
    m = max(3, int(0.6 * L))
    nx_, ny_ = -(Q[1] - P[1]) / L, (Q[0] - P[0]) / L
    votes = {"M": 0, "V": 0}
    for t in np.linspace(0.2, 0.8, m):
        x, y = P[0] + t * (Q[0] - P[0]), P[1] + t * (Q[1] - P[1])
        c = _pixel_class(a, x, y)
        if c in votes:
            side = [_pixel_class(a, x + s * perp * nx_, y + s * perp * ny_) for s in (-1, 1)]
            if not all(sc == c for sc in side):
                votes[c] += 1
    return votes["M"] / m, votes["V"] / m


def repair(path, cp, snap: int = 192, max_len: int = 6, min_ev: float = 0.35, rounds: int = 6, log=print):
    """Use local flat-foldability to complete a trace: at every vertex failing the local checks, try
    adding one lattice edge (box-pleating directions, 1..max_len lattice steps, ending on an existing
    vertex or the border) with pixel evidence >= ``min_ev``; keep the best-evidence addition that makes
    the vertex pass. Then fix Maekawa failures by flipping the edge with the weakest colour evidence."""
    from ..cp import CreasePattern
    from ..foldability import check_local

    a, box = load(path)
    dirs = [(1, 0), (0, 1), (1, 1), (1, -1), (-1, 0), (0, -1), (-1, -1), (-1, 1)]
    for r in range(rounds):
        rep = check_local(cp)
        bad = sorted(rep.bad_vertices())
        log(f"repair round {r}: {cp.num_creases()} creases, {len(bad)} bad vertices")
        if not bad:
            break
        verts = {tuple(np.round(v * snap).astype(int)): i for i, v in enumerate(cp.vertices)}
        segs = [[*p, *q, k] for p, q, k in cp.segments()]
        added = 0
        for vi in bad:
            p = np.round(cp.vertices[vi] * snap).astype(int)
            best = None
            for d in dirs:
                for s in range(1, max_len + 1):
                    q = p + np.array(d) * s
                    if not ((0 <= q).all() and (q <= snap).all()):
                        break
                    on_border = q[0] in (0, snap) or q[1] in (0, snap)
                    if tuple(q) not in verts and not on_border:
                        continue
                    ev_m, ev_v = edge_evidence(a, box, p / snap, q / snap)
                    ev = max(ev_m, ev_v)
                    if ev >= min_ev and (best is None or ev > best[0]):
                        best = (ev, q, "M" if ev_m >= ev_v else "V")
                    break  # first vertex in this direction only
            if best is not None:
                ev, q, k = best
                seg = [float(p[0] / snap), float(p[1] / snap), float(q[0] / snap), float(q[1] / snap), k]
                segs.append(seg)
                added += 1
        new = CreasePattern.from_segments(segs, tol=1e-9)
        if len(check_local(new).bad_vertices()) >= len(bad):
            log("  no improvement; stopping")
            break
        cp = new
    return cp
