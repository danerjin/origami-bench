# Origami Bench

A benchmark that tests the **spatial and analytical reasoning** of general-purpose LLM agents
through origami. It works much like PCB-design benchmarks: the model has to produce a precise
geometric artifact, and a simulator, not an LLM, decides whether the artifact works.

| Track | Input | Output | Graded by |
|---|---|---|---|
| **Analytic folding** (`af`) | crease pattern (FOLD JSON + image) | folded vertex positions (+ layer order), or "not foldable" | exact comparison with the simulated fold |
| **Design from text** (`dt`) | a description ("fold an equilateral triangle", "a fish") | crease pattern | folding the answer, then checking a geometric rubric (+ optional vision judge) |
| **Design from image** (`di`) | silhouette of a folded model (image + polygon) | crease pattern | folding the answer, then silhouette IoU against the target |

Every answer is graded by **actually folding it**. A design answer must be flat-foldable: it must
pass Maekawa's and Kawasaki's theorems at every vertex, and a SAT solver must find a valid,
non-self-intersecting layer order. Only then is its folded shape compared with the goal.

## Quickstart

```bash
pip install -e ".[anthropic,openai,dev]"
python -m creasebench.build            # regenerate tasks/ (already committed) and self-check them
pytest                                   # 41 tests

# sanity checks: the oracle should score 1.0, the trivial baseline 0.0
python -m creasebench.run --provider oracle
python -m creasebench.run --provider unfolded

# evaluate a model
python -m creasebench.run --provider anthropic --model claude-opus-5-5 --mode closed
python -m creasebench.run --provider anthropic --model claude-opus-5-5 --mode agentic
python -m creasebench.run --provider openai --model <name> --base-url <url> --mode agentic
```

Useful flags: `--tracks af,di`, `--difficulty hard`, `--ids af-gen`, `--limit 5`,
`--no-images` (text only), `--image-only` (design-from-image with just the picture),
`--judge-provider anthropic` (semantic judge for the fish/arrow tasks), `--save-transcripts`.
Results are written to `results/<run>/{results.jsonl,summary.md}`.

### Modes

- **closed**: one response, no tools. Pure reasoning.
- **agentic**: the model gets a `python` tool (numpy and shapely, with the task inputs as files)
  for up to `--max-steps` rounds. The benchmark's own simulator is *not* exposed, so the agent
  has to build whatever folding machinery it needs. Model-written code runs in a local
  subprocess, which is **not** a security boundary. Run agentic evaluations in a container.

### Inspecting things by hand

```bash
python -m creasebench verify my_answer.json --render out   # flat-foldability report + PNGs
python -m creasebench grade tasks/design_text/dt-house reply.txt
```

## Seed task set (49 tasks)

- **Analytic (31):** 11 traditional folds and bases (book, blintz, kite, waterbomb, preliminary,
  fish, double blintz, ...); 16 procedurally generated patterns from 1–7 random simple folds;
  4 *non-foldable* patterns: Maekawa violations, a Kawasaki violation, and one that passes
  every local test but has no valid layer order.
- **Design from image (9):** silhouettes of reference bases and generated models, randomly
  rotated and translated.
- **Design from text (9):** precise shape goals (corner to centre, quarter-area triangle, square
  where all corners meet, long strip, equilateral triangle, regular hexagon, house) and two
  semantic goals (fish, arrow).

The build step proves every task is solvable: the hidden reference answer must score 1.0. It
also records the score of a trivial baseline (paper left unfolded, or a single book fold), which
grading rescales to 0.

## Scoring at a glance

Each task gets a `score` in [0, 1] and a boolean `solved`. **Report the solved rate as the
headline number**, broken down by track and difficulty. The mean score is a secondary metric.
Full formulas, tolerances and answer formats are in [`docs/SPEC.md`](docs/SPEC.md).

## Layout

```
creasebench/
  cp.py           crease patterns: planar arrangement, faces, FOLD I/O
  foldability.py  Maekawa / Kawasaki
  simulate.py     folded geometry (composition of reflections)
  layers.py, sat.py  global flat-foldability: layer-order constraints + DPLL solver
  verify.py       one-call verification
  generate.py     random simple-fold generator, symmetric search
  reference.py    traditional bases; fold-to-convex-polygon constructor
  compare.py      rigid alignment, silhouette IoU, shape features
  graders.py      per-track graders
  prompts.py      shared conventions + answer formats
  providers/      anthropic, openai-compatible, oracle and unfolded baselines
  build.py        builds tasks/ ; run.py runs a benchmark ; judge.py optional VLM judge
tasks/            the committed seed set (task.json + images)
tests/
```
