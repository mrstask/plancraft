"""Disk-mirror renderer for profiles and inherited project metadata."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from config import settings


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str) -> str:
    return _SLUG_RE.sub("-", text.lower()).strip("-") or "profile"


def build_profile_ref(name: str, version: str) -> str:
    return f"{name}@{version}"


def parse_tech_stack_template(raw: str | None) -> list[dict[str, str]]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    rows: list[dict[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "layer": str(item.get("layer", "")).strip(),
                "choice": str(item.get("choice", "")).strip(),
                "rationale": str(item.get("rationale", "")).strip(),
            }
        )
    return rows


def serialize_tech_stack_template(entries: list[dict[str, str]]) -> str:
    normalized = [
        {
            "layer": str(entry.get("layer", "")).strip(),
            "choice": str(entry.get("choice", "")).strip(),
            "rationale": str(entry.get("rationale", "")).strip(),
        }
        for entry in entries
        if any(str(entry.get(key, "")).strip() for key in ("layer", "choice", "rationale"))
    ]
    return json.dumps(normalized, indent=2, ensure_ascii=True)


def parse_conventions_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def serialize_conventions(conventions: dict[str, Any]) -> str:
    return json.dumps(conventions or {}, indent=2, ensure_ascii=True, sort_keys=True)


def profile_dir_path(profile) -> Path:
    return settings.profiles_root / _slugify(profile.name)


def delete_profile_mirror(profile_name: str) -> None:
    path = settings.profiles_root / _slugify(profile_name)
    if path.exists():
        shutil.rmtree(path)


def _yaml_scalar(value: str) -> str:
    return json.dumps(value or "", ensure_ascii=False)


def _yaml_block(text: str, *, indent: int = 2) -> str:
    if not text.strip():
        return '""'
    lines = text.splitlines() or [text]
    padding = " " * indent
    return "|\n" + "\n".join(f"{padding}{line}" for line in lines)


def render_profile_mirror(profile) -> Path:
    root = profile_dir_path(profile)
    root.mkdir(parents=True, exist_ok=True)

    constitution_path = root / "constitution.md"
    constitution_path.write_text(profile.constitution_md or "", encoding="utf-8")

    tech_stack_rows = parse_tech_stack_template(profile.tech_stack_template)
    tech_lines = []
    for row in tech_stack_rows:
        tech_lines.append(f"- layer: {_yaml_scalar(row['layer'])}")
        tech_lines.append(f"  choice: {_yaml_scalar(row['choice'])}")
        tech_lines.append("  rationale: " + _yaml_block(row["rationale"], indent=4))
    (root / "tech-stack.yml").write_text("\n".join(tech_lines).strip() + ("\n" if tech_lines else ""), encoding="utf-8")

    conventions_path = root / "conventions.json"
    conventions_path.write_text(serialize_conventions(parse_conventions_json(profile.conventions_json)), encoding="utf-8")

    profile_yaml = (
        f"name: {_yaml_scalar(profile.name)}\n"
        f"description: {_yaml_scalar(profile.description or '')}\n"
        f"version: {_yaml_scalar(profile.version)}\n"
        f"profile_ref: {_yaml_scalar(build_profile_ref(profile.name, profile.version))}\n"
    )
    (root / "profile.yml").write_text(profile_yaml, encoding="utf-8")
    return root


def render_project_profile_metadata(ws, profile_ref: str | None) -> Path:
    path = ws.profile_file
    path.parent.mkdir(parents=True, exist_ok=True)
    if not profile_ref:
        if path.exists():
            path.unlink()
        return path

    name, _, version = profile_ref.rpartition("@")
    content = (
        f"profile_ref: {_yaml_scalar(profile_ref)}\n"
        f"name: {_yaml_scalar(name or profile_ref)}\n"
        f"version: {_yaml_scalar(version or '')}\n"
        'inheritance: "seeded once; project divergence is expected"\n'
    )
    path.write_text(content, encoding="utf-8")
    return path
