"""arc42 validator — checks all 12 sections are present."""
from __future__ import annotations

import re

from services.export.targets.base import BuildResult

_SECTION_RE = re.compile(r"^## (\d+)\.", re.MULTILINE)
EXPECTED_SECTIONS = set(range(1, 13))  # 1..12


class Arc42Validator:
    target_name = "arc42"

    def validate(self, result: BuildResult) -> list[str]:
        arc42_files = [f for f in result.files_written if f.name == "arc42.md"]
        if not arc42_files:
            return ["arc42.md not found in build output."]

        content = arc42_files[0].read_text(encoding="utf-8")
        found = {int(m.group(1)) for m in _SECTION_RE.finditer(content)}
        missing = EXPECTED_SECTIONS - found

        if missing:
            sorted_missing = sorted(missing)
            return [f"Missing arc42 section(s): {sorted_missing}"]
        return []
