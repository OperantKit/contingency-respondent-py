"""Tier B procedures registered in a contingency-py ``RespondentRegistry``.

The registry sends Tier A to contingency-rs and each Tier B type to its owner;
:data:`contingency_respondent.TIER_B` owns the procedures of
contingency-respondent-dsl. These tests pin that the Tier B trial list through
the registry is the same as :func:`contingency_respondent.expand`, that nested
Tier A goes back through the registry, and how options and errors are read.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from contingency.errors import (
    RespondentSpecError,
    RespondentUnresolvedError,
    UnknownRespondentElementError,
)
from contingency.respondent import TIER_A_TYPES, TRIAL_KEYS, RespondentRegistry
from contingency_respondent_dsl import from_dict

from contingency_respondent import TIER_B, expand, expand_control, registry, to_trial_dicts

ENV_ROOT = "RESPONDENT_CONFORMANCE_ROOT"
_CANDIDATES = (
    Path("contingency-respondent-dsl") / "conformance" / "tier-b",
    Path("apps") / "core" / "contingency-respondent-dsl" / "conformance" / "tier-b",
)
_SEC = {"value": 10, "unit": "s"}
_DUR = {"value": 15, "unit": "s"}


def _pair(cs: Any, us: str) -> dict[str, Any]:
    return {"type": "PairForwardDelay", "cs": cs, "us": us, "isi": _SEC, "cs_duration": _DUR}


BLOCKING: dict[str, Any] = {
    "type": "Blocking",
    "phase1": _pair("a", "shock"),
    "phase2": _pair({"type": "Compound", "cs_list": ["a", "x"]}, "shock"),
    "test": {"type": "Extinction", "cs": "x"},
    "phase1_trials": 3,
    "phase2_trials": 2,
    "test_trials": 1,
}


def _find_root() -> Path | None:
    explicit = os.environ.get(ENV_ROOT)
    if explicit:
        return Path(explicit)
    for ancestor in Path(__file__).resolve().parents:
        for rel in _CANDIDATES:
            if (ancestor / rel).is_dir():
                return ancestor / rel
    return None


def _tier_b_cases() -> list[tuple[str, dict[str, Any]]]:
    root = _find_root()
    if root is None:
        return []
    out = []
    for path in sorted(root.glob("*.json")):
        for i, case in enumerate(json.loads(path.read_text(encoding="utf-8"))):
            out.append((f"{path.stem}-{i}", case["expected_ast"]))
    return out


CASES = _tier_b_cases()


def test_types_are_the_tier_b_procedures_and_not_tier_a() -> None:
    assert not TIER_B.types & TIER_A_TYPES
    assert "Blocking" in TIER_B.types
    registry()  # builds without a clash


def test_fixture_types_are_all_registered() -> None:
    if not CASES:
        pytest.skip("Tier B conformance fixtures not found")
    assert {ast["type"] for _, ast in CASES} <= TIER_B.types


def test_blocking_trial_list() -> None:
    trials = registry().expand(BLOCKING, {"trials": 20})
    assert [(t["stage"], t["cs"], t["us"]) for t in trials] == [
        ("phase1", ["a"], "shock"),
        ("phase1", ["a"], "shock"),
        ("phase1", ["a"], "shock"),
        ("phase2", ["a", "x"], "shock"),
        ("phase2", ["a", "x"], "shock"),
        ("test", ["x"], None),
    ]
    assert all(set(t) == TRIAL_KEYS for t in trials)
    # Times come from the Tier A expansion of the nested Pair.
    assert trials[0]["time"] == {
        "cs_on": 0.0,
        "cs_off": 15.0,
        "us_on": 10.0,
        "us_off": None,
        "gap": None,
    }


def test_control_option() -> None:
    trials = registry().expand(BLOCKING, {"trials": 20, "control": True})
    assert [t["stage"] for t in trials] == ["phase2", "phase2", "test"]


def test_nested_non_tier_a_type_goes_to_its_registered_owner() -> None:
    seen: list[str] = []

    class Spy:
        name = "spy"
        types = frozenset({"SpyPair"})

        def expand(self, spec: Any, options: Any, expand_nested: Any) -> list[dict[str, Any]]:
            seen.append(spec["type"])
            return [
                {
                    "stage": "main",
                    "cs": ["spy"],
                    "us": "shock",
                    "context": None,
                    "order": None,
                    "time": None,
                    "iti_s": None,
                }
            ]

    spec = {**BLOCKING, "phase1": {"type": "SpyPair"}}
    trials = RespondentRegistry.build(TIER_B, Spy()).expand(spec, {"trials": 20})
    assert seen == ["SpyPair"]
    assert trials[0]["cs"] == ["spy"]


def test_unregistered_nested_type_is_refused() -> None:
    spec = {**BLOCKING, "phase1": {"type": "SpyPair"}}
    with pytest.raises(RespondentSpecError, match="SpyPair"):
        registry().expand(spec, {"trials": 20})


def test_trials_option_is_required() -> None:
    with pytest.raises(RespondentUnresolvedError) as info:
        registry().expand(BLOCKING)
    assert info.value.missing == "trials"


@pytest.mark.parametrize("bad", [0, -1, 2.0, True, "3"])
def test_trials_option_must_be_a_positive_int(bad: Any) -> None:
    with pytest.raises(RespondentSpecError):
        registry().expand(BLOCKING, {"trials": bad})


def test_control_option_must_be_bool() -> None:
    with pytest.raises(RespondentSpecError):
        registry().expand(BLOCKING, {"trials": 20, "control": "yes"})


def test_control_of_a_procedure_without_one_is_refused() -> None:
    spec = {
        "type": "ConditionedTasteAversion",
        "taste_cs": "saccharin",
        "visceral_us": "licl",
        "cs_duration": _DUR,
        "delay_to_us": _SEC,
    }
    with pytest.raises(RespondentSpecError, match="control"):
        registry().expand(spec, {"trials": 3, "control": True})


def test_malformed_tier_b_spec_is_a_spec_error() -> None:
    with pytest.raises(RespondentSpecError):
        registry().expand({"type": "Blocking"}, {"trials": 3})


def test_unknown_type_is_not_claimed() -> None:
    with pytest.raises(UnknownRespondentElementError):
        registry().expand({"type": "NotAProcedure"}, {"trials": 3})


@pytest.mark.parametrize("case_id,ast", CASES, ids=[c for c, _ in CASES])
def test_registry_matches_expand(case_id: str, ast: dict[str, Any]) -> None:
    node = from_dict(ast)
    local = expand(node, default_trials=7)
    if local.unsupported is not None:
        with pytest.raises(RespondentSpecError):
            registry().expand(ast, {"trials": 7})
        return
    assert registry().expand(ast, {"trials": 7}) == to_trial_dicts(local)
    control = expand_control(node, default_trials=7)
    if control is not None:
        assert registry().expand(ast, {"trials": 7, "control": True}) == to_trial_dicts(control)


_NO_US_TIME = {"cs_on": 0.0, "cs_off": 15.0, "us_on": None, "us_off": None, "gap": None}


def test_us_nothing_has_no_us_time() -> None:
    spec = {**BLOCKING, "phase2": _pair({"type": "Compound", "cs_list": ["a", "x"]}, "nothing")}
    phase2 = [t for t in registry().expand(spec, {"trials": 20}) if t["stage"] == "phase2"]
    assert phase2 and all(t["us"] is None and t["time"] == _NO_US_TIME for t in phase2)


def test_unreinforced_pree_trial_has_no_gap_to_the_us() -> None:
    spec = {
        "type": "PavlovianPREE",
        "acquisition": {
            "type": "PairForwardTrace",
            "cs": "tone",
            "us": "shock",
            "trace_interval": _SEC,
            "cs_duration": _DUR,
        },
        "extinction": {"type": "Extinction", "cs": "tone"},
        "test": {"type": "Extinction", "cs": "tone"},
        "reinforcement_probability": 0.5,
    }
    acq = [t for t in registry().expand(spec, {"trials": 2}) if t["stage"] == "acquisition"]
    assert [t["us"] for t in acq] == [None, "shock"]
    assert acq[0]["time"]["gap"] is None and acq[0]["time"]["us_on"] is None
    assert acq[1]["time"]["gap"] is not None


def test_us_nothing_in_a_procedure_built_trial_is_no_us() -> None:
    spec = {
        "type": "OccasionSetting",
        "feature": "light",
        "target": "tone",
        "us": "nothing",
        "mode": "FeaturePositive",
    }
    assert all(t["us"] is None for t in registry().expand(spec, {"trials": 2}))


@pytest.mark.parametrize("isi", [{"value": 0, "unit": "s"}, {"value": 1, "unit": "sec"}, 5])
def test_bad_serial_isi_is_a_spec_error(isi: Any) -> None:
    spec = {
        "type": "ConditionedInhibition",
        "training": {
            "type": "Serial",
            "elements": [_pair("a", "shock"), {"type": "Extinction", "cs": "b"}],
            "isi": isi,
        },
        "test": {"type": "Extinction", "cs": "b"},
    }
    with pytest.raises(RespondentSpecError):
        registry().expand(spec, {"trials": 2})


def test_unknown_option_is_refused() -> None:
    with pytest.raises(RespondentSpecError, match="controll"):
        registry().expand(BLOCKING, {"trials": 2, "controll": True})


def test_seed_and_labels_are_passed_to_nested_expressions() -> None:
    seen: list[Any] = []

    class Spy:
        name = "spy"
        types = frozenset({"SpyPair"})

        def expand(self, spec: Any, options: Any, expand_nested: Any) -> list[dict[str, Any]]:
            seen.append(dict(options))
            return [
                {
                    "stage": "main",
                    "cs": ["spy"],
                    "us": None,
                    "context": None,
                    "order": None,
                    "time": None,
                    "iti_s": None,
                }
            ]

    spec = {**BLOCKING, "phase1": {"type": "SpyPair"}}
    labels = {"cs": "tone", "us": "shock"}
    RespondentRegistry.build(TIER_B, Spy()).expand(
        spec, {"trials": 2, "seed": 7, "labels": labels, "control": False}
    )
    assert seen == [{"seed": 7, "labels": labels, "trials": 1}]
