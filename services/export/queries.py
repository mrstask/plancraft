"""Export-specific read models."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select

from models.db import (
    ArchitectureDecision,
    Component,
    Constraint,
    Task,
    TaskDependency,
    TaskStory,
    TaskTestSpec,
    TestSpec,
    UserStory,
)
from services.knowledge.common import KnowledgeBase


@dataclass
class TaskExportData:
    project_name: str
    tasks: list[Task]
    deps_by_task: dict[str, list[str]]
    stories_by_task: dict[str, list[str]]
    specs_by_task: dict[str, list[str]]


@dataclass
class Arc42ExportData:
    project_name: str
    problem_statement: str | None
    constraints: list[Constraint]
    components: list[Component]
    decisions: list[ArchitectureDecision]
    stories: list[UserStory]
    specs: list[TestSpec]
    tasks: list[Task]


class ExportDataLoader(KnowledgeBase):
    async def load_task_export(self, project_id: str) -> TaskExportData:
        project = await self.get_project(project_id)

        task_result = await self.db.execute(
            select(Task).where(Task.project_id == project_id).order_by(Task.created_at)
        )
        tasks = task_result.scalars().all()
        task_ids = [task.id for task in tasks]

        deps_by_task: dict[str, list[str]] = defaultdict(list)
        stories_by_task: dict[str, list[str]] = defaultdict(list)
        specs_by_task: dict[str, list[str]] = defaultdict(list)

        if task_ids:
            dep_result = await self.db.execute(
                select(TaskDependency).where(TaskDependency.task_id.in_(task_ids))
            )
            for row in dep_result.scalars().all():
                deps_by_task[row.task_id].append(row.depends_on_id)

            story_result = await self.db.execute(
                select(TaskStory).where(TaskStory.task_id.in_(task_ids))
            )
            for row in story_result.scalars().all():
                stories_by_task[row.task_id].append(row.story_id)

            spec_result = await self.db.execute(
                select(TaskTestSpec).where(TaskTestSpec.task_id.in_(task_ids))
            )
            for row in spec_result.scalars().all():
                specs_by_task[row.task_id].append(row.spec_id)

        return TaskExportData(
            project_name=project.name,
            tasks=tasks,
            deps_by_task=deps_by_task,
            stories_by_task=stories_by_task,
            specs_by_task=specs_by_task,
        )

    async def load_arc42_export(self, project_id: str) -> Arc42ExportData:
        project = await self.get_project(project_id)

        constraints = await self.db.execute(
            select(Constraint).where(Constraint.project_id == project_id).order_by(Constraint.created_at)
        )
        components = await self.db.execute(
            select(Component).where(Component.project_id == project_id).order_by(Component.created_at)
        )
        decisions = await self.db.execute(
            select(ArchitectureDecision)
            .where(ArchitectureDecision.project_id == project_id)
            .order_by(ArchitectureDecision.created_at)
        )
        stories = await self.db.execute(
            select(UserStory).where(UserStory.project_id == project_id).order_by(UserStory.created_at)
        )
        specs = await self.db.execute(
            select(TestSpec).where(TestSpec.project_id == project_id).order_by(TestSpec.created_at)
        )
        tasks = await self.db.execute(
            select(Task).where(Task.project_id == project_id).order_by(Task.created_at)
        )

        return Arc42ExportData(
            project_name=project.name,
            problem_statement=project.description,
            constraints=constraints.scalars().all(),
            components=components.scalars().all(),
            decisions=decisions.scalars().all(),
            stories=stories.scalars().all(),
            specs=specs.scalars().all(),
            tasks=tasks.scalars().all(),
        )
