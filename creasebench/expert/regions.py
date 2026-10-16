"""Region identification: which flap does each marked region of a crease pattern become?

Each region is a box on the unfolded paper around exactly one flap tip of the folded base (and no
other tip). Ground truth comes from folding: the base tree is extracted and fitted to the named
target tree, giving target leaf <- base leaf (a paper vertex). Mirror-symmetric labellings are
equally correct, so the grader accepts any labelling realised by an automorphism of the target tree.
"""

from __future__ import annotations

import random
import string

import numpy as np

REGIONS_PROMPT = (
    "Below is the crease pattern of a flat-foldable origami base (one uncut square), the stick-figure tree "
    "it realizes (with named flaps), and {k} rectangular regions of the unfolded paper, labelled {labels}, "
    "also drawn on the image. Each region contains the tip of exactly one flap, and every flap tip is marked. "
    "For every region, say which flap of the tree it becomes. Pass/fail: all regions must be right (mirror-image answers, e.g. left/right "
    "swapped consistently, are accepted when the tree is symmetric).")


def region_boxes(cp, tips: dict, rng: random.Random, k: int | None = None, half: float = 0.06,
                 others=()):
    """tips: {target_leaf: paper vertex id}. Picks up to k tips (all of them when k is None) and a box
    around each that contains no other tip, shrinking the box where tips are close together.
    ``others``: paper vertex ids of further flap tips of the base (flaps the target tree does not name);
    no box may contain one either. Returns {label: box}, {label: target_leaf}."""
    pts = {leaf: np.asarray(cp.vertices[v], float) for leaf, v in tips.items()}
    extra = [np.asarray(cp.vertices[v], float) for v in set(others) - set(tips.values())]
    leaves = list(pts)
    rng.shuffle(leaves)
    boxes, answer = {}, {}
    labels = iter(list(string.ascii_uppercase) + [a + b for a in string.ascii_uppercase for b in string.ascii_uppercase])
    for leaf in leaves:
        if k is not None and len(boxes) >= k:
            break
        p = pts[leaf]
        for i in range(200):
            h = half / 2 ** (i // 25)  # shrink every 25 tries
            if h < 0.004:
                break
            dx, dy = (rng.uniform(-0.6, 0.6) * h for _ in range(2))
            x0, y0 = max(0.0, p[0] - h + dx), max(0.0, p[1] - h + dy)
            x1, y1 = min(1.0, p[0] + h + dx), min(1.0, p[1] + h + dy)
            x0, y0, x1, y1 = (round(v, 4) for v in (x0, y0, x1, y1))  # check the box exactly as published
            inside = [o for o, q in pts.items() if x0 - 1e-9 <= q[0] <= x1 + 1e-9 and y0 - 1e-9 <= q[1] <= y1 + 1e-9]
            stray = any(x0 - 1e-9 <= q[0] <= x1 + 1e-9 and y0 - 1e-9 <= q[1] <= y1 + 1e-9 for q in extra)
            if inside == [leaf] and not stray:
                lab = next(labels)
                boxes[lab] = [round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4)]
                answer[lab] = leaf
                break
    return boxes, answer
