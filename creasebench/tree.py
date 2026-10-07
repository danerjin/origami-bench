"""Extract the stick-figure tree of a flat-folded base.

For a flat-folded state and an axis direction a, let g(p) = <fold(p), a> be the
coordinate along the axis of the folded image of paper point p. g is affine on
every face. The *tree of the base* is the Reeb graph of g on the paper: contract
every connected component of every level set g^-1(t) to a point. Edge lengths are
differences of g. For a uniaxial base folded flat with its flaps along the axis
this is exactly Lang's tree (the "shadow tree"); for any folded state the tree
distance between two points is a lower bound on their distance on the paper,
which is what makes the scale-factor score of ``treefit.py`` sound.

The paper is a disk, so the Reeb graph is a tree (the contour tree). It is
computed with the join/split-tree algorithm of Carr, Snoeyink & Axen (2003) on a
triangulation of the crease pattern.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import networkx as nx
import numpy as np

from .simulate import FoldedState

MIN_EDGE = 1e-6


@dataclass
class BaseTree:
    graph: nx.Graph  # nodes: paper vertex ids; attrs: g, folded (x, y); edges: length
    axis_deg: float  # axis direction in the folded frame, degrees in [0, 180)

    @property
    def leaves(self) -> list[int]:
        return sorted(n for n in self.graph if self.graph.degree(n) == 1)

    def leaf_distances(self) -> dict[tuple[int, int], float]:
        lv = self.leaves
        dist = {}
        for i, a in enumerate(lv):
            d = nx.single_source_dijkstra_path_length(self.graph, a, weight="length")
            for b in lv[i + 1:]:
                dist[(a, b)] = d[b]
        return dist

    def total_length(self) -> float:
        return float(sum(l for _, _, l in self.graph.edges(data="length")))

    def to_json(self) -> dict:
        return {
            "axis_deg": round(self.axis_deg, 4),
            "nodes": [{"id": int(n), "leaf": self.graph.degree(n) == 1,
                       "folded": [round(float(c), 6) for c in self.graph.nodes[n]["folded"]]}
                      for n in sorted(self.graph)],
            "edges": [[int(u), int(v), round(float(l), 6)] for u, v, l in self.graph.edges(data="length")],
        }


# ----------------------------------------------------------------------------- triangulation
def _ear_clip(poly: list[int], pts: np.ndarray) -> list[tuple[int, int, int]]:
    """Triangulate a simple CCW polygon given as vertex ids (collinear vertices allowed)."""
    idx = list(poly)
    tris = []

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    guard = 0
    while len(idx) > 3 and guard < 10 * len(poly) ** 2:
        guard += 1
        n = len(idx)
        for k in range(n):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % n]
            a, b, c = pts[i0], pts[i1], pts[i2]
            if cross(a, b, c) <= 1e-14:
                continue  # reflex or collinear: not an ear
            inside = False
            for j in idx:
                if j in (i0, i1, i2):
                    continue
                p = pts[j]
                if cross(a, b, p) >= -1e-14 and cross(b, c, p) >= -1e-14 and cross(c, a, p) >= -1e-14:
                    inside = True
                    break
            if inside:
                continue
            tris.append((i0, i1, i2))
            del idx[k]
            break
        else:
            # only collinear runs left: drop a collinear middle vertex
            for k in range(len(idx)):
                if abs(cross(pts[idx[k - 1]], pts[idx[k]], pts[idx[(k + 1) % len(idx)]])) <= 1e-14:
                    del idx[k]
                    break
            else:
                break
    if len(idx) == 3:
        tris.append(tuple(idx))
    return tris


def _mesh_edges(folded: FoldedState) -> set[tuple[int, int]]:
    cp = folded.cp
    edges = set()
    for face in cp.faces:
        for a, b, c in _ear_clip(face, cp.vertices):
            for u, v in ((a, b), (b, c), (c, a)):
                edges.add((min(u, v), max(u, v)))
    return edges


# ----------------------------------------------------------------------------- contour tree
def _contour_tree(n: int, value: np.ndarray, edges: set[tuple[int, int]]) -> list[tuple[int, int]]:
    order = sorted(range(n), key=lambda v: (value[v], v))
    rank = np.empty(n, int)
    rank[order] = np.arange(n)
    nbrs: list[list[int]] = [[] for _ in range(n)]
    for u, v in edges:
        nbrs[u].append(v)
        nbrs[v].append(u)

    def sweep(seq, lower):
        parent = list(range(n))
        head = list(range(n))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        arcs = []
        done = np.zeros(n, bool)
        for v in seq:
            for u in nbrs[v]:
                if not done[u]:
                    continue
                ru, rv = find(u), find(v)
                if ru != rv:
                    arcs.append((head[ru], v))  # head[ru] is on the "lower" side
                    parent[ru] = rv
            head[find(v)] = v
            done[v] = True
        return arcs

    jt = sweep(order, True)  # arcs (lower, upper)
    st = sweep(order[::-1], False)  # arcs (upper, lower)
    jt_down = [set() for _ in range(n)]
    jt_up = [None] * n
    for lo, hi in jt:
        jt_down[hi].add(lo)
        jt_up[lo] = hi
    st_up = [set() for _ in range(n)]
    st_down = [None] * n
    for hi, lo in st:
        st_up[lo].add(hi)
        st_down[hi] = lo
    alive = set(range(n))
    queue = [v for v in range(n) if (not jt_down[v] and len(st_up[v]) == 1)
             or (not st_up[v] and len(jt_down[v]) == 1)]
    ct = []
    while len(alive) > 1 and queue:
        v = queue.pop()
        if v not in alive:
            continue
        if not jt_down[v] and len(st_up[v]) <= 1 and jt_up[v] is not None:
            u = jt_up[v]  # v is a minimum: it attaches upward in the join tree
        elif not st_up[v] and len(jt_down[v]) <= 1 and st_down[v] is not None:
            u = st_down[v]  # v is a maximum: it attaches downward in the split tree
        else:
            continue
        ct.append((v, u))
        alive.discard(v)
        # remove v from the join tree
        if jt_up[v] is not None:
            p = jt_up[v]
            jt_down[p].discard(v)
            for c in jt_down[v]:
                jt_up[c] = p
                jt_down[p].add(c)
        else:
            for c in jt_down[v]:
                jt_up[c] = None
        # remove v from the split tree
        if st_down[v] is not None:
            p = st_down[v]
            st_up[p].discard(v)
            for c in st_up[v]:
                st_down[c] = p
                st_up[p].add(c)
        else:
            for c in st_up[v]:
                st_down[c] = None
        jt_down[v].clear()
        st_up[v].clear()
        for w in {u, jt_up[u] if jt_up[u] is not None else u, st_down[u] if st_down[u] is not None else u}:
            if w in alive and ((not jt_down[w] and len(st_up[w]) == 1) or (not st_up[w] and len(jt_down[w]) == 1)):
                queue.append(w)
        if u in alive:
            queue.append(u)
    return ct


def _simplify(g: nx.Graph, value: np.ndarray) -> nx.Graph:
    """Merge zero-length edges (ties) and contract degree-2 nodes."""
    for u, v in g.edges:
        g.edges[u, v]["length"] = abs(float(value[u] - value[v]))
    changed = True
    while changed:
        changed = False
        for u, v, l in list(g.edges(data="length")):
            if l < MIN_EDGE and g.has_edge(u, v):
                keep, drop = (u, v) if g.degree(u) != 1 else (v, u)
                for w in list(g.neighbors(drop)):
                    if w != keep and not g.has_edge(keep, w):
                        g.add_edge(keep, w, length=g.edges[drop, w]["length"])
                g.remove_node(drop)
                changed = True
                break
    # Contract degree-2 nodes. Path lengths between leaves are preserved, so tree distances
    # stay lower bounds on paper distances. (A node left as a local extremum after tie merging
    # is contracted too; the merged edge then exceeds the axis extent, which is harmless.)
    for node in list(g.nodes):
        if g.degree(node) == 2:
            a, b = list(g.neighbors(node))
            if g.has_edge(a, b):
                continue
            g.add_edge(a, b, length=g.edges[node, a]["length"] + g.edges[node, b]["length"])
            g.remove_node(node)
    return g


def tree_along(folded: FoldedState, axis_deg: float, edges=None) -> BaseTree:
    cp = folded.cp
    a = np.array([math.cos(math.radians(axis_deg)), math.sin(math.radians(axis_deg))])
    value = folded.vertices @ a
    edges = edges if edges is not None else _mesh_edges(folded)
    ct = _contour_tree(cp.num_vertices, value, edges)
    g = nx.Graph()
    g.add_nodes_from(range(cp.num_vertices))
    g.add_edges_from(ct)
    g = g.subgraph(max(nx.connected_components(g), key=len)).copy()
    g = _simplify(g, value)
    for node in g:
        g.nodes[node]["g"] = float(value[node])
        g.nodes[node]["folded"] = folded.vertices[node].tolist()
    return BaseTree(g, axis_deg % 180.0)


def candidate_axes(folded: FoldedState, max_axes: int = 16) -> list[float]:
    """Axis directions to try: the most common folded crease directions (and their normals)."""
    cp = folded.cp
    weight: dict[float, float] = {}
    for (u, v), asg in zip(cp.edges, cp.assignments):
        if asg not in "MVU":
            continue
        d = folded.vertices[v] - folded.vertices[u]
        L = float(np.hypot(*d))
        if L < 1e-9:
            continue
        ang = round(math.degrees(math.atan2(d[1], d[0])) % 180.0, 1) % 180.0
        for a2 in (ang, (ang + 90.0) % 180.0):
            weight[a2] = weight.get(a2, 0.0) + L
    axes = [a for a, _ in sorted(weight.items(), key=lambda kv: -kv[1])[:max_axes]]
    # the lattice directions are always tried: a base built only from diagonal creases (a
    # stacked map fold, for example) lies along an axis that no crease points in
    for a in (0.0, 45.0, 90.0, 135.0):
        if a not in axes:
            axes.append(a)
    return axes


def extract_trees(folded: FoldedState, axes: list[float] | None = None) -> list[BaseTree]:
    edges = _mesh_edges(folded)
    return [tree_along(folded, a, edges) for a in (axes or candidate_axes(folded))]


# ----------------------------------------------------------------------------- base metrics
def layer_count(folded: FoldedState, samples: int = 0) -> int:
    """Maximum number of paper layers over any point of the folded state."""
    from shapely.strtree import STRtree

    polys = [p.buffer(-1e-7) for p in folded.face_polygons()]
    polys = [p for p in polys if not p.is_empty]
    if not polys:
        return 0
    tree = STRtree(polys)
    best = 1
    for p in polys:
        pt = p.representative_point()
        best = max(best, sum(1 for j in tree.query(pt) if polys[int(j)].contains(pt)))
    return best
