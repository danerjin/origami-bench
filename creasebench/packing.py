"""Upper-bound estimates for the scale factor of a tree on a unit square.

Tree theory's necessary condition: flap-tip positions u_i in [0,1]^2 with

    ||u_i - u_j|| >= m * d_T(i, j)   for all leaf pairs.

The largest such m bounds every possible design (circle/river packing, Lang 1996).
Maximizing it is NP-hard (Demaine, Fekete & Lang 2010), so we report the best value
found by multi-start SLSQP. Box pleating replaces the Euclidean norm by L-infinity
(square packing); stretches recover some of the gap. Values are *estimates*: a
design scoring above them is flagged and the bound raised.
"""

from __future__ import annotations

import itertools

import numpy as np

from .treefit import TargetTree


def _solve(D: np.ndarray, norm: str, rng: np.random.Generator, starts: int) -> tuple[float, np.ndarray]:
    from scipy.optimize import minimize

    n = len(D)
    pairs = list(itertools.combinations(range(n), 2))
    I = np.array([p[0] for p in pairs])
    J = np.array([p[1] for p in pairs])
    dij = D[I, J]
    p = 2.0 if norm == "l2" else 16.0

    def dist(x):
        u = x[:-1].reshape(n, 2)
        d = u[I] - u[J]
        if norm == "l2":
            return np.sqrt((d ** 2).sum(1) + 1e-12)
        return ((np.abs(d) ** p).sum(1) + 1e-300) ** (1 / p)

    def cons(x):
        return dist(x) - x[-1] * dij

    best = (0.0, None)
    for _ in range(starts):
        x0 = np.concatenate([rng.random(2 * n), [0.01]])
        try:
            res = minimize(lambda x: -x[-1], x0, method="SLSQP",
                           bounds=[(0, 1)] * (2 * n) + [(0, 10)],
                           constraints=[{"type": "ineq", "fun": cons}],
                           options={"maxiter": 400, "ftol": 1e-10})
        except Exception:  # noqa: BLE001
            continue
        x = res.x
        u = np.clip(x[:-1].reshape(n, 2), 0, 1)
        # exact achieved value for these positions (true norm, not the smooth proxy)
        d = u[I] - u[J]
        true = np.sqrt((d ** 2).sum(1)) if norm == "l2" else np.abs(d).max(1)
        m = float((true / dij).min())
        if m > best[0]:
            best = (m, u)
    return best


def packing_bound(target: TargetTree, norm: str = "l2", starts: int = 40, seed: int = 0) -> dict:
    """Best packing scale found for ``target`` (norm 'l2' = circles, 'linf' = box pleating)."""
    lv = target.leaves
    dt = target.leaf_distances()
    n = len(lv)
    D = np.zeros((n, n))
    for (a, b), v in dt.items():
        i, j = lv.index(a), lv.index(b)
        D[i, j] = D[j, i] = v
    m, u = _solve(D, norm, np.random.default_rng(seed), starts)
    return {"norm": norm, "scale": m, "positions": {lv[i]: [float(x), float(y)] for i, (x, y) in enumerate(u)}
            if u is not None else {}}
