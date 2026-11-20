"""Same-experiment fixtures: the respondent program must yield the expected stimulus sequence.

The fixtures live in the contingency-dsl repository under
``conformance/equivalence/``. Each one holds the same arrangement written in
the respondent and the operant vocabularies, input response sequences, and the
expected stimulus sequence. This test runs only the ``respondent`` program; the
operant runner checks the ``operant`` program against the same expected
sequence. When both match, the two programs are the same experiment.

Set ``CONTINGENCY_DSL_CONFORMANCE`` to the ``conformance`` directory of a
contingency-dsl checkout; by default the sibling checkout is used.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from contingency_respondent.timeline import StimulusEvent, stimulus_timeline

_DEFAULT = Path(__file__).resolve().parents[3] / "core" / "contingency-dsl" / "conformance"
CONFORMANCE = Path(os.environ.get("CONTINGENCY_DSL_CONFORMANCE", _DEFAULT))
EQUIVALENCE = CONFORMANCE / "equivalence"


def _cases() -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    if not EQUIVALENCE.is_dir():
        return []
    out = []
    for path in sorted(EQUIVALENCE.glob("*.json")):
        for case in json.loads(path.read_text(encoding="utf-8")):
            for inp in case["inputs"]:
                out.append((path.name, case, inp))
    return out


CASES = _cases()


def test_fixtures_found() -> None:
    if not EQUIVALENCE.is_dir():
        pytest.skip(f"contingency-dsl conformance not found: {EQUIVALENCE}")
    names = {case["equivalence"] for _, case, _ in CASES}
    assert {"autoshaping", "superstition-ft"} <= names


@pytest.mark.parametrize(
    ("filename", "case", "inp"),
    CASES,
    ids=[f"{fn}::{inp['name']}" for fn, _, inp in CASES],
)
def test_respondent_program_matches_expected(
    filename: str, case: dict[str, Any], inp: dict[str, Any]
) -> None:
    del filename
    expected = tuple(StimulusEvent(float(t), str(s), str(k)) for t, s, k in case["expected"])
    got = stimulus_timeline(
        case["programs"]["respondent"]["ast"],
        presentation_s=case["presentation_s"],
        end_offsets=case["end"]["stimulus_offsets"],
        responses=[(float(t), str(r)) for t, r in inp["responses"]],
    )
    assert got == expected
