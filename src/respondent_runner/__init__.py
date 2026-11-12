"""Pavlovian trial expander and compound-CS Rescorla–Wagner executor."""

from __future__ import annotations

from .expand import expand, expand_control
from .okl import write_okl
from .rescorla_wagner import RescorlaWagner, Trace, TrialRecord, run
from .trials import Expansion, Trial

__all__ = [
    "Expansion",
    "RescorlaWagner",
    "Trace",
    "Trial",
    "TrialRecord",
    "expand",
    "expand_control",
    "run",
    "write_okl",
]
