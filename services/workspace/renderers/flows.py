"""User Flows renderer — writes user_flows.json and user_flows.md."""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.db import UserFlow
    from services.workspace.workspace import ProjectWorkspace


def render_user_flows(ws: "ProjectWorkspace", flows: "list[UserFlow]") -> tuple[Path, Path]:
    doc = []
    for flow in flows:
        sorted_steps = sorted(flow.steps or [], key=lambda s: s.order_index)
        step_strs = []
        for step in sorted_steps:
            actor_prefix = f"{step.actor}: " if step.actor else ""
            step_strs.append(f"{actor_prefix}{step.description}")
        doc.append({
            "id": flow.id,
            "name": flow.name,
            "description": flow.description or "",
            "steps": step_strs,
        })

    json_path = ws.ba_file("user_flows.json")
    json_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = ["# User Flows", ""]
    if not flows:
        lines.append("> *No user flows defined yet.*")
    for entry in doc:
        lines += [f"## {entry['name']}", ""]
        if entry["description"]:
            lines += [entry["description"], ""]
        if entry["steps"]:
            for i, step in enumerate(entry["steps"], start=1):
                lines.append(f"{i}. {step}")
        lines.append("")

    md_path = ws.ba_file("user_flows.md")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path
