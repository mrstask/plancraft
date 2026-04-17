"""Knowledge model service — CRUD over the structured project data."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.db import (
    Project, UserStory, AcceptanceCriterion, Epic, Constraint,
    Component, ComponentDependency, ArchitectureDecision,
    TestSpec, Task, TaskDependency, TaskStory, TaskTestSpec,
)
from models.domain import (
    KnowledgeSnapshot, StorySnapshot, ComponentSnapshot, DecisionSnapshot,
    AddUserStoryArgs, UpdateUserStoryArgs, AddEpicArgs, RecordConstraintArgs,
    AddComponentArgs, RecordDecisionArgs, AddTestSpecArgs, ProposeTaskArgs,
    SetProblemStatementArgs,
)


class KnowledgeService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Snapshot (for Claude's context)
    # ------------------------------------------------------------------

    async def get_snapshot(self, project_id: str) -> KnowledgeSnapshot:
        project = await self._get_project(project_id)

        story_result = await self.db.execute(
            select(UserStory).where(UserStory.project_id == project_id).limit(5)
        )
        stories = story_result.scalars().all()

        comp_result = await self.db.execute(
            select(Component).where(Component.project_id == project_id).limit(5)
        )
        components = comp_result.scalars().all()

        dec_result = await self.db.execute(
            select(ArchitectureDecision).where(ArchitectureDecision.project_id == project_id).limit(5)
        )
        decisions = dec_result.scalars().all()

        counts = await self._get_counts(project_id)

        return KnowledgeSnapshot(
            project_name=project.name,
            problem_statement=project.description,
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
        from sqlalchemy import func

        async def count(model, fk=None):
            col = fk or model.project_id
            r = await self.db.execute(select(func.count()).where(col == project_id))
            return r.scalar()

        return {
            "story_count": await count(UserStory),
            "epic_count": await count(Epic),
            "component_count": await count(Component),
            "decision_count": await count(ArchitectureDecision),
            "test_spec_count": await count(TestSpec),
            "task_count": await count(Task),
        }

    # ------------------------------------------------------------------
    # Tool handlers (called when Claude uses a knowledge tool)
    # ------------------------------------------------------------------

    async def set_problem_statement(self, project_id: str, args: SetProblemStatementArgs) -> str:
        project = await self._get_project(project_id)
        project.description = args.statement
        await self.db.commit()
        return f"Problem statement set."

    async def add_epic(self, project_id: str, args: AddEpicArgs) -> str:
        epic = Epic(project_id=project_id, title=args.title, description=args.description)
        self.db.add(epic)
        await self.db.commit()
        await self.db.refresh(epic)
        return f"Epic added: {epic.id}"

    async def add_user_story(self, project_id: str, args: AddUserStoryArgs) -> str:
        story = UserStory(
            project_id=project_id,
            epic_id=args.epic_id,
            as_a=args.as_a,
            i_want=args.i_want,
            so_that=args.so_that,
            priority=args.priority,
        )
        self.db.add(story)
        await self.db.flush()  # get the ID before committing criteria

        for i, criterion in enumerate(args.acceptance_criteria):
            self.db.add(AcceptanceCriterion(
                story_id=story.id, criterion=criterion, order_index=i
            ))
        await self.db.commit()
        await self.db.refresh(story)
        return f"User story added: {story.id}"

    async def update_user_story(self, args: UpdateUserStoryArgs) -> str:
        result = await self.db.execute(select(UserStory).where(UserStory.id == args.story_id))
        story = result.scalar_one_or_none()
        if not story:
            return f"Story {args.story_id} not found."
        if args.as_a is not None:
            story.as_a = args.as_a
        if args.i_want is not None:
            story.i_want = args.i_want
        if args.so_that is not None:
            story.so_that = args.so_that
        if args.priority is not None:
            story.priority = args.priority
        await self.db.commit()
        return f"Story {args.story_id} updated."

    async def record_constraint(self, project_id: str, args: RecordConstraintArgs) -> str:
        constraint = Constraint(
            project_id=project_id, type=args.type, description=args.description
        )
        self.db.add(constraint)
        await self.db.commit()
        return "Constraint recorded."

    async def add_component(self, project_id: str, args: AddComponentArgs) -> str:
        component = Component(
            project_id=project_id,
            name=args.name,
            responsibility=args.responsibility,
            component_type=args.component_type,
            file_paths=args.file_paths,
        )
        self.db.add(component)
        await self.db.flush()

        for dep_id in args.depends_on:
            self.db.add(ComponentDependency(from_id=component.id, to_id=dep_id))

        await self.db.commit()
        await self.db.refresh(component)
        return f"Component added: {component.id}"

    async def record_decision(self, project_id: str, args: RecordDecisionArgs) -> str:
        decision = ArchitectureDecision(
            project_id=project_id,
            title=args.title,
            context=args.context,
            decision=args.decision,
            consequences={
                "positive": args.consequences_positive,
                "negative": args.consequences_negative,
            },
        )
        self.db.add(decision)
        await self.db.commit()
        await self.db.refresh(decision)
        return f"Decision recorded: {decision.id}"

    async def add_test_spec(self, project_id: str, args: AddTestSpecArgs) -> str:
        spec = TestSpec(
            project_id=project_id,
            story_id=args.story_id,
            component_id=args.component_id,
            description=args.description,
            test_type=args.test_type,
            given_context=args.given_context,
            when_action=args.when_action,
            then_expectation=args.then_expectation,
        )
        self.db.add(spec)
        await self.db.commit()
        await self.db.refresh(spec)
        return f"Test spec added: {spec.id}"

    async def propose_task(self, project_id: str, args: ProposeTaskArgs) -> str:
        task = Task(
            project_id=project_id,
            title=args.title,
            description=args.description,
            complexity=args.complexity,
            file_paths=args.file_paths,
            acceptance_criteria=args.acceptance_criteria,
        )
        self.db.add(task)
        await self.db.flush()

        for dep_id in args.depends_on:
            self.db.add(TaskDependency(task_id=task.id, depends_on_id=dep_id))
        for story_id in args.story_ids:
            self.db.add(TaskStory(task_id=task.id, story_id=story_id))
        for spec_id in args.test_spec_ids:
            self.db.add(TaskTestSpec(task_id=task.id, spec_id=spec_id))

        await self.db.commit()
        await self.db.refresh(task)
        return f"Task proposed: {task.id}"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _get_project(self, project_id: str) -> Project:
        result = await self.db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if not project:
            raise ValueError(f"Project {project_id} not found")
        return project
