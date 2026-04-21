"""Business Rules renderer — writes business_rules.json and business_rules.md."""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.db import BusinessRule
    from services.workspace.workspace import ProjectWorkspace


def render_business_rules(ws: "ProjectWorkspace", rules: "list[BusinessRule]") -> tuple[Path, Path]:
    doc = [
        {
            "id": r.id,
            "rule": r.rule,
            "applies_to": list(r.applies_to or []),
        }
        for r in rules
    ]

    json_path = ws.ba_file("business_rules.json")
    json_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = ["# Business Rules", ""]
    if not rules:
        lines.append("> *No business rules defined yet.*")
    for entry in doc:
        applies = f" *(applies to: {', '.join(entry['applies_to'])})*" if entry["applies_to"] else ""
        lines.append(f"- {entry['rule']}{applies}")

    md_path = ws.ba_file("business_rules.md")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path
