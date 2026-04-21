"""arc42 export target — single Markdown file."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from .base import BuildResult


class Arc42Target:
    name = "arc42"
    display_name = "arc42 Architecture Doc"
    description = "All 12 arc42 sections as a single Markdown file."

    async def build(self, project_id: str, out_dir: Path, db: AsyncSession) -> BuildResult:
        from services.export_service import build_arc42
        content = await build_arc42(project_id, db)
        out_path = out_dir / "arc42.md"
        out_path.write_text(content, encoding="utf-8")
        result = BuildResult(out_dir=out_dir)
        result.add_file(out_path)
        return result
