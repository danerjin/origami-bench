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


def _chain(names, length):
    return [[a, b, length] for a, b in zip(names, names[1:])]


# Larger targets (14-22 flaps, uneven lengths) for the hard split.
_centipede_body = [f"s{i}" for i in range(9)]
BIG_TREES: dict[str, dict] = {
    "stag_beetle": {
        "description": "a stag beetle: long mandibles, antennae, palps, six legs, two elytra (wings), abdomen",
        "edges": [["head", "mandible_l", 4], ["head", "mandible_r", 4], ["head", "antenna_l", 2],
                  ["head", "antenna_r", 2], ["head", "palp_l", 1], ["head", "palp_r", 1], ["head", "t1", 1],
                  ["t1", "leg1_l", 3], ["t1", "leg1_r", 3], ["t1", "t2", 1], ["t2", "leg2_l", 3],
                  ["t2", "leg2_r", 3], ["t2", "elytron_l", 3], ["t2", "elytron_r", 3], ["t2", "t3", 1],
                  ["t3", "leg3_l", 3], ["t3", "leg3_r", 3], ["t3", "abdomen_tip", 2]],
    },
    "mantis": {
        "description": "a praying mantis: antennae, raptorial forelegs, four walking legs, four wings, "
                       "abdomen with two cerci",
        "edges": [["head", "antenna_l", 3], ["head", "antenna_r", 3], ["head", "prothorax", 2],
                  ["prothorax", "raptor_l", 4], ["prothorax", "raptor_r", 4], ["prothorax", "meso", 1],
                  ["meso", "mid_l", 3], ["meso", "mid_r", 3], ["meso", "forewing_l", 3],
                  ["meso", "forewing_r", 3], ["meso", "meta", 1], ["meta", "hind_l", 3.5],
                  ["meta", "hind_r", 3.5], ["meta", "hindwing_l", 3], ["meta", "hindwing_r", 3],
                  ["meta", "abdomen", 2], ["abdomen", "cercus_l", 1], ["abdomen", "cercus_r", 1]],
    },
    "lobster": {
        "description": "a lobster: two big claws, long antennae, antennules, eight walking legs, a three-lobed tail fan",
        "edges": [["head", "antenna_l", 6], ["head", "antenna_r", 6], ["head", "antennule_l", 2],
                  ["head", "antennule_r", 2], ["head", "thorax", 1], ["thorax", "claw_l", 4],
                  ["thorax", "claw_r", 4]] + [["thorax", f"leg{i}", 2] for i in range(1, 9)]
                 + [["thorax", "tail", 4], ["tail", "fan_l", 1.5], ["tail", "fan_m", 1.5], ["tail", "fan_r", 1.5]],
    },
    "centipede": {
        "description": "a centipede: antennae, forcipules, nine pairs of legs along a segmented body, long tail legs",
        "edges": [["s0", "antenna_l", 2.5], ["s0", "antenna_r", 2.5], ["s0", "forcipule_l", 1],
                  ["s0", "forcipule_r", 1]] + _chain(_centipede_body, 1)
                 + [[s, f"leg{i}_{side}", 2] for i, s in enumerate(_centipede_body) for side in ("l", "r")]
                 + [["s8", "tail_leg_l", 3], ["s8", "tail_leg_r", 3]],
    },
    "pegasus": {
        "description": "a pegasus: head with two ears and a muzzle, wings with three primary feathers each, four legs, a tail",
        "edges": [["neck", "head", 2], ["head", "ear_l", 0.75], ["head", "ear_r", 0.75], ["head", "muzzle", 1], ["neck", "withers", 1],
                  ["withers", "wing_l", 3], ["wing_l", "prim_l1", 2], ["wing_l", "prim_l2", 2.5],
                  ["wing_l", "prim_l3", 2], ["withers", "wing_r", 3], ["wing_r", "prim_r1", 2],
                  ["wing_r", "prim_r2", 2.5], ["wing_r", "prim_r3", 2], ["withers", "front_l", 4],
                  ["withers", "front_r", 4], ["withers", "hips", 3], ["hips", "hind_l", 4],
                  ["hips", "hind_r", 4], ["hips", "tail", 3]],
    },
    "tarantula": {
        "description": "a tarantula: eight long legs, pedipalps, chelicerae, spinnerets on a big abdomen",
        "edges": [["cephalothorax", f"leg{i}", 4] for i in range(1, 9)]
                 + [["cephalothorax", "pedipalp_l", 2], ["cephalothorax", "pedipalp_r", 2],
                    ["cephalothorax", "chelicera_l", 1], ["cephalothorax", "chelicera_r", 1],
                    ["cephalothorax", "abdomen", 2.5], ["abdomen", "spinneret_l", 0.75],
                    ["abdomen", "spinneret_r", 0.75]],
    },
}
