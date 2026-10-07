import math
import random

import pytest

from creasebench import ffolder
from creasebench import reference as R
from creasebench.build import global_only_failure
from creasebench.cp import CreasePattern
from creasebench.foldability import crimp_foldable
from creasebench.gen import bases22
from creasebench.generate import random_simple_folds
from creasebench.layers import check_claimed_order, solve_layers
from creasebench.packing import packing_bound
from creasebench.simulate import fold
from creasebench.style import analyze
from creasebench.tree import extract_trees
from creasebench.treefit import TargetTree, best_fit, fit_scale
from creasebench.verify import verify

STAR4 = TargetTree.from_json({"edges": [["c", "a", 1], ["c", "b", 1], ["c", "d", 1], ["c", "e", 1]]})
needs_node = pytest.mark.skipif(not ffolder.available(), reason="node.js not installed")


@needs_node
@pytest.mark.parametrize("name", ["waterbomb_base", "fish_base", "double_blintz", "preliminary_base"])
def test_flatfolder_agrees_with_python_solver(name):
    cp = R.REFERENCE[name][0]()
    f = fold(cp)
    r = ffolder.solve(cp, [f.face_flipped(i) for i in range(len(cp.faces))])
    assert r.status == "found" == solve_layers(f).status
    assert check_claimed_order(f, r.face_above)


@needs_node
def test_flatfolder_rejects_global_conflict_and_accepts_generated():
    cp = global_only_failure(random.Random(0))
    f = fold(cp)
    assert ffolder.solve(cp, [f.face_flipped(i) for i in range(len(cp.faces))]).status == "none"
    g = random_simple_folds(6, 1).cp
    assert verify(g, backend="flatfolder").foldable


def test_crimp_test():
    d = math.radians
    assert crimp_foldable([d(90)] * 4, ["M", "M", "M", "V"])
    assert not crimp_foldable([d(30), d(60), d(150), d(120)], ["V", "V", "M", "V"])


def test_bird_base_tree_is_four_equal_flaps():
    bird = bases22.bird_base()
    rep = verify(bird)
    assert rep.foldable
    fit = best_fit(extract_trees(rep.folded), STAR4)
    assert fit.scale == pytest.approx(0.5, abs=1e-6)  # the optimal scale for four equal flaps


def test_fit_scale_is_homogeneous():
    rep = verify(R.fish_base())
    trees = extract_trees(rep.folded)
    t1 = TargetTree.from_json({"edges": [["c", "h", 2], ["c", "t", 2], ["c", "f", 1], ["c", "g", 1]]})
    t2 = TargetTree.from_json({"edges": [["c", "h", 4], ["c", "t", 4], ["c", "f", 2], ["c", "g", 2]]})
    assert best_fit(trees, t1).scale == pytest.approx(2 * best_fit(trees, t2).scale)


def test_packing_bound_star4_and_dominates_designs():
    assert packing_bound(STAR4, "l2")["scale"] == pytest.approx(0.5, abs=1e-3)
    rep = verify(R.preliminary_base())
    assert best_fit(extract_trees(rep.folded), STAR4).scale <= packing_bound(STAR4, "l2")["scale"] + 1e-6


def test_style_detection():
    assert analyze(R.double_blintz()).box_pleat
    assert analyze(R.double_blintz()).grid == 4
    assert analyze(bases22.bird_base()).angles_22_5
    assert not analyze(bases22.bird_base()).box_pleat
    stretch = CreasePattern.from_segments([((0, 0), (1, 0.5), "V"), ((0, 0.5), (1, 0.5), "M")])
    rep = analyze(stretch)
    assert rep.pythagorean_stretch and rep.stretch_triples == [(3, 4, 5)]


def test_mirror_tiling_certifies_and_reads():
    cp = bases22.certify_tiling(bases22.mirror_cells("preliminary_base", 2))
    assert cp is not None and cp.num_creases() >= 30
    rep = verify(cp)
    assert rep.foldable and len(max(extract_trees(rep.folded), key=lambda t: t.total_length()).leaves) > 4


def test_prune_stubs_drops_short_leaves_only():
    import networkx as nx

    from creasebench.advanced import prune_stubs

    g = nx.Graph()
    for i in range(4):
        g.add_edge("h", f"c{i}", length=0.5)
    for i in range(16):
        g.add_edge("h", f"s{i}", length=0.0625)
    g.add_edge("h", "ctr", length=0.207)
    p = prune_stubs(g)
    assert sorted(round(l, 3) for *_, l in p.edges(data="length")) == [0.207, 0.5, 0.5, 0.5, 0.5]


def test_task_split_rules():
    from creasebench.tasks import Task, task_split

    big = {"edges_assignment": ["M"] * 120}
    assert task_split(Task("x", "analytic", "easy", "")) == "warmup"
    assert task_split(Task("x", "solve", "hard", "", inputs={"crease_pattern": big},
                           reference={"family": "solve"}, meta={"tier": "advanced"})) == "hard"
    assert task_split(Task("x", "read", "hard", "", inputs={"crease_pattern": big},
                           reference={"family": "read-tech"}, meta={"tier": "advanced"})) == "core"
    star = {"edges": [["h", f"l{i}", 1] for i in range(4)]}
    assert task_split(Task("x", "design", "hard", "", inputs={"tree": star},
                           reference={"family": "design"}, meta={"tier": "advanced"})) == "core"


def test_style_grid_window():
    from types import SimpleNamespace

    from creasebench.advanced import _style_ok

    rep = SimpleNamespace(box_pleat=True, grid=2)
    assert _style_ok(rep, {"kind": "box_pleat", "max_grid": 16})
    assert not _style_ok(rep, {"kind": "box_pleat", "min_grid": 8, "max_grid": 16})


def test_big_trees_are_big():
    from creasebench.trees import BIG_TREES

    for name, spec in BIG_TREES.items():
        n = len(TargetTree.from_json({"edges": spec["edges"]}).leaves)
        assert 14 <= n <= 24, (name, n)


def test_tilings_have_no_read_tree_task():
    from creasebench.build_advanced import is_tiling

    assert is_tiling({"name": "bird-2x2"}) and is_tiling({"name": "tiling-3"})
    assert not is_tiling({"name": "bird-border"}) and not is_tiling({"name": "bp-lizard-32"})


def test_design_reports_square_packing_milestone():
    from creasebench.advanced import grade_design
    from creasebench.tasks import Task

    star4 = {"edges": [["c", x, 1] for x in "abde"]}
    task = Task("x", "design", "hard", "", inputs={"tree": star4},
                reference={"family": "design", "bound": 0.5, "packing_bound_linf": 0.5})
    bird = bases22.bird_base()
    g = grade_design(task, {"creases": [[*p, *q, a] for p, q, a in bird.segments()]})
    assert g["solved"] and abs(g["scale"] - 0.5) < 1e-6
    assert g["beats_square_packing"] is False  # reaching the square packing is not beating it


def _assert_tree_edges_within_extent(cp):
    import numpy as np

    rep = verify(cp)
    for t in extract_trees(rep.folded):
        a = np.array([math.cos(math.radians(t.axis_deg)), math.sin(math.radians(t.axis_deg))])
        g = rep.folded.vertices @ a
        span = g.max() - g.min()
        for *_, length in t.graph.edges(data="length"):
            assert length <= span + 1e-9, (t.axis_deg, length, span)


def test_tree_edges_never_exceed_folded_extent():
    # a stacked map fold of a 1/3 diagonal grid: many tied extrema (regression for a
    # contraction bug that summed a rise and a fall into one 1.414-long edge)
    segs = []
    for n in range(1, 6):
        c = n / 3
        segs.append(((max(0, c - 1), min(1, c)), (min(1, c), max(0, c - 1)), "U"))
    for m in range(-2, 3):
        c = m / 3
        segs.append(((max(0, c), max(0, -c)), (min(1, 1 + c), min(1, 1 - c)), "U"))
    cp = CreasePattern.from_segments([(p, q, "U") for p, q, _ in segs])
    cp = __import__("creasebench.verify", fromlist=["x"]).complete_assignment(cp, timeout=60)
    assert cp is not None
    _assert_tree_edges_within_extent(cp)
    trees = extract_trees(verify(cp).folded)
    assert 0.0 in {t.axis_deg for t in trees}  # lattice axes are always candidates
    _assert_tree_edges_within_extent(bases22.bird_base())
    for name in ("fish_base", "waterbomb_base"):
        _assert_tree_edges_within_extent(getattr(R, name)())
