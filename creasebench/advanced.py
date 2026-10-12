"""Graders for the advanced tier: reading expert crease patterns and tree-theory design.

Families (``task.reference["family"]``):

* ``read-tree``  CP -> stick-figure tree of its folded base
* ``read-tech``  CP -> design system (box pleating + grid, 22.5 deg, stretch triples)
* ``read-color`` CP -> which side of two-tone paper shows at given flap tips
* ``solve``      geometry of a crease pattern with every crease unassigned -> M/V
* ``pack``       target tree -> flap-tip positions (circle or square packing)
* ``design``     target tree (+ optional style / colour / graft requirements) -> CP

Design answers are always folded for real (flat-folder), their tree is extracted from
the folded state and the scale factor they achieve for the target is compared with the
best known packing bound.
"""

from __future__ import annotations

import itertools
import math
from typing import Any

import networkx as nx
import numpy as np

from . import style
from .color import satisfiable, tip_sample_point
from .cp import CreasePattern
from .tree import BaseTree, extract_trees
from .treefit import TargetTree, best_fit, fit_scale, same_tree
from .verify import verify

DESIGN_TIMEOUT = 180.0


def _timeout(task) -> float:
    """Verifier budget: expert tasks carry a longer one, so a correct large answer is never
    failed as undetermined (the oracle answer is certified within the same budget)."""
    return float(task.reference.get("verify_timeout", DESIGN_TIMEOUT))


def _answer_cp(ans: dict) -> CreasePattern:
    from .graders import answer_cp

    return answer_cp(ans)


def answer_tree(d: Any) -> nx.Graph:
    return TargetTree.from_json(d).graph


# ----------------------------------------------------------------------------- reading
STUB_FRAC = 0.15  # same cut as simplified_tree: shorter leaves are not flaps


def prune_stubs(g: nx.Graph, frac: float = STUB_FRAC) -> nx.Graph:
    """Drop leaf edges shorter than ``frac`` x the longest leaf edge (pleat ridges and
    projection stubs that are not flaps), then merge the degree-2 nodes left behind."""
    g = g.copy()

    def leaf_edges():
        return [(n, p, g.edges[n, p]["length"]) for n in g if g.degree(n) == 1 for p in g.neighbors(n)]

    while True:
        le = leaf_edges()
        if len(le) <= 2:
            break
        longest = max(l for *_, l in le)
        short = [n for n, _, l in le if l < frac * longest]
        if not short or len(le) - len(short) < 2:
            break
        g.remove_nodes_from(short)
        for n in [n for n in g if g.degree(n) == 2]:
            a, b = list(g.neighbors(n))
            if not g.has_edge(a, b):
                g.add_edge(a, b, length=g.edges[n, a]["length"] + g.edges[n, b]["length"])
                g.remove_node(n)
    return g


def grade_read_tree(task, ans: dict) -> dict:
    ref = nx.Graph()
    for u, v, l in task.reference["tree"]["edges"]:
        ref.add_edge(int(u), int(v), length=float(l))
    try:
        got = answer_tree(ans["tree"])
    except (KeyError, ValueError, TypeError) as e:
        return {"score": 0.0, "solved": False, "error": f"bad tree: {e}"}
    # short stubs are not graded either way: neither reporting nor omitting them costs points
    ref, got = prune_stubs(ref), prune_stubs(got)
    n_ref = sum(1 for n in ref if ref.degree(n) == 1)
    n_got = sum(1 for n in got if got.degree(n) == 1)
    leaf_ok = n_ref == n_got
    topo = nx.is_isomorphic(ref, got)
    exact = topo and same_tree(got, ref)
    tl_ref = sum(l for *_, l in ref.edges(data="length"))
    tl_got = sum(l for *_, l in got.edges(data="length"))
    length_score = max(0.0, 1 - abs(tl_got - tl_ref) / tl_ref)
    # leaf-to-leaf distance agreement under the best leaf matching (only if counts match)
    dist_score = 0.0
    if leaf_ok and n_ref <= 9:
        lr = [n for n in ref if ref.degree(n) == 1]
        lg = [n for n in got if got.degree(n) == 1]
        dr = dict(nx.all_pairs_dijkstra_path_length(ref, weight="length"))
        dg = dict(nx.all_pairs_dijkstra_path_length(got, weight="length"))
        best = math.inf
        for perm in itertools.permutations(lg):
            err = max(abs(dr[a][b] - dg[perm[i]][perm[j]]) for (i, a), (j, b)
                      in itertools.combinations(enumerate(lr), 2)) if len(lr) > 1 else 0
            best = min(best, err)
        dist_score = max(0.0, 1 - best / max(dr[a][b] for a in lr for b in lr))
    score = 0.2 * leaf_ok + 0.3 * topo + 0.2 * length_score + 0.3 * (1.0 if exact else dist_score)
    return {"score": score, "solved": bool(exact), "leaf_count_correct": leaf_ok, "topology_correct": topo,
            "length_score": length_score, "distance_score": dist_score}


def grade_read_tech(task, ans: dict) -> dict:
    ref = task.reference["tech"]
    fields = ["box_pleat", "grid", "angles_22_5", "pythagorean_stretch", "stretch_triples"]
    got = {k: ans.get(k) for k in fields}
    if got.get("stretch_triples") is not None:
        got["stretch_triples"] = sorted(sorted(map(int, t)) for t in got["stretch_triples"])
    want = dict(ref)
    want["stretch_triples"] = sorted(sorted(t) for t in want.get("stretch_triples", []))
    if not want["box_pleat"] and not want["pythagorean_stretch"]:
        fields.remove("grid")  # grid only asked for lattice patterns
    correct = {k: got.get(k) == want.get(k) for k in fields}
    score = sum(correct.values()) / len(correct)
    return {"score": score, "solved": all(correct.values()), "fields": correct}


def grade_read_color(task, ans: dict) -> dict:
    ref = task.reference["colors"]  # {tip_id: {"above": side, "below": side}}
    got = ans.get("colors", {})
    total = correct = 0
    for tip, sides in ref.items():
        for view, side in sides.items():
            total += 1
            correct += str((got.get(tip) or {}).get(view, "")).lower() == side
    return {"score": correct / total if total else 0.0, "solved": correct == total}


# ----------------------------------------------------------------------------- solve
def grade_solve(task, ans: dict) -> dict:
    """Same geometry as given, every crease assigned, and it must fold flat."""
    try:
        cp = _answer_cp(ans)
    except Exception as e:  # noqa: BLE001
        return {"score": 0.0, "solved": False, "error": f"invalid answer: {e}"}
    given = CreasePattern.from_fold(task.inputs["crease_pattern"], rebuild=True)
    key = lambda c: {(tuple(np.round(c.vertices[u], 5)), tuple(np.round(c.vertices[v], 5)))  # noqa: E731
                     for u, v in c.edges}
    gk, ak = key(given), key(cp)
    norm = lambda s: {tuple(sorted(e)) for e in s}  # noqa: E731
    if norm(gk) != norm(ak):
        return {"score": 0.0, "solved": False, "error": "crease geometry differs from the given pattern",
                "missing": len(norm(gk) - norm(ak)), "extra": len(norm(ak) - norm(gk))}
    if "U" in cp.assignments:
        return {"score": 0.0, "solved": False, "error": "some creases left unassigned"}
    rep = verify(cp, timeout=_timeout(task))
    if rep.foldable:
        return {"score": 1.0, "solved": True}
    local_ok = 1 - len(rep.local.bad_vertices()) / max(1, sum(1 for _ in cp.vertices))
    return {"score": 0.5 * local_ok if rep.local and rep.local.ok is False else 0.5, "solved": False,
            "error": rep.reason}


# ----------------------------------------------------------------------------- pack
def grade_pack(task, ans: dict) -> dict:
    """Flap-tip positions for the target tree; graded on the scale factor they allow."""
    target = TargetTree.from_json(task.inputs["tree"])
    norm = task.reference.get("norm", "l2")
    pos = ans.get("positions", {})
    lv = target.leaves
    if set(map(str, pos)) != set(lv):
        return {"score": 0.0, "solved": False, "error": "positions must be given for exactly the leaves"}
    P = {k: np.array(pos[k], float) for k in lv}
    if any(not (-1e-9 <= c <= 1 + 1e-9) for p in P.values() for c in p):
        return {"score": 0.0, "solved": False, "error": "positions must lie in the unit square"}
    dt = target.leaf_distances()
    m = math.inf
    for (a, b), d in dt.items():
        diff = P[a] - P[b]
        dist = float(np.hypot(*diff)) if norm == "l2" else float(np.abs(diff).max())
        m = min(m, dist / d)
    claimed = ans.get("scale")
    bound = task.reference["bound"]
    eff = m / bound
    out = {"scale": m, "bound": bound, "efficiency": eff, "score": min(1.0, eff),
           "solved": eff >= task.reference.get("solve_threshold", 0.98)}
    if claimed is not None:
        out["claimed_scale_ok"] = abs(float(claimed) - m) <= 0.01 * max(m, 1e-9)
    return out


# ----------------------------------------------------------------------------- design
def analyze_design(cp: CreasePattern, target: TargetTree, timeout: float = DESIGN_TIMEOUT) -> dict:
    rep = verify(cp, timeout=timeout)
    out: dict[str, Any] = {"verify": rep.summary(), "num_creases": cp.num_creases()}
    if not rep.foldable:
        return out
    trees = extract_trees(rep.folded)
    fit = best_fit(trees, target)
    tree = next((t for t in trees if t.axis_deg == fit.axis_deg), None)
    out.update(rep=rep, fit=fit, tree=tree, scale=fit.scale)
    return out


def grade_design(task, ans: dict) -> dict:
    ref = task.reference
    target = TargetTree.from_json(task.inputs["tree"])
    try:
        cp = _answer_cp(ans)
    except Exception as e:  # noqa: BLE001
        return {"score": 0.0, "solved": False, "error": f"invalid answer: {e}"}
    if cp.num_creases() == 0:
        return {"score": 0.0, "solved": False, "error": "no creases"}
    a = analyze_design(cp, target, timeout=_timeout(task))
    out = {k: v for k, v in a.items() if k not in ("rep", "fit", "tree")}
    if "fit" not in a:
        out.update(score=0.0, solved=False, error=f"not flat-foldable: {a['verify']['reason']}")
        return out
    m = a["scale"]
    bound = ref["bound"]
    eff = m / bound if bound > 0 else 0.0
    out.update(efficiency=eff, bound=bound, mapping=a["fit"].mapping, axis_deg=a["fit"].axis_deg)
    if ref.get("packing_bound_linf"):
        # milestone, not scored: a box-pleating-style square packing is the easy way to a valid
        # base; beating its best scale needs genuine circle/river packing
        out["beats_square_packing"] = bool(a["fit"].scale > ref["packing_bound_linf"] * (1 + 1e-6))
    factors = [min(1.0, eff)]
    passed = [eff >= ref.get("solve_efficiency", 0.6)]
    if ref.get("require_beats_square"):
        passed.append(out.get("beats_square_packing", False))
    if m <= 0:
        out.update(score=0.0, solved=False, error="the folded base does not realize the target tree")
        return out
    if "style" in ref:
        rep_style = style.analyze(cp)
        req = ref["style"]
        ok = _style_ok(rep_style, req)
        out["style"] = {"required": req, "report": rep_style.to_json(), "passed": ok}
        factors.append(1.0 if ok else 0.0)
        passed.append(ok)
    if "colors" in ref:
        ok, detail = _colors_ok(a, ref["colors"])
        out["colors"] = {"required": ref["colors"], "detail": detail, "passed": ok}
        factors.append(1.0 if ok else 0.5)
        passed.append(ok)
    if "graft" in ref:
        from .style import graft_preserved

        base = CreasePattern.from_fold(task.inputs["base_crease_pattern"], rebuild=False)
        frac = graft_preserved(base, cp, ref["graft"]["pieces"])
        ok = frac >= ref["graft"].get("min_preserved", 0.9)
        out["graft"] = {"preserved": frac, "passed": ok}
        factors.append(frac)
        passed.append(ok)
    if "max_layers" in ref:
        from .tree import layer_count

        n = layer_count(a["rep"].folded)
        ok = n <= ref["max_layers"]
        out["layers"] = {"max": n, "limit": ref["max_layers"], "passed": ok}
        passed.append(ok)
        factors.append(1.0 if ok else 0.5)
    out["score"] = float(np.prod(factors))
    out["solved"] = all(passed)
    if eff > 1.0 + 1e-6:
        out["beats_reference"] = True
    return out


def _grid_ok(rep: "style.StyleReport", req: dict) -> bool:
    grid = rep.grid or 10 ** 9
    return grid <= req.get("max_grid", 10 ** 9) and grid >= req.get("min_grid", 0)


def _style_ok(rep: "style.StyleReport", req: dict) -> bool:
    kind = req["kind"]
    if kind == "box_pleat":
        return rep.box_pleat and _grid_ok(rep, req)
    if kind == "angles_22_5":
        return rep.angles_22_5
    if kind == "pythagorean_stretch":
        return rep.pythagorean_stretch and _grid_ok(rep, req)
    if kind == "hex":
        return rep.hex
    raise ValueError(kind)


def _colors_ok(a: dict, colors: dict) -> tuple[bool, dict]:
    """colors: {target_leaf: {"above": "back"}, ...} -- side visible at that flap's tip."""
    rep, fit, tree = a["rep"], a["fit"], a["tree"]
    reqs = []
    detail = {}
    polys = [p.buffer(-1e-7) for p in rep.folded.face_polygons()]
    for leaf, views in colors.items():
        base_leaf = fit.mapping.get(leaf)
        if base_leaf is None:
            return False, {"error": f"leaf {leaf} not matched"}
        pt = tip_sample_point(rep.folded, tree, base_leaf, polys)
        if pt is None:
            return False, {"error": f"no paper at tip of {leaf}"}
        for view, side in views.items():
            reqs.append((pt, view, side))
        detail[leaf] = [round(float(c), 4) for c in pt]
    ok = satisfiable(rep.folded, reqs, known_order=rep.layers.face_above if rep.layers else None)
    return ok, detail


# ----------------------------------------------------------------------------- repair (expert)
def _edge_keys(cp: CreasePattern) -> dict:
    out = {}
    for (u, v), a in zip(cp.edges, cp.assignments):
        k = tuple(sorted((tuple(np.round(cp.vertices[u], 5)), tuple(np.round(cp.vertices[v], 5)))))
        out[k] = a
    return out


def grade_repair(task, ans: dict) -> dict:
    """A defective pattern (several wrong M/V assignments) must be repaired: same geometry, every
    crease M/V, it must fold flat, and at most ``max_edits`` assignments may differ from the given
    pattern. Any repair meeting that is accepted (it need not be the original assignment)."""
    try:
        cp = _answer_cp(ans)
    except Exception as e:  # noqa: BLE001
        return {"score": 0.0, "solved": False, "error": f"invalid answer: {e}"}
    given = CreasePattern.from_fold(task.inputs["crease_pattern"], rebuild=True)
    gk, ak = _edge_keys(given), _edge_keys(cp)
    if set(gk) != set(ak):
        return {"score": 0.0, "solved": False, "error": "crease geometry differs from the given pattern",
                "missing": len(set(gk) - set(ak)), "extra": len(set(ak) - set(gk))}
    if any(a not in ("M", "V", "B") for a in ak.values()):
        return {"score": 0.0, "solved": False, "error": "every crease must be M or V"}
    edits = sum(1 for k, a in ak.items() if a != gk[k] and a != "B")
    limit = int(task.reference["max_edits"])
    out = {"edits": edits, "max_edits": limit}
    if edits > limit:
        return {**out, "score": 0.0, "solved": False, "error": f"{edits} creases changed, at most {limit} allowed"}
    rep = verify(cp, timeout=_timeout(task))
    if not rep.foldable:
        return {**out, "score": 0.0, "solved": False, "error": rep.reason}
    return {**out, "score": 1.0, "solved": True}


# ----------------------------------------------------------------------------- inverse (expert)
def grade_inverse(task, ans: dict) -> dict:
    """Reconstruct a crease pattern from its folded base alone. It must fold flat, realize the
    stick-figure tree at the reference scale (lengths within ``scale_tol``), and its folded
    outline must match the given one (IoU after rigid alignment, incl. reflection)."""
    from .compare import as_geometry, silhouette_iou

    ref = task.reference
    target = TargetTree.from_json(task.inputs["tree"])
    try:
        cp = _answer_cp(ans)
    except Exception as e:  # noqa: BLE001
        return {"score": 0.0, "solved": False, "error": f"invalid answer: {e}"}
    if cp.num_creases() == 0:
        return {"score": 0.0, "solved": False, "error": "no creases"}
    a = analyze_design(cp, target, timeout=_timeout(task))
    if "fit" not in a:
        return {"score": 0.0, "solved": False, "error": f"not flat-foldable: {a['verify']['reason']}"}
    scale_ratio = a["scale"] / ref["reference_scale"]
    iou = silhouette_iou(a["rep"].folded.silhouette(), as_geometry(task.inputs["folded_outline"]),
                         rot_step_deg=1.0)["iou"]
    tree_ok = scale_ratio >= 1 - ref.get("scale_tol", 0.02)
    sil_ok = iou >= ref.get("min_iou", 0.97)
    return {"score": 0.5 * min(1.0, scale_ratio) + 0.5 * iou, "solved": bool(tree_ok and sil_ok),
            "scale_ratio": scale_ratio, "silhouette_iou": iou, "num_creases": cp.num_creases()}


GRADERS = {
    "repair": grade_repair,
    "inverse": grade_inverse,
    "read-tree": grade_read_tree,
    "read-tech": grade_read_tech,
    "read-color": grade_read_color,
    "solve": grade_solve,
    "pack": grade_pack,
    "design": grade_design,
}
