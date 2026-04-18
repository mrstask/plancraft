"""Write-side commands for knowledge artifacts."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from models.db import (
    AcceptanceCriterion,
    ArchitectureDecision,
    Component,
    ComponentDependency,
    Constraint,
    Epic,
    Task,
    TaskDependency,
    TaskStory,
    TaskTestSpec,
    TestSpec,
    UserStory,
)
from models.domain import (
    AddComponentArgs,
    AddEpicArgs,
    AddTestSpecArgs,
    AddUserStoryArgs,
    DeleteComponentArgs,
    DeleteDecisionArgs,
    DeleteStoryArgs,
    DeleteTaskArgs,
    DeleteTestSpecArgs,
    ProposeTaskArgs,
    RecordConstraintArgs,
    RecordDecisionArgs,
    SetMvpScopeArgs,
    SetProblemStatementArgs,
    UpdateComponentArgs,
    UpdateDecisionArgs,
    UpdateTaskArgs,
    UpdateTestSpecArgs,
    UpdateUserStoryArgs,
)
from .common import KnowledgeBase, decision_fingerprint, similarity
from .queries import ArtifactQueries


class ArtifactCommands(KnowledgeBase):
    def __init__(self, db):
        super().__init__(db)
        self.queries = ArtifactQueries(db)

    async def set_problem_statement(self, project_id: str, args: SetProblemStatementArgs) -> str:
        project = await self.get_project(project_id)
        project.description = args.statement
        await self.db.commit()
        return "Problem statement set."

    async def set_mvp_scope(self, project_id: str, args: SetMvpScopeArgs) -> str:
        project = await self.get_project(project_id)
        resolved_story_ids: list[str] = []
        for story_ref in args.story_ids:
            resolved = await self.queries.resolve_story_id(project_id, story_ref)
            if resolved and resolved not in resolved_story_ids:
                resolved_story_ids.append(resolved)

        if not resolved_story_ids:
            return "MVP scope not updated: no valid story IDs were provided."

        project.mvp_story_ids = resolved_story_ids
        project.mvp_rationale = args.rationale or None
        await self.db.commit()
        return f"MVP scope set: {len(resolved_story_ids)} stor{'y' if len(resolved_story_ids) == 1 else 'ies'}."

    async def add_epic(self, project_id: str, args: AddEpicArgs) -> str:
        existing = await self.db.execute(
            select(Epic).where(
                Epic.project_id == project_id,
                Epic.title.ilike(args.title),
            )
        )
        epic = existing.scalar_one_or_none()
        if epic:
            epic.description = args.description or epic.description
            await self.db.commit()
            return f"Epic updated: {epic.id}"

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
        await self.db.flush()

        for index, criterion in enumerate(args.acceptance_criteria):
            self.db.add(
                AcceptanceCriterion(story_id=story.id, criterion=criterion, order_index=index)
            )
        await self.db.commit()
        await self.db.refresh(story)
        return f"User story added: {story.id}"

    async def update_user_story(self, project_id: str, args: UpdateUserStoryArgs) -> str:
        result = await self.db.execute(
            select(UserStory)
            .options(selectinload(UserStory.acceptance_criteria))
            .where(UserStory.id == args.story_id, UserStory.project_id == project_id)
        )
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
        if args.acceptance_criteria is not None:
            story.acceptance_criteria = [
                AcceptanceCriterion(criterion=criterion, order_index=index)
                for index, criterion in enumerate(args.acceptance_criteria)
            ]

        await self.db.commit()
        return f"Story {args.story_id} updated."

    async def record_constraint(self, project_id: str, args: RecordConstraintArgs) -> str:
        constraint = Constraint(project_id=project_id, type=args.type, description=args.description)
        self.db.add(constraint)
        await self.db.commit()
        return "Constraint recorded."

    async def add_component(self, project_id: str, args: AddComponentArgs) -> str:
        existing = await self.db.execute(
            select(Component).where(
                Component.project_id == project_id,
                Component.name.ilike(args.name),
            )
        )
        component = existing.scalar_one_or_none()
        if component:
            component.responsibility = args.responsibility or component.responsibility
            if args.component_type:
                component.component_type = args.component_type
            if args.file_paths:
                component.file_paths = args.file_paths
            await self.db.commit()
            return f"Component updated: {component.id}"

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
        all_decisions = await self.queries.get_all_decisions(project_id)
        new_fp = decision_fingerprint(args.title, args.decision)

        best_match = None
        best_score = 0.0
        for dec in all_decisions:
            score = max(
                similarity(dec.title, args.title),
                similarity(decision_fingerprint(dec.title, dec.decision), new_fp),
            )
            if score > best_score:
                best_score = score
                best_match = dec

        if best_match and best_score >= 0.50:
            if args.context and len(args.context) > len(best_match.context or ""):
                best_match.context = args.context
            if len(args.decision) > len(best_match.decision):
                best_match.decision = args.decision
            existing_cons = best_match.consequences or {}
            best_match.consequences = {
                "positive": args.consequences_positive or existing_cons.get("positive", []),
                "negative": args.consequences_negative or existing_cons.get("negative", []),
            }
            await self.db.commit()
            return f"Decision merged into existing '{best_match.title}': {best_match.id}"

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
        existing = await self.db.execute(
            select(TestSpec).where(
                TestSpec.project_id == project_id,
                TestSpec.description.ilike(args.description),
            )
        )
        spec = existing.scalar_one_or_none()
        if spec:
            spec.test_type = args.test_type or spec.test_type
            spec.given_context = args.given_context or spec.given_context
            spec.when_action = args.when_action or spec.when_action
            spec.then_expectation = args.then_expectation or spec.then_expectation
            if args.story_id:
                spec.story_id = args.story_id
            if args.component_id:
                spec.component_id = args.component_id
            await self.db.commit()
            return f"Test spec updated: {spec.id}"

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
            description=args.description or args.title,
            complexity=args.complexity,
            file_paths=args.file_paths,
            acceptance_criteria=args.acceptance_criteria,
        )
        self.db.add(task)
        await self.db.flush()

        for dep_id in args.depends_on:
            self.db.add(TaskDependency(task_id=task.id, depends_on_id=dep_id))

        resolved_story_ids: list[str] = []
        for sid in args.story_ids:
            story_id = await self.queries.resolve_story_id(project_id, sid)
            if story_id:
                resolved_story_ids.append(story_id)

        for story_id in resolved_story_ids:
            self.db.add(TaskStory(task_id=task.id, story_id=story_id))

        linked_spec_ids: set[str] = set(args.test_spec_ids)
        for spec_id in args.test_spec_ids:
            self.db.add(TaskTestSpec(task_id=task.id, spec_id=spec_id))

        if resolved_story_ids:
            auto_r = await self.db.execute(
                select(TestSpec).where(
                    TestSpec.project_id == project_id,
                    TestSpec.story_id.in_(resolved_story_ids),
                )
            )
            for spec in auto_r.scalars().all():
                if spec.id not in linked_spec_ids:
                    self.db.add(TaskTestSpec(task_id=task.id, spec_id=spec.id))
                    linked_spec_ids.add(spec.id)

        await self.db.commit()
        await self.db.refresh(task)
        linked = len(linked_spec_ids)
        return f"Task proposed: {task.id} (linked {linked} test spec{'s' if linked != 1 else ''})"

    async def delete_story(self, project_id: str, args: DeleteStoryArgs) -> str:
        r = await self.db.execute(
            select(UserStory).where(UserStory.id == args.story_id, UserStory.project_id == project_id)
        )
        obj = r.scalar_one_or_none()
        if not obj:
            return f"Story {args.story_id} not found."
        await self.db.delete(obj)
        await self.db.commit()
        return f"Story deleted: {args.story_id}"

    async def update_component(self, project_id: str, args: UpdateComponentArgs) -> str:
        r = await self.db.execute(
            select(Component).where(Component.id == args.component_id, Component.project_id == project_id)
        )
        obj = r.scalar_one_or_none()
        if not obj:
            return f"Component {args.component_id} not found."
        if args.name is not None:
            obj.name = args.name
        if args.responsibility is not None:
            obj.responsibility = args.responsibility
        if args.component_type is not None:
            obj.component_type = args.component_type
        await self.db.commit()
        return f"Component updated: {args.component_id}"

    async def delete_component(self, project_id: str, args: DeleteComponentArgs) -> str:
        r = await self.db.execute(
            select(Component).where(Component.id == args.component_id, Component.project_id == project_id)
        )
        obj = r.scalar_one_or_none()
        if not obj:
            return f"Component {args.component_id} not found."
        await self.db.delete(obj)
        await self.db.commit()
        return f"Component deleted: {args.component_id}"

    async def update_decision(self, project_id: str, args: UpdateDecisionArgs) -> str:
        r = await self.db.execute(
            select(ArchitectureDecision).where(
                ArchitectureDecision.id == args.decision_id,
                ArchitectureDecision.project_id == project_id,
            )
        )
        obj = r.scalar_one_or_none()
        if not obj:
            return f"Decision {args.decision_id} not found."
        if args.title is not None:
            obj.title = args.title
        if args.context is not None:
            obj.context = args.context
        if args.decision is not None:
            obj.decision = args.decision
        await self.db.commit()
        return f"Decision updated: {args.decision_id}"

    async def delete_decision(self, project_id: str, args: DeleteDecisionArgs) -> str:
        r = await self.db.execute(
            select(ArchitectureDecision).where(
                ArchitectureDecision.id == args.decision_id,
                ArchitectureDecision.project_id == project_id,
            )
        )
        obj = r.scalar_one_or_none()
        if not obj:
            return f"Decision {args.decision_id} not found."
        await self.db.delete(obj)
        await self.db.commit()
        return f"Decision deleted: {args.decision_id}"

    async def update_test_spec(self, project_id: str, args: UpdateTestSpecArgs) -> str:
        r = await self.db.execute(
            select(TestSpec).where(TestSpec.id == args.spec_id, TestSpec.project_id == project_id)
        )
        obj = r.scalar_one_or_none()
        if not obj:
            return f"Test spec {args.spec_id} not found."
        if args.description is not None:
            obj.description = args.description
        if args.given_context is not None:
            obj.given_context = args.given_context
        if args.when_action is not None:
            obj.when_action = args.when_action
        if args.then_expectation is not None:
            obj.then_expectation = args.then_expectation
        if args.test_type is not None:
            obj.test_type = args.test_type
        await self.db.commit()
        return f"Test spec updated: {args.spec_id}"

    async def delete_test_spec(self, project_id: str, args: DeleteTestSpecArgs) -> str:
        r = await self.db.execute(
            select(TestSpec).where(TestSpec.id == args.spec_id, TestSpec.project_id == project_id)
        )
        obj = r.scalar_one_or_none()
        if not obj:
            return f"Test spec {args.spec_id} not found."
        await self.db.delete(obj)
        await self.db.commit()
        return f"Test spec deleted: {args.spec_id}"

    async def update_task(self, project_id: str, args: UpdateTaskArgs) -> str:
        r = await self.db.execute(
            select(Task).where(Task.id == args.task_id, Task.project_id == project_id)
        )
        obj = r.scalar_one_or_none()
        if not obj:
            return f"Task {args.task_id} not found."
        if args.title is not None:
            obj.title = args.title
        if args.description is not None:
            obj.description = args.description
        if args.complexity is not None:
            obj.complexity = args.complexity
        await self.db.commit()
        return f"Task updated: {args.task_id}"

    async def delete_task(self, project_id: str, args: DeleteTaskArgs) -> str:
        r = await self.db.execute(
            select(Task).where(Task.id == args.task_id, Task.project_id == project_id)
        )
        obj = r.scalar_one_or_none()
        if not obj:
            return f"Task {args.task_id} not found."
        await self.db.delete(obj)
        await self.db.commit()
        return f"Task deleted: {args.task_id}"
