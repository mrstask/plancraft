"""Export-specific read models."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from models.db import (
    ArchitectureDecision,
    BusinessRule,
    Component,
    Constraint,
    DataEntity,
    FunctionalRequirement,
    Persona,
    Task,
    TaskDependency,
    TaskStory,
    TaskTestSpec,
    TestSpec,
    UserFlow,
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
class BAExportData:
    project_name: str
    problem_statement: str | None
    business_goals: list = field(default_factory=list)
    success_metrics: list = field(default_factory=list)
    in_scope: list = field(default_factory=list)
    out_of_scope: list = field(default_factory=list)
    target_users: list = field(default_factory=list)
    terminology: list = field(default_factory=list)
    llm_interaction_model: dict | None = None
    personas: list = field(default_factory=list)
    user_flows: list = field(default_factory=list)
    business_rules: list = field(default_factory=list)
    data_entities: list = field(default_factory=list)
    functional_requirements: list = field(default_factory=list)
    stories: list = field(default_factory=list)


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
    terminology: list = field(default_factory=list)


class ExportDataLoader(KnowledgeBase):
    async def load_task_export(self, project_id: str, feature_id: str | None = None) -> TaskExportData:
        project = await self.get_project(project_id)

        task_stmt = select(Task).where(Task.project_id == project_id).order_by(Task.created_at)
        scoped_feature_id = self.feature_id if feature_id is None else feature_id
        if scoped_feature_id is not None:
            task_stmt = task_stmt.where(Task.feature_id == scoped_feature_id)
        task_result = await self.db.execute(task_stmt)
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

    async def load_ba_export(self, project_id: str, feature_id: str | None = None) -> BAExportData:
        project = await self.get_project(project_id)
        scoped_feature_id = self.feature_id if feature_id is None else feature_id

        personas = await self.db.execute(
            select(Persona).where(Persona.project_id == project_id).order_by(Persona.created_at)
        )
        flows = await self.db.execute(
            select(UserFlow)
            .options(selectinload(UserFlow.steps))
            .where(UserFlow.project_id == project_id)
            .order_by(UserFlow.created_at)
        )
        rules = await self.db.execute(
            select(BusinessRule).where(BusinessRule.project_id == project_id).order_by(BusinessRule.created_at)
        )
        entities = await self.db.execute(
            select(DataEntity).where(DataEntity.project_id == project_id).order_by(DataEntity.created_at)
        )
        frs = await self.db.execute(
            select(FunctionalRequirement)
            .options(selectinload(FunctionalRequirement.story_links))
            .where(FunctionalRequirement.project_id == project_id)
            .order_by(FunctionalRequirement.created_at)
        )
        stories = await self.db.execute(
            select(UserStory)
            .options(selectinload(UserStory.acceptance_criteria))
            .where(UserStory.project_id == project_id)
            .where(UserStory.feature_id == scoped_feature_id if scoped_feature_id is not None else True)
            .order_by(UserStory.created_at)
        )

        return BAExportData(
            project_name=project.name,
            problem_statement=project.description,
            business_goals=list(project.business_goals or []),
            success_metrics=list(project.success_metrics or []),
            in_scope=list(project.in_scope or []),
            out_of_scope=list(project.out_of_scope or []),
            target_users=list(project.target_users or []),
            terminology=list(project.terminology or []),
            llm_interaction_model=project.llm_interaction_model,
            personas=personas.scalars().all(),
            user_flows=flows.scalars().all(),
            business_rules=rules.scalars().all(),
            data_entities=entities.scalars().all(),
            functional_requirements=frs.scalars().all(),
            stories=stories.scalars().all(),
        )

    async def load_arc42_export(self, project_id: str, feature_id: str | None = None) -> Arc42ExportData:
        project = await self.get_project(project_id)
        scoped_feature_id = self.feature_id if feature_id is None else feature_id

        constraints = await self.db.execute(
            select(Constraint).where(Constraint.project_id == project_id).order_by(Constraint.created_at)
        )
        components = await self.db.execute(
            select(Component).where(Component.project_id == project_id).order_by(Component.created_at)
        )
        decisions = await self.db.execute(
            select(ArchitectureDecision)
            .where(ArchitectureDecision.project_id == project_id)
            .where(
                or_(ArchitectureDecision.feature_id == scoped_feature_id, ArchitectureDecision.feature_id.is_(None))
                if scoped_feature_id is not None
                else ArchitectureDecision.feature_id.is_(None)
            )
            .order_by(ArchitectureDecision.created_at)
        )
        stories = await self.db.execute(
            select(UserStory)
            .options(selectinload(UserStory.acceptance_criteria))
            .where(UserStory.project_id == project_id)
            .where(UserStory.feature_id == scoped_feature_id if scoped_feature_id is not None else True)
            .order_by(UserStory.created_at)
        )
        specs = await self.db.execute(
            select(TestSpec)
            .where(TestSpec.project_id == project_id)
            .where(TestSpec.feature_id == scoped_feature_id if scoped_feature_id is not None else True)
            .order_by(TestSpec.created_at)
        )
        tasks = await self.db.execute(
            select(Task)
            .where(Task.project_id == project_id)
            .where(Task.feature_id == scoped_feature_id if scoped_feature_id is not None else True)
            .order_by(Task.created_at)
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
            terminology=list(project.terminology or []),
        )
