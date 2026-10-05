"""Prompt construction. Shared conventions + per-track answer formats."""

from __future__ import annotations

import json

from .tasks import Task

CONVENTIONS = """\
You are taking Origami Bench, a test of spatial and analytical reasoning about flat-folded origami.

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


def build_prompt(task: Task, agentic: bool = False, image_only: bool = False) -> str:
    parts = [CONVENTIONS]
    if agentic:
        parts.append(AGENTIC_NOTE)
    parts.append(f"Task ({task.track}, {task.difficulty}):\n{task.prompt}")
    inputs = dict(task.inputs)
    if image_only:
        inputs.pop("target_silhouette", None)
    for key, val in inputs.items():
        parts.append(f"Input `{key}`:\n```json\n{json.dumps(val, separators=(',', ':'))}\n```")
    parts.append(ANALYTIC_FORMAT if task.track == "analytic" else DESIGN_FORMAT)
    return "\n\n".join(parts)
