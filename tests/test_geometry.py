import math

import numpy as np
import pytest
from shapely import affinity
from shapely.geometry import Polygon

from creasebench import reference as R
from creasebench.compare import geometry_score, mirror_symmetry, sharp_points, silhouette_iou
from creasebench.cp import CreasePattern
from creasebench.foldability import check_local
from creasebench.simulate import fold
from creasebench.verify import verify


def test_arrangement_splits_crossings_and_adds_border():
    cp = CreasePattern.from_segments([((0, 0), (1, 1), "V"), ((1, 0), (0, 1), "V")])
    assert len(cp.faces) == 4
    assert cp.num_creases() == 4  # each diagonal split at the centre
    assert cp.assignments.count("B") == 4


def test_dangling_creases_are_pruned():
    cp = CreasePattern.from_segments([((0.5, 0), (0.5, 0.6), "V")])
    assert cp.num_creases() == 0
    assert cp.warnings


def test_segments_outside_paper_are_clipped():
    cp = CreasePattern.from_segments([[-1, 0.5, 2, 0.5, "M"]])
    assert cp.num_creases() == 1
    assert len(cp.faces) == 2


def test_kawasaki_and_maekawa_violations():
    bad_angle = CreasePattern.from_segments([((0, 0.5), (1, 0.5), "M"), ((0.5, 0.5), (0.7, 1), "V"),
                                             ((0.5, 0.5), (0.5, 0), "V")])
    assert any(v.rule in ("kawasaki", "odd_degree") for v in check_local(bad_angle).violations)
    all_valley = CreasePattern.from_segments([((0, 0), (1, 1), "V"), ((1, 0), (0, 1), "V"),
                                              ((0, 0.5), (1, 0.5), "V")])
    assert [v.rule for v in check_local(all_valley).violations] == ["maekawa"]


@pytest.mark.parametrize("name,area", [
    ("book", 0.5), ("diagonal", 0.5), ("cupboard", 0.5), ("accordion4", 0.25), ("blintz", 0.5),
    ("kite_base", 1 - math.tan(math.radians(22.5))), ("waterbomb_base", 0.25), ("preliminary_base", 0.25),
    ("map_fold", 0.25), ("double_blintz", 0.25),
])
def test_reference_patterns_fold_to_known_areas(name, area):
    rep = verify(R.REFERENCE[name][0]())
    assert rep.foldable, rep.reason
    assert rep.folded.silhouette().area == pytest.approx(area, abs=1e-6)


def test_fold_to_convex_makes_regular_polygons():
    h = math.sqrt(3) / 2
    rep = verify(R.fold_to_convex([(0, 0), (1, 0), (0.5, h)]))
    assert rep.foldable
    assert rep.folded.silhouette().area == pytest.approx(h / 2, abs=1e-6)


def test_folded_geometry_independent_of_root_face():
    cp = R.waterbomb_base()
    a = fold(cp, root_face=0)
    b = fold(cp, root_face=len(cp.faces) - 1)
    assert geometry_score(a.vertices, b.vertices)["fraction_correct"] == 1.0


def test_silhouette_iou_is_rigid_and_mirror_invariant():
    p = Polygon([(0, 0), (1, 0), (0.2, 0.6)])
    q = affinity.translate(affinity.rotate(affinity.scale(p, xfact=-1), 73), 3, -2)
    assert silhouette_iou(p, q)["iou"] > 0.999
    assert silhouette_iou(p, affinity.scale(p, 1.2, 1.2))["iou"] < 0.75  # scale matters


def test_geometry_score_handles_reflection_and_outliers():
    gt = np.random.default_rng(0).random((10, 2))
    pred = gt @ np.array([[-1, 0], [0, 1]]) + 5
    pred[3] += 0.5
    g = geometry_score(pred, gt)
    assert g["reflected"] and g["fraction_correct"] == pytest.approx(0.9)


def test_shape_features():
    tri = Polygon([(0, 0), (1, 0), (0.5, 0.1)])
    assert sharp_points(tri) == 2
    assert mirror_symmetry(tri) > 0.99
