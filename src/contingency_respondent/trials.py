"""Trial list produced by the expander and consumed by the executor."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from contingency_respondent_dsl.ast import Duration


@dataclass(frozen=True)
class Trial:
    """One Pavlovian trial.

    Attributes
    ----------
    stage:
        Stage name taken from the AST field (``phase1``, ``training``, ``test`` ...).
    cs:
        CS labels presented together on this trial (empty = US alone / context alone).
    us:
        US label, or ``None`` when no US is delivered. The executor maps labels to
        asymptotes; the DSL carries no US intensity.
    context:
        Context name, only for procedures that name a context.
    iti:
        Inter-trial interval copied from the AST when present. Not used by R–W.
    dropped:
        Names of time variables in the AST that the trial-level model ignores
        (``isi``, ``cs_duration`` ...).
    time:
        Times within the trial as contingency-py's Tier A expansion returns them
        (``cs_on``, ``cs_off``, ``us_on``, ``us_off``, ``gap``), or ``None`` for a
        trial this package builds itself. Not used by R–W.
    order:
        Presentation order of the CSs, as the Tier A expansion returns it.
    iti_s:
        Inter-trial interval in seconds, as the Tier A expansion returns it.
    """

    stage: str
    cs: frozenset[str]
    us: str | None = None
    context: str | None = None
    iti: Duration | None = None
    dropped: tuple[str, ...] = ()
    time: Mapping[str, Any] | None = None
    order: tuple[str, ...] | None = None
    iti_s: float | None = None

    def elements(self, context_as_element: bool) -> frozenset[str]:
        """Stimuli whose associative strengths are summed on this trial."""
        if context_as_element and self.context is not None:
            return self.cs | {self.context}
        return self.cs


@dataclass(frozen=True)
class Expansion:
    """Result of expanding one Tier B procedure.

    ``unsupported`` is a reason string when the procedure cannot be reduced to a
    trial list; ``trials`` is then empty.
    """

    trials: tuple[Trial, ...] = ()
    context_as_element: bool = False
    unsupported: str | None = None

    @property
    def stages(self) -> tuple[str, ...]:
        """Stage names in order of first appearance."""
        seen: dict[str, None] = {}
        for t in self.trials:
            seen.setdefault(t.stage, None)
        return tuple(seen)
