"""Certify reference CPs and measure the success rate on random trees.

    python -m creasebench.gen.bpstudio.certify_samples [--trials 20] [--seed 0] [--timeout 120] [--inflate]

Writes:
  samples/certified/<name>.fold    certified CPs (FOLD, unit square, every crease M/V)
  samples/certified/summary_{random,tight}_seed<N>.json   per-design status, failure stage, timings
"""
from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

from creasebench.gen.bpstudio import certified_cp, generate

OUT = Path(__file__).resolve().parent / "samples" / "certified"

FIXED = {
    "star4_16": ([(0, 1, 8), (0, 2, 8), (0, 3, 8), (0, 4, 8)],
                 [(1, 0, 0), (2, 16, 0), (3, 0, 16), (4, 16, 16)], 16),
    "lizard_32": ([(0, 1, 8), (0, 2, 8), (0, 3, 8), (0, 4, 16), (4, 5, 8), (4, 6, 8), (4, 7, 8)],
                  [(1, 16, 32), (2, 0, 32), (3, 32, 32), (5, 0, 0), (6, 32, 0), (7, 16, 0)], 32),
    "three_flap_16": ([(0, 1, 8), (0, 2, 8), (0, 3, 8)], [(1, 0, 0), (2, 16, 0), (3, 8, 16)], 16),
    "star4_r6_16": ([(0, i, 6) for i in range(1, 5)], [(1, 0, 0), (2, 16, 0), (3, 0, 16), (4, 16, 16)], 16),
    # GOPS (3,2,u3,v1) with 3-4-5 slopes; sheet 13/14 keeps the excess paper small.
    "stretch_gops_13": ([(0, 1, 7), (0, 2, 4)], [(1, 0, 0), (2, 8, 9)], 13),
    "stretch_gops_14": ([(0, 1, 7), (0, 2, 4)], [(1, 0, 0), (2, 8, 9)], 14),
    "stretch_kamiya_13": ([(0, 1, 7), (0, 2, 4)], [(1, 0, 0), (2, 8, 8)], 13),
    "stretch_gops_16": ([(0, 1, 7), (0, 2, 4)], [(1, 0, 0), (2, 8, 9)], 16),
    "stretch_3flap_relay_20": ([(0, 1, 1), (0, 2, 18), (0, 3, 1)], [(1, 7, 18), (2, 0, 0), (3, 9, 17)], 20),
}


def random_design(rng: random.Random, max_tries: int = 400):
    """A random star / two-level tree with flaps on the sheet border that BP Studio accepts."""
    for _ in range(max_tries):
        grid = rng.choice([12, 16, 16, 20, 24])
        n_leaves = rng.randint(3, 6)
        edges, leaves = [], []
        nid = 1
        if rng.random() < 0.5 and n_leaves >= 4:  # two hubs joined by a river
            hub = nid; nid += 1
            edges.append((0, hub, rng.randint(1, grid // 4)))
            split = rng.randint(2, n_leaves - 2)
            parents = [0] * split + [hub] * (n_leaves - split)
        else:
            parents = [0] * n_leaves
        for par in parents:
            edges.append((par, nid, rng.randint(2, grid // 2)))
            leaves.append(nid); nid += 1
        border = [(x, y) for x in range(grid + 1) for y in range(grid + 1)
                  if x in (0, grid) or y in (0, grid)]
        corners = [(0, 0), (grid, 0), (0, grid), (grid, grid)]
        pts = rng.sample(corners, min(len(corners), len(leaves)))
        pts += rng.sample([p for p in border if p not in pts], len(leaves) - len(pts))
        flaps = [(i, x, y) for i, (x, y) in zip(leaves, pts)]
        r = generate(edges, flaps, grid)
        if r["status"] == "ok":
            return edges, flaps, grid, r
    raise RuntimeError("no valid design found")


def inflate(edges, flaps, grid, rng: random.Random, allow_stretch: bool = False):
    """Lengthen leaf edges one unit at a time while BP Studio still accepts the layout.

    This removes most of the excess paper (a tight layout, as in real BP
    designs). Without ``allow_stretch``, a step that would create a stretch is
    rejected.
    """
    edges = [list(e) for e in edges]
    leaf_idx = [i for i, (a, b, _) in enumerate(edges) if b in {f[0] for f in flaps}]
    r = generate([tuple(e) for e in edges], flaps, grid)
    active = list(leaf_idx)
    while active:
        i = rng.choice(active)
        edges[i][2] += 1
        r2 = generate([tuple(e) for e in edges], flaps, grid)
        if r2["status"] == "ok" and (allow_stretch or r2["stretches"] == 0):
            r = r2
        else:
            edges[i][2] -= 1
            active.remove(i)
    return [tuple(e) for e in edges], r


def certify(name, edges, flaps, grid, timeout, save=True):
    t0 = time.perf_counter()
    cp, info = certified_cp(edges, flaps, grid, timeout=timeout)
    total = time.perf_counter() - t0
    row = {
        "name": name, "tree": edges, "flaps": flaps, "grid": grid,
        "stage": info.get("stage"), "reason": info.get("reason"),
        "stretches": info["bp"].get("stretches"), "gadget_types": info["bp"].get("gadget_types"),
        "n_creases": info.get("n_creases"), "timings": info["timings"], "total_s": round(total, 2),
        "pleat_info": {k: v for k, v in (info.get("pleats") or {}).items() if k != "violations"},
        "n_violations": len((info.get("pleats") or {}).get("violations", [])),
    }
    if cp is not None and save:
        OUT.mkdir(parents=True, exist_ok=True)
        cp.save(OUT / f"{name}.fold", file_description=f"BP Studio + pleat completion: {name}",
                creasebench_source={"tree": edges, "flaps": flaps, "grid": grid,
                                    "generator": "creasebench.gen.bpstudio.certified_cp"})
    print(f"{name:26s} {row['stage']:8s} creases={row['n_creases']} stretches={row['stretches']} "
          f"{row['gadget_types']} {total:.1f}s {row['reason'] if row['stage'] != 'ok' else ''}", flush=True)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--timeout", type=float, default=120)
    ap.add_argument("--skip-fixed", action="store_true")
    ap.add_argument("--inflate", action="store_true", help="tighten random layouts (see inflate())")
    a = ap.parse_args()
    rows = []
    if not a.skip_fixed:
        for name, (e, f, g) in FIXED.items():
            rows.append(certify(name, e, f, g, a.timeout))
    rng = random.Random(a.seed)
    rand_rows = []
    for i in range(a.trials):
        e, f, g, _ = random_design(rng)
        tag = "random"
        if a.inflate:
            e, _ = inflate(e, f, g, rng)
            tag = "tight"
        rand_rows.append(certify(f"{tag}_{a.seed}_{i:02d}", e, f, g, a.timeout))
    ok = sum(r["stage"] == "ok" for r in rand_rows)
    summary = {"fixed": rows, "random": rand_rows,
               "random_success": f"{ok}/{len(rand_rows)}",
               "random_failure_stages": {s: sum(r["stage"] == s for r in rand_rows)
                                         for s in {r["stage"] for r in rand_rows}}}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"summary_{'tight' if a.inflate else 'random'}_seed{a.seed}.json").write_text(json.dumps(summary, indent=1))
    print("random success", summary["random_success"], summary["random_failure_stages"])


if __name__ == "__main__":
    main()
