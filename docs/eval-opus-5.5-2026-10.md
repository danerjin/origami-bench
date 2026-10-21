# CreaseBench: Claude Opus 5.5 pilot evaluation (October 2026)

A first run of a frontier model on a 24-task representative subset (8 basic, 16 advanced), in two
settings:

- **closed:** a single reply, no code;
- **agentic:** the model may write and run Python (numpy, shapely) in its task folder.

Every answer was graded by the normal CreaseBench pipeline (`creasebench.run --provider file`).
Answers are folded with flat-folder, and their trees and colours are measured.

## How it was run (read this before quoting numbers)

- **Harness:** each task was given to a separate Claude Code subagent running Opus 5.5. The
  subagent got the exported `prompt.md`, the images and the input JSON
  (`python -m creasebench.export`). It wrote its final reply to `answer.txt`.
  - The model therefore ran with Claude Code's system prompt and tools, not the bare API runner.
  - The numbers are indicative, not an official API result.
- **Isolation was by instruction only:**
  - Agents were told not to read the repository or import `creasebench`.
  - Four closed-book agents admitted to one `ls` of their own task folder. It listed file names
    only.
  - One agentic agent used `pysat`, a general SAT solver that was installed in the container, for
    layer ordering. That is allowed: only origami libraries were off limits.
- **One sample per task, no retries.** Agentic runs were capped at about 20 commands by
  instruction.
- **Grading fix found by this run:** the first grading pass exposed a bug in the read-tree
  references.
  - `base_tree` chose the projection axis with the largest *total* length. Tilted axes add short
    projection stubs that inflate that total, so the references were wrong. The bird base, for
    example, became corners of 0.462 plus 0.079 stubs instead of four flaps of 0.5.
  - The model's answers were the textbook trees.
  - The axis rule is now "maximize the total length of real flaps (leaf edges ≥ 20% of the
    longest flap on any axis)". It picks the expected axis on every uniaxial source.
  - All 17 read-tree tasks were regenerated, and they pass the oracle self-check.
  - Design and colour targets keep their old derivation. A target only has to be realizable by
    its reference, so they were not affected.
  - The scores below use the corrected references.
  - The read-tech format now also states that a pattern with stretch gadgets is not `box_pleat`.
    The old wording contradicted the analyzer. It caused the closed-book miss on
    `adv-read-tech-bp-stretch-gops-13`, which is graded here with the original prompt.

## Results

| | closed | agentic |
|---|---|---|
| mean score (24 tasks) | **0.957** | **0.920** |
| solved | 22/24 | 22/24 |
| basic tier (8) | 0.974 | 0.974 |
| advanced tier (16) | 0.948 | 0.893 |
| mean design efficiency (m / best known) | 0.932 | 0.851 |

Mean score by family:

| family | n | closed | agentic |
|---|---|---|---|
| basic analytic folding | 4 | 0.949 | 0.949 |
| basic text / image design | 4 | 1.000 | 1.000 |
| adv. folding + defect finding | 2 | 1.000 | 1.000 |
| adv. M/V solve | 2 | 1.000 | 1.000 |
| adv. packing (L2, L∞) | 2 | 1.000 | 1.000 |
| adv. read-tech | 2 | 0.900 | 1.000 |
| adv. read-tree | 3 | 0.883 | 0.700 |
| adv. read-color | 1 | 1.000 | 0.778 |
| adv. design (lizard, 22.5° star, BP three-flap, colour change) | 4 | 0.932 | 0.851 |

### Per task

| task | closed | agentic | notes |
|---|---|---|---|
| af-ref-waterbomb_base | 1.000 | 1.000 | |
| af-gen-3f-1 | 1.000 | 1.000 | |
| af-gen-6f-0 | 0.796 | 0.796 | geometry exact; the layer order was wrong (closed) or inconsistent (agentic) |
| af-bad-global-0 | 1.000 | 1.000 | correctly called globally unfoldable |
| di-ref-fish_base / di-gen-4f-2 | 1.000 / 1.000 | 1.000 / 1.000 | |
| dt-equilateral-triangle / dt-corners-meet-square | 1.000 / 1.000 | 1.000 / 1.000 | |
| adv-read-tree-bird | 1.000 | 1.000 | 4 flaps of 0.5 + the 0.207 centre point |
| adv-read-tree-bp-star4-16 | 1.000 | 0.100 | agentic reported 16 extra 1/16 "pleat" stubs |
| adv-read-tree-tm-lizard (TreeMaker) | 0.650 | 1.000 | closed: right leaves and lengths, wrong branching |
| adv-read-tech-bp-stretch-gops-13 | 0.800 | 1.000 | closed called it box-pleated (prompt ambiguity, now fixed) |
| adv-read-tech-bird-border | 1.000 | 1.000 | |
| adv-read-color-bird-border | 1.000 | 0.778 | |
| adv-af-bird | 1.000 | 1.000 | exact folded geometry and layer order |
| adv-bug-flip-bp-lizard-32 | 1.000 | 1.000 | found the flipped crease in a 32-grid BP lizard |
| adv-solve-bird / adv-solve-bp-three-flap-16 | 1.000 / 1.000 | 1.000 / 1.000 | |
| adv-pack-l2-lizard | 1.000 | 1.000 | m = 0.1111 (bound 0.1112) |
| adv-pack-linf-spider | 1.000 | 1.000 | m = 1/12 (bound 1/12) |
| adv-style-22_5-star4 | 1.000 | 1.000 | 22.5° bird base, m = 0.5 |
| adv-design-lizard | 0.900 | 0.642 | closed: 15-crease pleated strip, m = 0.100 / 0.111 |
| adv-style-bp-three-flap-16 | 0.966 | 0.966 | 6–8 creases on a 2-grid; matches the reference |
| adv-color-bird-border | 0.861 | 0.796 | colour change met; efficiency is the loss |

## What we learned

1. **The model is strong on this subset.** It solves almost every analysis task, including:
   - exact folding of a 22.5° base with its layer order;
   - finding a single flipped crease among about 300 in a box-pleated lizard;
   - M/V assignment;
   - reading the design system and the Pythagorean triple of a GOPS stretch.

   On packing it reaches the best known bounds.
2. **Design efficiency is where the scores spread.**
   - The best answer was a closed-book lizard: a pleated strip with reverse-folded ends that
     reaches 90% of the circle-packing bound in 15 creases. It is certified flat-foldable and
     scored by measuring the folded tree.
   - The agentic lizard took 26 tool calls and 23 minutes, yet scored lower (64%).
   - Code access did not help design here; it mostly went to self-verification.
3. **Several tasks are too easy, so the subset is near saturation:**
   - The box-pleating style task accepts any grid up to 16. A 6-crease 2-grid pattern matches the
     reference efficiency.
   - The solve and pack tasks for textbook bases can be answered from memory.

   The hard part of the benchmark is not in this subset. That covers the eight semantic designs
   with no reference (beetle, scorpion, spider, deer, crab, dragon, BP lizard, stretch beetle),
   larger solve and read instances, and the composite tasks.
4. **The run found a real grading bug** (read-tree axis), now fixed. The model's answers were
   right and the reference was wrong. Reading the agents' disagreements with the references is a
   useful audit.

## Recommended next steps

- Run the full 135-task set through the API runner (`--provider anthropic`) with several samples
  per task.
- Harden the easy families:
  - require a minimum grid, flap count and layer count in style tasks;
  - use larger, generated-only bases for solve, read-tree and af;
  - move the bound-only semantic designs into the headline score.
- Add a check that graders agree with the oracle under alternative but equivalent answers. For
  example, short stubs could be tolerated in read-tree, and ambiguous layer orders already are.

Raw results: `results/opus-5.5-closed/` and `results/opus-5.5-agentic/`. Each holds
`results.jsonl` with the full replies and grade details, plus `summary.md`.

## Follow-up: the hard split (14 tasks the pilot did not sample)

The pilot was near saturation, so the next run covered the hardest committed tasks. Setup and
caveats are as above: one sample per task, isolation by instruction only. The read-tree grader
now ignores leaf stubs shorter than 15% of the longest flap, on both sides.

The 14 tasks:

- **Designs (8):** the bound-only semantic designs (beetle, scorpion, spider, deer, crab,
  dragon, BP lizard, stretch beetle; 6-12 flaps).
- **Composites (2):** the graft and colour/22.5° composite tasks.
- **Solves (2):** a 305-crease BP lizard and a 154-crease GOPS stretch.
- **Tree readings (2):** a Kamiya stretch and a bird 2×2 tiling.

| | closed | agentic |
|---|---|---|
| mean score (14 tasks) | **0.643** | **0.652** |
| solved | 9/14 | 11/14 |
| designs (10), mean score | 0.632 | 0.595 |
| six semantic animals, mean efficiency | 0.647 | 0.710 |
| analysis (4: two solves, two tree readings) | 0.669 | 0.794 |

| task | closed | agentic | notes |
|---|---|---|---|
| adv-design-beetle | 0.758 | 0.758 | |
| adv-design-scorpion | 0.438 | 0.618 | agentic: annealing search over pleat grids, 158 creases |
| adv-design-spider | 0.703 | 0.795 | agentic: 342 creases |
| adv-design-deer | 0.703 | 0.685 | |
| adv-design-crab | 0.780 | 0.780 | |
| adv-design-dragon | 0.503 | 0.622 | |
| adv-style-bp-lizard (BP, grid ≤ 32) | 0.750 | 0.900 | |
| adv-style-stretch-beetle (must use a Pythagorean stretch) | 0.000 | 0.000 | neither design contains a stretch; agentic tried 3-4-5 layouts but found no flat-foldable assignment and fell back |
| adv-composite-bird-border (22.5° + colour) | 0.821 | 0.796 | |
| adv-graft-bird-border | 0.866 | 0.000 | agentic: three mountains around two equal 22.5° sectors violate the crimp (big-little-big) rule; the agent's own solver missed it |
| adv-solve-bp-lizard-32 (305 creases) | 1.000 | 1.000 | |
| adv-solve-bp-stretch-gops-14 (154 creases) | 0.500 | 1.000 | closed: locally valid, but no global layer order exists |
| adv-read-tree-bp-stretch-kamiya-13 | 1.000 | 1.000 | |
| adv-read-tree-bird-2x2 | 0.175 | 0.175 | the tiling has no single base axis, so this reference is debatable (see below) |

What this shows:

1. **The benchmark has headroom; the pilot subset did not.**
   - **Score drop:** on the hard split the score falls from 0.96 to about 0.65.
   - **Design gap:** design efficiency on 9-12 flap animals sits at 0.44-0.80 of the best known
     packing, versus 0.9-1.0 on 3-6 flap targets.
   - **Constraint failures:** constrained techniques fail outright. Both settings got the
     Pythagorean stretch task wrong, and the closed run broke the global layer order on a
     154-crease solve.
2. **A recurring agent strategy: "fold the whole stack" designs.**
   - **The strategy:** agents accordion-pleat the entire sheet in x and y, then fold the stack
     diagonally. That turns lattice points into flap tips, and every fold goes through all
     layers, which guarantees a valid layer order.
   - **It is graded honestly:** these designs fold, and the grader measures them correctly. Across
     every axis and every leaf pair, tree distances never exceed paper distances. They reach
     about 0.6-0.8 of the packing bound.
   - **Why it matters:** this is a cheap general strategy that is not real tree-theory design.
     Hardening should make it uncompetitive, for example with layer-count caps or larger
     targets, rather than ban it.
3. **Agentic help is mixed.**
   - **Where code helped:** the large solve, the scorpion and dragon searches, and the BP lizard.
   - **Where it hurt:** one agent trusted its own incomplete flat-foldability checker and
     submitted a pattern with a crimp violation.
4. **Weak task:** `adv-read-tree-bird-2x2` (and the other 2×2 tilings) are not uniaxial bases.
   Their "tree" depends on an arbitrary axis choice, so they should move to `core` or be
   dropped from read-tree.

**Decision (per the plan): targeted hardening, not a rewrite.** The hard split scores about
0.65, which is between the "fix only saturating families" band (0.4-0.6) and the "harden
everything" threshold (0.8). So:

- make the `hard` split the headline;
- drop tilings from read-tree;
- add larger (14-24 flap) semantic targets with layer caps, so whole-stack pleating stops
  competing;
- give style tasks a minimum grid.

Raw results: `results/opus-5.5-hard-closed/` and `results/opus-5.5-hard-agentic/`.

## v0.3 changes after this evaluation

The task set was hardened following the decision above (see `docs/SPEC.md` §7.8):

- **Tasks:** 2×2 tilings were removed from read-tree, and six 14-24 flap animal designs were
  added.
- **Style tasks:** they now carry grid windows. Box-pleating tasks require N ≥ half the
  reference grid, and the bound-only BP lizard requires 8 ≤ N ≤ 32. A second Pythagorean-stretch
  task was added.
- **New field:** `beats_square_packing`, an unscored milestone.

These hard-split answers were regraded against the rebuilt tasks, without re-running the model:

| | closed | agentic |
|---|---|---|
| mean score (13 tasks; bird-2x2 read-tree removed) | 0.621 | 0.689 |

- **The one change.** The closed-book BP lizard used a 4-grid. That is now outside the 8-32
  window, so the task scores 0. The answer was written under the old prompt, which had no
  minimum.
- **Square-packing milestone.** Only the closed-book graft beats it, by reusing the grafted bird
  base. No from-scratch design does.
- **Baselines.** The heuristic and unfolded baselines score 0 on all 47 hard tasks.
- **Not yet run.** The six new large designs have not been evaluated.

## Large designs (14-24 flaps) and a grader fix

These are the six new animal targets plus `adv-style-stretch-lizard`. Setup is the same: one
sample per task, run as Claude Code subagents.

| task | flaps | closed | agentic |
|---|---|---|---|
| adv-design-stag_beetle | 15 | 0.618 (36 creases) | 0.618 (36) |
| adv-design-mantis | 14 | 0.686 (96) | **0.895** (129); beats square packing |
| adv-design-lobster | 17 | 0.466 (65) | 0.388 (96) |
| adv-design-centipede | 24 | 0.492 (176) | 0.738 (434) |
| adv-design-pegasus | 14 | 0.589 (48) | 0.000 (312): layer order undetermined within the budget |
| adv-design-tarantula | 14 | 0.709 (60) | 0.000 (1104): layer order undetermined within the 180 s budget; flat-folder certifies it given 546 s |
| adv-style-stretch-lizard | 6 | 0.000: no stretch | 0.900 |
| **mean** | | **0.508** | **0.505** |

What happened:

- **Most agents chose safety over efficiency.** Most agents explicitly picked a "provably
  foldable" grid design: a map fold or a whole-stack accordion with a diagonal fold. They said a
  tree-specific design would be too risky without a folding checker. These designs reach 0.4-0.7
  of the packing bound.
- **The best answer used an optimizer.** The agentic mantis tuned pleat widths and the
  leaf-to-tip assignment by annealing and reached 0.895. It is the only from-scratch design so
  far that beats the square-packing milestone.
- **Large-pattern answers hit the verifier budget.** Two agentic answers (312 and 1104 creases)
  scored 0 because the layer-order solver ran out of budget. Answers have to be verifiable
  within the grading budget. The tarantula does fold, so the budget, or a faster check for
  whole-stack patterns, is worth revisiting.
- **The stretch check is gameable.** The agentic stretch lizard passed the Pythagorean-stretch
  check with a 3-4-5 pleat that it describes as "not a true stretch", added only to satisfy the
  rule. The style check confirms that 3-4-5 directions occur, not that the stretch does
  anything. Tightening it, for example by requiring the stretch to change the flap layout, is
  open work.
- **Grader fix found by this run.**
  - **Symptom:** both stag-beetle answers first scored 0 ("does not realize the target tree").
  - **Cause:** they are map folds whose creases are all diagonal. Candidate axes came only from
    crease directions, so the 0°/90° axis, along which the base's 16 flaps lie, was never tried.
  - **Fix:** `candidate_axes` now always includes 0°, 45°, 90° and 135°. A regression test
    covers it.
  - **Side effects:** rebuilding with the fix changes no committed task. All Opus answers were
    regraded with it, and only the stag beetles changed (0 → 0.618).

### Hard split, all Opus 5.5 answers so far (final grader)

| | closed | agentic |
|---|---|---|
| hard-split tasks graded | 25 | 25 |
| mean score | **0.656** | **0.677** |
| designs (19) | 0.573 | 0.575 |
| analysis (6: 113-305 crease solves, defect finding, stretch tree reading) | 0.917 | 1.000 |
| designs beating the square-packing milestone | 2 | 1 |

The remaining 22 hard-split tasks have not been run yet. They are mostly 100-300 crease
read-tree, af and solve instances, and a few designs. The design half of the benchmark has clear
headroom, with no from-scratch design near the circle-packing bound. The large analysis tasks
are close to saturation for this model.

## Complete hard split (all 47 tasks)

The last 22 hard tasks are graded under the same protocol:
- 4 defect-finding tasks on 113-157 crease patterns;
- 7 tree readings on 104-305 crease patterns;
- 7 solves on 104-184 crease patterns;
- 4 designs.

| | closed | agentic |
|---|---|---|
| these 22 tasks | 0.841 (17/22 solved) | 0.868 (19/22) |
| **hard split, all 47 tasks** | **0.742** (33/47) | **0.766** (39/47) |
| designs (23) | 0.581 | 0.588 |
| analysis (24: af, read-tree, solve) | 0.897 | 0.938 |
| excluding the 5 tasks whose id leaks the answer (see below) | 0.712 (42 tasks) | 0.762 |
| designs beating the square-packing milestone | 3 | 2 |

Misses among the 22:

- **Closed solves.**
  - star4-r6: 0.44; a Maekawa violation.
  - gops-13 and gops-14: 0.5 each; locally valid, but no global layer order exists.
  - bird-2x2: 0.5; the layer solver ran out of budget, so the result is undetermined, not proven wrong.
  - closed star4-r6 read-tree: 0.6.
- **Agentic.**
  - gops-13 solve: 0.5; no layer order exists.
  - bird-2x2 global-defect task: 0. The agent's own SAT layer search accepted a pattern that has no valid layer order. Both of our solvers (flat-folder and the Python SAT model) agree it has none, so its checker was missing a constraint.
- **`adv-style-bp-lizard-32`** scored 0 in both settings. The 14-crease answers reach the best-known scale, but on grids below the required minimum of 16.

The agentic setting solved 13 of 14 large read-tree and solve tasks perfectly. These large analysis tasks are close to saturated for an agent with Python. Design is not: no from-scratch design is near the circle-packing bound.

### Task ids leaked into the prompts

- **How it leaked.** Exports named each task folder after its task id, so agents could see it. Some ids state the answer:
  - `adv-bug-global-*`, `adv-bug-flip-*` (the defect type);
  - `af-bad-global-0`;
  - `af-ref-waterbomb_base` and `di-ref-fish_base` (the base);
  - `adv-read-tech-bp-stretch-gops-13` (box pleating, a stretch, the grid);
  - `adv-read-tree-tm-lizard`.
- **Agents used it.** One closed-book agent wrote that it answered "globally unfoldable" mainly because of the folder name. On `adv-bug-global-bird-2x2`, the closed-book agent, which could see the name, scored 1. The agentic one, which checked the pattern itself, scored 0.
- **Fixed.** `creasebench.export` now uses opaque folder names (`task-<hash>`). The id map is written outside the export directory, and a test checks that no exported file names its task.
- **Effect on the hard split.** Five hard-split tasks have answer-revealing ids. Without them, the hard split scores 0.712 closed and 0.762 agentic, against 0.742 / 0.766 with them.
- **Other runs.** The pilot's basic af/di tasks and its read-tech, read-color and tm read-tree tasks were affected the same way. Treat those scores as upper bounds.
- **Re-run.** Done; see "Clean re-run of the id-leaky tasks" below.

## Clean re-run of the id-leaky tasks

All 34 evaluated tasks whose id says something about the content were re-run with the opaque export (`task-<hash>` folders,
id map kept outside the export) in both settings, using the same prompts and rules. That covers every advanced analysis task
(af, bug, read-tree, read-tech, read-color, solve) plus `af-ref-waterbomb_base`, `af-bad-global-0` and `di-ref-fish_base`.
Results are in `results/opus-5.5-clean-{closed,agentic}`. In the combined numbers below the clean result replaces the leaky one
for each of these ids; everything else (designs, pack, `dt-*`, `af-gen-*`, `di-gen-*`) is unchanged.

| family (n) | closed leaky | closed clean | agentic leaky | agentic clean |
|---|---|---|---|---|
| bug: find the injected defect (5) | 1.00 (5 solved) | **0.46** (1) | 0.80 (4) | 1.00 (5) |
| read-tree (11) | 0.93 | 1.00 | 1.00 | 1.00 |
| solve (11) | 0.81 | 0.85 | 0.95 | 1.00 |
| read-tech (2) | 0.90 | 1.00 | 1.00 | 1.00 |
| read-color (1) | 1.00 | 0.78 | 0.78 | 1.00 |
| adv af (1) | 1.00 | 1.00 | 1.00 | 1.00 |
| basic af/di (3) | 1.00 | 0.87 | 1.00 | 0.87 |
| **all 34** | 0.911 | **0.854** | 0.949 | **0.988** |

- **The leak mattered for closed-book defect finding, and almost nowhere else.**
  - Closed bug tasks fell from 5/5 to 1/5. Without the name saying "global" or "flip", the closed-book agent claimed two
    defective patterns were foldable (scored 0). For the global defect in the three-flap pattern and the nudged vertex in
    gops-14, it said "not foldable" but marked the wrong vertices (0.60 and 0.68).
  - `af-bad-global-0` fell from 1.0 to 0.6 in both settings: "not foldable" was correct, but the violation vertex was wrong.
- **Agentic scores went up, not down** (0.949 → 0.988). The agent checks the pattern itself, so the name gave it little. It solved
  all 5 bug tasks, including `bug-global-bird-2x2`, which its leaky run had scored 0. All 11 solves and all 24 hard analysis tasks
  were perfect. One agent solved its layer order with the general-purpose `pysat` package. The rules allow it (no origami library),
  but it is worth noting.
- **Single-sample noise is as large as the leak everywhere except bug.** Several closed solves and tree readings went *up* clean:
  - solve-bird-2x2 and solve-gops-13: 0.5 → 1;
  - read-tree star4-r6: 0.6 → 1;
  - read-tree tm-lizard: 0.65 → 1.
  
  Closed solve-star4-16 went down, 1.0 → 0.39, from a Maekawa violation. So per-task differences outside the bug family say more
  about run-to-run variance than about the leak.

### Final numbers (clean answers for all leaky ids)

| | closed | agentic |
|---|---|---|
| **hard split, all 47 tasks** | **0.703** (was 0.742) | **0.798** (was 0.766) |
| hard-split designs (23) | 0.581 | 0.588 |
| hard-split analysis (24) | 0.820 (was 0.897) | 1.000 (was 0.938) |
| 24-task pilot, current graders | 0.872 (was 0.917) | 0.910 (was 0.917) |

The pilot's leaky figures here are re-graded with the current graders. They differ from the 0.957 / 0.920 reported at the top of
this document, which used the graders as they were before the fixes.

**Takeaway.** With nothing leaking, the gap between the two settings is real: **0.70 closed against 0.80 agentic** on the hard
split. It comes entirely from analysis. Agentic large-pattern analysis is now saturated at 1.000. Closed-book defect finding
and solving on 100-300 crease patterns are not. Design, at about 0.59 in both settings, remains the open problem, and it was
never affected by the leak.

### Second clean sample

Each task in the clean re-run was run only once, and per-task swings looked as large as the leak itself. So the same 34
tasks were run a second time. This run used a fresh opaque export with a new random salt, so the folder names are new; the
prompts and rules were unchanged. The results are in `results/opus-5.5-clean2-{closed,agentic}`.

| family (n) | closed leaky | closed clean 1 / 2 | closed solved (of 2n) | agentic leaky | agentic clean 1 / 2 | agentic solved (of 2n) |
|---|---|---|---|---|---|---|
| bug (5) | 1.00 | 0.46 / 0.20 | **2/10** | 0.80 | 1.00 / 0.80 | 9/10 |
| read-tree (11) | 0.93 | 1.00 / 0.89 | 20/22 | 1.00 | 1.00 / 0.96 | 20/22 |
| solve (11) | 0.81 | 0.85 / 0.86 | 16/22 | 0.95 | 1.00 / 1.00 | 22/22 |
| read-tech (2) | 0.90 | 1.00 / 0.90 | 3/4 | 1.00 | 1.00 / 1.00 | 4/4 |
| read-color (1) | 1.00 | 0.78 / 1.00 | 1/2 | 0.78 | 1.00 / 0.78 | 1/2 |
| adv af (1) | 1.00 | 1.00 / 0.80 | 1/2 | 1.00 | 1.00 / 1.00 | 2/2 |
| basic af/di (3) | 1.00 | 0.87 / 0.87 | 4/6 | 1.00 | 0.87 / 0.87 | 4/6 |
| **all 34** | 0.911 | 0.854 / 0.780 | | 0.949 | 0.988 / 0.938 | |

**Run-to-run noise.**

| | closed | agentic |
|---|---|---|
| mean per-task difference between the two clean samples | 0.17 | 0.05 |
| tasks whose two clean scores differ by more than 0.1 | 12 of 34 | 3 of 34 |

Single closed-book scores on these tasks are not reliable on their own. Examples:
- solve star4-16: 0.39, then 1.0;
- read-tree gops-14: 1.0, then 0.16 (wrong leaf count);
- solve kamiya-13: 1.0, then 0.5 (no layer order exists).

Agentic scores are much more stable.

**What survives two samples.**

- **Closed-book defect finding is where the leak mattered.**
  - With the leaky ids it solved 5 of 5 bug tasks. With clean ids it solved **2 of 10**.
  - In 6 of the 10 clean attempts it said a defective pattern folds flat (2 in the first sample, 4 in the second). The second sample did this even on bug-flip-bird-2x2 and bug-global-three-flap-16, which the leaky run had solved.
  - Agentic defect finding solved 9 of 10, and its one miss was `bug-global-bird-2x2` again. The agent's own layer check accepted a pattern that has no valid layer order, as in the leaky run. So this task is genuinely hard, and the leak is not what drives it.
- **Everywhere else the leak effect is within noise.**
  - Agentic solve was 22/22 clean, against 0.95 leaky. Agentic read-tree, read-tech and af are at or near 1.0 in every run.
  - The closed solve family mean barely moves (0.81 leaky, 0.85 and 0.86 clean).
- **Remaining agentic misses:**
  - `af-bad-global-0`: 0.6 in all four clean runs. The agent says "not foldable" correctly but names the wrong violation vertex.
  - `read-tree-tm-lizard`: 0.60 once, from a wrong topology on the TreeMaker base.
  - `read-color-bird-border`: 0.78 once.

### Final numbers (two-sample mean of the clean runs for the 34 ids)

| | closed | agentic |
|---|---|---|
| **hard split, all 47 tasks** | **0.681** | **0.787** |
| hard-split designs (23) | 0.581 | 0.588 |
| hard-split analysis (24) | 0.778 | 0.978 |
| 24-task pilot, current graders | 0.861 | 0.897 |

These replace the single-sample figures above (0.703 closed / 0.798 agentic).

The conclusion is unchanged and now rests on two samples:
- Without the leak, the two settings are about 0.11 apart on the hard split.
- All of that gap is in analysis, mainly closed-book defect finding and solving.
- Agentic analysis is close to saturated.
- Design, at about 0.59 in both settings, is the open problem.

The design scores are still single-sample. Closed-book analysis has a noise floor of about 0.17 per task, which suggests per-design numbers should also be read with care.

## Expert split (v0.4): pass/fail, target under 10%

The hard split stopped separating models: agentic analysis was at 0.98, and partial credit propped up the headline. The
`expert` split is scored **pass/fail**. Every task's reference answer passes its own grader (oracle self-check), so a
0% is not caused by impossible tasks. The aim was for the current frontier to pass fewer than 10% of headline tasks.
Opus 5.5 ran as subagents, one task per fresh agent, with the same closed-book and agentic rules as above. Task folders
had opaque hashed names.

### Round 1 (53 tasks, first build)

| | closed | agentic |
|---|---|---|
| expert pass rate | 16/53 (30.2%) | 21/53 (39.6%) |

| family (round 1) | n | closed | agentic |
|---|---|---|---|
| design (incl. thin and min-grid) | 20 | 3 | 5 |
| read-tree | 9 | 1 | 3 |
| inverse | 9 | 0 | 0 |
| regions | 9 | 6 | 8 |
| repair | 5 | 5 | 4 |
| solve (mega mirror) | 1 | 1 | 1 |

Every family that leaked was hardened:
- **Design and thin.** The bar went from ≥ 0.95 × the TreeMaker reference to matching or beating it. Tasks are built
  only where the reference reaches ≥ 0.7 of the circle-packing bound, so a weak reference cannot set a low bar.
  Phoenix is excluded on this rule: a wider reference search (seeds 5–16) found nothing better.
- **Read-tree** is image only. Coordinates were removed, so the tree has to be read off a rendered pattern, and the
  prompt states the length tolerance.
- **Repair** now injects only locally invisible conflicts: 3 per pattern, or 4 on the mega mirror. Every vertex passes
  Maekawa and Kawasaki, so the defects cannot be found by local checking.
- **Regions** marks every flap tip, not a subset.
- **Min-grid and the mega mirror solve** were removed from the split.

**Regions and repair moved to a separate `expert-analysis` split.** The agentic setting solves them largely by writing
its own search code: a SAT or layer-order solver for repair, and tree automorphism checks for regions. Kept in the
headline, they would mask the design result. They are still built, graded and reported.

### Grader fixes found during round 2

- **Tree-fit search budget.** A valid agentic tarantula design was scored at exactly half its true scale: 0.0263
  instead of 0.0526. The search behind `treefit.fit_scale` used up its node budget on the k! orderings of
  interchangeable base leaves (the 8 legs of a spider base), so it reported the real scale as infeasible. The fix is
  sound base-side value symmetry: leaves with identical distances to all other leaves are tried once per class. All 8
  design references re-measure at unchanged scale. The regression test is
  `test_fit_scale_finds_designs_with_many_interchangeable_flaps`. Round-2 answers were re-graded with the fixed fitter.
- **Regions boxes held a second tip.** Some boxes contained a flap tip of the base that was not in the fitted mapping,
  or a tip that only exists along another axis, which made those tasks ambiguous. Boxes now exclude the tips of every
  candidate axis's tree and are checked after rounding to 4 decimals. Pegasus, scaled_wyrm and phoenix cannot meet
  this rule (their tips are too dense) and were dropped. 6 regions tasks remain.

### Round 2 results (hardened split, final grader)

Headline `expert` split, 34 tasks, single sample:

| family | n | closed | agentic |
|---|---|---|---|
| design | 8 | 0 | 2 (crab, tarantula) |
| thin | 8 | 0 | 1 (tarantula) |
| read-tree (image only) | 9 | 0 | 1 (dragon) |
| inverse | 9 | 0 | 0 |
| **expert, pass rate** | **34** | **0/34 (0%)** | **4/34 (11.8%)** |

The inverse tasks were not changed by the hardening, so their round-1 answers were re-graded under the final grader
(`inverse-round1.jsonl`).

**Second sample.** Each agentic pass was re-run once, in a fresh export with new opaque folder names:

| task | sample 1 | sample 2 |
|---|---|---|
| design-crab | pass | fail: does not fold (vertex with 3 creases, odd degree) |
| design-tarantula | pass (scale 0.0526) | fail (scale 0.0389, below reference) |
| read-tree-dragon | pass | pass |
| thin-tarantula | pass | fail: folds, but scale 0.0500 is below the 0.0516 reference |

Counting only tasks that pass in both samples, the agentic headline is **1/34 (2.9%)**: read-tree-dragon. Closed-book
is 0/34. Both are under the 10% target. The single-sample agentic rate, 4/34 (11.8%), is mostly variance: 3 of the 4
passes did not repeat.

`expert-analysis` split (reported separately):

| family | n | closed | agentic |
|---|---|---|---|
| regions | 6 | 5 | 5 |
| repair | 5 | 1 | 4 |

Regions passes are accepted up to tree automorphism (these trees are highly symmetric). On repair, the agentic runs
wrote their own layer-order and SAT solvers.

### Rule bends logged

- **Closed-book Grep.** Two closed-book runs used Grep on their own `prompt.md`: one in round 1, and the round-2
  repair-mirror run. That gave no extra information, but it broke the "no tools" rule. Neither run passed a headline
  task.
- **Agentic budget and libraries.**
  - Round-2 design-dragon used about 27 commands (the limit is about 20) and scipy. It failed.
  - Thin-stag_beetle used scipy SLSQP. It failed.
  - The passing design-tarantula sample 1 used pysat. That is a general SAT library, not an origami library, so it
    is allowed.
- No passing headline answer depended on a rule breach.

### Operational notes

The session and weekly usage limits stopped about 22 round-2 runs partway through. They were re-queued and run from
a clean folder after the limit reset. One second-sample run was lost to a container restart and re-run. Results are
in `results/opus-5.5-expert-v3-{closed,agentic}/`. Second samples are in `results/opus-5.5-expert-v3-agentic/sample2/`.
Superseded partial and pre-fix grades are in `results/opus-5.5-expert-v2-*`.

### Smaller models on the expert split

Haiku and Sonnet ran the 34 headline tasks in both settings, one sample each. They used the same subagent templates and
fresh opaque exports as the Opus runs, and the same final grader.

| | Haiku, closed | Haiku, agentic | Sonnet, closed | Sonnet, agentic |
|---|---|---|---|---|
| **pass rate** | **0/34** | **0/34** | **0/34** | **0/34** |
| mean partial credit: design + thin (16) | 0.033 | 0.046 | 0.000 | 0.145 |
| mean partial credit: inverse (9) | 0.068 | 0.038 | 0.037 | 0.157 |
| mean partial credit: read-tree (9) | 0.128 | 0.140 | 0.149 | 0.183 |

No task passed in any setting. Most answers were explicit placeholders: a single fold, an empty pattern, or a guessed
tree that the model itself labelled low-confidence. The closest misses were Sonnet with tools:
- thin stag beetle at scale 0.0424, where the pass bar is 0.0454;
- thin scaled wyrm at 0.0447 (bar 0.0609);
- an inverse pegasus pattern scoring 0.78 partial credit.

They built these from pleat grids and accordion folds, not tree-theory constructions.

Run notes are in `results/haiku-expert-agentic/RUN_NOTES.txt`:
- Nine Haiku runs made one unneeded call to the session-management tools available in the harness, such as listing
  sessions. Each one said it ignored the output.
- One Haiku run tried to create a session, and the harness denied it.

None of these runs passed, so the breaches do not affect any result.

The ordering is consistent across models:

| model | closed | agentic, one sample | agentic, passed in both samples |
|---|---|---|---|
| Haiku | 0/34 | 0/34 | – |
| Sonnet | 0/34 | 0/34 | – |
| Opus | 0/34 | 4/34 | 1/34 |

Results are in `results/{haiku,sonnet}-expert-{closed,agentic}/`.
