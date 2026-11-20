"""Write a :class:`~contingency_respondent.rescorla_wagner.Trace` as an OKL v1 log.

Layout (virtual clock, fixed trial width):

- each stage is a ``phase_enter(label=<stage>, name=<context>)`` ... ``phase_exit``;
- each trial is a ``phase_enter(label="trial-<k>", name=<context>)`` ... ``phase_exit``;
- every CS of the trial is a ``stimulus_on`` at the trial start and a
  ``stimulus_off`` at the trial end;
- the US, when the trial has one, is a ``stimulus_on`` / ``stimulus_off`` pair
  ending with the trial.

CS and US are written with the same theory-neutral stimulus events. Model
quantities (``lambda``, associative strength) are not written to the log.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from contingency_respondent_dsl.ast import Duration
from session_recorder import OklSink

from .rescorla_wagner import Trace

_UNIT_SECONDS = {"ms": 1e-3, "s": 1.0, "min": 60.0, "h": 3600.0}


def _seconds(d: Duration | None) -> float:
    return 0.0 if d is None else d.value * _UNIT_SECONDS[d.unit]


def _ctx(name: str | None) -> dict[str, Any] | None:
    return {"name": name} if name else None


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
    for r in trace.records:
        trial = r.trial
        if trial.stage != current:
            if current is not None:
                sink.write_phase_exit(timestamp=t, label=current)
            current = trial.stage
            sink.write_phase_enter(timestamp=t, label=current, context=_ctx(trial.context))
        label = f"trial-{r.index}"
        cs = sorted(trial.cs)
        sink.write_phase_enter(timestamp=t, label=label, context=_ctx(trial.context))
        for s in cs:
            sink.write_stimulus_on(timestamp=t, stimulus=s)
        end = t + trial_s
        if trial.us is not None:
            sink.write_stimulus_on(timestamp=end - us_s, stimulus=trial.us)
            sink.write_stimulus_off(timestamp=end, stimulus=trial.us)
        for s in cs:
            sink.write_stimulus_off(timestamp=end, stimulus=s)
        t = end
        sink.write_phase_exit(timestamp=t, label=label)
        t += _seconds(trial.iti)
    if current is not None:
        sink.write_phase_exit(timestamp=t, label=current)
    return Path(path)
