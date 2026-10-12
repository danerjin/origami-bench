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


# Expert targets (20-40 flaps): insects with segmented appendages, multi-tined antlers, a dragon
# with clawed feet. Used by the expert split, only where a certified reference design exists.
def _fan(parent, prefix, lengths):
    return [[parent, f"{prefix}{i}", l] for i, l in enumerate(lengths, 1)]


def _sym(parent, name, length):
    return [[parent, f"{name}_l", length], [parent, f"{name}_r", length]]


def _legs(parent, name, length, claw=0.5):
    """A left/right pair of legs, each ending in two tarsal claws."""
    out = []
    for s in "lr":
        out += [[parent, f"{name}_{s}", length]] + _sym(f"{name}_{s}", f"{name}_{s}_claw", claw)
    return out


EXPERT_TREES: dict[str, dict] = {
    "hercules_beetle": {
        "description": "a hercules beetle: a long thoracic horn and a curved head horn, antennae, palps, "
                       "six legs, elytra and hind wings, abdomen",
        "edges": [["head", "head_horn", 4], ["head", "pronotum", 1], ["pronotum", "thorax_horn", 5]]
                 + _sym("head", "antenna", 1.5) + _sym("head", "palp", 1) + [["pronotum", "meso", 1]]
                 + _legs("pronotum", "leg1", 3) + _legs("meso", "leg2", 3) + _sym("meso", "elytron", 3)
                 + _sym("meso", "hindwing", 3.5) + [["meso", "meta", 1]] + _legs("meta", "leg3", 3.5)
                 + [["meta", "abdomen", 2]],
    },
    "dragonfly": {
        "description": "a dragonfly: four long wings, six legs, antennae, compound-eye bumps, a long abdomen "
                       "with two cerci",
        "edges": _sym("head", "antenna", 1) + _sym("head", "eye", 0.75) + [["head", "thorax", 1]]
                 + _sym("thorax", "forewing", 6) + _sym("thorax", "hindwing", 6) + _legs("thorax", "leg1", 2)
                 + _legs("thorax", "leg2", 2) + _legs("thorax", "leg3", 2.5) + [["thorax", "abdomen", 7]]
                 + _sym("abdomen", "cercus", 0.75),
    },
    "elk": {
        "description": "a bull elk: antlers with six tines on each side, ears, four legs, a tail, a muzzle",
        "edges": [["neck", "head", 2], ["head", "muzzle", 1.5]] + _sym("head", "ear", 1)
                 + [["head", "beam_l", 2], ["head", "beam_r", 2]]
                 + _fan("beam_l", "tine_l", [2, 2.5, 2, 1.5, 1.5, 1]) + _fan("beam_r", "tine_r", [2, 2.5, 2, 1.5, 1.5, 1])
                 + [["neck", "shoulders", 1]] + _sym("shoulders", "front", 4) + [["shoulders", "hips", 4]]
                 + _sym("hips", "hind", 4) + [["hips", "tail", 1]],
    },
    "clawed_dragon": {
        "description": "a dragon: horned head with whiskers, wings with three finger tips each, four legs with "
                       "three toes each, a spiked tail",
        "edges": [["neck", "head", 2], ["head", "jaw", 1.5]] + _sym("head", "horn", 2) + _sym("head", "whisker", 1.5)
                 + [["neck", "shoulders", 1], ["shoulders", "wing_l", 3], ["shoulders", "wing_r", 3]]
                 + _fan("wing_l", "finger_l", [3, 3.5, 3]) + _fan("wing_r", "finger_r", [3, 3.5, 3])
                 + [["shoulders", "fl", 2.5], ["shoulders", "fr", 2.5], ["shoulders", "hips", 3],
                    ["hips", "hl", 2.5], ["hips", "hr", 2.5]]
                 + _fan("fl", "fl_toe", [0.75] * 3) + _fan("fr", "fr_toe", [0.75] * 3)
                 + _fan("hl", "hl_toe", [0.75] * 3) + _fan("hr", "hr_toe", [0.75] * 3)
                 + [["hips", "tail", 5], ["tail", "spike_1", 1], ["tail", "spike_2", 1]],
    },
    "emperor_scorpion": {
        "description": "a scorpion: pincers with fixed and movable fingers, chelicerae, eight legs, pectines, "
                       "a segmented tail ending in a stinger",
        "edges": [["prosoma", "arm_l", 3], ["prosoma", "arm_r", 3]] + _sym("arm_l", "finger_l", 1.5)
                 + _sym("arm_r", "finger_r", 1.5) + _sym("prosoma", "chelicera", 0.75)
                 + sum((_legs("prosoma", f"leg{i}", 2.5) for i in (1, 2, 3, 4)), [])
                 + [["prosoma", "mesosoma", 2]] + _sym("mesosoma", "pectine", 0.75)
                 + [["mesosoma", "tail", 5], ["tail", "stinger", 1]],
    },
    "phoenix": {
        "description": "a phoenix: a crest of three plumes, a beak, wings with five primaries each, two legs with "
                       "three toes each, a tail of seven long feathers",
        "edges": [["neck", "head", 1.5], ["head", "beak", 1]] + _fan("head", "crest", [1.5, 2, 1.5])
                 + [["neck", "body", 1], ["body", "wing_l", 3], ["body", "wing_r", 3]]
                 + _fan("wing_l", "prim_l", [3, 3.5, 4, 3.5, 3]) + _fan("wing_r", "prim_r", [3, 3.5, 4, 3.5, 3])
                 + [["body", "leg_l", 2], ["body", "leg_r", 2]] + _fan("leg_l", "toe_l", [0.75] * 3)
                 + _fan("leg_r", "toe_r", [0.75] * 3) + [["body", "rump", 1]]
                 + _fan("rump", "tail", [5, 6, 7, 8, 7, 6, 5]),
    },
    "ant": {
        "description": "an ant: elbowed antennae, mandibles, six legs with tarsal claws (two per leg), a petiole "
                       "and gaster",
        "edges": [["head", "antenna_l", 2.5], ["head", "antenna_r", 2.5]] + _sym("head", "mandible", 1)
                 + [["head", "thorax", 1]]
                 + sum(([["thorax", f"leg{i}_{s}", 3]] + _sym(f"leg{i}_{s}", f"claw{i}_{s}", 0.5)
                        for i in (1, 2, 3) for s in "lr"), [])
                 + [["thorax", "petiole", 1], ["petiole", "gaster", 3]],
    },
}
