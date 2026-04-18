"""Facade that exposes read/write/context helpers behind one service object."""
from __future__ import annotations

from .commands import ArtifactCommands
from .contexts import PromptContextBuilder
from .queries import ArtifactQueries
from .snapshots import SnapshotBuilder


class KnowledgeService:
    def __init__(self, db):
        self.db = db
        self.commands = ArtifactCommands(db)
        self.queries = ArtifactQueries(db)
        self.snapshot_builder = SnapshotBuilder(db)
        self.context_builder = PromptContextBuilder(db)
        self._parts = (
            self.commands,
            self.queries,
            self.snapshot_builder,
            self.context_builder,
        )

    async def _get_project(self, project_id: str):
        return await self.queries.get_project(project_id)

    def __getattr__(self, name: str):
        for part in self._parts:
            if hasattr(part, name):
                return getattr(part, name)
        raise AttributeError(name)
