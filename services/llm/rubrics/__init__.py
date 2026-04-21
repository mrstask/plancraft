"""Rubric YAML stubs per role.

Rubrics layer as:
  1. Global defaults in this directory (shipped with the app).
  2. Constitution overrides (added in M1).
  3. Feature overrides (added in M4).

M0 ships only the global layer. Each file has a `version` field and a list
of `rules`. Null-evaluator does not read these files; real evaluators will.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_RUBRICS_DIR = Path(__file__).resolve().parent


def load_rubric(role: str) -> dict[str, Any]:
    """Load the YAML rubric for a role, or return an empty rubric if missing."""
    path = _RUBRICS_DIR / f"{role}.yml"
    if not path.exists():
        return {"version": "missing", "rules": []}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    data.setdefault("version", "unversioned")
    data.setdefault("rules", [])
    return data
