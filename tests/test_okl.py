"""OKL output round-trips through session_recorder.read_log."""

from __future__ import annotations

from pathlib import Path

from contingency_respondent_dsl import from_dict
from experiment_core import ReinforcerEndEvent, ReinforcerStartEvent
from session_recorder import read_log
from test_laws_min import BLOCKING

from respondent_runner.expand import expand
from respondent_runner.okl import write_okl
from respondent_runner.rescorla_wagner import RescorlaWagner, run


def test_trial_cue_matches_cs_set(tmp_path: Path) -> None:
    exp = expand(from_dict(BLOCKING))
    trace = run(exp, RescorlaWagner({}, lambda_by_us={"shock": 1.0}))
    out = tmp_path / "blocking.txt"
    write_okl(trace, out, {"session_name": "blocking"})

    log = read_log(out)
    trial_enters = [
        m for m in log.phase_markers if m.kind == "enter" and m.label.startswith("trial-")
    ]
    assert len(trial_enters) == len(exp.trials) == 70
    for marker, trial in zip(trial_enters, exp.trials, strict=True):
        assert marker.context.get("cue") == "+".join(sorted(trial.cs))

    stage_enters = [m.label for m in log.phase_markers if m.kind == "enter"]
    stage_enters = [s for s in stage_enters if not s.startswith("trial-")]
    assert stage_enters == ["phase1", "phase2", "test"]

    starts = [e for e in log.events if isinstance(e, ReinforcerStartEvent)]
    ends = [e for e in log.events if isinstance(e, ReinforcerEndEvent)]
    assert len(starts) == len(ends) == 60
    timestamps = [m.timestamp for m in log.phase_markers]
    assert timestamps == sorted(timestamps)
