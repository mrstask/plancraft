"""Vision & Scope renderer — writes vision_scope.json and vision_scope.md."""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.db import Project
    from services.workspace.workspace import ProjectWorkspace


def render_vision_scope(ws: "ProjectWorkspace", project: "Project") -> tuple[Path, Path]:
    doc = {
        "problem_statement": project.description or "",
        "target_users": list(project.target_users or []),
        "business_goals": list(project.business_goals or []),
        "success_metrics": list(project.success_metrics or []),
        "in_scope": list(project.in_scope or []),
        "out_of_scope": list(project.out_of_scope or []),
    }

    json_path = ws.ba_file("vision_scope.json")
    json_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# Vision & Scope",
        "",
        "## Problem Statement",
        "",
        project.description or "> *Not yet defined.*",
        "",
    ]
    if doc["target_users"]:
        lines += ["## Target Users", ""]
        for u in doc["target_users"]:
            lines.append(f"- {u}")
        lines.append("")
    if doc["business_goals"]:
        lines += ["## Business Goals", ""]
        for g in doc["business_goals"]:
            lines.append(f"- {g}")
        lines.append("")
    if doc["success_metrics"]:
        lines += ["## Success Metrics", ""]
        for m in doc["success_metrics"]:
            lines.append(f"- {m}")
        lines.append("")
    if doc["in_scope"]:
        lines += ["## In Scope", ""]
        for item in doc["in_scope"]:
            lines.append(f"- {item}")
        lines.append("")
    if doc["out_of_scope"]:
        lines += ["## Out of Scope", ""]
        for item in doc["out_of_scope"]:
            lines.append(f"- {item}")

    md_path = ws.ba_file("vision_scope.md")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path
