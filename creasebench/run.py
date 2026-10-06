"""Run a model on CreaseBench and score it.

    python -m creasebench.run --provider anthropic --model claude-opus-5-5 --mode closed
    python -m creasebench.run --provider openai --model gpt-x --base-url ... --mode agentic
    python -m creasebench.run --provider oracle        # sanity check: should score 1.0
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .graders import grade
from .prompts import build_prompt
from .providers import PythonSandbox, make_provider
from .tasks import Task, load_tasks


def run_one(task: Task, provider, args) -> dict:
    agentic = args.mode == "agentic"
    prompt = build_prompt(task, agentic=agentic, image_only=args.image_only)
    images = task.image_paths() if args.images else []
    if args.image_only and task.track == "design_image":
        images = task.image_paths()
    sandbox = PythonSandbox(task) if agentic else None
    t0 = time.time()
    try:
        res = provider.run(task, prompt, images, sandbox, args.max_steps)
    finally:
        if sandbox is not None:
            sandbox.close()
    g = grade(task, res.text)
    rec = {"id": task.id, "tier": task.meta.get("tier", "basic"), "track": task.track,
           "family": task.reference.get("family"), "difficulty": task.difficulty, "score": g["score"],
           "efficiency": g.get("efficiency"),
           "solved": bool(g.get("solved")), "grade": g, "response": res.text, "error": res.error,
           "usage": res.usage, "tool_calls": res.tool_calls, "seconds": round(time.time() - t0, 1)}
    if args.judge_provider and task.reference.get("judge_subject"):
        from .judge import judge

        rec["judge"] = judge(task, res.text, args.judge_provider, args.judge_model)
    if args.save_transcripts:
        rec["transcript"] = res.transcript
    return rec


def summarize(records: list[dict]) -> str:
    by = defaultdict(list)
    for r in records:
        tier = r.get("tier", "basic")
        by[(tier, r["track"], r["difficulty"])].append(r)
        by[(tier, r["track"], "all")].append(r)
        by[(tier, "all", "all")].append(r)
    order = {"easy": 0, "medium": 1, "hard": 2, "all": 3}
    lines = ["| tier | track | difficulty | n | mean score | solved | mean efficiency |",
             "|---|---|---|---|---|---|---|"]
    for (tier, track, diff), rs in sorted(by.items(), key=lambda kv: (kv[0][0], kv[0][1] == "all", kv[0][1],
                                                                      order[kv[0][2]])):
        mean = sum(r["score"] for r in rs) / len(rs)
        solved = sum(r["solved"] for r in rs)
        effs = [r["efficiency"] for r in rs if r.get("efficiency") is not None]
        eff = f"{sum(min(e, 1.0) for e in effs) / len(effs):.3f}" if effs else "-"
        lines.append(f"| {tier} | {track} | {diff} | {len(rs)} | {mean:.3f} | {solved}/{len(rs)} | {eff} |")
    judged = [r["judge"]["judge_score"] for r in records if r.get("judge") and r["judge"].get("judge_score") is not None]
    if judged:
        lines.append(f"\nSemantic judge (n={len(judged)}): mean {sum(judged) / len(judged):.3f}")
    return "\n".join(lines)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provider", required=True, choices=["anthropic", "openai", "oracle", "unfolded", "heuristic"])
    ap.add_argument("--model")
    ap.add_argument("--base-url", help="OpenAI-compatible endpoint")
    ap.add_argument("--effort", help="reasoning effort passed to the provider")
    ap.add_argument("--mode", choices=["closed", "agentic"], default="closed")
    ap.add_argument("--max-steps", type=int, default=20, help="tool-call rounds in agentic mode")
    ap.add_argument("--tasks-dir", default="tasks")
    ap.add_argument("--tracks", default="af,dt,di,read,solve,pack,design",
                    help="comma list of af,dt,di,read,solve,pack,design")
    ap.add_argument("--tiers", default="basic,advanced", help="comma list of basic,advanced")
    ap.add_argument("--ids", nargs="*", help="task ids or id prefixes")
    ap.add_argument("--difficulty", nargs="*", choices=["easy", "medium", "hard"])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--no-images", dest="images", action="store_false", help="text-only prompts")
    ap.add_argument("--image-only", action="store_true",
                    help="design_image: show only the picture, not the target polygon coordinates")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--judge-provider", choices=["anthropic", "openai"])
    ap.add_argument("--judge-model")
    ap.add_argument("--save-transcripts", action="store_true")
    ap.add_argument("--out", help="results directory (default results/<provider>-<model>-<mode>-<time>)")
    args = ap.parse_args(argv)

    tasks = load_tasks(args.tasks_dir, tracks=args.tracks.split(","), ids=args.ids, difficulty=args.difficulty,
                       tiers=args.tiers.split(","))
    if args.limit:
        tasks = tasks[: args.limit]
    if not tasks:
        raise SystemExit("no tasks selected (did you run `python -m creasebench.build`?)")
    provider = make_provider(args.provider, args.model, args.base_url, args.effort)
    name = f"{args.provider}-{args.model or 'default'}-{args.mode}-{time.strftime('%Y%m%d-%H%M%S')}"
    out = Path(args.out or Path("results") / name.replace("/", "_"))
    out.mkdir(parents=True, exist_ok=True)
    (out / "config.json").write_text(json.dumps(vars(args), indent=1))
    records = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool, (out / "results.jsonl").open("w") as f:
        for rec in pool.map(lambda t: run_one(t, provider, args), tasks):
            records.append(rec)
            f.write(json.dumps(rec) + "\n")
            f.flush()
            flag = "+" if rec["solved"] else " "
            print(f"[{flag}] {rec['id']:32} score={rec['score']:.3f}" + (f"  ({rec['error']})" if rec["error"] else ""))
    summary = summarize(records)
    (out / "summary.md").write_text(summary + "\n")
    print("\n" + summary + f"\n\nresults written to {out}/")


if __name__ == "__main__":
    main()
