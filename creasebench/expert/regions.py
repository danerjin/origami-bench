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
    "also drawn on the image. Each region contains the tip of exactly one flap. For every region, say which "
    "flap of the tree it becomes. Pass/fail: all regions must be right (mirror-image answers, e.g. left/right "
    "swapped consistently, are accepted when the tree is symmetric).")


def region_boxes(cp, tips: dict, rng: random.Random, k: int = 6, half: float = 0.06):
    """tips: {target_leaf: paper vertex id}. Picks up to k tips and a box around each that contains
    no other tip. Returns {label: box}, {label: target_leaf}."""
    pts = {leaf: np.asarray(cp.vertices[v], float) for leaf, v in tips.items()}
    leaves = list(pts)
    rng.shuffle(leaves)
    boxes, answer = {}, {}
    labels = iter(string.ascii_uppercase)
    for leaf in leaves:
        if len(boxes) >= k:
            break
        p = pts[leaf]
        for _ in range(50):
            dx, dy = (rng.uniform(-0.6, 0.6) * half for _ in range(2))
            x0, y0 = max(0.0, p[0] - half + dx), max(0.0, p[1] - half + dy)
            x1, y1 = min(1.0, p[0] + half + dx), min(1.0, p[1] + half + dy)
            inside = [o for o, q in pts.items() if x0 - 1e-9 <= q[0] <= x1 + 1e-9 and y0 - 1e-9 <= q[1] <= y1 + 1e-9]
            if inside == [leaf]:
                lab = next(labels)
                boxes[lab] = [round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4)]
                answer[lab] = leaf
                break
    return boxes, answer
