"""Target trees and the scale factor a folded base achieves for them.

A target tree is the designer's stick figure: edges with relative lengths and
named nodes. A base whose extracted tree is A realizes target T at scale m if
its flap tips can be matched to T's leaves (injectively) so that

    d_A(phi(i), phi(j)) >= m * d_T(i, j)   for every pair of target leaves.

This is Lang's path condition, the necessary and (with bundling/shortening of
flaps) sufficient condition of tree theory. We report the largest such m.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

import networkx as nx

from .tree import BaseTree


@dataclass
class TargetTree:
    graph: nx.Graph  # nodes are names; edges have "length"

    @classmethod
    def from_json(cls, d) -> "TargetTree":
        """Accepts {"edges": [[u, v, len], ...]} or COrigami-style stick figures
        ({"children": [{"start", "end", "length", ...}]}), or a bare edge list."""
        if isinstance(d, dict) and "children" in d and "edges" not in d:
            items = [(c["start"], c["end"], c["length"]) for c in d["children"]]
        else:
            items = d["edges"] if isinstance(d, dict) else d
            items = [(e["start"], e["end"], e["length"]) if isinstance(e, dict) else tuple(e) for e in items]
        g = nx.Graph()
        for u, v, length in items:
            if float(length) <= 0:
                raise ValueError(f"edge {u}-{v} has non-positive length")
            g.add_edge(str(u), str(v), length=float(length))
        if not nx.is_tree(g):
            raise ValueError("target is not a tree")
        return cls(g)

    def to_json(self) -> dict:
        return {"edges": [[u, v, l] for u, v, l in self.graph.edges(data="length")]}

    @property
    def leaves(self) -> list[str]:
        return sorted(n for n in self.graph if self.graph.degree(n) == 1)

    def leaf_distances(self) -> dict[tuple[str, str], float]:
        lv = self.leaves
        out = {}
        for i, a in enumerate(lv):
            d = nx.single_source_dijkstra_path_length(self.graph, a, weight="length")
            for b in lv[i + 1:]:
                out[(a, b)] = d[b]
        return out


@dataclass
class Fit:
    scale: float
    mapping: dict[str, int]  # target leaf -> base leaf (paper vertex id)
    axis_deg: float | None = None


def fit_scale(base: BaseTree, target: TargetTree) -> Fit:
    tl = target.leaves
    bl = base.leaves
    if len(tl) > len(bl) or len(tl) < 2:
        return Fit(0.0, {})
    dt = target.leaf_distances()
    db = base.leaf_distances()

    def dB(a, b):
        return db[(a, b)] if (a, b) in db else db[(b, a)]

    def dT(a, b):
        return dt[(a, b)] if (a, b) in dt else dt[(b, a)]

    # candidate scale values: every ratio d_B / d_T
    cands = sorted({dB(a, b) / dT(i, j) for i, j in itertools.combinations(tl, 2)
                    for a, b in itertools.combinations(bl, 2)})

    def feasible(m: float):
        order = sorted(tl, key=lambda x: -sum(dT(x, y) for y in tl if y != x))
        assign: dict[str, int] = {}
        used: set[int] = set()

        def rec(k):
            if k == len(order):
                return True
            i = order[k]
            for a in bl:
                if a in used:
                    continue
                if all(dB(a, assign[j]) >= m * dT(i, j) - 1e-9 for j in assign):
                    assign[i] = a
                    used.add(a)
                    if rec(k + 1):
                        return True
                    del assign[i]
                    used.discard(a)
            return False

        return dict(assign) if rec(0) else None

    lo, hi = 0, len(cands) - 1
    best = Fit(0.0, {})
    while lo <= hi:
        mid = (lo + hi) // 2
        sol = feasible(cands[mid])
        if sol is not None:
            best = Fit(cands[mid], sol, base.axis_deg)
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def best_fit(trees: list[BaseTree], target: TargetTree) -> Fit:
    best = Fit(0.0, {})
    for t in trees:
        f = fit_scale(t, target)
        if f.scale > best.scale:
            best = f
    return best


def same_tree(a: nx.Graph, b: nx.Graph, rel_tol: float = 0.02, abs_tol: float = 0.01) -> bool:
    """Isomorphism of weighted trees, edge lengths equal within tolerance."""
    return nx.is_isomorphic(
        a, b, edge_match=lambda e1, e2: abs(e1["length"] - e2["length"]) <= max(abs_tol, rel_tol * e2["length"]))
