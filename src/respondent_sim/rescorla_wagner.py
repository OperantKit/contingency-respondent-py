"""Compound-CS Rescorla–Wagner executor.

On each trial, for every stimulus ``i`` in the presented set ``S``::

    dV_i = alpha_i * beta * (lambda_us - sum_{j in S} V_j)

``S`` is the trial's CS set, plus the context when the expansion treats the
context as an element. A trial without a US uses ``lambda = 0`` and
``beta_nonreinforced``. Stimuli not in ``S`` are not updated.

Associative strength is kept separately per US label (one R–W system per US).
A trial delivering US ``u`` drives the ``u`` system toward ``lambda_by_us[u]``
and every other system toward 0. US labels not in ``lambda_by_us`` (for
example a CS used in the US slot in higher-order designs) carry no asymptote:
they count as a trial without a US.

Reference: Rescorla, R. A., & Wagner, A. R. (1972). A theory of Pavlovian
conditioning: Variations in the effectiveness of reinforcement and
nonreinforcement. In A. H. Black & W. F. Prokasy (Eds.), *Classical
conditioning II: Current research and theory* (pp. 64–99). Appleton-Century-Crofts.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from .trials import Expansion, Trial

DEFAULT_SYSTEM = ""


def _frozen(m: Mapping[str, float]) -> Mapping[str, float]:
    return MappingProxyType(dict(m))


@dataclass(frozen=True)
class RescorlaWagner:
    """Model parameters.

    ``alpha_by_cs`` gives per-stimulus salience; stimuli not listed use
    ``alpha_default``. ``lambda_by_us`` gives the asymptote of each US label.
    """

    alpha_by_cs: Mapping[str, float]
    lambda_by_us: Mapping[str, float]
    alpha_default: float = 0.3
    beta: float = 1.0
    beta_nonreinforced: float | None = None
    v0: float = 0.0

    def __init__(
        self,
        alpha_by_cs: Mapping[str, float],
        *,
        lambda_by_us: Mapping[str, float],
        alpha_default: float = 0.3,
        beta: float = 1.0,
        beta_nonreinforced: float | None = None,
        v0: float = 0.0,
    ) -> None:
        for name, a in {**alpha_by_cs, "<alpha_default>": alpha_default}.items():
            if not 0.0 < a <= 1.0:
                raise ValueError(f"alpha for {name!r} must lie in (0, 1], got {a}")
        for name, b in (("beta", beta), ("beta_nonreinforced", beta_nonreinforced)):
            if b is not None and not 0.0 < b <= 1.0:
                raise ValueError(f"{name} must lie in (0, 1], got {b}")
        object.__setattr__(self, "alpha_by_cs", _frozen(alpha_by_cs))
        object.__setattr__(self, "lambda_by_us", _frozen(lambda_by_us))
        object.__setattr__(self, "alpha_default", alpha_default)
        object.__setattr__(self, "beta", beta)
        object.__setattr__(self, "beta_nonreinforced", beta_nonreinforced)
        object.__setattr__(self, "v0", v0)

    def alpha(self, stimulus: str) -> float:
        return self.alpha_by_cs.get(stimulus, self.alpha_default)

    def asymptote(self, us: str | None) -> float | None:
        """``lambda`` of ``us``; ``None`` when the label has no asymptote."""
        if us is None:
            return None
        return self.lambda_by_us.get(us)


@dataclass(frozen=True)
class TrialRecord:
    """Associative strengths before and after one trial.

    ``v_before`` / ``v_after`` are the primary system (the first US label of
    ``lambda_by_us`` that occurs in the expansion); ``*_by_us`` hold every system.
    """

    index: int
    trial: Trial
    elements: frozenset[str]
    v_before_by_us: Mapping[str, Mapping[str, float]]
    v_after_by_us: Mapping[str, Mapping[str, float]]
    primary: str

    @property
    def stage(self) -> str:
        return self.trial.stage

    @property
    def us(self) -> str | None:
        return self.trial.us

    @property
    def v_before(self) -> dict[str, float]:
        return dict(self.v_before_by_us[self.primary])

    @property
    def v_after(self) -> dict[str, float]:
        return dict(self.v_after_by_us[self.primary])

    @property
    def sum_v_before(self) -> float:
        return sum(self.v_before[s] for s in self.elements)


@dataclass(frozen=True)
class Trace:
    """Trial-by-trial associative strengths of one run."""

    records: tuple[TrialRecord, ...]
    model: RescorlaWagner
    context_as_element: bool = False
    systems: tuple[str, ...] = field(default=())

    def v_at_stage_start(self, stage: str, *, us: str | None = None) -> dict[str, float]:
        """Strengths entering the first trial of ``stage`` (pre-trial values)."""
        for r in self.records:
            if r.stage == stage:
                return dict(r.v_before_by_us[us if us is not None else r.primary])
        raise KeyError(f"stage {stage!r} not in trace")

    def final(self, *, us: str | None = None) -> dict[str, float]:
        if not self.records:
            return {}
        last = self.records[-1]
        return dict(last.v_after_by_us[us if us is not None else last.primary])

    def to_json(self) -> str:
        return json.dumps(
            [
                {
                    "index": r.index,
                    "stage": r.stage,
                    "elements": sorted(r.elements),
                    "us": r.us,
                    "context": r.trial.context,
                    "v_after": {k: dict(v) for k, v in r.v_after_by_us.items()},
                }
                for r in self.records
            ],
            ensure_ascii=False,
        )


def _systems(expansion: Expansion, model: RescorlaWagner) -> tuple[str, ...]:
    used = {t.us for t in expansion.trials if t.us is not None}
    systems = tuple(u for u in model.lambda_by_us if u in used)
    return systems or (DEFAULT_SYSTEM,)


def run(expansion: Expansion, model: RescorlaWagner) -> Trace:
    """Run ``model`` over the trials of ``expansion``."""
    if expansion.unsupported is not None:
        raise ValueError(f"cannot run an unsupported expansion: {expansion.unsupported}")
    cae = expansion.context_as_element
    stimuli: dict[str, None] = {}
    for t in expansion.trials:
        for s in sorted(t.elements(cae)):
            stimuli.setdefault(s, None)
    systems = _systems(expansion, model)
    v: dict[str, dict[str, float]] = {u: dict.fromkeys(stimuli, model.v0) for u in systems}
    records: list[TrialRecord] = []
    for index, t in enumerate(expansion.trials):
        elements = t.elements(cae)
        before = {u: _frozen(vs) for u, vs in v.items()}
        lam_us = model.asymptote(t.us)
        reinforced_label = t.us if lam_us is not None else None
        nxt: dict[str, dict[str, float]] = {}
        for u, vs in v.items():
            if u == reinforced_label:
                lam, beta = model.lambda_by_us[u], model.beta
            else:
                lam = 0.0
                beta = model.beta if model.beta_nonreinforced is None else model.beta_nonreinforced
            error = lam - sum(vs[s] for s in elements)
            nxt[u] = {
                s: (x + model.alpha(s) * beta * error if s in elements else x)
                for s, x in vs.items()
            }
        v = nxt
        records.append(
            TrialRecord(
                index=index,
                trial=t,
                elements=elements,
                v_before_by_us=MappingProxyType(before),
                v_after_by_us=MappingProxyType({u: _frozen(vs) for u, vs in v.items()}),
                primary=systems[0],
            )
        )
    return Trace(tuple(records), model, cae, systems)


__all__ = ["RescorlaWagner", "Trace", "TrialRecord", "run"]
