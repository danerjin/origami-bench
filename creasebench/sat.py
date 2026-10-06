"""A small DPLL SAT solver with two-watched-literal propagation.

Good enough for layer-ordering instances of a few thousand variables. Variables
are 1-based ints; literals are +v / -v.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


@dataclass
class SATResult:
    status: str  # "sat" | "unsat" | "budget"
    model: dict[int, bool] = field(default_factory=dict)
    decisions: int = 0


class SAT:
    def __init__(self) -> None:
        self.nvars = 0
        self.clauses: list[list[int]] = []

    def new_var(self) -> int:
        self.nvars += 1
        return self.nvars

    def add_clause(self, lits) -> None:
        c = sorted(set(lits), key=abs)
        if any(-l in c for l in c):
            return  # tautology
        self.clauses.append(c)

    def solve(self, assumptions=(), budget: int = 200_000) -> SATResult:
        n = self.nvars
        assign = [0] * (n + 1)
        trail: list[int] = []
        clauses = [list(c) for c in self.clauses]
        watches: dict[int, list[int]] = {}
        units = list(assumptions)
        for ci, c in enumerate(clauses):
            if not c:
                return SATResult("unsat")
            if len(c) == 1:
                units.append(c[0])
            else:
                watches.setdefault(c[0], []).append(ci)
                watches.setdefault(c[1], []).append(ci)

        def val(lit: int) -> int:
            v = assign[abs(lit)]
            return v if lit > 0 else -v

        def enqueue(lit: int) -> bool:
            v = val(lit)
            if v == -1:
                return False
            if v == 0:
                assign[abs(lit)] = 1 if lit > 0 else -1
                trail.append(lit)
            return True

        def propagate(qhead: int) -> tuple[bool, int]:
            while qhead < len(trail):
                false_lit = -trail[qhead]
                qhead += 1
                wl = watches.get(false_lit)
                if not wl:
                    continue
                j = 0
                while j < len(wl):
                    ci = wl[j]
                    c = clauses[ci]
                    if c[0] == false_lit:
                        c[0], c[1] = c[1], c[0]
                    if val(c[0]) == 1:
                        j += 1
                        continue
                    moved = False
                    for k in range(2, len(c)):
                        if val(c[k]) != -1:
                            c[1], c[k] = c[k], c[1]
                            watches.setdefault(c[1], []).append(ci)
                            wl[j] = wl[-1]
                            wl.pop()
                            moved = True
                            break
                    if moved:
                        continue
                    if not enqueue(c[0]):
                        return False, qhead
                    j += 1
            return True, qhead

        for u in units:
            if not enqueue(u):
                return SATResult("unsat")
        ok, qhead = propagate(0)
        if not ok:
            return SATResult("unsat")

        occ = Counter(abs(l) for c in self.clauses for l in c)
        order = sorted(range(1, n + 1), key=lambda v: -occ[v])
        stack: list[tuple[int, int, bool]] = []  # (trail length, literal, flipped)
        decisions = 0
        ptr = 0
        while True:
            while ptr < len(order) and assign[order[ptr]] != 0:
                ptr += 1
            if ptr == len(order):
                return SATResult("sat", {v: assign[v] == 1 for v in range(1, n + 1)}, decisions)
            if decisions >= budget:
                return SATResult("budget", decisions=decisions)
            decisions += 1
            var = order[ptr]
            stack.append((len(trail), var, False))
            enqueue(var)
            ok, qhead = propagate(len(trail) - 1)
            while not ok:
                while stack:
                    tl, lit, flipped = stack.pop()
                    for l in trail[tl:]:
                        assign[abs(l)] = 0
                    del trail[tl:]
                    if not flipped:
                        stack.append((tl, -lit, True))
                        enqueue(-lit)
                        break
                else:
                    return SATResult("unsat", decisions=decisions)
                ok, qhead = propagate(len(trail) - 1)
                ptr = 0
            ptr = min(ptr, len(order))
