"""Personas renderer — writes personas.json and personas.md."""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.db import Persona
    from services.workspace.workspace import ProjectWorkspace


def render_personas(ws: "ProjectWorkspace", personas: "list[Persona]") -> tuple[Path, Path]:
    doc = [
        {
            "name": p.name,
            "role": p.role,
            "goals": list(p.goals or []),
            "pain_points": list(p.pain_points or []),
        }
        for p in personas
    ]

    json_path = ws.ba_file("personas.json")
    json_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = ["# Personas", ""]
    if not personas:
        lines.append("> *No personas defined yet.*")
    for p in personas:
        lines += [f"## {p.name}", "", f"**Role:** {p.role}", ""]
        if p.goals:
            lines += ["**Goals:**", ""]
            for g in p.goals:
                lines.append(f"- {g}")
            lines.append("")
        if p.pain_points:
            lines += ["**Pain Points:**", ""]
            for pp in p.pain_points:
                lines.append(f"- {pp}")
            lines.append("")

    md_path = ws.ba_file("personas.md")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path
