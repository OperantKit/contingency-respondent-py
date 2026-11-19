"""Replay the Tier A respondent corpus of contingency-py against ``expand``.

contingency-py's ``conformance/respondent/`` pins the trial list of every
Tier A respondent expression (stage, CS set, US, context, times). This
package's expander reads only the trial level of the nested Tier A forms it
needs for Tier B procedures, and drops the times. So:

- For the forms it reads (``Pair.*``, ``Extinction``, ``CSOnly``, ``USOnly``,
  ``Compound``) the stage, CS set, US and context of every trial must equal
  the corpus.
- For the other Tier A elements it must refuse (``UnsupportedExpressionError``),
  so that a Tier B procedure nesting one is reported as unsupported instead of
  being expanded in a way the corpus does not pin.

Corpus location: ``$RESPONDENT_TIER_A_CONFORMANCE_ROOT`` if set, else the first
ancestor holding ``contingency-py/conformance/respondent`` or
``apps/core/contingency-py/conformance/respondent``; skipped when none is found.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from respondent_sim.expand import UnsupportedExpressionError, stage, templates

ENV_ROOT = "RESPONDENT_TIER_A_CONFORMANCE_ROOT"
_CANDIDATES = (
    Path("contingency-py") / "conformance" / "respondent",
    Path("apps") / "core" / "contingency-py" / "conformance" / "respondent",
)
READ_BY_EXPANDER = frozenset(
    {
        "Pair.ForwardDelay",
        "Pair.ForwardTrace",
        "Pair.Simultaneous",
        "Pair.Backward",
        "Extinction",
        "CSOnly",
        "USOnly",
        "Compound",
    }
)
REFUSED_BY_EXPANDER = frozenset(
    {"Contingency", "TrulyRandom", "ExplicitlyUnpaired", "Serial", "ITI", "Differential"}
)


def _find_root() -> Path | None:
    explicit = os.environ.get(ENV_ROOT)
    if explicit:
        return Path(explicit)
    here = Path(__file__).resolve()
    for ancestor in here.parents:
        for rel in _CANDIDATES:
            if (ancestor / rel).is_dir() and any((ancestor / rel).glob("*.json")):
                return ancestor / rel
    return None


ROOT = _find_root()
FIXTURES = sorted(ROOT.glob("*.json")) if ROOT is not None else []
pytestmark = pytest.mark.skipif(not FIXTURES, reason="Tier A respondent corpus not found")


def _load(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _projection(trial: dict[str, Any]) -> tuple[str, tuple[str, ...], str | None, str | None]:
    return (trial["stage"], tuple(sorted(trial["cs"])), trial["us"], trial["context"])


def test_corpus_elements_are_partitioned() -> None:
    elements = {_load(p)["element"] for p in FIXTURES}
    assert elements == READ_BY_EXPANDER | REFUSED_BY_EXPANDER


@pytest.mark.parametrize("path", FIXTURES, ids=[p.stem for p in FIXTURES])
def test_expander_matches_corpus(path: Path) -> None:
    case = _load(path)
    spec, expected = case["spec"], case["expected"]
    if case["element"] in REFUSED_BY_EXPANDER:
        with pytest.raises(UnsupportedExpressionError):
            templates(spec)
        return
    assert "trials" in expected, case["name"]
    n = int(spec.get("trials", case["options"]["trials"]))
    got = stage("main", templates(spec), n)
    assert [(t.stage, tuple(sorted(t.cs)), t.us, t.context) for t in got] == [
        _projection(t) for t in expected["trials"]
    ]
