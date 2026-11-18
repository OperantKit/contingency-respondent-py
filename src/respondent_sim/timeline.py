"""Stimulus sequence of a respondent program on a real-time clock.

This is the respondent runner's side of the same-experiment fixtures
(contingency-dsl ``conformance/equivalence/``): given a respondent program AST
and a response sequence, return the sequence of stimulus onsets and offsets.

Supported programs (fixed values only):

- ``Pair.ForwardDelay(cs, us, isi, cs_duration)`` -- CS on at the trial start,
  CS off at ``cs_duration``, US on at ``isi``;
- ``USOnly(us, trials)`` -- the US alone;

each optionally annotated with ``@iti(distribution=fixed, mean=...)``.

Timing rules:

- the session starts with an ITI;
- the ITI runs from the offset of the last stimulus of a trial to the next
  trial start;
- the US lasts ``presentation_s[us]`` seconds (a property of the apparatus,
  carried by neither vocabulary);
- the session ends after ``end_offsets[name]`` offsets of each named stimulus;
- at the same time, offsets come before onsets.

None of the supported programs has a response->stimulus dependency, so the
response sequence does not change the result. It is still validated so that a
malformed input fails loudly.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, NamedTuple

_UNIT_SECONDS = {"ms": 1e-3, "s": 1.0, "min": 60.0, "h": 3600.0}


class StimulusEvent(NamedTuple):
    """One onset or offset: ``kind`` is ``"on"`` or ``"off"``."""

    time: float
    stimulus: str
    kind: str


class UnsupportedProgramError(ValueError):
    """The program has no stimulus-sequence reading here."""


def _seconds(value: Any) -> float:
    if not isinstance(value, Mapping) or "value" not in value:
        raise UnsupportedProgramError(f"duration not understood: {value!r}")
    unit = value.get("unit", value.get("time_unit"))
    if unit not in _UNIT_SECONDS:
        raise UnsupportedProgramError(f"time unit not understood: {unit!r}")
    return float(value["value"]) * _UNIT_SECONDS[str(unit)]


def _iti(annotations: Iterable[Mapping[str, Any]]) -> float:
    iti = 0.0
    for ann in annotations:
        if ann.get("keyword") != "iti":
            raise UnsupportedProgramError(f"annotation not handled: @{ann.get('keyword')}")
        params = ann.get("params", {})
        if params.get("distribution") != "fixed":
            raise UnsupportedProgramError("only @iti(distribution=fixed) gives a fixed sequence")
        iti = _seconds(params["mean"])
    return iti


def _trial(expr: Mapping[str, Any], presentation_s: Mapping[str, float]) -> list[StimulusEvent]:
    """Events of one trial, with times relative to the trial start."""
    kind = expr.get("type")
    if kind in ("PairForwardDelay", "Pair.ForwardDelay"):
        cs, us = str(expr["cs"]), str(expr["us"])
        isi, cs_dur = _seconds(expr["isi"]), _seconds(expr["cs_duration"])
        return [
            StimulusEvent(0.0, cs, "on"),
            StimulusEvent(cs_dur, cs, "off"),
            StimulusEvent(isi, us, "on"),
            StimulusEvent(isi + _presentation(presentation_s, us), us, "off"),
        ]
    if kind == "USOnly":
        us = str(expr["us"])
        return [
            StimulusEvent(0.0, us, "on"),
            StimulusEvent(_presentation(presentation_s, us), us, "off"),
        ]
    raise UnsupportedProgramError(f"program type not handled: {kind!r}")


def _presentation(presentation_s: Mapping[str, float], us: str) -> float:
    if us not in presentation_s:
        raise UnsupportedProgramError(f"no presentation duration for {us!r}")
    d = float(presentation_s[us])
    if d <= 0:
        raise UnsupportedProgramError(f"presentation duration of {us!r} must be > 0, got {d}")
    return d


def _order(e: StimulusEvent) -> tuple[float, int, str]:
    return (e.time, 0 if e.kind == "off" else 1, e.stimulus)


def _validate(responses: Iterable[tuple[float, str]]) -> None:
    last = float("-inf")
    for t, name in responses:
        if not isinstance(name, str) or not name:
            raise ValueError(f"response name must be a non-empty string, got {name!r}")
        if t < last:
            raise ValueError("responses must be in time order")
        last = t


def stimulus_timeline(
    program: Mapping[str, Any],
    *,
    presentation_s: Mapping[str, float],
    end_offsets: Mapping[str, int],
    responses: Iterable[tuple[float, str]] = (),
) -> tuple[StimulusEvent, ...]:
    """Stimulus onsets and offsets of ``program`` until ``end_offsets`` is reached."""
    _validate(responses)
    if not end_offsets or any(n <= 0 for n in end_offsets.values()):
        raise ValueError(f"end_offsets needs positive counts, got {dict(end_offsets)!r}")
    if program.get("type") == "AnnotatedSchedule":
        expr, iti = program["expr"], _iti(program.get("annotations", ()))
    else:
        expr, iti = program, 0.0
    trial = sorted(_trial(expr, presentation_s), key=_order)
    width = max(e.time for e in trial)
    limit = expr.get("trials") if expr.get("type") == "USOnly" else None

    events: list[StimulusEvent] = []
    offsets: dict[str, int] = {}
    start = iti
    n = 0
    while any(offsets.get(s, 0) < k for s, k in end_offsets.items()):
        if limit is not None and n >= int(limit):
            raise ValueError(f"program ends after {limit} trials before end_offsets is reached")
        for e in trial:
            events.append(StimulusEvent(start + e.time, e.stimulus, e.kind))
            if e.kind == "off":
                offsets[e.stimulus] = offsets.get(e.stimulus, 0) + 1
        n += 1
        start += width + iti
    return tuple(sorted(events, key=_order))
