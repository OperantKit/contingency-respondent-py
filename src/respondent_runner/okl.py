"""Write a :class:`~respondent_runner.rescorla_wagner.Trace` as an OKL v1 log.

Layout (virtual clock, fixed trial width):

- each stage is a ``phase_enter(label=<stage>, name=<context>)`` ... ``phase_exit``;
- each trial is a ``phase_enter(label="trial-<k>", name=<context>, cue=<cs>)`` ...
  ``phase_exit``, where ``cue`` joins the sorted CS labels with ``+`` (``"a+x"``);
- a US with an asymptote in the model is a ``reinforcer_start`` / ``reinforcer_end``
  pair at the end of the trial, ``potency`` = its ``lambda``.

The OKL v1 canonical events have no stimulus-presentation field, so the CS is
carried by the ``cue`` context coordinate of the trial marker.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from contingency_respondent_dsl.ast import Duration
from experiment_core import ReinforcerEndEvent, ReinforcerStartEvent
from session_recorder import OklSink

from .rescorla_wagner import Trace

_UNIT_SECONDS = {"ms": 1e-3, "s": 1.0, "min": 60.0, "h": 3600.0}


def _seconds(d: Duration | None) -> float:
    return 0.0 if d is None else d.value * _UNIT_SECONDS[d.unit]


def _ctx(name: str | None, cue: str | None = None) -> dict[str, Any] | None:
    out = {k: v for k, v in (("name", name), ("cue", cue)) if v}
    return out or None


def write_okl(
    trace: Trace,
    path: str | Path,
    meta: Mapping[str, Any],
    *,
    trial_s: float = 10.0,
    us_s: float = 1.0,
) -> Path:
    """Write ``trace`` to ``path``.

    ``meta`` is passed to :meth:`session_recorder.OklSink.write_header`;
    ``session_name`` is required, ``clock_type`` defaults to ``"virtual"`` and
    ``session_start`` to ``0.0``.
    """
    if not 0.0 < us_s <= trial_s:
        raise ValueError(f"need 0 < us_s <= trial_s, got us_s={us_s}, trial_s={trial_s}")
    header = {"clock_type": "virtual", "session_start": 0.0, **meta}
    sink = OklSink(path)
    sink.write_header(**header)
    t = 0.0
    current: str | None = None
    rid = 0
    for r in trace.records:
        trial = r.trial
        if trial.stage != current:
            if current is not None:
                sink.write_phase_exit(timestamp=t, label=current)
            current = trial.stage
            sink.write_phase_enter(timestamp=t, label=current, context=_ctx(trial.context))
        label = f"trial-{r.index}"
        cue = "+".join(sorted(trial.cs))
        sink.write_phase_enter(timestamp=t, label=label, context=_ctx(trial.context, cue))
        lam = trace.model.asymptote(trial.us)
        if lam is not None:
            sink.emit(ReinforcerStartEvent(id=rid, timestamp=t + trial_s - us_s, potency=lam))
            sink.emit(ReinforcerEndEvent(id=rid, timestamp=t + trial_s))
            rid += 1
        t += trial_s
        sink.write_phase_exit(timestamp=t, label=label)
        t += _seconds(trial.iti)
    if current is not None:
        sink.write_phase_exit(timestamp=t, label=current)
    return Path(path)
