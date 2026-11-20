"""Replay the Tier A respondent corpus of contingency-py against ``expand``.

contingency-py's ``conformance/respondent/`` pins the trial list of every
Tier A respondent expression (stage, CS set, US, context, order, times). This
package does not expand Tier A itself: it reads one trial template from
``contingency.respondent`` for each nested form and repeats it. So:

- For the forms read this way (``Pair.*``, ``Extinction``, ``CSOnly``,
  ``USOnly``, ``Compound``) every trial, all 7 keys, must equal the corpus,
  and the template must have come from contingency-py (a spy wraps it).
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
from contingency import respondent as tier_a

from contingency_respondent.expand import (
    TEMPLATE_TYPES,
    UnsupportedExpressionError,
    nested_expansion,
    stage,
    templates,
)
from contingency_respondent.tier_b import to_trial_dicts
from contingency_respondent.trials import Expansion

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


def test_corpus_elements_are_partitioned() -> None:
    elements = {_load(p)["element"] for p in FIXTURES}
    assert elements == READ_BY_EXPANDER | REFUSED_BY_EXPANDER
    assert {_load(p)["spec"]["type"] for p in FIXTURES} == tier_a.TIER_A_TYPES
    read = {_load(p)["spec"]["type"] for p in FIXTURES if _load(p)["element"] in READ_BY_EXPANDER}
    assert read == TEMPLATE_TYPES


@pytest.mark.parametrize("path", FIXTURES, ids=[p.stem for p in FIXTURES])
def test_expander_matches_corpus(path: Path) -> None:
    case = _load(path)
    spec, expected = case["spec"], case["expected"]
    calls: list[str] = []

    def spy(s: Any, o: Any) -> list[dict[str, Any]]:
        calls.append(s["type"])
        return tier_a.expand(s, o)

    with nested_expansion(spy, {k: v for k, v in case["options"].items() if k != "trials"}):
        if case["element"] in REFUSED_BY_EXPANDER:
            with pytest.raises(UnsupportedExpressionError):
                templates(spec)
            assert calls == []
            return
        tmpl = templates(spec)
    assert calls == [spec["type"]]
    assert "trials" in expected, case["name"]
    n = int(spec.get("trials", case["options"]["trials"]))
    assert to_trial_dicts(Expansion(stage("main", tmpl, n))) == expected["trials"]


def test_templates_are_what_the_nested_expander_returns() -> None:
    """A marked trial from the nested expander is the template (nothing is recomputed here)."""
    marked = {
        "stage": "main",
        "cs": ["__marked__"],
        "us": "__marked_us__",
        "context": None,
        "order": None,
        "time": {"cs_on": 1.5, "cs_off": None, "us_on": None, "us_off": None, "gap": None},
        "iti_s": 2.5,
    }
    with nested_expansion(lambda s, o: [marked]):
        (tmpl,) = templates({"type": "Extinction", "cs": "tone"})
    assert to_trial_dicts(Expansion(stage("x", (tmpl,), 1))) == [{**marked, "stage": "x"}]
