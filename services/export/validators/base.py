"""ExportValidator protocol — one validator per target."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from services.export.targets.base import BuildResult


class ExportValidator(Protocol):
    target_name: str

    def validate(self, result: BuildResult) -> list[str]:
        """Return a list of error strings (empty = valid)."""
        ...
