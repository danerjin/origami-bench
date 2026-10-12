"""Minimal-grid box pleating: the smallest N x N grid on which a tree's flaps can be laid out.

A box-pleated base on an N-grid realizes a tree with integer flap lengths (one grid unit = one
length unit) when the flap tips sit on lattice points with L-infinity distance >= the tree
distance for every pair of leaves (square packing). ``min_packing_grid`` finds the smallest N for
which such a lattice packing exists (exhaustive backtracking, so this N is a proven lower bound for
any lattice-aligned BP layout); ``certified_min_grid`` then tries packings at N, N+1, ... through
BP Studio + pleat completion + the flat-foldability check and returns the first certified CP. That
N is the best *known* grid for the task.
"""

from __future__ import annotations

import itertools
from typing import Iterator

import networkx as nx


def _tree(edges):
    g = nx.Graph()
    for a, b, l in edges:
        g.add_edge(a, b, length=int(l))
    leaves = sorted((n for n in g if g.degree(n) == 1), key=str)
    d = dict(nx.all_pairs_dijkstra_path_length(g, weight="length"))
    return g, leaves, d


def lattice_packings(edges, n: int, limit: int = 200, border_only: bool = False,
                     node_budget: int = 2_000_000) -> Iterator[dict]:
    """Yield up to ``limit`` lattice placements {leaf: (x, y)} on [0, n]^2 (one per symmetry-ish
    class is not guaranteed). Leaves with the longest flaps are placed first."""
    g, leaves, d = _tree(edges)
    flap = {u: next(iter(g.edges(u, data="length")))[2] for u in leaves}
    order = sorted(leaves, key=lambda u: -flap[u])
    pts = [(x, y) for x in range(n + 1) for y in range(n + 1)
           if not border_only or x in (0, n) or y in (0, n)]
    # a flap of length L needs its tip at least L from... nothing (it can sit anywhere); but a tip
    # near the middle wastes paper, so try border points first
    pts.sort(key=lambda p: (min(p[0], p[1], n - p[0], n - p[1]), p))
    out = 0
    nodes = 0
    pos: dict = {}

    def ok(u, p):
        return all(max(abs(p[0] - q[0]), abs(p[1] - q[1])) >= d[u][v] for v, q in pos.items())

    def rec(i):
        nonlocal out, nodes
        nodes += 1
        if out >= limit or nodes > node_budget:
            return
        if i == len(order):
            out += 1
            yield dict(pos)
            return
        u = order[i]
        cand = pts
        if i == 0:  # symmetry: first (longest) flap in the lower-left triangle of the square
            cand = [p for p in pts if p[0] <= n / 2 and p[1] <= p[0]]
        for p in cand:
            if ok(u, p):
                pos[u] = p
                yield from rec(i + 1)
                del pos[u]
                if out >= limit:
                    return

    yield from rec(0)


def min_packing_grid(edges, n_max: int = 64) -> int | None:
    """Smallest n at which the (budgeted) search finds a lattice packing. The search starts at the
    continuous square-packing bound, so smaller grids are not even tried; this is a best-found
    value, not a proof of optimality."""
    from ..packing import packing_bound
    from ..treefit import TargetTree

    _, leaves, d = _tree(edges)
    m = packing_bound(TargetTree.from_json({"edges": [list(e) for e in edges]}), "linf", starts=60)["scale"]
    lo = max(int(1 / m) - 2 if m > 0 else 1, max(d[a][b] for a, b in itertools.combinations(leaves, 2)) // 2, 1)
    for n in range(lo, n_max + 1):
        if next(lattice_packings(edges, n, limit=1, node_budget=150_000), None) is not None:
            return n
    return None


def certified_min_grid(edges, n_max: int = 48, tries_per_grid: int = 40, slack: int = 6, timeout: float = 120.0,
                       log=print):
    """(n_pack, n_ref, cp, layout): the proven packing lower bound, the smallest grid with a certified
    BP Studio crease pattern (searching n_pack .. n_pack + slack), the CP and its flap layout."""
    from .bpstudio import certified_cp

    n_pack = min_packing_grid(edges, n_max)
    if n_pack is None:
        return None
    for n in range(n_pack, min(n_max, n_pack + slack) + 1):
        stages = {}
        for lay in lattice_packings(edges, n, limit=tries_per_grid):
            flaps = [(u, x, y) for u, (x, y) in lay.items()]
            try:
                cp, info = certified_cp(edges, flaps, n, timeout=timeout)
            except Exception as e:  # noqa: BLE001
                stages["exception"] = stages.get("exception", 0) + 1
                continue
            stages[info.get("stage")] = stages.get(info.get("stage"), 0) + 1
            if cp is not None:
                log(f"  n={n}: certified after {sum(stages.values())} layouts")
                return n_pack, n, cp, lay
        log(f"  n={n}: no certified layout ({stages})")
    return n_pack, None, None, None
