"""Data Model renderer — writes data_model.json and data_model.md."""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.db import DataEntity
    from services.workspace.workspace import ProjectWorkspace


def render_data_model(ws: "ProjectWorkspace", entities: "list[DataEntity]") -> tuple[Path, Path]:
    doc = {
        "entities": [
            {
                "name": e.name,
                "attributes": list(e.attributes or []),
                "relationships": list(e.relationships or []),
            }
            for e in entities
        ]
    }

    json_path = ws.ba_file("data_model.json")
    json_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = ["# Data Model (Conceptual)", ""]
    if not entities:
        lines.append("> *No data entities defined yet.*")
    for entry in doc["entities"]:
        lines += [f"## {entry['name']}", ""]
        if entry["attributes"]:
            lines += ["**Attributes:**", ""]
            for attr in entry["attributes"]:
                lines.append(f"- {attr}")
            lines.append("")
        if entry["relationships"]:
            lines += ["**Relationships:**", ""]
            for rel in entry["relationships"]:
                lines.append(f"- {rel}")
            lines.append("")

    md_path = ws.ba_file("data_model.md")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path
