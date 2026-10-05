# Origami Bench specification (v0.1)

## 1. Motivation

Origami design is a compact test of skills that LLMs are weak at but that real engineering
depends on:

- **Spatial simulation.** You have to track how regions of paper move under a series of
  reflections.
- **Global constraint satisfaction.** Stacking paper without self-intersection is NP-hard in
  general.
- **Inverse design.** You have to find a crease pattern that produces a given shape.

The answers are precise geometric objects that a program can check exactly, much as a PCB
benchmark runs DRC and simulation on a netlist. Because the benchmark targets *general*
agents, every input is plain JSON plus an image. Nothing requires an origami-specific tool.

## 2. Conventions

- The paper is the unit square [0,1]², seen from its top side (+z). All lengths are in units of
  the paper side.
- Crease patterns use [FOLD](https://github.com/edemaine/fold): `vertices_coords`,
  `edges_vertices`, `edges_assignment` (`M`, `V`, `B`, `U`, and `F`, which means not folded) and
  `faces_vertices` (counter-clockwise loops).
- A crease pattern describes a **flat-folded state in which every crease is folded by ±180°**.
  Precreases that are not folded must be left out.
- **Valley** means the paper on both sides rises toward the viewer, so the moving part lands on
  top. **Mountain** is the opposite.
- Folded frame: the largest face, with ties broken by the lowest index, keeps its CP position
  with the top side up. "Above" means +z in that frame. A reported answer can sit in any rigid
  frame. The grader aligns it, allows a mirror image, and reverses the reported layer claims when
  the alignment is a mirror (looking from below).

## 3. Verification pipeline (`verify.py`)

1. **Arrangement** (`cp.py`). Segments are clipped to the square, split at every intersection,
   and their endpoints merged within a tolerance (1e-9 for authored tasks, 1e-4 for model
   answers). Creases that dangle inside the paper are pruned, with a warning. Faces are found
   by walking half-edges.
2. **Local checks** (`foldability.py`). At each interior vertex the crease count must be even.
   **Kawasaki:** the alternating sector sum must be 0, within 5e-3 rad. **Maekawa:** |M − V| = 2
   when every crease at the vertex is assigned.
3. **Geometry** (`simulate.py`). A breadth-first search over the face graph composes the
   reflections across creases. Each vertex's folded position must agree across all its faces
   to within 2e-3; this is the global Kawasaki condition. M/V assignments do not affect the
   geometry.
4. **Layer order** (`layers.py` + `sat.py`). There is one Boolean variable per pair of faces
   whose folded images overlap. The constraints are:
   - **crease:** the M/V assignment, together with the flip state of the face, fixes the order of
     the two faces at that crease;
   - **transitivity:** any three faces with a common overlap are ordered without cycles;
   - **taco–tortilla:** a face that spans a folded crease cannot lie between that crease's two
     faces;
   - **taco–taco:** two coincident creases folded to the same side must nest, never interleave.

   A DPLL solver with two-watched-literal propagation decides the instance, with a decision
   budget. `U` creases get extra variables, so the solver also finds an M/V assignment for them.
   The solver was validated against the generator: every one of the generated patterns' known
   layer orders satisfies the constraints, and wrong orders are rejected.

## 4. Tracks and grading (`graders.py`)

All answers are a JSON object in the model's last ```json block.

### 4.1 Analytic folding

Answer: `{"foldable": true, "folded_vertices": [[x,y],…], "face_above": [[f,g],…]}`, or, for a
non-foldable pattern, `{"foldable": false, "violation_vertices": [i,…]}`.

- **shape** = max(fraction of vertices within 0.01 of the truth after robust rigid/mirror
  alignment, 0.75 × silhouette IoU). A silhouette-only answer can earn at most 0.75.
- **layer** = coverage of the overlapping pairs × [the claims are consistent with some valid
  layer order]. Consistency is checked by the SAT solver with the claims as assumptions, so any
  valid order earns credit, not just the reference one.
- raw score = 0.8 · shape + 0.2 · layer. **solved** ⇔ every vertex is correct.
- Non-foldable tasks: claiming the pattern folds scores 0. Otherwise 0.6 + 0.4 × Jaccard(predicted
  violation vertices, true violation vertices). Global-only failures expect an empty list.

### 4.2 Design (text and image)

Answer: `{"creases": [[x1,y1,x2,y2,"M"|"V"], …]}`. The paper boundary is implicit, and a FOLD
object under `"fold"` is also accepted.

The answer must pass the full verification pipeline, or it scores 0. After that, each task's
rubric checks run on the folded silhouette:

| check | meaning |
|---|---|
| `iou` | silhouette IoU after the best rigid/mirror alignment (scale is fixed), normalised so the unfolded square scores 0; passes at ≥ threshold (0.95 by default) |
| `regular_polygon` | IoU against the best-aligned regular n-gon of equal area, plus a minimum area |
| `area`, `extent`, `rectangularity`, `convexity`, `vertex_count`, `symmetry`, `sharp_points` | simple shape features |
| `coincident` | listed paper points must fold to the same location (e.g. "all corners meet") |

raw score = the weighted mean of the check scores (× 0.9 if any `U` creases are used).
**solved** ⇔ every check passes. Design-from-image tasks use a single `iou` check against the
target. Design-from-text tasks use hand-written rubrics.

### 4.3 Baseline normalisation

At build time each task stores the raw score of the trivial `unfolded` answer: the paper left
flat for analytic tasks, a single book fold for design tasks. The reported score is
max(0, (raw − baseline) / (1 − baseline)), so 0 means "no better than doing nothing". The raw
score is kept as `raw_score`.

### 4.4 Semantic judge (optional)

The fish and arrow tasks have only loose automatic rubrics: symmetry, aspect ratio, sharp
points, concavity. Their reference solutions pass the rubric without looking much like a fish.
To measure meaning, `--judge-provider` renders the answer's folded silhouette and asks a vision
model to rate, from 0 to 10, how clearly it depicts the subject. This is reported in a separate
column so the main score stays deterministic.

## 5. Task generation (`build.py`, `generate.py`)

- **Simple-fold generator:** a random sequence of folds through all layers. Each fold line goes
  through two reference points of the current silhouette (vertices or edge midpoints), or is
  the perpendicular bisector between two such points ("fold A onto B"). These patterns are
  flat-foldable by construction, and their folded state and a valid layer order are known.
  Patterns with faces smaller than 2e-3 or edges shorter than 0.02 are rejected. Difficulty
  scales with the number of folds.
- **Non-foldable variants:** flip one assignment (Maekawa), move a vertex (Kawasaki), or search
  for random reassignments that are locally valid but have no layer order (global).
- **Design references:** traditional bases; `fold_to_convex` (repeatedly fold whatever sticks
  out of a convex target back inside); `search_symmetric` (random mirror-symmetric fold
  sequences filtered by the rubric).
- Every built task is self-checked: the oracle answer must solve it.

## 6. Known limitations and roadmap

- **Flat folds only.** There are no 3D or partially folded states, curved creases, or
  tessellations at scale.
- **Simple-fold distribution.** Generated analytic tasks come from simple folds. Patterns with
  collapses, like the bird or frog base, can only enter through hand-authored references.
  Adding a tree-method / box-pleating generator would add these.
- **Semantic design.** Silhouette-only rubrics cannot tell a fish from a fish-shaped triangle.
  Future work: flap/tree extraction (uniaxial bases) and per-flap length checks.
- **Contamination.** The seed set, including hidden reference answers, is public. For a held-out
  evaluation, rebuild with a private `--seed` and keep that split private.
- **Numerical tolerances.** Answer endpoints are merged within 1e-4 and Kawasaki is checked to
  5e-3 rad. Answers should therefore give at least 6 significant digits.
- **Solver budget.** Very large layer instances may exhaust the solver budget. These are
  reported as "undetermined" and graded as not foldable.
- **Human baselines** have not been collected yet.
