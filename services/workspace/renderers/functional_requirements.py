"""Functional Requirements renderer — writes functional_requirements.json and .md."""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.db import FunctionalRequirement
    from services.workspace.workspace import ProjectWorkspace


def render_functional_requirements(
    ws: "ProjectWorkspace",
    frs: "list[FunctionalRequirement]",
) -> tuple[Path, Path]:
    doc = []
    for i, fr in enumerate(frs, start=1):
        story_ids = [link.story_id for link in (fr.story_links or [])]
        doc.append({
            "id": f"FR-{i:03d}",
            "description": fr.description,
            "inputs": list(fr.inputs or []),
            "outputs": list(fr.outputs or []),
            "related_user_stories": story_ids,
        })

    json_path = ws.ba_file("functional_requirements.json")
    json_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = ["# Functional Requirements", ""]
    if not frs:
        lines.append("> *No functional requirements defined yet.*")
    for entry in doc:
        lines += [f"## {entry['id']}", "", entry["description"], ""]
        if entry["inputs"]:
            lines += ["**Inputs:** " + ", ".join(entry["inputs"]), ""]
        if entry["outputs"]:
            lines += ["**Outputs:** " + ", ".join(entry["outputs"]), ""]
        if entry["related_user_stories"]:
            lines += ["**User stories:** " + ", ".join(entry["related_user_stories"]), ""]

    md_path = ws.ba_file("functional_requirements.md")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path
