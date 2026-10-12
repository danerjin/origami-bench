"""Inject a single subtle defect into a certified crease pattern (for error-finding tasks)."""

from __future__ import annotations

import random

import numpy as np

from ..cp import CreasePattern, is_boundary_vertex
from ..foldability import check_local
from ..verify import verify


def _with_assignments(cp: CreasePattern, asg) -> CreasePattern:
    return CreasePattern(cp.vertices.copy(), list(cp.edges), list(asg), [list(f) for f in cp.faces])


def flip_one(cp: CreasePattern, rng: random.Random) -> tuple[CreasePattern, dict]:
    i = rng.choice(cp.crease_indices())
    asg = list(cp.assignments)
    asg[i] = "M" if asg[i] == "V" else "V"
    out = _with_assignments(cp, asg)
    bad = sorted(check_local(out).bad_vertices())
    return out, {"kind": "flipped_assignment", "edge": int(i), "violation_vertices": bad}


def nudge_vertex(cp: CreasePattern, rng: random.Random, amount: float = 0.01) -> tuple[CreasePattern, dict]:
    interior = [i for i, p in enumerate(cp.vertices) if not is_boundary_vertex(p)]
    v = rng.choice(interior)
    verts = cp.vertices.copy()
    ang = rng.uniform(0, 2 * np.pi)
    verts[v] += amount * np.array([np.cos(ang), np.sin(ang)])
    out = CreasePattern(verts, list(cp.edges), list(cp.assignments), [list(f) for f in cp.faces])
    bad = sorted(check_local(out).bad_vertices())
    return out, {"kind": "moved_vertex", "vertex": int(v), "violation_vertices": bad}


def global_conflict(cp: CreasePattern, rng: random.Random, tries: int = 200) -> tuple[CreasePattern, dict] | None:
    """Reassign a few creases so every vertex still passes the local tests but no valid
    layer order exists."""
    idx = cp.crease_indices()
    for _ in range(tries):
        asg = list(cp.assignments)
        # flip all creases around one random face: keeps Maekawa parity at every vertex
        f = rng.randrange(len(cp.faces))
        face = cp.faces[f]
        eidx = cp.edge_index()
        ring = [eidx[(min(a, b), max(a, b))] for a, b in zip(face, face[1:] + face[:1])]
        ring = [e for e in ring if asg[e] in "MV"]
        if len(ring) < 2:
            continue
        k = rng.randint(2, min(4, len(ring)))
        for e in rng.sample(ring, k):
            asg[e] = "M" if asg[e] == "V" else "V"
        cand = _with_assignments(cp, asg)
        if not check_local(cand).ok:
            continue
        rep = verify(cand, timeout=60)
        if rep.layers is not None and rep.layers.status == "none":
            return cand, {"kind": "global_conflict", "violation_vertices": []}
    return None


def compose_defects(cp: CreasePattern, rng: random.Random, n_flips: int = 3, with_global: bool = True,
                    min_sep: float = 0.08, timeout: float = 300) -> tuple[CreasePattern, dict] | None:
    """Several defects at once (for repair tasks): ``n_flips`` single M/V flips at well-separated
    creases, plus optionally one locally invisible global conflict. Returns the defective pattern
    and the indices of every changed crease (the original assignment is one valid repair)."""
    base = cp
    changed: list[int] = []
    if with_global:
        res = global_conflict(cp, rng)
        if res is None:
            return None
        base, _ = res
        changed = [i for i, (a, b) in enumerate(zip(cp.assignments, base.assignments)) if a != b]
    mids = {i: cp.vertices[list(cp.edges[i])].mean(axis=0) for i in cp.crease_indices()}
    asg = list(base.assignments)
    pool = [i for i in cp.crease_indices() if i not in changed]
    rng.shuffle(pool)
    flips = 0
    for i in pool:
        if flips >= n_flips:
            break
        if all(np.linalg.norm(mids[i] - mids[c]) >= min_sep for c in changed):
            asg[i] = "M" if asg[i] == "V" else "V"
            changed.append(i)
            flips += 1
    out = _with_assignments(cp, asg)
    rep = verify(out, timeout=timeout)
    if rep.foldable:
        return None
    return out, {"kind": "composed", "changed_edges": sorted(int(c) for c in changed), "n_edits": len(changed)}
