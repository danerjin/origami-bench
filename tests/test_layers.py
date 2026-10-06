import random

import pytest

from creasebench import reference as R
from creasebench.build import global_only_failure
from creasebench.generate import random_simple_folds
from creasebench.layers import build_problem, check_claimed_order
from creasebench.simulate import fold
from creasebench.verify import verify


@pytest.mark.parametrize("n,seed", [(1, 0), (2, 1), (3, 2), (4, 3), (5, 4)])
def test_generator_patterns_are_foldable_and_orders_valid(n, seed):
    g = random_simple_folds(n, seed)
    rep = verify(g.cp)
    assert rep.foldable, rep.reason
    assert check_claimed_order(rep.folded, g.face_above_in_frame(rep.folded))


def test_wrong_order_is_rejected():
    folded = fold(R.book())
    prob = build_problem(folded)
    (a, b), = prob.pair_var
    # exactly one of the two orders is valid for a single valley fold
    assert check_claimed_order(folded, [(a, b)], prob) != check_claimed_order(folded, [(b, a)], prob)


def test_unassigned_creases_get_resolved():
    cp = R.preliminary_base()
    cp.assignments = ["U" if a in "MV" else a for a in cp.assignments]
    rep = verify(cp)
    assert rep.foldable
    assert "U" not in rep.layers.assignments


def test_locally_valid_but_globally_unfoldable():
    cp = global_only_failure(random.Random(0))
    rep = verify(cp)
    assert rep.local.ok
    assert not rep.foldable and rep.layers.status == "none"
