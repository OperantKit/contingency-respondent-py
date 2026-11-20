"""Expand a Tier B respondent AST into a trial list.

The input is the object returned by ``contingency_respondent_dsl.from_dict``:
Tier B nodes are frozen dataclasses, nested Tier A expressions stay as dicts in
the conformance ``expected_ast`` shape.

Nested Tier A expressions are expanded by contingency-py
(``contingency.respondent``, which runs contingency-rs); this module does not
expand Tier A itself. A Tier B procedure reads one trial template from each
nested expression and repeats it over its own stages. A nested dict whose type
is not Tier A goes to the same expander (under a registry, to its registered
owner) and must return exactly one trial. A nested Tier B procedure of
contingency-respondent-dsl is not read: ``from_dict`` turns it into a node,
which no stage takes as a template, and the procedure is reported as
unsupported. The forms read this way:

- ``Pair<Mode>(cs, us)`` (Core's type name, e.g. ``PairForwardDelay``; the
  surface spelling ``Pair.ForwardDelay`` is read too) -- ``cs`` is a label or
  ``Compound(cs_list)``; ``us="nothing"`` means no US.
- ``Extinction(cs)`` / ``Compound(cs_list)`` -- CS without US.
- ``CSOnly(cs, trials)`` / ``USOnly(us, trials)``.

``Serial(elements=[...])`` is read here, not by contingency-py: it is not a
Tier A form (Tier A ``Serial`` takes ``cs_list``). Its elements are expanded as
above and cycled one trial at a time (intermixed presentation).

The other Tier A elements (``Serial(cs_list)``, ``Contingency``,
``TrulyRandom``, ``ExplicitlyUnpaired``, ``ITI``, ``Differential``) do not
reduce to one repeated trial template, and are reported as unsupported when a
Tier B procedure nests them.

:data:`TIER_B` registers these procedures in a contingency-py
``RespondentRegistry`` (see :func:`registry`).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from typing import Any

from contingency import respondent as tier_a
from contingency.errors import RespondentSpecError, RespondentUnresolvedError
from contingency_respondent_dsl.ast import (
    Blocking,
    ConditionedInhibition,
    ConditionedTasteAversion,
    ContextualExtinction,
    ContextualFearConditioning,
    Counterconditioning,
    Duration,
    HigherOrderConditioning,
    InhibitionOfDelay,
    LatentExtinction,
    LatentInhibition,
    MediatedConditioning,
    OccasionSetting,
    Overexpectation,
    Overshadowing,
    PavlovianPREE,
    PeakProcedure,
    ReconsolidationInterference,
    Reinstatement,
    Renewal,
    RetrospectiveRevaluation,
    SensoryPreconditioning,
    SpontaneousRecovery,
    StimulusGeneralization,
    SummationRetardationTest,
    SuperConditioning,
    USPreexposure,
)

from .trials import Expansion, Trial

NO_US = "nothing"
DEFAULT_CONTEXT = "ctx"
"""Context name used when the procedure implies one context but names none."""
OTHER_CONTEXT = "ctx_other"
"""Second context for controls that test outside the training context."""
ACQUISITION_CONTEXT = "acq"
"""Acquisition context of ``ContextualExtinction`` (the AST names only the extinction context)."""
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


#: Tier A types whose trial list is one trial template repeated.
TEMPLATE_TYPES: frozenset[str] = frozenset(
    {
        "PairForwardDelay",
        "PairForwardTrace",
        "PairSimultaneous",
        "PairBackward",
        "Extinction",
        "CSOnly",
        "USOnly",
        "Compound",
    }
)

NestedExpand = Callable[[Mapping[str, Any], Mapping[str, Any]], list[dict[str, Any]]]
"""Expands one nested Tier A expression (``contingency.respondent`` signature)."""

_NESTED: ContextVar[tuple[NestedExpand, Mapping[str, Any]]] = ContextVar(
    "_NESTED", default=(tier_a.expand, {})
)


class UnsupportedExpressionError(ValueError):
    """Raised internally when a nested expression has no trial-level reading."""


@dataclass(frozen=True)
class _Template:
    cs: frozenset[str]
    us: str | None
    dropped: tuple[str, ...] = ()
    iti: Duration | None = None
    time: Mapping[str, Any] | None = None
    order: tuple[str, ...] | None = None
    iti_s: float | None = None


@contextmanager
def nested_expansion(
    expand_nested: NestedExpand, options: Mapping[str, Any] | None = None
) -> Iterator[None]:
    """Expand nested Tier A expressions with ``expand_nested`` inside the block.

    ``options`` (``seed``, ``labels``) are passed with every nested call; the
    trial count is always set here. Outside any block, nested expressions go
    to ``contingency.respondent.expand``.
    """
    token = _NESTED.set((expand_nested, dict(options or {})))
    try:
        yield
    finally:
        _NESTED.reset(token)


def _us_label(value: Any) -> str | None:
    if value is None or value == NO_US:
        return None
    if isinstance(value, str):
        return value
    raise UnsupportedExpressionError(f"US argument not understood: {value!r}")


def _nested_template(expr: Mapping[str, Any], kind: str) -> _Template:
    nested, options = _NESTED.get()
    # One template is read; the Tier B procedure sets the count (an own
    # ``trials`` of 0, as in a schematic fixture, would return no trial).
    spec = {**expr, "type": kind}
    if "trials" in spec:
        spec["trials"] = 1
    try:
        trials = nested(spec, {**options, "trials": 1})
    except (RespondentSpecError, RespondentUnresolvedError) as exc:
        raise UnsupportedExpressionError(f"{kind}: {exc}") from exc
    if len(trials) != 1:
        raise UnsupportedExpressionError(
            f"{kind}: expected one trial template, the expansion returned {len(trials)} trials"
        )
    first = trials[0]
    order = first.get("order")
    us = _us_label(first["us"])
    time = first.get("time")
    if us is None and first["us"] is not None:
        # ``nothing`` reaches contingency-rs as a label; the trial has no US.
        time = _without_us(time)
    return _Template(
        cs=frozenset(str(c) for c in first["cs"]),
        us=us,
        dropped=_dropped(expr),
        time=time,
        order=None if order is None else tuple(str(c) for c in order),
        iti_s=first.get("iti_s"),
    )


def _dropped(expr: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(k for k in _TIME_FIELDS if k in expr)


def _duration(value: Any) -> Duration | None:
    if value is None or isinstance(value, Duration):
        return value
    if isinstance(value, Mapping) and "value" in value and "unit" in value:
        try:
            return Duration(value=float(value["value"]), unit=str(value["unit"]))
        except (TypeError, ValueError) as exc:
            raise UnsupportedExpressionError(f"duration not understood: {value!r}") from exc
    raise UnsupportedExpressionError(f"duration not understood: {value!r}")


_US_TIMES = frozenset({"us_on", "us_off"})


def _without_us(time: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    """``time`` of the same trial with no US: US times, and a gap to or from one, are null."""
    if time is None:
        return None
    gap = time.get("gap")
    if isinstance(gap, Mapping) and {gap.get("from"), gap.get("to")} & _US_TIMES:
        gap = None
    return {**time, "us_on": None, "us_off": None, "gap": gap}


def _is_pair(kind: str) -> bool:
    rest = kind.removeprefix("Pair").removeprefix(".")
    return kind.startswith("Pair") and rest[:1].isupper()


def templates(expr: Any) -> tuple[_Template, ...]:
    """Trial templates of one nested Tier A expression (cycled when > 1)."""
    if not isinstance(expr, Mapping):
        raise UnsupportedExpressionError(f"nested expression not understood: {expr!r}")
    kind = str(expr.get("type", ""))
    if kind == "Serial" and "elements" in expr:
        iti = _duration(expr.get("isi"))
        out: list[_Template] = []
        for element in expr["elements"]:
            out.extend(replace(t, iti=iti) for t in templates(element))
        return tuple(out)
    if _is_pair(kind):
        kind = "Pair" + kind.removeprefix("Pair").removeprefix(".")
    if kind == "Serial":
        raise UnsupportedExpressionError(
            "Serial(cs_list) is a serial compound; needs within-CS time"
        )
    if kind in tier_a.TIER_A_TYPES - TEMPLATE_TYPES:
        raise UnsupportedExpressionError(f"{kind} does not reduce to one repeated trial template")
    return (_nested_template(expr, kind),)


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
            time=t.time,
            order=t.order,
            iti_s=t.iti_s,
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


def _inhibitor_training(excitor: _Template, inhibitor: frozenset[str]) -> tuple[_Template, ...]:
    """A+ / AX- intermix synthesised from a single excitor template."""
    return (excitor, _Template(excitor.cs | inhibitor, None, excitor.dropped))


def _two_phase(node: Any, d: int, *, test: Any = None) -> tuple[Trial, ...]:
    """``phase1`` then ``phase2`` (then ``test`` when given)."""
    trials = stage(
        "phase1", templates(node.phase1), _n(node.phase1_trials, node.phase1, d)
    ) + stage("phase2", templates(node.phase2), _n(node.phase2_trials, node.phase2, d))
    if test is not None:
        trials += stage("test", templates(test), _n(None, test, d))
    return trials


def _higher_order(node: HigherOrderConditioning, d: int) -> Expansion:
    # phase2's US slot holds a CS label; the executor gives it lambda = 0.
    return Expansion(_two_phase(node, d))


def _with_test(node: Any, d: int) -> Expansion:
    return Expansion(_two_phase(node, d, test=node.test))


def _counterconditioning(node: Counterconditioning, d: int) -> Expansion:
    return Expansion(_two_phase(node, d))


def _overexpectation(node: Overexpectation, d: int, *, control: bool) -> Expansion:
    n1 = _n(node.phase1_trials, node.phase1_a, d)
    phase1 = templates(node.phase1_a) + templates(node.phase1_b)
    trials = stage("phase1", phase1, 2 * n1)
    if not control:
        trials += stage(
            "phase2",
            templates(node.phase2_compound),
            _n(node.phase2_trials, node.phase2_compound, d),
        )
    return Expansion(trials + stage("test", templates(node.test), d))


def _super_conditioning(node: SuperConditioning, d: int, *, control: bool) -> Expansion:
    inner = _conditioned_inhibition(node.phase1_inhibitor, d)
    phase1 = tuple(
        replace(t, stage="phase1_inhibitor") for t in inner.trials if t.stage == "training"
    )
    target = templates(node.phase2_target)
    if control:
        # Same compound size with a pretrained-neutral partner, so the control
        # also shares the asymptote (an X-alone control would not).
        inhibitor = frozenset().union(*(t.cs for t in inner.trials if t.stage == "test"))
        neutral = frozenset(f"{s}_neutral" for s in inhibitor)
        target = tuple(replace(t, cs=(t.cs - inhibitor) | neutral) for t in target)
    return Expansion(phase1 + stage("phase2", target, d) + stage("test", templates(node.test), d))


def _retrospective(node: RetrospectiveRevaluation, d: int, *, control: bool) -> Expansion:
    trials = stage("phase1", templates(node.phase1_compound), d)
    if not control:
        trials += stage("phase2", templates(node.phase2_element), d)
    return Expansion(trials + stage("test", templates(node.test), d))


def _occasion_setting(node: OccasionSetting, d: int) -> Expansion:
    target = frozenset({node.target})
    both = target | {node.feature}
    if node.mode == "FeaturePositive":
        training = (_Template(both, _us_label(node.us)), _Template(target, None))
    elif node.mode == "FeatureNegative":
        training = (_Template(target, _us_label(node.us)), _Template(both, None))
    else:
        raise UnsupportedExpressionError(f"occasion-setting mode not handled: {node.mode!r}")
    probes = (_Template(frozenset({node.feature}), None), _Template(target, None))
    return Expansion(
        stage("training", training, _n(node.training_trials, None, d)) + stage("test", probes, 2)
    )


def _summation_retardation(node: SummationRetardationTest, d: int, *, control: bool) -> Expansion:
    excitor = _Template(frozenset({node.excitor}), _us_label(node.us))
    training = stage("training", _inhibitor_training(excitor, frozenset({node.inhibitor})), d)
    if node.mode == "Summation":
        probe = frozenset({node.excitor}) | (frozenset() if control else {node.inhibitor})
        return Expansion(training + stage("summation_test", (_Template(probe, None),), 1))
    if node.mode == "Retardation":
        cs = f"{node.inhibitor}_probe" if control else node.inhibitor
        return Expansion(
            training + stage("retardation", (_Template(frozenset({cs}), _us_label(node.us)),), d)
        )
    raise UnsupportedExpressionError(f"summation/retardation mode not handled: {node.mode!r}")


def _latent_inhibition(node: LatentInhibition, d: int, *, control: bool) -> Expansion:
    trials: tuple[Trial, ...] = ()
    if not control:
        trials += stage(
            "preexposure",
            templates(node.preexposure),
            _n(node.preexposure_trials, node.preexposure, d),
        )
    trials += stage(
        "training", templates(node.training), _n(node.training_trials, node.training, d)
    )
    return Expansion(trials + stage("test", templates(node.test), d))


def _us_preexposure(node: USPreexposure, d: int, *, control: bool) -> Expansion:
    ctx = DEFAULT_CONTEXT
    trials: tuple[Trial, ...] = ()
    if not control:
        trials += stage(
            "preexposure",
            templates(node.preexposure),
            _n(node.preexposure_trials, node.preexposure, d),
            context=ctx,
        )
    trials += stage(
        "training",
        templates(node.training),
        _n(node.training_trials, node.training, d),
        context=ctx,
    )
    trials += stage("test", templates(node.test), d, context=ctx)
    return Expansion(trials, context_as_element=True)


def _acq_ext(node: Any, d: int, acq_ctx: str | None, ext_ctx: str | None) -> tuple[Trial, ...]:
    return stage("acquisition", templates(node.acquisition), d, context=acq_ctx) + stage(
        "extinction", templates(node.extinction), d, context=ext_ctx
    )


def _renewal(node: Renewal, d: int, *, control: bool) -> Expansion:
    test_ctx = node.extinction_context if control else node.test_context
    return Expansion(
        _acq_ext(node, d, node.acquisition_context, node.extinction_context)
        + stage("test", templates(node.test), d, context=test_ctx),
        context_as_element=True,
    )


def _reinstatement(node: Reinstatement, d: int, *, control: bool) -> Expansion:
    ctx = DEFAULT_CONTEXT
    us_only = templates(node.reinstatement_us)
    return Expansion(
        _acq_ext(node, d, ctx, ctx)
        + stage("reinstatement", us_only, _n(None, node.reinstatement_us, d), context=ctx)
        + stage("test", templates(node.test), d, context=OTHER_CONTEXT if control else ctx),
        context_as_element=True,
    )


def _spontaneous_recovery(node: SpontaneousRecovery, d: int) -> Expansion:
    test = tuple(
        replace(t, dropped=(*t.dropped, "retention_interval")) for t in templates(node.test)
    )
    return Expansion(_acq_ext(node, d, None, None) + stage("test", test, d))


def _latent_extinction(node: LatentExtinction, d: int, *, control: bool) -> Expansion:
    pre = templates(node.preexposure)
    ctx_names = frozenset().union(*(t.cs for t in pre))
    if len(ctx_names) != 1:
        raise UnsupportedExpressionError("preexposure must name exactly one context")
    (ctx,) = ctx_names
    trials = stage("acquisition", templates(node.acquisition), d, context=ctx)
    if not control:
        context_alone = tuple(replace(t, cs=frozenset()) for t in pre)
        trials += stage(
            "preexposure",
            context_alone,
            _n(node.preexposure_trials, node.preexposure, d),
            context=ctx,
        )
    trials += stage("test", templates(node.test), d, context=ctx)
    return Expansion(trials, context_as_element=True)


def _pree(node: PavlovianPREE, d: int, *, control: bool) -> Expansion:
    p = 1.0 if control else node.reinforcement_probability
    if not 0.0 < p <= 1.0:
        raise UnsupportedExpressionError(f"reinforcement probability out of range: {p}")
    acq = templates(node.acquisition)
    if len(acq) != 1:
        raise UnsupportedExpressionError("acquisition must be a single trial form")
    # Deterministic spacing: trial k is reinforced when floor((k+1)p) > floor(kp).
    reinforced = acq[0]
    unreinforced = replace(reinforced, us=None, time=_without_us(reinforced.time))
    acquisition = tuple(
        stage("acquisition", (t,), 1)[0]
        for t in (reinforced if int((k + 1) * p) > int(k * p) else unreinforced for k in range(d))
    )
    return Expansion(
        acquisition
        + stage("extinction", templates(node.extinction), d)
        + stage("test", templates(node.test), d)
    )


def _contextual_extinction(node: ContextualExtinction, d: int, *, control: bool) -> Expansion:
    test_ctx = node.context if control else ACQUISITION_CONTEXT
    return Expansion(
        _acq_ext(node, d, ACQUISITION_CONTEXT, node.context)
        + stage("test", templates(node.test), d, context=test_ctx),
        context_as_element=True,
    )


def _reconsolidation(node: ReconsolidationInterference, d: int, *, control: bool) -> Expansion:
    trials = stage("acquisition", templates(node.acquisition), d)
    if not control:
        reactivation = tuple(
            replace(t, dropped=(*t.dropped, "interference_window"))
            for t in templates(node.reactivation)
        )
        trials += stage("reactivation", reactivation, _n(None, node.reactivation, 1))
    return Expansion(
        trials
        + stage("extinction", templates(node.extinction), d)
        + stage("test", templates(node.test), d)
    )


def _taste_aversion(node: ConditionedTasteAversion, d: int) -> Expansion:
    tmpl = _Template(
        frozenset({node.taste_cs}), _us_label(node.visceral_us), ("cs_duration", "delay_to_us")
    )
    return Expansion(stage("training", (tmpl,), _n(node.training_trials, None, d)))


def _generalization(node: StimulusGeneralization, d: int) -> Expansion:
    trials = stage("training", templates(node.training), _n(node.training_trials, node.training, d))
    n_test = _n(node.test_trials, None, d)
    for s in node.test_gradient:
        trials += stage(f"test_{s}", (_Template(frozenset({s}), None),), n_test)
    return Expansion(trials)


def _contextual_fear(node: ContextualFearConditioning, d: int) -> Expansion:
    tmpl = _Template(frozenset(), _us_label(node.us), ("us_onset_from_entry",))
    return Expansion(
        stage("training", (tmpl,), _n(node.training_trials, None, d), context=node.context),
        context_as_element=True,
    )


_Handler = Callable[[Any, int, bool], Expansion]

_HANDLERS: Mapping[type, _Handler] = {
    HigherOrderConditioning: lambda n, d, c: _higher_order(n, d),
    SensoryPreconditioning: lambda n, d, c: _with_test(n, d),
    Counterconditioning: lambda n, d, c: _counterconditioning(n, d),
    Blocking: lambda n, d, c: _blocking(n, d, control=c),
    Overshadowing: lambda n, d, c: _overshadowing(n, d, control=c),
    Overexpectation: lambda n, d, c: _overexpectation(n, d, control=c),
    SuperConditioning: lambda n, d, c: _super_conditioning(n, d, control=c),
    RetrospectiveRevaluation: lambda n, d, c: _retrospective(n, d, control=c),
    ConditionedInhibition: lambda n, d, c: _conditioned_inhibition(n, d),
    OccasionSetting: lambda n, d, c: _occasion_setting(n, d),
    SummationRetardationTest: lambda n, d, c: _summation_retardation(n, d, control=c),
    LatentInhibition: lambda n, d, c: _latent_inhibition(n, d, control=c),
    USPreexposure: lambda n, d, c: _us_preexposure(n, d, control=c),
    Renewal: lambda n, d, c: _renewal(n, d, control=c),
    Reinstatement: lambda n, d, c: _reinstatement(n, d, control=c),
    SpontaneousRecovery: lambda n, d, c: _spontaneous_recovery(n, d),
    LatentExtinction: lambda n, d, c: _latent_extinction(n, d, control=c),
    PavlovianPREE: lambda n, d, c: _pree(n, d, control=c),
    ContextualExtinction: lambda n, d, c: _contextual_extinction(n, d, control=c),
    ReconsolidationInterference: lambda n, d, c: _reconsolidation(n, d, control=c),
    ConditionedTasteAversion: lambda n, d, c: _taste_aversion(n, d),
    StimulusGeneralization: lambda n, d, c: _generalization(n, d),
    ContextualFearConditioning: lambda n, d, c: _contextual_fear(n, d),
    MediatedConditioning: lambda n, d, c: _with_test(n, d),
}

_HAS_CONTROL: frozenset[type] = frozenset(
    {
        Blocking,
        Overshadowing,
        Overexpectation,
        SuperConditioning,
        RetrospectiveRevaluation,
        SummationRetardationTest,
        LatentInhibition,
        USPreexposure,
        Renewal,
        Reinstatement,
        LatentExtinction,
        PavlovianPREE,
        ContextualExtinction,
        ReconsolidationInterference,
    }
)

HANDLED_TYPES: frozenset[str] = frozenset(
    kind.__name__ for kind in (*_HANDLERS, *_UNSUPPORTED_REASONS)
)
"""AST ``type`` of every Tier B procedure this module recognises (the class name)."""


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
