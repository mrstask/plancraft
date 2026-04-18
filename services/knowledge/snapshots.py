"""Snapshot builder for LLM and UI state."""
from __future__ import annotations

from sqlalchemy import func, select

from models.db import ArchitectureDecision, Component, Epic, Task, TestSpec, UserStory
from models.domain import ComponentSnapshot, DecisionSnapshot, KnowledgeSnapshot, StorySnapshot
from .common import KnowledgeBase


class SnapshotBuilder(KnowledgeBase):
    async def get_snapshot(self, project_id: str) -> KnowledgeSnapshot:
        project = await self.get_project(project_id)

        story_result = await self.db.execute(
            select(UserStory)
            .where(UserStory.project_id == project_id)
            .order_by(UserStory.created_at.desc())
            .limit(5)
        )
        stories = list(reversed(story_result.scalars().all()))

        comp_result = await self.db.execute(
            select(Component)
            .where(Component.project_id == project_id)
            .order_by(Component.created_at.desc())
            .limit(5)
        )
        components = list(reversed(comp_result.scalars().all()))

        dec_result = await self.db.execute(
            select(ArchitectureDecision)
            .where(ArchitectureDecision.project_id == project_id)
            .order_by(ArchitectureDecision.created_at.desc())
            .limit(5)
        )
        decisions = list(reversed(dec_result.scalars().all()))

        counts = await self._get_counts(project_id)

        return KnowledgeSnapshot(
            project_name=project.name,
            problem_statement=project.description,
            mvp_story_count=len(project.mvp_story_ids or []),
            mvp_rationale=project.mvp_rationale,
            **counts,
            recent_stories=[
                StorySnapshot(id=s.id, as_a=s.as_a, i_want=s.i_want, priority=s.priority)
                for s in stories
            ],
            recent_components=[
                ComponentSnapshot(id=c.id, name=c.name, responsibility=c.responsibility)
                for c in components
            ],
            recent_decisions=[
                DecisionSnapshot(id=d.id, title=d.title, decision=d.decision)
                for d in decisions
            ],
        )

    async def _get_counts(self, project_id: str) -> dict:
        async def count(model):
            r = await self.db.execute(select(func.count()).where(model.project_id == project_id))
            return r.scalar()

        return {
            "story_count": await count(UserStory),
            "epic_count": await count(Epic),
            "component_count": await count(Component),
            "decision_count": await count(ArchitectureDecision),
            "test_spec_count": await count(TestSpec),
            "task_count": await count(Task),
        }
