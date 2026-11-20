"""OKL output round-trips through session_recorder.read_log."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from contingency_respondent_dsl import from_dict
from session_recorder import read_log
from test_laws_min import BLOCKING

from contingency_respondent.expand import expand
from contingency_respondent.okl import write_okl
from contingency_respondent.rescorla_wagner import RescorlaWagner, run


def _blocking_log(tmp_path: Path):  # type: ignore[no-untyped-def]
    exp = expand(from_dict(BLOCKING))
    trace = run(exp, RescorlaWagner({}, lambda_by_us={"shock": 1.0}))
    out = tmp_path / "blocking.txt"
    write_okl(trace, out, {"session_name": "blocking"})
    return exp, read_log(out)


def test_cs_and_us_are_stimulus_events(tmp_path: Path) -> None:
    exp, log = _blocking_log(tmp_path)
    trial_enters = [
        m for m in log.phase_markers if m.kind == "enter" and m.label.startswith("trial-")
    ]
    assert len(trial_enters) == len(exp.trials) == 70
    for marker in trial_enters:
        assert "cue" not in marker.context

    on = [r for r in log.raw_records if r.type == "stimulus_on"]
    off = [r for r in log.raw_records if r.type == "stimulus_off"]
    n_cs = sum(len(t.cs) for t in exp.trials)
    n_us = sum(1 for t in exp.trials if t.us is not None)
    assert n_us == 60
    assert len(on) == len(off) == n_cs + n_us
    assert sum(1 for r in on if r.args["stimulus"] == "shock") == 60
    for r in on + off:
        assert set(r.args) == {"stimulus"}

    # CS onset at the trial start, in the trial's CS set.
    for marker, trial in zip(trial_enters, exp.trials, strict=True):
        at_start = {
            r.args["stimulus"] for r in on if r.timestamp == marker.timestamp
        }
        assert at_start == set(trial.cs)

    assert not any(r.type.startswith("reinforcer") for r in log.raw_records)
    assert log.events == []

    stage_enters = [m.label for m in log.phase_markers if m.kind == "enter"]
    stage_enters = [s for s in stage_enters if not s.startswith("trial-")]
    assert stage_enters == ["phase1", "phase2", "test"]

    timestamps = [r.timestamp for r in log.raw_records]
    assert timestamps == sorted(timestamps)


def test_writer_does_not_load_experiment_core() -> None:
    code = (
        "import sys, contingency_respondent.okl; "
        "sys.exit(1 if 'experiment_core' in sys.modules else 0)"
    )
    assert subprocess.run([sys.executable, "-c", code], check=False).returncode == 0
