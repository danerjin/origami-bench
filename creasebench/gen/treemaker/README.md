# TreeMaker 5 crease-pattern generator (optional)

Headless wrapper around Robert J. Lang's **TreeMaker 5** model library: give it
a stick-figure tree (edges with lengths) and it returns a uniaxial-base crease
pattern (circle/river packing → universal-molecule creases → facet ordering →
mountain/valley assignment) with the scale factor, the leaf positions, and the
vertex → tree-node map.

This component is **optional**. Nothing else in `creasebench` imports it
unconditionally; call `available()` first.

## Provenance and licensing

| Part | Where it lives | License |
|---|---|---|
| TreeMaker 5 model (`Source/tmModel`, `Source/tmHeader.*`), (c) Robert J. Lang | fetched by `build.sh` into `~/.cache/creasebench/treemaker/TreeMaker`, **never committed here** | GPL v2 or later |
| wnlib subset (bundled in TreeMaker, Will Naylor & Bill Chapman) | same cache dir | unrestricted |
| `tm_driver.cpp` (our console driver) | this directory | GPL-2.0-or-later (it links against TreeMaker) |
| `build.sh` | this directory | GPL-2.0-or-later |
| `__init__.py` (Python wrapper; only runs the binary as a subprocess) | this directory | the repository's license |
| Generated crease patterns (`samples/*.json`, anything `generate()` returns) | anywhere | program output, not covered by the GPL |

Upstream source: GitHub mirror <https://github.com/StOriJimmy/TreeMaker>, pinned
at commit `3cf34524c99323dbf06b816a5c8cd72b129e187f` (2016-09-23, TreeMaker 5.0.x).
Only the GUI-free model is compiled; no wxWidgets. CFSQP/RFSQP (proprietary
optimizers) are excluded. The ALM optimizer (Lang's own code) and wnlib are
both compiled in.

## Build

```bash
creasebench/gen/treemaker/build.sh                 # git clone @ pinned commit + compile (~20 s)
TM_SRC=/path/to/TreeMaker creasebench/gen/treemaker/build.sh   # use an existing checkout instead
CREASEBENCH_CACHE=/elsewhere creasebench/gen/treemaker/build.sh # different cache root
```

Output: `~/.cache/creasebench/treemaker/bin/tm_generate` (the Python wrapper
looks there; `CREASEBENCH_CACHE` or `CREASEBENCH_TM_GENERATE` override it).
Requirements: `git`, `g++`/`gcc` (tested with GCC 13.3), `ar`.

Compiler flags (also documented in `build.sh`), no TreeMaker source is patched:

```
C++ : -std=gnu++98 -O2 -w -fpermissive -include cstddef -include cstring -include cstdlib -DtmUSE_WNLIB -I<every tmModel subdir>
C   : -O2 -w -I<every tmModel subdir>            (wnlib + tmNLCO_wnlibStub.c)
link: g++ ... tm_driver.cpp libtmmodel.a -lm
```

`-fpermissive` turns the 2005-era two-phase-lookup errors in `tmArray<T>`
(calls to inherited `std::vector` members without `this->`) into warnings;
the `-include`s supply headers missing for `ptrdiff_t`/`strcpy`.

## Python API

```python
from creasebench.gen import treemaker as tm

tm.available()                    # -> bool: binary built?
tm.build()                        # runs build.sh (optional convenience)
r = tm.generate(
    [("body", "head", 1), ("body", "tail", 1.5), ("body", "fl", 1), ("body", "fr", 1)],
    timeout=60,                   # total budget, seconds
    corners="auto",               # or [leaf ids] / () ; see below
)
r["ok"]            # full CP with facet order + M/V (TreeMaker HasFullCP)
r["local_ok"]      # ok and every interior vertex passes Maekawa + Kawasaki (1e-3 rad)
r["covers_square"] # CP fills the whole unit square (else only the leaves' convex hull)
r["scale"]         # TreeMaker scale m: tree length 1 -> paper length m (square side 1)
r["creases"]       # [[x1, y1, x2, y2, assignment, kind], ...]
r["leaves"]        # {leaf_id: [x, y]}
r["vertices"]      # [{x, y, tree_node, elevation, depth, border}], tree_node = tmVertex::mTreeNode
r["nodes"], r["edges"], r["facets"], r["status"], r["corners"], r["seconds"], r["raw"]
```

* `assignment`: `M`, `V`, `F` (crease line that stays unfolded in the base:
  TreeMaker's *unfolded hinges*), `B` (on the square's border), `U`
  (boundary of the leaf-node convex hull that is *inside* the square:
  TreeMaker gives it no M/V; only happens when `covers_square` is false).
* `kind`: `axial`, `gusset`, `ridge`, `hinge` (folded hinge),
  `unfolded_hinge`, `pseudohinge`.
* To feed `creasebench.cp.CreasePattern.from_segments`, drop the kind:
  `[s[:5] for s in r["creases"]]` (use `tol=1e-5`: coordinates are only
  accurate to ~1e-6, TreeMaker's own distance tolerance is 1e-4).
* Coordinates within 1e-4 of 0/1 are snapped onto the border.
* When `ok` is false the crease/vertex lists may be partial or empty.

Other keyword options: `borders=[ids]` (leaf on a paper edge), `locs={id:(x,y)}`
(initial positions), `solver="auto"|"alm"|"wnlib"`, `restarts=8`, `seed=1`,
`stubs=0|1|2`, `pin=True`, `first=False`, `max_corner_sets=6`.

`corners="auto"` runs the unconditioned problem, then up to `max_corner_sets`
choices of 4 long-flap leaves fixed to the 4 corners, and returns the best by
(ok, local_ok, covers_square, scale). This is what makes square-filling CPs:
without corner leaves TreeMaker only creases the convex hull of the leaf
nodes and the excess paper outside it is left uncreased.

## What the driver does (`tm_driver.cpp`)

stdin, one item per line (`#` comments):

```
edge <a> <b> <length>      # tree edges (>= 3 leaves; ids without spaces)
corner <leaf>              # tmConditionNodeCombo: fixed to a paper corner
border <leaf>              # ... fixed to a paper edge
loc <id> <x> <y>           # optional initial position
option <key> <value>       # solver, restarts, seed, stubs, pin, pin_iters, first, attempt_timeout
```

Per restart attempt (each in a `fork()`ed child, so a TreeMaker crash or hang
only kills that attempt):

1. Build `tmTree` with `AddNode`/`SetLength`; leaves start on a circle in
   planar DFS order (attempt 0 deterministic, later ones rotated/jittered);
   corner/border leaves start on their constraint.
2. **Scale optimization** (`tmScaleOptimizer`) with ALM or wnlib. The NLCO
   engines often stop slightly outside the feasible set, so the driver then
   snaps conditioned nodes onto their corner/edge and sets
   `m = min_ij |p_i - p_j| / L_ij` (exactly feasible, binding paths exactly
   active), and re-polishes up to 3 times.
3. **Pinning**: while some leaf is unpinned, run `tmEdgeOptimizer` on the
   unpinned leaves and their edges (stretches those flaps — reported as edge
   `strain` — until they become pinned). This is the standard manual TreeMaker
   workflow for `POLYS_NOT_VALID` (mostly needed after a poorly converged
   wnlib run). A round that ends infeasible is repaired or reverted.
4. `BuildPolysAndCreasePattern()` (universal molecule; tree cleanup then
   computes depth, facet ordering via `tmTree_FacetOrder`, facet colours and
   `CalcFold` M/V). If that fails, `tmStubFinder::TriangulateTree()` adds
   stubs and the CP is rebuilt (`stubs=1`).
5. Local check at interior vertices (Maekawa + Kawasaki on the M/V creases).

Attempts are ranked: clean full CP > full CP > feasible > other; ties by larger
scale. Output is one JSON object; `attempts` lists every attempt's status.

## Measured results (GCC 13.3, single core, this container)

Test set: 4-flap star (equal flaps), 3 unequal flaps (1, 0.6, 0.3), 5-flap fish
(head 0.5, 2 long 1.0, 2 short 0.5, all on one body node), `fish_split` (same but the 2 short flaps on a 0.5 tail edge), lizard
(head, 4 legs, tail, body edge 1.5) and 20 random trees with 3-7 leaves
(lengths U[0.3,1.5], no degree-2 nodes; seed 7).

| configuration | full CP (`ok`) | `ok` + interior Maekawa/Kawasaki | covers whole square | time per tree |
|---|---|---|---|---|
| first prototype: wnlib, 8 restarts, no feasibility projection | 4/25 | – | – | ~0.01 s |
| `solver="wnlib"`, 1 attempt | 6/25 | 5/25 | 1/25 | < 0.02 s |
| `solver="wnlib"`, 8 restarts | 15/25 | 14/25 | 2/25 | < 0.08 s |
| `solver="alm"`, 1 attempt | 24/25 | 23/25 | 1/25 | < 0.02 s |
| defaults (`auto`, 8 restarts) | **25/25** | 24/25 | 2/25 | 0.03–0.08 s |
| defaults, `pin=False` | 25/25 | 24/25 | 2/25 | same |
| defaults, `stubs=0` | 24/25 (1 `FACETS_NOT_VALID`) | 23/25 | 2/25 | same |
| defaults + `corners="auto"` | **25/25** | **25/25** | **21/25** (all 21 trees with >= 4 leaves) | 0.03–0.22 s |

Global flat-foldability of the 21 square-covering `corners="auto"` CPs with the
repo's own `creasebench.verify.verify` (FlatFolder backend), using
TreeMaker's M/V unchanged: **18/21 flat-foldable**; the 3 rejections are all
`big_little_big` at vertices whose sectors are equal up to ~1e-6 rad, i.e. a
tie-tolerance artefact (`crimp_foldable` uses `tol=1e-6`); with that
tolerance at 1e-4 all **21/21** are flat-foldable with a valid layer order.

Larger random trees (20 trees per bucket, lengths U[0.3,1.5], seed 11;
"clean" = `ok` and the interior Maekawa/Kawasaki check passes):

| leaves | defaults: full CP / clean | median / max time | `corners="auto"`: full CP / clean / covers square | median / max time |
|---|---|---|---|---|
| 3-7 | 20/20 / 20/20 | 0.06 s / 0.12 s | 20/20 / 20/20 / 15/20 (5 trees have 3 leaves) | 0.12 s / 0.29 s |
| 8-11 | 20/20 / 20/20 | 0.15 s / 30 s | 20/20 / 20/20 / 16/20 | 0.44 s / 90 s |
| 12-16 | 20/20 / 15/20 | 0.28 s / 0.61 s | 20/20 / 16/20 / 16/20 | 1.5 s / 62 s |
| 17-24 | 20/20 / 10/20 | 0.76 s / 31 s | 20/20 / 14/20 / 13/20 | 6.3 s / 106 s |

The long tails are single attempts that hang inside TreeMaker until the
per-attempt alarm (these runs used 60 s; the wrapper now uses
`min(10, timeout/4)` s). Square coverage for >= 8 leaves fails when none of
the tried 4-corner sets gives a clean CP; the unconditioned (hull-only)
result is then returned.

Failure modes seen:

* **wnlib** frequently stops early (inform `WN_SUBOPTIMAL`), leaving only one
  or two active paths → `POLYS_NOT_VALID` / `POLYS_MULTIPLE_IBPS`; it can also
  segfault later in CP construction on the resulting near-degenerate states
  (isolated by `fork`). ALM is much more reliable here, so `solver="auto"`
  starts with ALM and alternates.
* Without step 2's feasibility projection, wnlib/ALM results are slightly
  infeasible (beyond TreeMaker's 1e-4 tolerance) → no CP at all.
* With wnlib, unpinned leaves (too few active paths) give `POLYS_NOT_VALID`;
  pinning helps there. With ALM + restarts the scale optimum is usually
  already pinned, so `pin=False` gives the same 25/25 on the test set.
* The stub finder rescued 1/25 (a `FACETS_NOT_VALID` tree).
* Corner choices matter: e.g. lizard with head/tail/front legs in the corners
  ends `NOT_LOCAL_ROOT_CONNECTABLE` (facet-ordering failure); other corner
  sets work, hence the search in `corners="auto"`.
* TreeMaker sometimes reports a full CP (seen once on a 6-leaf tree, in
  25-50 % of 12-24-leaf trees) whose
  M/V violates Maekawa at gusset/axial vertices (assignment flips along an
  axial line) or has ~5e-3 rad Kawasaki error from imprecise optimization;
  check `local_ok`.

Compared with the reported ~1 % automated success on complex stick figures:
the big differences here are (a) the feasibility projection, (b) automatic
pinning via the edge optimizer, (c) restarts with ALM, and (d) the trees are
small/simple. No symmetry conditions or manual stubs are used.

## Caveats

* M/V is TreeMaker's (`tmCrease::CalcFold` from facet colour + order). It is
  complete for every crease inside the CP region, except `U` hull-boundary
  creases when the CP does not cover the square. Not every crease is folded
  in the base: `F` (unfolded hinges) stay flat — they exist so that flaps can
  be swung/reoriented — and should be dropped when checking flat-foldability
  of the base itself.
* If `covers_square` is false, the paper outside the leaf hull has no
  creases; the CP alone does not fold from a square (use `corners="auto"`).
* Edge lengths in the result can exceed the input (`edges[].strain` > 0)
  because pinning stretches slack flaps; `scale` refers to the strained tree.
* Geometry accuracy ~1e-6 (ALM tolerance); downstream tolerances should be
  >= 1e-5.
* Only uniaxial bases; no symmetry handling; no strain optimization.
