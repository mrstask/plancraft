"""Facade that exposes read/write/context helpers behind one service object."""
from __future__ import annotations

from .commands import ArtifactCommands
from .contexts import PromptContextBuilder
from .queries import ArtifactQueries
from .snapshots import SnapshotBuilder


class KnowledgeService:
    def __init__(self, db, feature_id: str | None = None):
        self.db = db
        self.feature_id = feature_id
        self.commands = ArtifactCommands(db, feature_id=feature_id)
        self.queries = ArtifactQueries(db, feature_id=feature_id)
        self.snapshot_builder = SnapshotBuilder(db, feature_id=feature_id)
        self.context_builder = PromptContextBuilder(db, feature_id=feature_id)
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
