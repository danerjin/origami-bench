# CreaseBench: Expert Crease-Pattern Analysis and Design, Verified by Folding

CreaseBench tests whether general-purpose LLM agents can do **real origami design**. That means
the expert techniques used for intricate models: tree theory and circle/river packing, box
pleating on N-grids, 22.5° design, Pythagorean stretches, grafting and two-tone color change.
The constraint is always the same: **one uncut square sheet**.

It is graded the way a PCB benchmark runs DRC and simulation on a netlist. Every answer is
**folded for real**:

1. **Local checks:** Maekawa, Kawasaki and crimp/big-little-big.
2. **Global layer order:** solved by Jason Ku's flat-folder, vendored (MIT).
3. **Structural measurement:** the folded state is measured, not shown to a judge. That covers
   the base's stick-figure tree (via a Reeb graph), the scale factor it achieves, the design
   system it uses, and which paper side shows at each flap.

The headline scores never depend on an LLM or VLM judge.

## Tiers and task families

| Tier | Family (track) | Input → output | Graded by |
|---|---|---|---|
| basic | `af` analytic folding | crease pattern → folded vertices + layer order, or "not foldable" | exact geometry after rigid alignment; layer claims checked by solver |
| basic | `dt` / `di` shape design | text / silhouette → crease pattern | fold → rubric / IoU |
| **advanced** | `read-tree` | expert CP (22.5°, tilings, grafts, TreeMaker, box pleating) → tree of its base | isomorphism + lengths |
| advanced | `read-tech` | CP → box pleating grid N / 22.5° / Pythagorean-stretch triples | exact analyzers |
| advanced | `read-color` | CP on two-tone paper → side visible at each flap tip | layer-order analysis (only order-independent tips) |
| advanced | `af` (adv) | advanced CP → folded geometry; or find an injected defect (flipped crease, moved vertex, locally valid but globally impossible) | exact |
| advanced | `solve` | expert CP geometry with every crease unassigned → full M/V | flat-folder |
| advanced | `pack` | target tree → flap-tip positions (circle or box-pleating square packing) | scale m / best known packing |
| advanced | `design` | target tree (lizard, beetle, scorpion, spider, deer with antlers, dragon, crab, bird...) → CP | fold → extract tree → **efficiency = m / best known**; optional technique (22.5°, BP grid, Pythagorean stretch), grafting, color-change and layer limits |

**Scale m.** A design realizes a target tree at scale m when its flap tips match the target's
leaves so that the tree distance between every pair of tips is at least m times the target
distance. This is Lang's path condition. Efficiency compares m with the best circle/river
packing found by multi-start optimization, or with a reference design, whichever is higher.
Optimal packing is NP-hard, so efficiency is reported relative to that best-known value rather
than a proven optimum.

## The committed task set (135 tasks)

| Tier | Family | n | Notes |
|---|---|---|---|
| basic | analytic / design_text / design_image | 31 / 9 / 9 | the v0.1 warm-up set |
| advanced | `read-tree` / `solve` | 17 / 17 | one per certified source: 22.5° bases and tilings, border grafts, 10 Box Pleating Studio designs (incl. GOPS 3-4-5 and Kamiya stretches, up to 305 creases), 2 TreeMaker bases |
| advanced | `read-tech` / `read-color` | 16 / 3 | box-pleating grid, 22.5°, stretch triples; two-tone colour at flap tips |
| advanced | `af` (folding + defects) | 8 | exact folds and injected defects: flipped crease, moved vertex, locally valid but globally impossible |
| advanced | `pack` | 6 | circle (L2) and box-pleating (L∞) packing of semantic trees |
| advanced | `design` | 19 | semantic trees (lizard, beetle, scorpion, spider, deer, bird, crab, dragon), trees of generated bases, 22.5° / box-pleat (≤ N grid) / Pythagorean-stretch styles, border grafting, colour change, composite |

The build self-check passes every task that has a reference answer: 49/49 basic and 78/86
advanced. The remaining 8 advanced design tasks have no reference design, so they are scored
against the packing bound alone. The non-LLM `heuristic` provider reaches 0.68 mean efficiency
on `pack` and 0 elsewhere.

## Quickstart

```bash
pip install -e ".[anthropic,openai,dev]"     # Node.js >= 18 recommended (flat-folder); falls back to Python
python -m creasebench.build                   # rebuild tasks/ and self-check every reference answer
pytest

python -m creasebench.run --provider oracle      # reference answers: 1.0 wherever a reference exists
python -m creasebench.run --provider unfolded    # trivial baseline: 0
python -m creasebench.run --provider heuristic   # non-LLM baseline (edge-flap packing)

python -m creasebench.run --provider anthropic --model claude-opus-5-5 --mode agentic --tiers advanced
python -m creasebench.run --provider openai --model <name> --base-url <url> --mode closed
```

**Modes.** `closed` is a single response. `agentic` gives the model a Python tool (numpy and
shapely) for up to `--max-steps` rounds; that is the realistic way to write a 500-crease
pattern. Model code runs in a local subprocess, so use a container.

**Offline / external agents.** To evaluate an agent that the runner can't call directly
(a coding agent, a human, another harness), export the prompts, let the agent write
`answer.txt` into each task folder, then grade the folder:

```bash
python -m creasebench.export --out eval/ --ids adv-design-lizard adv-pack-l2-lizard [--agentic]
# ... agent writes eval/<task_id>/answer.txt ...
python -m creasebench.run --provider file --answers eval/ --ids adv-design-lizard adv-pack-l2-lizard
```

The export contains only the prompt, images and inputs, never reference answers.

## Where the crease patterns come from

Every shipped crease pattern is **generated**. Origami designers hold copyright on their crease
patterns, so none are scraped. Each generated pattern is certified flat-foldable before use.

| Generator | Produces | Notes |
|---|---|---|
| `gen/bases22.py` | bird base and other 22.5° modules; mirror and mixed tilings | exact Q(√2) geometry; M/V found by the solver |
| `gen/graft.py` | strip and border grafts; point grafts at strip crossings | the border graft with its edge folded back gives a color change |
| `gen/defects.py` | single defects for error-finding tasks | |
| `gen/bpstudio/` | box-pleated layouts with Kamiya / GOPS stretch gadgets | headless driver for Box Pleating Studio (Mu-Tsun Tsai, MIT) plus pleat completion |
| `gen/treemaker/` | tree-method bases (universal molecule) | optional; a build script compiles Robert Lang's TreeMaker 5 (GPL) locally; only generated outputs ship |

## Related work

| Work | What it is | How it grades |
|---|---|---|
| **OrigamiBench** (Agarwal et al., LM4Plan @ ICML 2026) | interactive environment in which vision models add creases toward a target image | Flat-Folder validity; IoU and CLIP similarity |
| **COrigami** (Zahavy et al., DeepMind 2026) | text → stick figure → box-pleated base → shaping; an algorithmic packer and solver do the crease work | VLM judge; flat-foldability by construction |
| **OrigamiSpace** (NeurIPS 2025) | multiple-choice spatial reasoning, plus image → CP code | Hausdorff and topology similarity |
| **GamiBench** (AAAI 2026 workshops) | multiple choice on simple CPs, including impossible ones | exact match |

COrigami reports that fine-tuned LLMs writing crease patterns directly plateau near 60%
flat-foldability, and that automated TreeMaker builds succeeded on 1.1% of complex stick
figures. CreaseBench asks the agent to do the expert work itself: packing, river routing,
stretches and M/V assignment. It scores **efficiency**, which COrigami deliberately trades away,
and it adds techniques COrigami lists as future work (Pythagorean stretches, level shifters),
reading tasks on expert-scale patterns, and exact answers.

## Layout

```
creasebench/
  cp.py, foldability.py, simulate.py   crease patterns, local checks (incl. crimp), folding
  ffolder/                             vendored flat-folder (MIT) + Node driver;  verify.py: backends
  layers.py, sat.py                    pure-Python layer-order solver (fallback / cross-check)
  tree.py, treefit.py, packing.py      Reeb-graph tree extraction, scale factor, packing bounds
  style.py, color.py                   technique detection, grafting check, two-tone colours
  gen/                                 generators (22.5° modules, grafts, defects, BP Studio, TreeMaker)
  trees.py                             semantic target trees
  build.py, build_advanced.py          task builders with oracle self-check
  graders.py, advanced.py, prompts.py  grading and prompts;  run.py runner;  providers/
tasks/                                 the committed task set
docs/SPEC.md                           full specification
```
