"""One-call verification of a crease pattern: local checks, folding, layer order."""

from __future__ import annotations

from dataclasses import dataclass, field

from .cp import CPError, CreasePattern
from .foldability import LocalReport, check_local
from .layers import LayerResult, solve_layers
from .simulate import FoldedState, fold

CONSISTENCY_TOL = 2e-3


@dataclass
class VerifyReport:
    foldable: bool
    reason: str
    local: LocalReport | None = None
    folded: FoldedState | None = None
    layers: LayerResult | None = None
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        d = {"foldable": self.foldable, "reason": self.reason, "warnings": self.warnings}
        if self.local is not None:
            d["local_violations"] = [v.to_dict() for v in self.local.violations]
        if self.folded is not None:
            d["consistency_error"] = self.folded.consistency_error
        if self.layers is not None:
            d["layer_status"] = self.layers.status
            d["layer_stats"] = self.layers.stats
        return d


def assignments_from_order(folded: FoldedState, above) -> list[str]:
    """Resolve U creases to M/V from a valid layer order (valley = the far face lies above)."""
    cp = folded.cp
    rel = set(map(tuple, above))
    asg = list(cp.assignments)
    eidx = cp.edge_index()
    for key, fs in cp.edge_faces().items():
        ei = eidx[key]
        if asg[ei] != "U" or len(fs) != 2:
            continue
        a, b = fs
        b_above = (b, a) in rel
        valley = b_above != folded.face_flipped(a)
        asg[ei] = "V" if valley else "M"
    return asg


def _layers_flatfolder(folded: FoldedState, timeout: float) -> LayerResult:
    from . import ffolder

    flips = [folded.face_flipped(i) for i in range(len(folded.cp.faces))]
    r = ffolder.solve(folded.cp, flips, timeout=timeout)
    stats = dict(r.stats, backend="flat-folder", seconds=round(r.seconds, 3))
    if r.status == "found":
        return LayerResult("found", r.face_above, assignments_from_order(folded, r.face_above), stats)
    if r.status == "none":
        return LayerResult("none", stats=dict(stats, reason=r.reason))
    if r.status == "error":  # e.g. a numerical-precision failure inside flat-folder
        return LayerResult("error", stats=dict(stats, reason=r.reason))
    return LayerResult("budget", stats=dict(stats, reason=r.reason))


def verify(cp: CreasePattern, budget: int = 200_000, solve: bool = True, backend: str = "auto",
           timeout: float = 120.0) -> VerifyReport:
    """Check flat-foldability.

    backend: "flatfolder" (Node.js, scales to thousands of creases), "python" (pure-Python
    SAT, fine for small patterns), or "auto" (flat-folder when Node is available).
    """
    warnings = list(cp.warnings)
    local = check_local(cp)
    try:
        folded = fold(cp)
    except CPError as e:
        return VerifyReport(False, f"cannot fold: {e}", local, warnings=warnings)
    if not local.ok:
        v = local.violations[0]
        return VerifyReport(False, f"local violation at vertex {v.vertex}: {v.rule} ({v.detail})",
                            local, folded, warnings=warnings)
    if folded.consistency_error > CONSISTENCY_TOL:
        return VerifyReport(False, f"folded geometry inconsistent (error {folded.consistency_error:.4f})",
                            local, folded, warnings=warnings)
    if not solve:
        return VerifyReport(True, "locally flat-foldable (layer order not checked)", local, folded,
                            warnings=warnings)
    if backend == "auto":
        from . import ffolder

        backend = "flatfolder" if ffolder.available() else "python"
    if backend == "flatfolder":
        layers = _layers_flatfolder(folded, timeout)
        if layers.status == "error":
            layers = solve_layers(folded, budget=budget)  # fall back to the Python solver
    else:
        layers = solve_layers(folded, budget=budget)
    if layers.status == "found":
        return VerifyReport(True, "flat-foldable", local, folded, layers, warnings)
    if layers.status == "none":
        return VerifyReport(False, "no valid layer order exists (self-intersection)", local, folded,
                            layers, warnings)
    return VerifyReport(False, "layer solver budget exceeded (undetermined)", local, folded, layers,
                        warnings)


def complete_assignment(cp: CreasePattern, timeout: float = 120.0) -> CreasePattern | None:
    """Assign M/V to every U crease so the pattern folds flat; None if impossible."""
    rep = verify(cp, timeout=timeout)
    if not rep.foldable or rep.layers is None or rep.layers.assignments is None:
        return None
    out = CreasePattern(cp.vertices.copy(), list(cp.edges), list(rep.layers.assignments),
                        [list(f) for f in cp.faces])
    out.warnings = list(cp.warnings)
    return out
