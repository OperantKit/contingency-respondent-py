"""Single-CS agreement with session-analyzer's simulate_rescorla_wagner."""

from __future__ import annotations

import pytest

from respondent_runner.rescorla_wagner import RescorlaWagner, run
from respondent_runner.trials import Expansion, Trial

ALPHA = 0.3
BETA = 0.5
LAMBDA = 1.0


def _single_cs(us_present: list[bool]) -> Expansion:
    return Expansion(
        trials=tuple(
            Trial(stage="acquisition", cs=frozenset({"tone"}), us="shock" if p else None)
            for p in us_present
        )
    )


def _runner_trace(us_present: list[bool]) -> list[float]:
    model = RescorlaWagner({"tone": ALPHA}, beta=BETA, lambda_by_us={"shock": LAMBDA})
    return [r.v_after["tone"] for r in run(_single_cs(us_present), model).records]


def test_matches_closed_form_acquisition() -> None:
    got = _runner_trace([True] * 20)
    ab = ALPHA * BETA
    want = [LAMBDA * (1 - (1 - ab) ** n) for n in range(1, 21)]
    assert got == pytest.approx(want, abs=1e-12)


def test_matches_session_analyzer() -> None:
    analytics = pytest.importorskip("session_analyzer.analytics")
    us = [True] * 12 + [False] * 8
    want = analytics.simulate_rescorla_wagner(us, alpha_beta=ALPHA * BETA, lambda_=LAMBDA)
    assert _runner_trace(us) == pytest.approx(want, abs=1e-12)


def test_compound_uses_summed_error() -> None:
    exp = Expansion(trials=(Trial(stage="s", cs=frozenset({"a", "b"}), us="shock"),))
    model = RescorlaWagner({}, alpha_default=0.5, lambda_by_us={"shock": 1.0})
    after = run(exp, model).records[0].v_after
    assert after == {"a": 0.5, "b": 0.5}
    exp2 = Expansion(trials=exp.trials * 2)
    after2 = run(exp2, model).records[1].v_after
    # sum after trial 1 is 1.0, so the error on trial 2 is 0.
    assert after2 == pytest.approx({"a": 0.5, "b": 0.5})


def test_unknown_us_label_has_zero_lambda() -> None:
    exp = Expansion(trials=(Trial(stage="s", cs=frozenset({"light"}), us="tone"),))
    model = RescorlaWagner({}, lambda_by_us={"shock": 1.0})
    assert run(exp, model).records[0].v_after["light"] == 0.0


def test_context_as_element() -> None:
    exp = Expansion(
        trials=(Trial(stage="s", cs=frozenset(), us="shock", context="box"),),
        context_as_element=True,
    )
    model = RescorlaWagner({}, alpha_default=0.4, lambda_by_us={"shock": 1.0})
    assert run(exp, model).records[0].v_after["box"] == pytest.approx(0.4)


def test_two_us_labels_keep_separate_systems() -> None:
    tone = frozenset({"tone"})
    exp = Expansion(
        trials=tuple(Trial(stage="phase1", cs=tone, us="shock") for _ in range(30))
        + tuple(Trial(stage="phase2", cs=tone, us="food") for _ in range(30))
    )
    trace = run(exp, RescorlaWagner({}, lambda_by_us={"shock": 1.0, "food": 1.0}))
    before = trace.v_at_stage_start("phase2", us="shock")["tone"]
    after_shock = trace.final(us="shock")["tone"]
    after_food = trace.final(us="food")["tone"]
    assert after_shock < before
    assert after_food > 0.9
