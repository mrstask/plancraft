"""C4 renderer — emits a Structurizr DSL workspace.dsl from components and relationships.

Generates three C4 views:
  1. System Context  — the software system + external actors
  2. Container       — top-level components inside the system
  3. Component       — internal components (same as container for now; expand when layers are added)

The DSL is consumable by the Structurizr CLI to produce SVG/PNG diagrams.
If Structurizr CLI is absent the file is still useful as documentation-as-code.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.db import Component
    from services.workspace.workspace import ProjectWorkspace

_EXTERNAL_TYPES = {"gateway", "api", "cli", "external"}


def _id(name: str) -> str:
    """Turn a component name into a valid DSL identifier."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", name).strip("_") or "unknown"


def render_c4(ws: "ProjectWorkspace", project_name: str, components: list["Component"]) -> Path:
    internal = [c for c in components if (c.component_type or "").lower() not in _EXTERNAL_TYPES]
    external = [c for c in components if (c.component_type or "").lower() in _EXTERNAL_TYPES]

    # Model block
    model_lines: list[str] = [
        f'    softwareSystem = softwareSystem "{project_name}" {{',
    ]
    for comp in internal:
        cid = _id(comp.name)
        ctype = comp.component_type or "service"
        model_lines.append(
            f'        {cid} = container "{comp.name}" "{comp.responsibility}" "{ctype}"'
        )
    model_lines.append("    }")
    model_lines.append("")

    for comp in external:
        cid = _id(comp.name)
        ctype = comp.component_type or "external"
        model_lines.append(
            f'    {cid} = softwareSystem "{comp.name}" "{comp.responsibility}" tags "{ctype}"'
        )

    # Relationships — internal components that depend on each other
    # (We don't have full dependency data here; placeholders added as comments)
    model_lines.append("")
    model_lines.append("    # Add relationships below as the architecture is refined:")
    for comp in internal:
        model_lines.append(f"    # {_id(comp.name)} -> ??? \"depends on\"")

    # Views block
    views_lines = [
        "    views {",
        f'        systemContext softwareSystem "SystemContext" {{',
        "            include *",
        "            autolayout lr",
        "        }",
        f'        container softwareSystem "Containers" {{',
        "            include *",
        "            autolayout lr",
        "        }",
        '        theme default',
        "    }",
    ]

    dsl = "\n".join([
        "workspace {",
        "",
        "    model {",
        *model_lines,
        "    }",
        "",
        *views_lines,
        "}",
        "",
    ])

    path = ws.c4_workspace
    path.write_text(dsl, encoding="utf-8")
    return path
