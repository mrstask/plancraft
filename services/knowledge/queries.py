"""Read-side queries for knowledge artifacts."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from models.db import (
    ArchitectureDecision,
    Component,
    Constraint,
    Epic,
    Task,
    TestSpec,
    UserStory,
)
from .common import KnowledgeBase


class ArtifactQueries(KnowledgeBase):
    async def get_all_epics(self, project_id: str):
        r = await self.db.execute(
            select(Epic).where(Epic.project_id == project_id).order_by(Epic.created_at)
        )
        return r.scalars().all()

    async def get_all_stories(self, project_id: str):
        r = await self.db.execute(
            select(UserStory)
            .options(selectinload(UserStory.acceptance_criteria), selectinload(UserStory.epic))
            .where(UserStory.project_id == project_id)
            .order_by(UserStory.created_at)
        )
        return r.scalars().all()

    async def get_all_components(self, project_id: str):
        r = await self.db.execute(
            select(Component).where(Component.project_id == project_id).order_by(Component.created_at)
        )
        return r.scalars().all()

    async def get_all_decisions(self, project_id: str):
        r = await self.db.execute(
            select(ArchitectureDecision)
            .where(ArchitectureDecision.project_id == project_id)
            .order_by(ArchitectureDecision.created_at)
        )
        return r.scalars().all()

    async def get_all_constraints(self, project_id: str):
        r = await self.db.execute(
            select(Constraint).where(Constraint.project_id == project_id).order_by(Constraint.created_at)
        )
        return r.scalars().all()

    async def get_all_test_specs(self, project_id: str):
        r = await self.db.execute(
            select(TestSpec).where(TestSpec.project_id == project_id).order_by(TestSpec.created_at)
        )
        return r.scalars().all()

    async def get_all_tasks(self, project_id: str):
        r = await self.db.execute(
            select(Task).where(Task.project_id == project_id).order_by(Task.created_at)
        )
        return r.scalars().all()

    async def get_story(self, project_id: str, story_id: str):
        r = await self.db.execute(
            select(UserStory)
            .options(selectinload(UserStory.acceptance_criteria), selectinload(UserStory.epic))
            .where(UserStory.project_id == project_id, UserStory.id == story_id)
        )
        return r.scalar_one_or_none()

    async def get_component(self, project_id: str, component_id: str):
        r = await self.db.execute(
            select(Component).where(
                Component.project_id == project_id,
                Component.id == component_id,
            )
        )
        return r.scalar_one_or_none()

    async def get_decision(self, project_id: str, decision_id: str):
        r = await self.db.execute(
            select(ArchitectureDecision).where(
                ArchitectureDecision.project_id == project_id,
                ArchitectureDecision.id == decision_id,
            )
        )
        return r.scalar_one_or_none()

    async def get_test_spec(self, project_id: str, spec_id: str):
        r = await self.db.execute(
            select(TestSpec).where(TestSpec.project_id == project_id, TestSpec.id == spec_id)
        )
        return r.scalar_one_or_none()

    async def get_task(self, project_id: str, task_id: str):
        r = await self.db.execute(
            select(Task).where(Task.project_id == project_id, Task.id == task_id)
        )
        return r.scalar_one_or_none()

    async def resolve_story_id(self, project_id: str, story_ref: str) -> str | None:
        r = await self.db.execute(
            select(UserStory.id).where(
                UserStory.project_id == project_id,
                UserStory.id.ilike(f"{story_ref}%"),
            )
        )
        rows = r.scalars().all()
        # Exact match or unique prefix match — reject ambiguous short prefixes
        return rows[0] if len(rows) == 1 else None
