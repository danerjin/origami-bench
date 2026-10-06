# bpstudio: headless box-pleating CP generator

This folder runs the layout core of Box Pleating Studio (BP Studio) without the app. You give it a tree and the flap positions on an integer grid. It returns the crease lines of a box-pleated crease pattern (CP), including the stretch gadgets: GOPS, Pythagorean (3-4-5), Kamiya half-integral, universal-GPS and joins.

## Provenance

- Upstream: https://github.com/MuTsunTsai/box-pleating-studio (also known as bp-studio/box-pleating-studio)
- Version: v0.7.17, commit `5029782af057cd90225230ffcf6c86764197634c` ("v1904: v0.7.17")
- License: MIT, Copyright (c) 2020-PRESENT Mu-Tsun Tsai. The full text is in `LICENSE-bpstudio`, and the bundle carries a header that points to it.
- We do not modify the upstream code. The bundle contains `src/core/**` and `src/shared/**` exactly as they are upstream. The build only does two things to them:
  1. It resolves the `core/…` and `shared/…` path aliases.
  2. It removes the `/// #if DEBUG … /// #endif` blocks. Upstream does the same in production through `ifdef-loader` with `DEBUG=false`.

  Our own code is `src/entry.ts`, the driver, plus `build.mjs`, `__init__.py` and `make_samples.py`.

## Files

| file | what it is |
|---|---|
| `bp_core.bundle.mjs` | Prebuilt self-contained ESM bundle (~280 KB). It needs only `node` (>= 18) at runtime. |
| `src/entry.ts` | Driver source. It reads JSON from stdin and writes JSON to stdout. |
| `build.mjs` | esbuild script that produces the bundle. |
| `__init__.py` | Python wrapper: `generate(...)` and `diagnose(...)`. |
| `make_samples.py` | Regenerates `samples/*.json`. |
| `samples/` | Example outputs. |
| `LICENSE-bpstudio` | Upstream MIT license. |

## Rebuilding the bundle

```bash
SCR=/path/to/scratch
git clone https://github.com/MuTsunTsai/box-pleating-studio $SCR/box-pleating-studio
git -C $SCR/box-pleating-studio checkout 5029782af057cd90225230ffcf6c86764197634c
mkdir -p $SCR/build && cd $SCR/build && npm init -y && npm i esbuild@0.25   # 0.25.12 was used
node /path/to/origami-bench/creasebench/gen/bpstudio/build.mjs $SCR/box-pleating-studio
```

The build does not need `pnpm install` for BP Studio. The core has no npm runtime dependencies, and it does not need the WASM optimizer in `lib/` because we supply the flap positions ourselves. `build.mjs` resolves `esbuild` from the current working directory, which is why you run it from `$SCR/build`.

## CLI (stdin to stdout)

```bash
echo '{"tree":[[0,1,7],[0,2,4]],"flaps":[{"id":1,"x":0,"y":0},{"id":2,"x":8,"y":9}],"sheet":{"width":16,"height":16}}' \
  | node bp_core.bundle.mjs
```

### Input fields

- `tree`: `[[n1, n2, length], ...]`. Node ids and lengths are integers, and the tree is undirected. BP Studio picks the root itself.
- `flaps`: `[{"id", "x", "y", "width"=0, "height"=0}]`, one per leaf, in grid units. A non-zero width or height gives a rectangular flap.
- `sheet`: `{"width", "height"}`. The sheet is the rectangle `[0,W]x[0,H]`.
- `pattern_choice` (optional): a pattern index for every stretch (an int), or `{stretchId: index}`.
- `config_choice` (optional): `{stretchId: index}`.

### Output fields

- `status`: `"ok"` or `"error"`.
- `errors`: the reasons for an error. Possible reasons:
  - a flap lies outside the sheet
  - a leaf has no flap
  - an invalid (overlapping) flap pair, which BP Studio shows as a red junction
  - a stretch without a pattern

  Even with errors, `lines` still holds whatever BP Studio drew.
- `grid`: the sheet width. `sheet` holds `{width, height}`.
- `lines`: `[[x1, y1, x2, y2, kind], ...]` in grid units, from BP Studio's `LayoutController.getCP(borders, useAuxiliary=true)`. That function clips, splits and deduplicates the lines. `kind` is one of:
  - `border`: the sheet edge.
  - `hinge`: the outer contour of a flap or river. Hinges are exported as ORIPA type 4, "auxiliary".
  - `ridge`: a ridge of a flap or river, or a gadget ridge. BP Studio labels ridges `M`.
  - `axis-parallel`: a gadget crease parallel to the gadget's (possibly slanted) axis. BP Studio labels these `V`. They are *not* necessarily parallel to the sheet.
- `assignment`: `"B"` for border lines and `"U"` for everything else. This is the recommended input for an M/V solver.
- `bp_assignment`: BP Studio's own labels, `B`, `M`, `V` or `A` (auxiliary).
- `stretches`: the number of stretches. `patterns_found` holds one bool per stretch.
- `gadget_types`: the distinct gadget types used. They come from the partition strategy and the pieces:
  - `GOPS`: one integral piece `(ox, oy, u, v)`.
  - `Kamiya`: the `HALFINTEGRAL` strategy.
  - `universal-GPS`
  - `join`: base or standard join, or a multi-gadget device.
  - `simple`: `u = v = 0`.
- `stretch_details`: per stretch, the configuration count and index, the pattern count, and the devices with their gadgets and pieces. Each piece lists `ox, oy, u, v`, its GOPS `rank` and whether it has detours.
- `invalid_junctions` and `warnings`.

## Python API

```python
from creasebench.gen.bpstudio import generate, diagnose
res = generate(tree_edges=[(0,1,7),(0,2,4)], flaps=[(1,0,0),(2,8,9)], grid=16,
               timeout=60, pattern_choice=None, config_choice=None,
               diagnose_foldability=False)
res["lines_unit"]   # lines divided by the sheet width/height (unit square for square sheets)
```

- `flaps` accepts dicts or tuples `(id, x, y[, w, h])`.
- `grid` is an int, or `(w, h)`.
- The wrapper raises `BPStudioError` only when node is missing or the bundle crashes. Design problems come back as `status == "error"`.
- `diagnose(res)` runs local necessary checks on every interior vertex: even degree and Kawasaki. It uses exact rational planarization and is O(n²), which is fine for a few hundred lines.

## Samples (`python -m creasebench.gen.bpstudio.make_samples`)

| sample | status | lines | stretches / gadgets | interior vertices failing the check |
|---|---|---|---|---|
| `star4_16`: 4 flaps of length 8 at the corners of a 16 grid | ok | 16 | 0 | 0/1 |
| `lizard_32`: head, 4 legs, tail, body river of 16, on a 32 grid | ok | 32 | 0 | 4/4 |
| `stretch_gops_16`: flaps r7 at (0,0) and r4 at (8,9), a 3x2 overlap | ok | 36 | 1, GOPS `(3,2,u3,v1)` | 10/16 |
| `stretch_kamiya_16`: r7 at (0,0) and r4 at (8,8), a 3x3 overlap | ok | 44 | 1, Kamiya | 13/20 |
| `stretch_3flap_relay_20`: the 3-flap relay case from BP Studio's tests | ok | 64 | 1 (2 devices), GOPS | 22/31 |
| `nopattern_3flap_16`: the "no pattern" case from BP Studio's tests | **error** | 43 | 1, none found | 13/19 |

- `stretch_gops_16` contains slope 3/4 and 4/3 lines, which are the Pythagorean 3-4-5 axis-parallels. Its ridges have slopes 2 and 1/3, the bisectors of the 3-4-5 angles. `pattern_choice=1` selects the rank-5 alternative `(u1, v3)`.
- The numbers of configurations, patterns and devices in the samples match the upstream mocha expectations: 2 patterns for the 7/4 pair at (8,9), and 1/1/2 for the relay.
- Each call takes about 0.1 s. Almost all of that is node startup.

## Crease completion and certification (`pleats.py`, `certified_cp`)

```python
from creasebench.gen.bpstudio import certified_cp
cp, info = certified_cp(tree_edges, flaps, grid, timeout=120)   # cp: CreasePattern (M/V) or None
info["stage"]   # "ok" | "generate" | "pleats" (local violations remain) | "verify" (flat-folder failed/timed out)

from creasebench.gen.bpstudio.pleats import complete_pleats
segs, pinfo = complete_pleats(generate(...), return_info=True)   # [x1,y1,x2,y2,kind] in grid units
```

`complete_pleats` adds the creases that BP Studio leaves out. All arithmetic is exact (`fractions.Fraction`).

- **Elevation pleats.** In each face of BP Studio's arrangement, the pleats are the integer level lines perpendicular to the face's hinges. This is COrigami F.1's "keep grid segments perpendicular to an intersecting hinge", applied face by face. Inside a stretch, the pleats follow the gadget's own axis-parallels, at the same phase and unit spacing. This works exactly for Pythagorean directions such as 3-4-5.
- **Excess paper**, meaning paper outside every contour:
  - It is first split by corner-bisector rays, a straight-skeleton step.
  - If local violations remain, the code falls back to a nearest-hinge (L∞) Voronoi fill on a quarter-cell grid.
- **Diagnose-driven repair.** A local search re-picks the families of ambiguous faces, then greedily adds straight rays from vertices that still violate even degree or Kawasaki.

`certified_cp` then builds `CreasePattern.from_segments(..., tol=1e-9)` with every non-border crease set to `U`, and runs `creasebench.verify.verify` once (vendored flat-folder). It derives the M/V assignment from the layer order exactly as `complete_assignment` does.

`python -m creasebench.gen.bpstudio.certify_samples [--trials N --seed S --inflate]` writes:
- the certified FOLD files to `samples/certified/`
- per-design results to `samples/certified/summary_*.json`

`--inflate` lengthens random leaf edges until the layout is tight.

RESULTS_PLACEHOLDER

## Limitations

1. **The line set is not crease-complete. This is more than the M/V labels.** BP Studio's CP export contains only:
   - flap and river *outer contours* (hinges)
   - ridges
   - gadget ridges and axis-parallels

   It leaves out the axial and elevation pleats inside flaps and rivers, and the hinge-pleat creases a folder adds by hand. As a result, most interior vertices fail even-degree or Kawasaki (see the table). The lizard's degree-5 vertices at (8,8), (24,8) and so on are one example. So a pure M/V-assignment solver cannot succeed on these lines alone. Crease completion has to come first: add the axial lines at every integer level of each contour, then extend ridges through them. `diagnose()` lists exactly which vertices need it. Only trivial bases, such as `star4_16`, pass as exported.
2. **The M/V labels cannot be trusted.** Every hinge is "auxiliary", every ridge is `M` and every axis-parallel is `V` by construction. These are conventions, not a folding assignment. Use `assignment` (all `U`) and treat `bp_assignment` as metadata.
3. Paper outside every flap and river contour, the excess margin, gets no creases.
4. There is one design per node process, because upstream `fullReset()` depends on DEBUG-only methods. The wrapper starts a fresh process for each call.
5. The tool only checks validity: overlapping flaps and stretches without patterns are reported as errors. It does not optimize the layout. The flap coordinates must already form a valid BP layout. Stretches whose patterns BP Studio cannot find (its "general case" TODO) return `status: "error"`.
6. Only rectangular sheets are supported. The diagonal grid type is not exposed.
