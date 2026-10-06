"""Regenerate samples/*.json.  Run from the repo root:
    python -m creasebench.gen.bpstudio.make_samples
"""
import json
import time
from pathlib import Path

from creasebench.gen.bpstudio import generate

SAMPLES = {
    # (a) 4-flap star, flaps at the corners of a 16 grid (classic BP base).
    "star4_16": dict(
        tree_edges=[(0, 1, 8), (0, 2, 8), (0, 3, 8), (0, 4, 8)],
        flaps=[(1, 0, 0), (2, 16, 0), (3, 0, 16), (4, 16, 16)],
        grid=16,
    ),
    # (b) lizard: 0 = shoulders, 4 = hips; head 1, front legs 2/3, hind legs 5/6, tail 7,
    #     body river 0-4 of length 16. All flap distances are tight on the 32 grid.
    "lizard_32": dict(
        tree_edges=[(0, 1, 8), (0, 2, 8), (0, 3, 8), (0, 4, 16), (4, 5, 8), (4, 6, 8), (4, 7, 8)],
        flaps=[(1, 16, 32), (2, 0, 32), (3, 32, 32), (5, 0, 0), (6, 32, 0), (7, 16, 0)],
        grid=32,
    ),
    # (c1) two flaps diagonally offset -> overlap 3x2 -> integral GOPS gadget (3-4-5 slopes).
    "stretch_gops_16": dict(
        tree_edges=[(0, 1, 7), (0, 2, 4)],
        flaps=[(1, 0, 0), (2, 8, 9)],
        grid=16,
    ),
    # (c2) overlap 3x3 (both odd) -> half-integral Kamiya gadget.
    "stretch_kamiya_16": dict(
        tree_edges=[(0, 1, 7), (0, 2, 4)],
        flaps=[(1, 0, 0), (2, 8, 8)],
        grid=16,
    ),
    # (c3) three-flap stretch (BP Studio test "three flap relay").
    "stretch_3flap_relay_20": dict(
        tree_edges=[(0, 1, 1), (0, 2, 18), (0, 3, 1)],
        flaps=[(1, 7, 18), (2, 0, 0), (3, 9, 17)],
        grid=20,
    ),
    # (d) negative control: BP Studio test "Signifies when no pattern is found" -> status error.
    "nopattern_3flap_16": dict(
        tree_edges=[(2, 0, 10), (2, 1, 2), (2, 3, 3)],
        flaps=[(0, 0, 0), (1, 11, 5), (3, 9, 10)],
        grid=16,
    ),
}


def main() -> None:
    out_dir = Path(__file__).resolve().parent / "samples"
    out_dir.mkdir(exist_ok=True)
    for name, kw in SAMPLES.items():
        t0 = time.perf_counter()
        res = generate(**kw, diagnose_foldability=True)
        dt = time.perf_counter() - t0
        res["input"] = {"tree": kw["tree_edges"], "flaps": kw["flaps"], "grid": kw["grid"]}
        res["elapsed_s"] = round(dt, 3)
        (out_dir / f"{name}.json").write_text(json.dumps(res, indent=1))
        print(f"{name:24s} {res['status']:5s} lines={len(res['lines']):4d} stretches={res.get('stretches')} "
              f"found={res.get('patterns_found')} gadgets={res.get('gadget_types')} {dt:.2f}s "
              f"viol={len(res['diagnostics']['violations'])}/{res['diagnostics']['interior_vertices']} "
              f"{res.get('errors') or ''}")


if __name__ == "__main__":
    main()
