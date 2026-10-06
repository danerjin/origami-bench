"""Semantic target trees (stick figures) for design tasks.

Edges are [node, node, length] in arbitrary units; the scale factor reported by the
graders is paper-side units per tree unit. Node names are descriptive so models can
reason about anatomy; only the tree metric matters for grading.
"""

SEMANTIC_TREES: dict[str, dict] = {
    "lizard": {
        "description": "a lizard: head, four legs, a long tail and a body",
        "edges": [["shoulders", "head", 2], ["shoulders", "front_left_foot", 2],
                  ["shoulders", "front_right_foot", 2], ["shoulders", "hips", 3],
                  ["hips", "hind_left_foot", 2], ["hips", "hind_right_foot", 2], ["hips", "tail_tip", 4]],
    },
    "beetle": {
        "description": "a beetle: head with two antennae, six legs (two per thoracic segment), abdomen",
        "edges": [["head", "left_antenna", 2], ["head", "right_antenna", 2], ["head", "t1", 1],
                  ["t1", "leg1_l", 2], ["t1", "leg1_r", 2], ["t1", "t2", 1],
                  ["t2", "leg2_l", 2], ["t2", "leg2_r", 2], ["t2", "t3", 1],
                  ["t3", "leg3_l", 2], ["t3", "leg3_r", 2], ["t3", "abdomen_tip", 2]],
    },
    "scorpion": {
        "description": "a scorpion: two pincers, eight legs, a long segmented tail with a stinger",
        "edges": [["prosoma", "left_pincer", 3], ["prosoma", "right_pincer", 3],
                  ["prosoma", "a", 1], ["a", "leg1_l", 2], ["a", "leg1_r", 2], ["a", "b", 1],
                  ["b", "leg2_l", 2], ["b", "leg2_r", 2], ["b", "c", 1], ["c", "leg3_l", 2], ["c", "leg3_r", 2],
                  ["c", "d", 1], ["d", "leg4_l", 2], ["d", "leg4_r", 2], ["d", "stinger", 5]],
    },
    "spider": {
        "description": "a spider: eight equal legs, a small head and an abdomen",
        "edges": [["c", f"leg{i}", 3] for i in range(1, 9)] + [["c", "head", 1], ["c", "abdomen", 2]],
    },
    "deer": {
        "description": "a deer: branched antlers (two tines each), head, four legs, short tail",
        "edges": [["neck", "head", 1], ["head", "antler_l", 1], ["antler_l", "tine_l1", 1.5],
                  ["antler_l", "tine_l2", 1.5], ["head", "antler_r", 1], ["antler_r", "tine_r1", 1.5],
                  ["antler_r", "tine_r2", 1.5], ["neck", "front_left", 3], ["neck", "front_right", 3],
                  ["neck", "hips", 3], ["hips", "hind_left", 3], ["hips", "hind_right", 3], ["hips", "tail", 1]],
    },
    "bird": {
        "description": "a standing bird: head and beak, two wings, two legs, a tail",
        "edges": [["body", "head", 2], ["body", "left_wing", 3], ["body", "right_wing", 3],
                  ["body", "hips", 1], ["hips", "left_leg", 2], ["hips", "right_leg", 2], ["hips", "tail", 2]],
    },
    "crab": {
        "description": "a crab: two claws, eight legs, eyes on stalks",
        "edges": [["body", "left_claw", 3], ["body", "right_claw", 3], ["body", "left_eye", 1],
                  ["body", "right_eye", 1]] + [["body", f"leg{i}", 2] for i in range(1, 9)],
    },
    "dragon": {
        "description": "a dragon: head with two horns, two wings, four legs, long tail",
        "edges": [["head", "horn_l", 1], ["head", "horn_r", 1], ["head", "jaw", 1], ["head", "shoulders", 2],
                  ["shoulders", "wing_l", 4], ["shoulders", "wing_r", 4], ["shoulders", "front_l", 2],
                  ["shoulders", "front_r", 2], ["shoulders", "hips", 3], ["hips", "hind_l", 2],
                  ["hips", "hind_r", 2], ["hips", "tail", 5]],
    },
}
