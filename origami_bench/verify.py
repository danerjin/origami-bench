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


def verify(cp: CreasePattern, budget: int = 200_000, solve: bool = True) -> VerifyReport:
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
    layers = solve_layers(folded, budget=budget)
    if layers.status == "found":
        return VerifyReport(True, "flat-foldable", local, folded, layers, warnings)
    if layers.status == "none":
        return VerifyReport(False, "no valid layer order exists (self-intersection)", local, folded,
                            layers, warnings)
    return VerifyReport(False, "layer solver budget exceeded (undetermined)", local, folded, layers,
                        warnings)
