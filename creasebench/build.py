"""Build the seed task set into ``tasks/``.

    python -m creasebench.build [--out tasks] [--seed 0]

Every task is checked on build: the oracle answer must score 1.0 (solved).
"""

from __future__ import annotations

import argparse
import json
import math
import random
import shutil
from pathlib import Path

import numpy as np
from shapely import affinity

from . import reference as R
from .cp import CreasePattern
from .foldability import check_local
from .generate import random_simple_folds, search_symmetric
from .graders import grade
from .layers import solve_layers
from .render import render_cp, render_silhouette
from .simulate import fold
from .tasks import Task
from .verify import verify


SEED_OFFSET = 0  # set from --seed; 0 reproduces the committed seed set


def r6(x):
    return [[round(float(a), 6), round(float(b), 6)] for a, b in x]


def poly_coords(geom) -> list:
    if geom.geom_type == "Polygon":
        return r6(geom.exterior.coords[:-1])
    return [r6(g.exterior.coords[:-1]) for g in geom.geoms]


def difficulty_for(cp: CreasePattern) -> str:
    n = cp.num_creases()
    return "easy" if n <= 4 else "medium" if n <= 16 else "hard"


# ----------------------------------------------------------------- analytic
AF_PROMPT = (
    "Below is a crease pattern (also shown as an image). Fold every crease flat and report the folded "
    "model: the folded position of every vertex and, if you can, the layer order of overlapping faces. "
    "If the pattern cannot be folded flat, say so instead.")


def analytic_task(task_id: str, cp: CreasePattern, out: Path, meta: dict, difficulty: str | None = None) -> Task:
    fold_dict = cp.to_fold(precision=10)
    cp2 = CreasePattern.from_fold(fold_dict, rebuild=False)
    rep = verify(cp2)
    ref: dict = {"foldable": rep.foldable, "reason": rep.reason}
    if rep.foldable:
        ref["folded_vertices"] = r6(rep.folded.vertices)
        ref["silhouette"] = poly_coords(rep.folded.silhouette())
        ref["face_above"] = [list(p) for p in rep.layers.face_above]
    else:
        ref["violation_vertices"] = sorted(check_local(cp2).bad_vertices())
    inputs_fold = {k: fold_dict[k] for k in ("vertices_coords", "edges_vertices", "edges_assignment",
                                              "faces_vertices")}
    inputs_fold["vertices_coords"] = r6(inputs_fold["vertices_coords"])
    t = Task(task_id, "analytic", difficulty or difficulty_for(cp2), AF_PROMPT,
             inputs={"crease_pattern": inputs_fold}, images=["cp.png"], reference=ref,
             meta={**meta, "num_creases": cp2.num_creases(), "num_faces": len(cp2.faces)})
    d = out / "analytic" / task_id
    t.save(d)
    render_cp(cp2, d / "cp.png", label_vertices=cp2.num_vertices <= 40)
    return t


def flip_one(cp: CreasePattern, rng: random.Random) -> CreasePattern:
    idx = [i for i in cp.crease_indices()]
    i = rng.choice(idx)
    asg = list(cp.assignments)
    asg[i] = "M" if asg[i] == "V" else "V"
    return CreasePattern(cp.vertices.copy(), list(cp.edges), asg, [list(f) for f in cp.faces])


def perturb_vertex(cp: CreasePattern, rng: random.Random, amount: float = 0.04) -> CreasePattern:
    interior = [i for i, (x, y) in enumerate(cp.vertices) if 1e-6 < x < 1 - 1e-6 and 1e-6 < y < 1 - 1e-6]
    v = rng.choice(interior)
    segs = []
    ang = rng.uniform(0, 2 * math.pi)
    newpos = cp.vertices[v] + amount * np.array([math.cos(ang), math.sin(ang)])
    for (a, b), asg in zip(cp.edges, cp.assignments):
        if asg == "B":
            continue
        p = newpos if a == v else cp.vertices[a]
        q = newpos if b == v else cp.vertices[b]
        segs.append((tuple(p), tuple(q), asg))
    return CreasePattern.from_segments(segs, tol=1e-9)


def global_only_failure(rng: random.Random) -> CreasePattern:
    """Locally valid (Maekawa + Kawasaki everywhere) but no valid layer order."""
    for seed in range(1000):
        g = random_simple_folds(rng.choice([3, 4]), seed=10_000 + seed)
        cp = g.cp
        for _ in range(60):
            asg = list(cp.assignments)
            for i in rng.sample(cp.crease_indices(), k=min(len(cp.crease_indices()), rng.randint(2, 4))):
                asg[i] = "M" if asg[i] == "V" else "V"
            cand = CreasePattern(cp.vertices.copy(), list(cp.edges), asg, [list(f) for f in cp.faces])
            if not check_local(cand).ok:
                continue
            if solve_layers(fold(cand)).status == "none":
                return cand
    raise RuntimeError("no global-only failure found")


def build_analytic(out: Path, rng: random.Random) -> list[Task]:
    tasks = []
    for name, (fn, desc) in R.REFERENCE.items():
        tasks.append(analytic_task(f"af-ref-{name}", fn(), out, {"source": "reference", "name": name,
                                                                 "description": desc}))
    plan = [(1, 2), (2, 3), (3, 3), (4, 3), (5, 2), (6, 2), (7, 1)]
    for n, count in plan:
        for k in range(count):
            g = random_simple_folds(n, seed=SEED_OFFSET + 1000 * n + k)
            diff = "easy" if n <= 2 else "medium" if n <= 4 else "hard"
            tasks.append(analytic_task(f"af-gen-{n}f-{k}", g.cp, out,
                                       {"source": "simple_folds", "folds": n, "seed": SEED_OFFSET + 1000 * n + k},
                                       difficulty=diff))
    # non-foldable variants
    base = random_simple_folds(3, seed=SEED_OFFSET + 77).cp
    tasks.append(analytic_task("af-bad-maekawa-0", flip_one(base, rng), out,
                               {"source": "flipped_assignment"}, "medium"))
    base = random_simple_folds(4, seed=SEED_OFFSET + 78).cp
    tasks.append(analytic_task("af-bad-maekawa-1", flip_one(base, rng), out,
                               {"source": "flipped_assignment"}, "hard"))
    tasks.append(analytic_task("af-bad-kawasaki-0", perturb_vertex(R.waterbomb_base(), rng), out,
                               {"source": "perturbed_vertex"}, "medium"))
    tasks.append(analytic_task("af-bad-global-0", global_only_failure(rng), out,
                               {"source": "global_only_failure"}, "hard"))
    return tasks


# ----------------------------------------------------------------- design from image
DI_PROMPT = (
    "The image shows the outline (silhouette) of a flat-folded origami model, folded from a unit-square "
    "sheet; the grid unit equals the side of the original paper. The outline's polygon coordinates are also "
    "given (its position and rotation are arbitrary). Design a crease pattern that folds into this shape. "
    "You are graded on the overlap (IoU) between your folded silhouette and the target, after the best "
    "rigid alignment (mirror images allowed); scale is NOT normalised.")


def design_image_task(task_id: str, solution: CreasePattern, out: Path, rng: random.Random, meta: dict,
                      difficulty: str) -> Task:
    rep = verify(solution)
    assert rep.foldable, task_id
    sil = rep.folded.silhouette()
    c = sil.centroid
    sil = affinity.rotate(sil, rng.uniform(0, 360), origin=c)
    sil = affinity.translate(sil, rng.uniform(-0.3, 0.3) - c.x + 0.5, rng.uniform(-0.3, 0.3) - c.y + 0.5)
    target = poly_coords(sil)
    checks = [{"type": "iou", "target": target, "threshold": 0.95}]
    t = Task(task_id, "design_image", difficulty, DI_PROMPT, inputs={"target_silhouette": target},
             images=["target.png"],
             reference={"checks": checks, "solution": [list(map(float, p)) + list(map(float, q)) + [a]
                                                       for p, q, a in solution.segments()]},
             meta={**meta, "target_area": sil.area})
    d = out / "design_image" / task_id
    t.save(d)
    render_silhouette(sil, d / "target.png")
    return t


def build_design_image(out: Path, rng: random.Random) -> list[Task]:
    tasks = []
    for name, diff in [("kite_base", "easy"), ("waterbomb_base", "easy"), ("preliminary_base", "medium"),
                       ("fish_base", "medium"), ("double_blintz", "medium")]:
        tasks.append(design_image_task(f"di-ref-{name}", R.REFERENCE[name][0](), out, rng,
                                       {"source": "reference", "name": name}, diff))
    for n, k, diff in [(2, 0, "easy"), (3, 1, "medium"), (4, 2, "hard"), (5, 3, "hard")]:
        g = random_simple_folds(n, seed=SEED_OFFSET + 5000 + 10 * n + k)
        tasks.append(design_image_task(f"di-gen-{n}f-{k}", g.cp, out, rng,
                                       {"source": "simple_folds", "folds": n}, diff))
    return tasks


# ----------------------------------------------------------------- design from text
def _segs(cp: CreasePattern) -> list:
    return [list(map(float, p)) + list(map(float, q)) + [a] for p, q, a in cp.segments()]


def _shape_checks(name: str) -> list[dict]:
    return {
        "fish": [{"type": "sharp_points", "min": 2}, {"type": "symmetry", "min": 0.95},
                 {"type": "extent", "min_aspect": 1.6}, {"type": "convexity", "max": 0.95}],
        "arrow": [{"type": "sharp_points", "min": 1}, {"type": "symmetry", "min": 0.95},
                  {"type": "extent", "min_aspect": 2.0}, {"type": "convexity", "max": 0.85}],
    }[name]


def _passes(checks, sil) -> bool:
    from .graders import run_check

    return all(run_check(c, sil, None)[1]["passed"] for c in checks if c["type"] != "coincident")


def build_design_text(out: Path) -> list[Task]:
    h = math.sqrt(3) / 2
    hexagon = [(0.5 + 0.5 * math.cos(a * math.pi / 3), 0.5 + 0.5 * math.sin(a * math.pi / 3)) for a in range(6)]
    house = [(0.15, 0), (0.85, 0), (0.85, 0.6), (0.5, 0.95), (0.15, 0.6)]
    accordion6 = CreasePattern.from_segments(
        [((k / 6, 0), (k / 6, 1), "V" if k % 2 else "M") for k in range(1, 6)], tol=1e-9)
    specs = [
        ("dt-corner-to-center", "easy",
         "Fold the paper so that the corner at (0, 0) lands exactly on the centre of the paper, (0.5, 0.5). "
         "The folded model must have an area of exactly 7/8 of the paper.",
         [{"type": "coincident", "points": [[0, 0], [0.5, 0.5]]}, {"type": "area", "min": 0.87, "max": 0.88}],
         CreasePattern.from_segments([((0, 0.5), (0.5, 0), "V")], tol=1e-9), {}),
        ("dt-quarter-triangle", "easy",
         "Fold the paper into a right isosceles triangle whose area is exactly one quarter of the paper.",
         [{"type": "iou", "target": [[0, 0], [1, 0], [0.5, 0.5]], "threshold": 0.97}],
         R.waterbomb_base(), {}),
        ("dt-corners-meet-square", "medium",
         "Fold the paper into a square with one quarter of the paper's area, in such a way that all four "
         "corners of the paper meet at a single point.",
         [{"type": "coincident", "points": [[0, 0], [1, 0], [1, 1], [0, 1]]},
          {"type": "area", "min": 0.245, "max": 0.255}, {"type": "rectangularity", "min": 0.98},
          {"type": "extent", "max_length": 0.51}],
         R.preliminary_base(), {}),
        ("dt-long-strip", "medium",
         "Fold the paper into a long thin rectangular strip at least 0.95 long and at most 0.2 wide.",
         [{"type": "extent", "min_length": 0.95, "max_width": 0.2}, {"type": "rectangularity", "min": 0.98}],
         accordion6, {}),
        ("dt-equilateral-triangle", "medium",
         "Fold the paper into an equilateral triangle with an area of at least 0.3.",
         [{"type": "regular_polygon", "n": 3, "min_area": 0.3, "threshold": 0.97}],
         R.fold_to_convex([(0, 0), (1, 0), (0.5, h)]), {}),
        ("dt-regular-hexagon", "hard",
         "Fold the paper into a regular hexagon with an area of at least 0.4.",
         [{"type": "regular_polygon", "n": 6, "min_area": 0.4, "threshold": 0.97}],
         R.fold_to_convex(hexagon), {}),
        ("dt-house", "medium",
         "Fold the paper into the outline of a simple house: a convex, mirror-symmetric pentagon made of a "
         "rectangular wall with a triangular roof on top. The area must be at least 0.4.",
         [{"type": "vertex_count", "min": 5, "max": 5}, {"type": "symmetry", "min": 0.97},
          {"type": "convexity", "min": 0.98}, {"type": "area", "min": 0.4, "max": 1.0}],
         R.fold_to_convex(house), {}),
        ("dt-fish", "hard",
         "Design a simple flat fish: an elongated, mirror-symmetric body with a pointed head or tail and "
         "at least one notch or fin making the outline non-convex.",
         _shape_checks("fish"), None, {"semantic": "a fish"}),
        ("dt-arrow", "hard",
         "Design an arrow: a long, mirror-symmetric shape with a pointed arrowhead at one end that is wider "
         "than the shaft behind it.",
         _shape_checks("arrow"), None, {"semantic": "an arrow"}),
    ]
    tasks = []
    for tid, diff, prompt, checks, solution, extra in specs:
        if solution is None:
            for seed in range(1, 40):
                solution = search_symmetric(lambda s, c=checks: _passes(c, s), seed)
                if solution is not None and _passes(checks, verify(solution).folded.silhouette()):
                    break
                solution = None
            assert solution is not None, tid
        ref = {"checks": checks, "solution": _segs(solution)}
        if extra.get("semantic"):
            ref["judge_subject"] = extra["semantic"]
        t = Task(tid, "design_text", diff, prompt, reference=ref,
                 meta={"semantic": bool(extra.get("semantic"))})
        t.save(out / "design_text" / tid)
        tasks.append(t)
    return tasks


# ----------------------------------------------------------------- oracle answers
def _oracle_grade(task: Task):
    ans = oracle_answer(task)
    return grade(task, ans) if ans else None


def oracle_answer(task: Task) -> str:
    fam = task.reference.get("family")
    if fam == "read-tree":
        ans = {"tree": task.reference["tree"]}
    elif fam == "read-tech":
        ans = dict(task.reference["tech"])
    elif fam == "read-color":
        ans = {"colors": task.reference["colors"]}
    elif fam == "regions":
        ans = {"regions": task.reference["regions"]}
    elif fam == "pack":
        ans = {"positions": task.reference["solution"]}
    elif fam in ("solve", "design"):
        if "solution" not in task.reference:
            return ""  # no reference design: scored against the packing bound only
        ans = {"creases": task.reference["solution"]}
    elif task.track == "analytic":
        ref = task.reference
        if not ref["foldable"]:
            ans = {"foldable": False, "violation_vertices": ref["violation_vertices"]}
        else:
            ans = {"foldable": True, "folded_vertices": ref["folded_vertices"], "face_above": ref["face_above"]}
    else:
        ans = {"creases": task.reference["solution"]}
    return "```json\n" + json.dumps(ans) + "\n```"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="tasks")
    ap.add_argument("--seed", type=int, default=0,
                    help="0 reproduces the public seed set; any other value builds a fresh private split")
    ap.add_argument("--tiers", default="basic,advanced,expert", help="comma list of basic,advanced,expert")
    ap.add_argument("--skip-oracle", action="store_true", help="build only; check later with --oracle-only")
    ap.add_argument("--resume", action="store_true", help="expert: keep already-built per-tree task folders")
    ap.add_argument("--oracle-only", nargs="*", metavar="ID_PREFIX",
                    help="no build: re-run the oracle self-check on saved tasks (optionally only these id prefixes)")
    args = ap.parse_args(argv)
    tiers = args.tiers.split(",")
    if args.oracle_only is not None:
        from .tasks import load_tasks

        return _oracle_check(load_tasks(args.out, ids=args.oracle_only or None), Path(args.out))
    global SEED_OFFSET
    SEED_OFFSET = 1_000_000 * args.seed
    out = Path(args.out)
    rng = random.Random(args.seed)
    tasks: list[Task] = []
    if "basic" in tiers:
        for sub in ("design_image", "design_text"):
            shutil.rmtree(out / sub, ignore_errors=True)
        for d in (out / "analytic").glob("af-*"):
            shutil.rmtree(d)
        basic = build_analytic(out, rng) + build_design_image(out, rng) + build_design_text(out)
        for t in basic:
            t.meta["tier"] = "basic"
            t.save(t.root)
        tasks += basic
    if "advanced" in tiers:
        from .build_advanced import build_advanced

        for sub in ("read", "solve", "pack", "design"):
            for d in (out / sub).glob("adv-*"):
                shutil.rmtree(d)
        for d in (out / "analytic").glob("adv-*"):
            shutil.rmtree(d)
        tasks += build_advanced(out, seed=args.seed)
    if "expert" in tiers:
        from .expert.build import build_expert

        if not args.resume:
            for d in out.glob("*/expert-*"):
                shutil.rmtree(d)
        tasks += build_expert(out, seed=args.seed, resume=args.resume)
    from .providers.baselines import UnfoldedProvider

    for t in tasks:  # record the trivial baseline's raw score so grading can rescale it to 0
        if t.meta.get("tier") == "advanced":
            continue
        t.reference.pop("baseline_score", None)
        t.reference["baseline_score"] = round(grade(t, UnfoldedProvider().run(t, "", [], None, 0).text)["score"], 6)
        t.save(t.root)
    if args.skip_oracle:
        print(f"built {len(tasks)} tasks into {out}/ (oracle check skipped)")
        return
    _oracle_check(tasks, out)


def _oracle_check(tasks, out) -> None:
    bad = []
    from concurrent.futures import ProcessPoolExecutor

    with ProcessPoolExecutor(max_workers=4) as ex:  # expert references take minutes each to verify
        grades = list(ex.map(_oracle_grade, tasks))
    for t, g in zip(tasks, grades):
        if g is None:
            print(f"--   {t.id:32} {t.difficulty:6} (no reference design; bound only)")
            continue
        if t.reference.get("family") == "design":
            # reference designs need not reach the packing bound; they must solve the task
            status = "ok" if g.get("solved") else "FAIL"
        else:
            status = "ok" if g.get("solved") and g["score"] > 0.999 else "FAIL"
        if status != "ok":
            bad.append(t.id)
        print(f"{status:4} {t.id:32} {t.difficulty:6} score={g['score']:.3f}")
    print(f"built {len(tasks)} tasks into {out}/")
    if bad:
        raise SystemExit(f"oracle failed on: {bad}")


if __name__ == "__main__":
    main()
