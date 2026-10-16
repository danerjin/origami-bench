"""Target trees and the scale factor a folded base achieves for them.

A target tree is the designer's stick figure: edges with relative lengths and
named nodes. A base whose extracted tree is A realizes target T at scale m if
its flap tips can be matched to T's leaves (injectively) so that

    d_A(phi(i), phi(j)) >= m * d_T(i, j)   for every pair of target leaves.

This is Lang's path condition, the necessary and (with bundling/shortening of
flaps) sufficient condition of tree theory. We report the largest such m.
"""

from __future__ import annotations

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


def fit_scale(base: BaseTree, target: TargetTree, node_budget: int = 200_000) -> Fit:
    """Largest m with an injective leaf map satisfying every pairwise path condition.

    Binary search over the finitely many candidate ratios; feasibility by backtracking
    with forward checking (most-constrained target leaf first). The node budget makes
    the search deterministic; exhausting it counts as infeasible (a conservative score).
    """
    import numpy as np

    tl = target.leaves
    bl = base.leaves
    if len(tl) > len(bl) or len(tl) < 2:
        return Fit(0.0, {})
    nt, nb = len(tl), len(bl)
    DT = np.zeros((nt, nt))
    for (a, b), v in target.leaf_distances().items():
        i, j = tl.index(a), tl.index(b)
        DT[i, j] = DT[j, i] = v
    DB = np.zeros((nb, nb))
    for (a, b), v in base.leaf_distances().items():
        i, j = bl.index(a), bl.index(b)
        DB[i, j] = DB[j, i] = v
    iu = np.triu_indices(nt, 1)
    ju = np.triu_indices(nb, 1)
    cands = np.unique(np.round(np.outer(DB[ju], 1.0 / DT[iu]).ravel(), 12))
    # value symmetry: base leaves with identical distances to every other base leaf (the 8 legs of a spider
    # base, short stubs) are interchangeable while unused, so each search node tries one per class. Without
    # this the search spends its budget on k! equivalent orderings and reports a valid design as infeasible.
    cls = list(range(nb))
    for a_ in range(nb):
        for b_ in range(a_):
            if cls[b_] == b_:
                others = [k for k in range(nb) if k not in (a_, b_)]
                if np.allclose(DB[a_, others], DB[b_, others], atol=1e-9):
                    cls[a_] = b_
                    break

    def feasible(m: float):
        # compat[i][j] : (nb x nb) boolean, base pair (a, b) allowed for target pair (i, j)
        ok = DB[None, None, :, :] >= m * DT[:, :, None, None] - 1e-9
        eye = np.eye(nb, dtype=bool)
        domains = [np.ones(nb, bool) for _ in range(nt)]
        assign = [-1] * nt
        nodes = [0]

        def rec(doms, used):
            if nodes[0] > node_budget:
                return False
            free = [i for i in range(nt) if assign[i] < 0]
            if not free:
                return True
            i = min(free, key=lambda k: int((doms[k] & ~used).sum()))
            seen = set()
            for a in np.flatnonzero(doms[i] & ~used):
                if cls[a] in seen:
                    continue
                seen.add(cls[a])
                nodes[0] += 1
                new = list(doms)
                dead = False
                for k in free:
                    if k == i:
                        continue
                    new[k] = doms[k] & ok[i, k, a] & ~eye[a]
                    if not (new[k] & ~used).any():
                        dead = True
                        break
                if dead:
                    continue
                assign[i] = int(a)
                u2 = used.copy()
                u2[a] = True
                if rec(new, u2):
                    return True
                assign[i] = -1
            return False

        if rec(domains, np.zeros(nb, bool)):
            return {tl[i]: bl[assign[i]] for i in range(nt)}
        return None

    lo, hi = 0, len(cands) - 1
    best = Fit(0.0, {})
    while lo <= hi:
        mid = (lo + hi) // 2
        sol = feasible(float(cands[mid]))
        if sol is not None:
            best = Fit(float(cands[mid]), sol, base.axis_deg)
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
