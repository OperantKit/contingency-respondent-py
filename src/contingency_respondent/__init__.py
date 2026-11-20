"""Tier B respondent procedures for contingency-py, and a compound-CS Rescorla–Wagner executor."""

from __future__ import annotations

from .expand import expand, expand_control
from .okl import write_okl
from .rescorla_wagner import RescorlaWagner, Trace, TrialRecord, run
from .tier_b import TIER_B, TierBExpansion, registry, to_trial_dicts
from .trials import Expansion, Trial

__all__ = [
    "TIER_B",
    "Expansion",
    "RescorlaWagner",
    "TierBExpansion",
    "Trace",
    "Trial",
    "TrialRecord",
    "expand",
    "expand_control",
    "registry",
    "run",
    "to_trial_dicts",
    "write_okl",
]
