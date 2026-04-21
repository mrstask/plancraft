"""ExportTarget protocol and BuildResult — the pluggable exporter interface."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class BuildResult:
    out_dir: Path
    files_written: list[Path] = field(default_factory=list)
    schema_valid: bool = True
    schema_errors: list[str] = field(default_factory=list)

    def add_file(self, path: Path) -> None:
        self.files_written.append(path)


class ExportTarget(Protocol):
    name: str          # machine key, e.g. "arc42"
    display_name: str  # shown in UI
    description: str   # one-line description shown in UI

    async def build(
        self,
        project_id: str,
        out_dir: Path,
        db: "AsyncSession",
    ) -> BuildResult: ...
