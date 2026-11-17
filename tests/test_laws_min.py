"""Minimal law checks: blocking, overshadowing, conditioned inhibition.

Inputs are Tier B ASTs written inline in the conformance ``expected_ast``
dict shape and reconstructed with ``contingency_respondent_dsl.from_dict``.
"""

from __future__ import annotations

from typing import Any

from contingency_respondent_dsl import from_dict

from respondent_sim.expand import expand, expand_control
from respondent_sim.rescorla_wagner import RescorlaWagner, run

_SEC = {"value": 10, "unit": "s"}
_DUR = {"value": 15, "unit": "s"}


def _pair(cs: Any, us: str) -> dict[str, Any]:
    return {"type": "Pair.ForwardDelay", "cs": cs, "us": us, "isi": _SEC, "cs_duration": _DUR}


def _compound(*elements: str) -> dict[str, Any]:
    return {"type": "Compound", "elements": list(elements)}


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


def _model(**alpha: float) -> RescorlaWagner:
    return RescorlaWagner(alpha, lambda_by_us={"shock": 1.0})


def test_blocking_x_below_control() -> None:
    node = from_dict(BLOCKING)
    exp = expand(node)
    ctrl = expand_control(node)
    assert exp.unsupported is None
    assert ctrl is not None
    v = run(exp, _model()).v_at_stage_start("test")
    v_ctrl = run(ctrl, _model()).v_at_stage_start("test")
    assert v["x"] < v_ctrl["x"]
    assert v["x"] < 0.05


def test_overshadowing_salient_element_wins() -> None:
    node = from_dict(OVERSHADOWING)
    model = _model(loud_tone=0.5, dim_light=0.2)
    exp = expand(node)
    ctrl = expand_control(node)
    assert ctrl is not None
    v = run(exp, model).v_at_stage_start("test_a")
    v_alone = run(ctrl, model).v_at_stage_start("test_b")
    assert v["loud_tone"] > v["dim_light"]
    assert v["dim_light"] < v_alone["dim_light"]


def test_conditioned_inhibition_negative_and_cancels() -> None:
    node = from_dict(CONDITIONED_INHIBITION)
    v = run(expand(node), _model()).v_at_stage_start("test")
    assert v["i"] < 0
    assert abs(v["a"] + v["i"]) < 1e-3


def test_conditioned_inhibition_single_pair_is_synthesised() -> None:
    node = from_dict({**CONDITIONED_INHIBITION, "training": _pair("a", "shock")})
    exp = expand(node)
    kinds = {(t.cs, t.us) for t in exp.trials if t.stage == "training"}
    assert kinds == {(frozenset({"a"}), "shock"), (frozenset({"a", "i"}), None)}
    v = run(exp, _model()).v_at_stage_start("test")
    assert v["i"] < 0


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
