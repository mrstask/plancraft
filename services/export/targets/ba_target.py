"""BA bundle export target — full BA artifact set as JSON."""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from .base import BuildResult


class BaTarget:
    name = "ba"
    display_name = "BA Bundle (JSON)"
    description = "All Business Analyst artifacts: vision/scope, personas, flows, stories, FRs, data model, business rules."

    async def build(self, project_id: str, out_dir: Path, db: AsyncSession) -> BuildResult:
        from services.export_service import build_ba_bundle
        payload = await build_ba_bundle(project_id, db)
        out_path = out_dir / "ba_bundle.json"
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        result = BuildResult(out_dir=out_dir)
        result.add_file(out_path)
        return result
