"""Expansion of a few Tier B procedures written inline.

Inputs are Tier B ASTs written inline in the conformance ``expected_ast``
dict shape and reconstructed with ``contingency_respondent_dsl.from_dict``.
What the model predicts from these trials is checked by contingency-bench's
respondent law suite, not here.
"""

from __future__ import annotations

from typing import Any

from contingency_respondent_dsl import from_dict

from contingency_respondent.expand import expand, expand_control

_SEC = {"value": 10, "unit": "s"}
_DUR = {"value": 15, "unit": "s"}


def _pair(cs: Any, us: str) -> dict[str, Any]:
    return {"type": "Pair.ForwardDelay", "cs": cs, "us": us, "isi": _SEC, "cs_duration": _DUR}


def _compound(*elements: str) -> dict[str, Any]:
    return {"type": "Compound", "cs_list": list(elements)}


BLOCKING = {
    "type": "Blocking",
    "phase1": _pair("a", "shock"),
    "phase2": _pair(_compound("a", "x"), "shock"),
    "test": {"type": "Extinction", "cs": "x"},
    "phase1_trials": 40,
    "phase2_trials": 20,
    "test_trials": 10,
}

OVERSHADOWING = {
    "type": "Overshadowing",
    "training": _pair(_compound("loud_tone", "dim_light"), "shock"),
    "test_a": {"type": "Extinction", "cs": "loud_tone"},
    "test_b": {"type": "Extinction", "cs": "dim_light"},
    "training_trials": 40,
}

CONDITIONED_INHIBITION = {
    "type": "ConditionedInhibition",
    "training": {
        "type": "Serial",
        "elements": [_pair("a", "shock"), _pair(_compound("a", "i"), "nothing")],
        "isi": {"value": 30, "unit": "s"},
    },
    "test": {"type": "Extinction", "cs": "i"},
    "training_trials": 400,
}


def _stage_kinds(exp: Any, stage: str) -> set[tuple[frozenset[str], str | None]]:
    return {(t.cs, t.us) for t in exp.trials if t.stage == stage}


def test_blocking_stages_and_control() -> None:
    node = from_dict(BLOCKING)
    exp = expand(node)
    ctrl = expand_control(node)
    assert exp.unsupported is None
    assert ctrl is not None
    assert exp.stages == ("phase1", "phase2", "test")
    assert _stage_kinds(exp, "phase1") == {(frozenset({"a"}), "shock")}
    assert _stage_kinds(exp, "phase2") == {(frozenset({"a", "x"}), "shock")}
    assert _stage_kinds(exp, "test") == {(frozenset({"x"}), None)}
    assert [len([t for t in exp.trials if t.stage == s]) for s in exp.stages] == [40, 20, 10]
    # The control skips phase 1, so A has no history when AX is trained.
    assert ctrl.stages == ("phase2", "test")
    assert _stage_kinds(ctrl, "phase2") == {(frozenset({"a", "x"}), "shock")}


def test_overshadowing_tests_each_element_alone() -> None:
    node = from_dict(OVERSHADOWING)
    exp = expand(node)
    ctrl = expand_control(node)
    assert ctrl is not None
    assert _stage_kinds(ctrl, "training") == {(frozenset({"dim_light"}), "shock")}
    assert _stage_kinds(exp, "training") == {(frozenset({"loud_tone", "dim_light"}), "shock")}
    assert _stage_kinds(exp, "test_a") == {(frozenset({"loud_tone"}), None)}
    assert _stage_kinds(exp, "test_b") == {(frozenset({"dim_light"}), None)}


def test_conditioned_inhibition_intermixes_a_plus_and_ai_minus() -> None:
    exp = expand(from_dict(CONDITIONED_INHIBITION))
    training = [(t.cs, t.us) for t in exp.trials if t.stage == "training"]
    assert len(training) == 400
    assert set(training) == {(frozenset({"a"}), "shock"), (frozenset({"a", "i"}), None)}
    assert training[:2] == [(frozenset({"a"}), "shock"), (frozenset({"a", "i"}), None)]


def test_conditioned_inhibition_single_pair_is_synthesised() -> None:
    node = from_dict({**CONDITIONED_INHIBITION, "training": _pair("a", "shock")})
    exp = expand(node)
    kinds = {(t.cs, t.us) for t in exp.trials if t.stage == "training"}
    assert kinds == {(frozenset({"a"}), "shock"), (frozenset({"a", "i"}), None)}


def test_time_dependent_procedures_are_unsupported() -> None:
    for data in (
        {
            "type": "InhibitionOfDelay",
            "cs": "tone",
            "us": "shock",
            "cs_duration": {"value": 60, "unit": "s"},
            "isi": {"value": 45, "unit": "s"},
            "training_trials": 200,
        },
        {
            "type": "PeakProcedure",
            "cs": "tone",
            "us": "food",
            "fi_duration": {"value": 30, "unit": "s"},
            "peak_probe_duration": {"value": 90, "unit": "s"},
            "peak_probe_probability": 0.25,
            "training_trials": 400,
        },
    ):
        exp = expand(from_dict(data))
        assert exp.unsupported is not None
        assert exp.trials == ()


def test_serial_compound_is_unsupported() -> None:
    node = from_dict(
        {
            **BLOCKING,
            "phase2": {"type": "Serial", "cs_list": ["a", "x"], "isi": _SEC},
        }
    )
    assert expand(node).unsupported is not None
