"""Expand a Tier B respondent AST into a trial list.

The input is the object returned by ``contingency_respondent_dsl.from_dict``:
Tier B nodes are frozen dataclasses, nested Tier A expressions stay as dicts in
the conformance ``expected_ast`` shape.

Nested Tier A forms understood here (one form = one trial template):

- ``Pair.<mode>(cs, us)`` -- ``cs`` is a label or ``Compound(elements)``;
  ``us="nothing"`` means no US. Timing arguments are dropped.
- ``Extinction(cs)`` / ``Compound(elements)`` -- CS without US.
- ``CSOnly(cs, trials)`` / ``USOnly(us, trials)``.
- ``Serial(elements=[...])`` -- intermixed presentation: the element templates
  are cycled one trial at a time.

``Serial(cs_list=[...])`` (a serial compound stimulus) needs within-CS time and
is reported as unsupported.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from contingency_respondent_dsl.ast import (
    Blocking,
    ConditionedInhibition,
    Duration,
    InhibitionOfDelay,
    Overshadowing,
    PeakProcedure,
)

from .trials import Expansion, Trial

NO_US = "nothing"
_TIME_FIELDS = (
    "isi",
    "cs_duration",
    "retention_interval",
    "interference_window",
    "delay_to_us",
    "us_onset_from_entry",
)

_UNSUPPORTED_REASONS: Mapping[type, str] = {
    InhibitionOfDelay: "needs the distribution of responding within the CS",
    PeakProcedure: "needs the distribution of responding within the CS",
}


class UnsupportedExpressionError(ValueError):
    """Raised internally when a nested expression has no trial-level reading."""


@dataclass(frozen=True)
class _Template:
    cs: frozenset[str]
    us: str | None
    dropped: tuple[str, ...] = ()
    iti: Duration | None = None


def _cs_set(value: Any) -> frozenset[str]:
    if isinstance(value, str):
        return frozenset({value})
    if isinstance(value, Mapping) and value.get("type") == "Compound":
        return frozenset(str(e) for e in value.get("elements", value.get("cs_list", ())))
    raise UnsupportedExpressionError(f"CS argument not understood: {value!r}")


def _us_label(value: Any) -> str | None:
    if value is None or value == NO_US:
        return None
    if isinstance(value, str):
        return value
    raise UnsupportedExpressionError(f"US argument not understood: {value!r}")


def _dropped(expr: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(k for k in _TIME_FIELDS if k in expr)


def _duration(value: Any) -> Duration | None:
    if isinstance(value, Duration):
        return value
    if isinstance(value, Mapping) and "value" in value and "unit" in value:
        return Duration(value=float(value["value"]), unit=str(value["unit"]))
    return None


def templates(expr: Any) -> tuple[_Template, ...]:
    """Trial templates of one nested Tier A expression (cycled when > 1)."""
    if not isinstance(expr, Mapping):
        raise UnsupportedExpressionError(f"nested expression not understood: {expr!r}")
    kind = str(expr.get("type", ""))
    if kind.startswith("Pair."):
        return (_Template(_cs_set(expr["cs"]), _us_label(expr.get("us")), _dropped(expr)),)
    if kind in ("Extinction", "CSOnly", "Compound"):
        cs = _cs_set(expr["cs"] if kind != "Compound" else expr)
        return (_Template(cs, None, _dropped(expr)),)
    if kind == "USOnly":
        return (_Template(frozenset(), _us_label(expr["us"]), _dropped(expr)),)
    if kind == "Serial":
        if "elements" not in expr:
            raise UnsupportedExpressionError(
                "Serial(cs_list) is a serial compound; needs within-CS time"
            )
        iti = _duration(expr.get("isi"))
        out: list[_Template] = []
        for element in expr["elements"]:
            out.extend(replace(t, iti=iti) for t in templates(element))
        return tuple(out)
    raise UnsupportedExpressionError(f"nested expression type not handled: {kind!r}")


def _own_trials(expr: Any) -> int | None:
    if isinstance(expr, Mapping) and isinstance(expr.get("trials"), int) and expr["trials"] > 0:
        return int(expr["trials"])
    return None


def stage(
    name: str,
    tmpl: Sequence[_Template],
    n: int,
    *,
    context: str | None = None,
) -> tuple[Trial, ...]:
    """``n`` trials cycling through ``tmpl``."""
    if not tmpl:
        return ()
    return tuple(
        Trial(
            stage=name,
            cs=t.cs,
            us=t.us,
            context=context,
            iti=t.iti,
            dropped=t.dropped,
        )
        for t in (tmpl[k % len(tmpl)] for k in range(n))
    )


def _n(value: int | None, expr: Any, default: int) -> int:
    if value is not None:
        return value
    own = _own_trials(expr)
    return own if own is not None else default


def _first_us(tmpl: Sequence[_Template]) -> str | None:
    return next((t.us for t in tmpl if t.us is not None), None)


# --------------------------------------------------------------------------- #
# Procedures
# --------------------------------------------------------------------------- #


def _blocking(node: Blocking, d: int, *, control: bool) -> Expansion:
    trials: tuple[Trial, ...] = ()
    if not control:
        trials += stage("phase1", templates(node.phase1), _n(node.phase1_trials, node.phase1, d))
    trials += stage("phase2", templates(node.phase2), _n(node.phase2_trials, node.phase2, d))
    trials += stage("test", templates(node.test), _n(node.test_trials, node.test, d))
    return Expansion(trials)


def _overshadowing(node: Overshadowing, d: int, *, control: bool) -> Expansion:
    training = templates(node.training)
    n = _n(node.training_trials, node.training, d)
    test_b = templates(node.test_b)
    if control:
        single = tuple(_Template(t.cs, _first_us(training), t.dropped) for t in test_b)
        return Expansion(stage("training", single, n) + stage("test_b", test_b, d))
    return Expansion(
        stage("training", training, n)
        + stage("test_a", templates(node.test_a), d)
        + stage("test_b", test_b, d)
    )


def _conditioned_inhibition(node: ConditionedInhibition, d: int) -> Expansion:
    training = templates(node.training)
    test = templates(node.test)
    if len(training) == 1 and training[0].us is not None:
        # Schematic fixture: only A+ is written. Synthesise the A+ / AI- intermix,
        # with I taken from the test expression.
        a = training[0]
        inhibitor = frozenset().union(*(t.cs for t in test)) - a.cs
        if not inhibitor:
            raise UnsupportedExpressionError("cannot find the inhibitor in the test expression")
        training = (a, _Template(a.cs | inhibitor, None, a.dropped))
    return Expansion(
        stage("training", training, _n(node.training_trials, node.training, d))
        + stage("test", test, d)
    )


_Handler = Callable[[Any, int, bool], Expansion]

_HANDLERS: Mapping[type, _Handler] = {
    Blocking: lambda n, d, c: _blocking(n, d, control=c),
    Overshadowing: lambda n, d, c: _overshadowing(n, d, control=c),
    ConditionedInhibition: lambda n, d, c: _conditioned_inhibition(n, d),
}

_HAS_CONTROL: frozenset[type] = frozenset({Blocking, Overshadowing})


def expand(node: Any, *, default_trials: int = 20) -> Expansion:
    """Expand ``node`` into trials.

    ``default_trials`` is used for every stage whose trial count is not given in
    the AST.
    """
    return _dispatch(node, default_trials, control=False)


def expand_control(node: Any, *, default_trials: int = 20) -> Expansion | None:
    """Control condition needed to judge the phenomenon, or ``None`` if none."""
    if type(node) not in _HAS_CONTROL:
        return None
    return _dispatch(node, default_trials, control=True)


def _dispatch(node: Any, default_trials: int, *, control: bool) -> Expansion:
    if default_trials <= 0:
        raise ValueError(f"default_trials must be > 0, got {default_trials}")
    kind = type(node)
    if kind in _UNSUPPORTED_REASONS:
        return Expansion(unsupported=f"{kind.__name__}: {_UNSUPPORTED_REASONS[kind]}")
    handler = _HANDLERS.get(kind)
    if handler is None:
        return Expansion(unsupported=f"{kind.__name__}: expansion not implemented")
    try:
        return handler(node, default_trials, control)
    except UnsupportedExpressionError as exc:
        return Expansion(unsupported=f"{kind.__name__}: {exc}")
