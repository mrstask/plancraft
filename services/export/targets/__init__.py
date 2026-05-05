"""Export target registry.

Add a new target by importing it here and appending to TARGETS.
"""
from __future__ import annotations

from .arc42_target import Arc42Target
from .ba_target import BaTarget
from .base import BuildResult, ExportTarget
from .impl_target import ImplTarget
from .tasks_target import TasksTarget
from .workspace_target import WorkspaceTarget

TARGETS: list[ExportTarget] = [
    Arc42Target(),
    TasksTarget(),
    BaTarget(),
    WorkspaceTarget(),
    ImplTarget(),
]

_REGISTRY: dict[str, ExportTarget] = {t.name: t for t in TARGETS}


def get_target(name: str) -> ExportTarget:
    target = _REGISTRY.get(name)
    if target is None:
        raise ValueError(f"Unknown export target: {name!r}. Available: {list(_REGISTRY)}")
    return target


__all__ = ["TARGETS", "BuildResult", "ExportTarget", "get_target"]
