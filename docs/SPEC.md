# CreaseBench specification (v0.4)

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

---

## 7. Advanced tier (v0.2)

### 7.1 Verification at scale
- **Global layer order** is decided by Jason Ku's *flat-folder*, vendored unmodified (MIT) under
  `creasebench/ffolder/vendor`. It runs headless through Node.js (`ff_solve.mjs`).
  - It uses the facewise formulation of Akitaya, Demaine & Ku (OSME 2024): taco-taco,
    taco-tortilla and tortilla-tortilla constraints with lazily reduced transitivity, unit
    propagation, then component-wise search.
  - flat-folder may fold from a different root face. Its layer order is converted to our frame
    by comparing per-face flip states.
  - `U` creases are solved together with the layer order, and their M/V is read back from the
    order (`verify.assignments_from_order`).
  - Without Node, the pure-Python solver is used. Both solvers agree on every v0.1 instance, and
    flat-folder's orders validate in the Python constraint model (`tests/test_advanced.py`).
- **Local sufficiency** is checked with the crimp algorithm (big-little-big) on top of Maekawa
  and Kawasaki.
- Instances get time caps. A cap hit is reported as "undetermined", which is distinct from
  "not foldable".

### 7.2 The tree of a folded base (`tree.py`)
- **Definition.** For an axis direction a, let g(p) be the coordinate along a of the folded
  image of paper point p. g is affine on each face. The base's tree is the **Reeb graph of g on
  the paper**: every connected component of every level set collapses to a point, and edge
  lengths are differences of g.
- **Computation.** The paper is a disk, so this is the contour tree. It is computed with Carr,
  Snoeyink & Axen's join/split-tree algorithm on an ear-clipped triangulation of the faces.
  Ties are resolved by simulation of simplicity, zero-length edges are merged, and degree-2
  nodes are contracted.
- **Why it is sound.** Folding is a piecewise isometry and projection is 1-Lipschitz, so the
  tree distance between two paper points never exceeds their distance on the paper. A design
  therefore cannot claim more than the paper allows.
- **Uniaxial bases.** For a uniaxial base folded with its flaps along the axis, this tree is
  exactly Lang's tree. For example, the bird base gives four flaps of length 0.5, the optimum
  for a 4-star.
- **Axis.** Candidate axes are the dominant folded crease directions. Design grading uses the
  axis that best fits the target.
  - **Reading tasks** use the axis with the largest total length of real flaps: leaf edges of
    at least 20% of the longest flap seen on any axis. This counts flaps, not the projection
    stubs that a tilted axis adds.
  - **Read-tree grading** ignores leaf stubs shorter than 15% of the longest flap, on both
    sides.
  - **Tilings** (2×2 module tilings) are not uniaxial bases, so they have no read-tree task.

### 7.3 Scale and efficiency (`treefit.py`, `packing.py`)
- **Scale m.** m is the largest value for which an injective leaf map φ exists with
  d_A(φ i, φ j) ≥ m·d_T(i, j) for all target leaf pairs. It is found by binary search over the
  candidate ratios, with backtracking.
- **Best-known bound.** Multi-start SLSQP on ‖u_i − u_j‖ ≥ m·d_ij with u_i ∈ [0,1]². The L∞
  variant is used for box pleating. This is an *estimate* of the circle-packing optimum, which
  is NP-hard to compute. The bound is raised to a reference design's scale when one is better.
- **Efficiency** is m divided by the best known value, capped at 1. Values above 1 are recorded
  as "beats reference".
- **Square-packing milestone (not scored).** Each design task also stores the best L∞ (square)
  packing scale. The grade reports `beats_square_packing` when m exceeds it.
  - A box-pleating-like square packing is the cheap route to a valid base. One example is
    stacking the sheet with folds through every layer, which agents discovered on their own.
  - Beating that scale needs genuine circle/river packing.
  - In the Opus 5.5 pilot, no design reached it.
- **Solving a design task** requires efficiency ≥ 0.6, plus every technique, color, graft and
  layer requirement.

### 7.4 Technique compliance (`style.py`)
| Technique | Check |
|---|---|
| box pleating (grid N) | every crease direction is in {0, 45, 90, 135}°, and every vertex lies on the 1/N lattice (smallest N ≤ 512) |
| 22.5° | every crease direction is a multiple of 22.5° (coordinates checked in Z[√2]/2^k) |
| Pythagorean stretch | the pattern is rational and box-pleated except for lattice directions whose slopes come from a primitive triple (a, b, c) with c ≤ 65: b/a, a/b, b/(a+c), a/(b+c) and their inverses; at least one such crease must be present |
| hex | crease directions are multiples of 30°, with at least one direction off the 90° family |
| graft | the task states a piecewise transform (scale + offsets per region). The fraction of base crease length found in the answer at the transformed positions must reach the threshold. M/V may be globally swapped. |

### 7.5 Colour (`color.py`)
- "Front" is the side shown in the crease-pattern drawing. A face that is not flipped shows its
  front upward.
- From above you see the top-most face covering a point; from below, the bottom-most face's
  other side.
- Flap tips are sampled just inside each leaf of the extracted tree.
- A requirement holds if **some** valid layer order meets it. This is decided by SAT, with
  auxiliary "face f is outermost here" literals.
- Reading tasks only ask about tips whose colour is the same in every valid order.

### 7.6 Generators (all output certified before use)
- **22.5° modules and tilings** (`gen/bases22.py`).
  - The bird base is written in exact Q(√2) geometry, with M/V assigned by the solver.
  - In n×n tilings, mirrored cells swap M/V. Seams are first tried with module assignments,
    then with seam creases unassigned.
- **Grafting** (`gen/graft.py`).
  - Strip grafts run along lines where every crossing crease is perpendicular and every vertex
    on the line carries only perpendicular creases.
  - Border grafts extend the edge creases outward; when the old edge is folded too, this
    produces a color change.
  - Point grafts place a module where two strips cross.
- **Defects** (`gen/defects.py`): flip one crease, move one vertex, or flip creases around a
  face so every vertex stays locally valid while the pattern becomes globally impossible.
- **Box Pleating Studio** (`gen/bpstudio`).
  - Tree and flap rectangles go to BP Studio's core (bundled), which returns contours, ridges
    and stretch gadgets (GOPS, Kamiya).
  - The pleats are then completed, and M/V is assigned by flat-folder.
- **TreeMaker 5** (`gen/treemaker`, optional and built locally from Lang's GPL source). Its
  pipeline is scale optimization, pinning, universal-molecule creases, and facet ordering.
  Patterns must cover the square and pass flat-folder.

### 7.7 Limitations
- Only flat bases are graded. 3D shaping, which COrigami's shaping stage covers, is out of
  scope.
- The packing bounds are estimates, not proven optima.
- Flap separability is not enforced beyond the Reeb tree and the layer order. Bundling flaps is
  allowed, as in tree theory.
- Color reading is restricted to patterns with at most 250 faces, where uniqueness can be
  proven with the Python SAT model.

### 7.8 Splits and hardening (v0.3)
- **Reporting splits** (`tasks.task_split`), with `hard` as the headline number:
  - `warmup` is the basic tier.
  - `hard` is design targets with at least 6 flaps, plus solve, read-tree and af tasks on
    patterns of at least 100 creases.
  - `core` is everything else in the advanced tier. pack, read-tech and read-color are always
    `core`, because an optimizer or a direct analysis answers them at any size.
- **Larger targets.** `trees.BIG_TREES` adds 14-24 flap animals with uneven lengths: a stag
  beetle, a mantis, a lobster, a centipede, a pegasus and a tarantula.
- **Style windows.** Box-pleating tasks state a grid range (`min_grid` to `max_grid`), so a
  trivial coarse-grid answer no longer ties the reference. Two tasks require a Pythagorean
  stretch.
- **Considered and rejected: layer-count caps.**
  - Measured layer counts do not separate cheap whole-stack designs (16-64 layers) from
    reference designs (18-96).
  - Those cheap designs are already scored below the square-packing bound.
- **Larger generated patterns: open.**
  - Box Pleating Studio layouts for the semantic trees on 32-40 grids were placed from their L∞
    packings, so the layouts are valid.
  - All 36 failed at pleat completion (`gen/bpstudio/pleats.py`).
  - The largest certified pattern is still 305 creases. Extending pleat completion to these
    layouts is the next step for bigger solve and read-tree instances.


### 7.9 Expert split (v0.4)

The hard split had saturated on its analysis half: the agentic setting scored 0.98 with clean task ids. Partial credit
also carried its headline: proportional efficiency, 0.5 for a locally valid solve, and 0.6 for "not foldable" with the
wrong vertices. The **expert** split (`meta["split"] = "expert"`, built by `creasebench/expert/build.py`) is scored
**pass/fail**, and its pass rate is the headline number. `run.summarize` reports a pass rate for every split, with mean
partial credit as a secondary column.

**The rule that keeps it honest.** Every expert task has a reference answer that passes its own grader within the same
verifier budget (`verify_timeout = 900 s`). The oracle self-check in `build.py` enforces this, with no "bound only"
exemptions. Tasks are hard because they demand expert-level results, not because they are impossible or ambiguous.

References are generated offline into `tasks/expert_cache/`:
- `expert.refgen`: TreeMaker, then M/V completion, then verify, then tree fit;
- `expert.megagen`: mirror tilings with the map-fold assignment, and random 22.5° tilings;
- `expert.gridgen`: lattice square packing, then BP Studio, then verify.

The headline `expert` split has four families, all pass/fail:

| family | task | passes when |
|---|---|---|
| `expert-design-*` | design a base for a 14–27 flap tree | it folds and realizes the tree at a scale matching or beating the certified TreeMaker reference (≥ 1 − 1e-6 × ref) |
| `expert-thin-*` | the same, plus a thickness limit | additionally, no point has more layers than the reference |
| `expert-read-tree-*` | read the tree of a TreeMaker base from a rendered image only (no coordinates) | exact topology, every segment length within 0.01 of the paper side or 2% |
| `expert-inverse-*` | reconstruct the CP from the folded outline, an x-ray image and the tree | it folds, scale ≥ 0.98 × reference, folded-outline IoU ≥ 0.97 |

Design and thin tasks are built only when the certified reference reaches at least `MIN_REF_RATIO = 0.7` of the
circle-packing bound, so a weak reference cannot make the bar trivial (this excludes phoenix).

Two analysis families are reported separately as `expert-analysis` (`meta["split"] = "expert-analysis"`). Agentic
models largely solve them with their own search code, so they would mask the design result in the headline:

| family | task | passes when |
|---|---|---|
| `expert-regions-*` | which flap does each marked box become? every flap tip is marked, and each box holds exactly one tip of the folded base along any candidate axis | every label right, up to automorphisms of the target tree |
| `expert-repair-*` | repair 3–4 locally invisible global conflicts (every vertex passes Maekawa/Kawasaki; only the layer order fails) | it folds, with at most the number of injected edits changed |

Earlier v0.4 drafts also had `expert-min-grid-*` and `expert-solve-mirror-*`; both were removed when the split was
hardened (see `docs/eval-opus-5.5-2026-10.md`, "Expert split").

**What was tried and left out:**
- **Scale-texture grafting** (Kamiya-style scale panels made by strip grafts). It needs full-length cut lines that cross
  only perpendicular creases, and only 1 of the 27 certified BP bases has one. The scales are instead modelled at tree
  level (`scaled_dragon`, `scaled_wyrm`: rows of small dorsal flaps).
- **Mega patterns above about 900 creases.** The verifier cannot check them within the grading budget.
- **Designer CPs from raster images.** `creasebench/tools/trace.py` traces box-pleated images (red = mountain,
  blue = valley) and repairs the trace with local checks. At 880 px, the dense texture panels (features about 4 px
  apart) still fail local checks, so these CPs need higher-resolution sources. `creasebench/importers.py` reads ORIPA
  `.cp` / `.opx` directly.
