"""The Tier B procedures as a contingency-py respondent expansion.

contingency-py's ``RespondentRegistry`` expands Tier A itself (on
contingency-rs) and leaves Tier B to expansions registered per program.
:data:`TIER_B` is that expansion for the procedures of
contingency-respondent-dsl; :func:`registry` builds a registry holding it.

Options read by :data:`TIER_B` (the rest is passed on to nested Tier A):

- ``trials`` (required, positive int) -- trials of every stage whose count the
  expression does not give. No default is chosen.
- ``control`` (bool, default false) -- expand the control condition the
  phenomenon is judged against, instead of the procedure.
- ``seed``, ``labels`` -- passed to every nested Tier A expansion (checked
  there, so a procedure with no nested Tier A does not check them).

Any other option is an error.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from contingency.errors import RespondentSpecError, RespondentUnresolvedError
from contingency.respondent import ExpandNested, RespondentExpansion, RespondentRegistry
from contingency_respondent_dsl import from_dict

from .expand import HANDLED_TYPES, expand, expand_control, nested_expansion
from .trials import Expansion

__all__ = ["TIER_B", "TierBExpansion", "registry", "to_trial_dicts"]

_UNIT_SECONDS = {"ms": 1e-3, "s": 1.0, "min": 60.0, "h": 3600.0}
_NO_TIME: Mapping[str, Any] = {
    "cs_on": None,
    "cs_off": None,
    "us_on": None,
    "us_off": None,
    "gap": None,
}
_PASSED_ON = ("seed", "labels")
_OPTIONS = frozenset({"trials", "control", *_PASSED_ON})


def to_trial_dicts(expansion: Expansion) -> list[dict[str, Any]]:
    """Trials of ``expansion`` in the contract's 7-key shape.

    ``context_as_element`` is a choice of the R–W executor and is not part of
    the trial list.
    """
    if expansion.unsupported is not None:
        raise RespondentSpecError(expansion.unsupported)
    out: list[dict[str, Any]] = []
    for t in expansion.trials:
        iti_s = t.iti_s
        if iti_s is None and t.iti is not None:
            iti_s = t.iti.value * _UNIT_SECONDS[t.iti.unit]
        out.append(
            {
                "stage": t.stage,
                "cs": sorted(t.cs),
                "us": t.us,
                "context": t.context,
                "order": None if t.order is None else list(t.order),
                "time": dict(_NO_TIME if t.time is None else t.time),
                "iti_s": iti_s,
            }
        )
    return out


def _trials_option(options: Mapping[str, Any]) -> int:
    if "trials" not in options or options["trials"] is None:
        raise RespondentUnresolvedError("trials")
    n = options["trials"]
    if isinstance(n, bool) or not isinstance(n, int) or n <= 0:
        raise RespondentSpecError(f"option 'trials' must be a positive int, got {n!r}")
    return n


def _control_option(options: Mapping[str, Any]) -> bool:
    control = options.get("control", False)
    if not isinstance(control, bool):
        raise RespondentSpecError(f"option 'control' must be a bool, got {control!r}")
    return control


class TierBExpansion:
    """Expands the Tier B procedures of contingency-respondent-dsl."""

    def __init__(self) -> None:
        self.name: str = "contingency-respondent"
        self.types: frozenset[str] = HANDLED_TYPES

    def expand(
        self,
        spec: Mapping[str, Any],
        options: Mapping[str, Any],
        expand_nested: ExpandNested,
    ) -> list[dict[str, Any]]:
        """Trial list of one Tier B expression (``spec`` is its AST dict)."""
        unknown = sorted(set(options) - _OPTIONS)
        if unknown:
            raise RespondentSpecError(f"unknown options {unknown}; known: {sorted(_OPTIONS)}")
        n = _trials_option(options)
        control = _control_option(options)
        try:
            node = from_dict(dict(spec))
        except (KeyError, TypeError, ValueError) as exc:
            raise RespondentSpecError(f"{spec.get('type')!r} is malformed: {exc}") from exc
        nested_options = {k: options[k] for k in _PASSED_ON if k in options}
        with nested_expansion(expand_nested, nested_options):
            if control:
                result = expand_control(node, default_trials=n)
                if result is None:
                    raise RespondentSpecError(f"{type(node).__name__} has no control condition")
            else:
                result = expand(node, default_trials=n)
        return to_trial_dicts(result)


TIER_B: TierBExpansion = TierBExpansion()
"""The expansion to register for the procedures of contingency-respondent-dsl."""


def registry(*others: RespondentExpansion) -> RespondentRegistry:
    """A registry with :data:`TIER_B` and ``others``."""
    return RespondentRegistry.build(TIER_B, *others)
