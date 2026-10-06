"""Prompt construction. Shared conventions + per-track answer formats."""

from __future__ import annotations

import json

from .tasks import Task

CONVENTIONS = """\
You are taking CreaseBench, a test of spatial and analytical reasoning about flat-folded origami.

Conventions (all tasks):
- The paper is the unit square [0,1] x [0,1], seen from its top side. Lengths are in units of the paper side.
- Crease patterns (CPs) use the FOLD format: `vertices_coords`, `edges_vertices`, `edges_assignment`
  ("M" mountain, "V" valley, "B" paper boundary, "U" folded but direction unspecified) and `faces_vertices`
  (counter-clockwise vertex loops; face indices refer to this list).
- Valley fold: the paper on both sides of the crease rises toward the viewer, so the moving part ends up
  ON TOP. Mountain fold: the opposite (it ends up underneath).
- A crease pattern describes a flat-folded state in which EVERY crease is folded completely flat (by 180
  degrees) and the paper is otherwise unbent. No paper may pass through other paper.
- Folded coordinates: report them as seen from above, without mirroring. Any position and rotation is fine
  (answers are aligned rigidly before grading), but the scale must be true.
- Layer order: a pair [f, g] in `face_above` means face f lies above face g (closer to the viewer) where
  they overlap, in the frame of your reported coordinates.
- Give your final answer as a single JSON object in a ```json fenced code block at the end of your reply.
  Numbers should have at least 6 significant digits."""

AGENTIC_NOTE = """\
You have a `python` tool that runs Python 3 code (numpy and shapely are installed) in a scratch directory
containing the task's input files. Use it as much as you like; only your final JSON answer is graded."""

ANALYTIC_FORMAT = """\
Answer format:
```json
{
  "foldable": true,
  "folded_vertices": [[x, y], ...],
  "face_above": [[f, g], ...],
  "silhouette": [[x, y], ...]
}
```
- `folded_vertices`: folded position of every CP vertex, in the same order as `vertices_coords` (main score).
- `face_above`: optional layer order for overlapping face pairs (bonus; full credit requires every
  overlapping pair).
- `silhouette`: optional outline polygon of the folded model; only used if `folded_vertices` is missing
  (worth at most 75% of the shape score).
- If the CP CANNOT be flat-folded, answer `{"foldable": false, "violation_vertices": [i, ...]}` listing
  the vertices where a local flat-foldability condition fails (empty list if the failure is global)."""

DESIGN_FORMAT = """\
Answer format: a crease pattern on the unit square, as a list of straight creases.
```json
{
  "creases": [[x1, y1, x2, y2, "M"], [x1, y1, x2, y2, "V"], ...]
}
```
- Only list creases that are folded in the final model; the paper boundary is added automatically.
- Creases may cross; they are split at intersections. Creases must end on the paper edge or on other
  creases (dangling crease ends are removed). Endpoints closer than 1e-4 are merged.
- Assignments must be "M" or "V" ("U" is accepted but costs 10% of the score).
- The pattern is graded by actually folding it: it must be flat-foldable (Maekawa, Kawasaki and a valid
  layer order), otherwise the score is 0."""


TREE_THEORY = """\
Tree theory conventions (advanced tasks):
- A flat-folded base is described by its stick-figure TREE: project the folded model onto its axis (the
  line its flaps lie along) and contract every connected piece of paper at the same axis coordinate to a
  point. Leaves are flap tips; edge lengths are distances along the axis, in units of the paper side.
- A tree is given as JSON `{"edges": [[node, node, length], ...]}`; node names are arbitrary labels.
- A design realizes a target tree at SCALE m if its flap tips can be matched to the target's leaves so
  that for every pair of target leaves (i, j) the tree distance between the matched tips is at least
  m * d_target(i, j) (Lang's path condition: flaps may be shortened or bundled afterwards). The paper is
  ONE uncut unit square. Bigger m is better; it is compared with the best known circle/river packing.
- Design systems: box pleating on an N-grid = every crease at 0/45/90/135 degrees with vertices on the 1/N
  lattice; 22.5-degree design = every crease at a multiple of 22.5 degrees; a Pythagorean stretch = a
  box-pleated pattern that also uses lattice directions from a Pythagorean triple (a, b, c) (slopes
  b/a, a/(b+c), b/(a+c), ...) to place flaps that are diagonally offset; grafting = inserting strips of
  paper into an existing crease pattern."""

FAMILY_FORMATS = {
    "read-tree": """Answer format:
```json
{"tree": {"edges": [["a", "b", 0.25], ...]}}
```
Report the tree of the folded base (all leaves, including short ones; lengths to 3 decimals).""",
    "read-tech": """Answer format:
```json
{"box_pleat": true, "grid": 16, "angles_22_5": false, "pythagorean_stretch": false, "stretch_triples": []}
```
`grid` is the smallest N such that all vertices lie on the 1/N lattice (null if none <= 512);
`stretch_triples` lists the Pythagorean triples [a, b, c] whose directions occur.""",
    "read-color": """Answer format:
```json
{"colors": {"tip_id": {"above": "front" | "back", "below": "front" | "back"}, ...}}
```
"front" is the side of the paper facing you in the crease-pattern drawing.""",
    "solve": """Answer format: the SAME creases, each assigned.
```json
{"creases": [[x1, y1, x2, y2, "M" | "V"], ...]}
```
Every crease of the input must appear with an assignment, and nothing else may be added.""",
    "pack": """Answer format:
```json
{"positions": {"leaf_name": [x, y], ...}, "scale": m}
```
Give a point in the unit square for every leaf of the tree; graded on the scale m they allow.""",
}


def build_prompt(task: Task, agentic: bool = False, image_only: bool = False) -> str:
    parts = [CONVENTIONS]
    family = task.reference.get("family")
    if task.meta.get("tier") == "advanced":
        parts.append(TREE_THEORY)
    if agentic:
        parts.append(AGENTIC_NOTE)
    parts.append(f"Task ({task.track}, {task.difficulty}):\n{task.prompt}")
    inputs = dict(task.inputs)
    if image_only:
        inputs.pop("target_silhouette", None)
    for key, val in inputs.items():
        parts.append(f"Input `{key}`:\n```json\n{json.dumps(val, separators=(',', ':'))}\n```")
    if family in FAMILY_FORMATS:
        parts.append(FAMILY_FORMATS[family])
    else:
        parts.append(ANALYTIC_FORMAT if task.track == "analytic" else DESIGN_FORMAT)
    return "\n\n".join(parts)
