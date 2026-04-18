"""Knowledge model service — CRUD over the structured project data."""
from __future__ import annotations

from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


def _similarity(a: str, b: str) -> float:
    """Return a 0-1 similarity ratio between two strings (case-insensitive)."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _decision_fingerprint(title: str, decision: str) -> str:
    """Combine title + decision text for a richer similarity signal."""
    return f"{title} {decision}"

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
    UpdateComponentArgs, UpdateDecisionArgs, UpdateTestSpecArgs, UpdateTaskArgs,
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
            select(ArchitectureDecision).where(ArchitectureDecision.project_id == project_id)
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
        # Upsert by title (case-insensitive) to avoid duplicates
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
        # Upsert by name (case-insensitive) to avoid duplicates across retries
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
        # Fuzzy dedup: compare against ALL existing decisions using title+text fingerprint.
        # Threshold 0.55 catches near-duplicates ("Layered Architecture Adoption" ≈
        # "Implementing Layered Architecture") without merging genuinely different decisions.
        all_decisions = await self.get_all_decisions(project_id)
        new_fp = _decision_fingerprint(args.title, args.decision)

        best_match = None
        best_score = 0.0
        for dec in all_decisions:
            # Title similarity is a more reliable signal than full-text for decisions —
            # the LLM rephrases the same concept rather than changing the underlying text.
            score = _similarity(dec.title, args.title)
            if score > best_score:
                best_score = score
                best_match = dec

        if best_match and best_score >= 0.50:
            # Merge: keep the existing record, enrich it with any new info
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
        # Upsert by description (case-insensitive) to avoid duplicates
        existing = await self.db.execute(
            select(TestSpec).where(
                TestSpec.project_id == project_id,
                TestSpec.description.ilike(args.description),
            )
        )
        spec = existing.scalar_one_or_none()
        if spec:
            spec.test_type       = args.test_type or spec.test_type
            spec.given_context   = args.given_context or spec.given_context
            spec.when_action     = args.when_action or spec.when_action
            spec.then_expectation= args.then_expectation or spec.then_expectation
            if args.story_id:     spec.story_id     = args.story_id
            if args.component_id: spec.component_id = args.component_id
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
        for story_id in args.story_ids:
            self.db.add(TaskStory(task_id=task.id, story_id=story_id))
        for spec_id in args.test_spec_ids:
            self.db.add(TaskTestSpec(task_id=task.id, spec_id=spec_id))

        await self.db.commit()
        await self.db.refresh(task)
        return f"Task proposed: {task.id}"

    # ------------------------------------------------------------------
    # Full-list fetchers (for the document tree sidebar)
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Single-item fetchers (for the detail view)
    # ------------------------------------------------------------------

    async def get_story(self, story_id: str):
        r = await self.db.execute(
            select(UserStory)
            .options(selectinload(UserStory.acceptance_criteria), selectinload(UserStory.epic))
            .where(UserStory.id == story_id)
        )
        return r.scalar_one_or_none()

    async def get_component(self, component_id: str):
        r = await self.db.execute(select(Component).where(Component.id == component_id))
        return r.scalar_one_or_none()

    async def get_decision(self, decision_id: str):
        r = await self.db.execute(select(ArchitectureDecision).where(ArchitectureDecision.id == decision_id))
        return r.scalar_one_or_none()

    async def get_test_spec(self, spec_id: str):
        r = await self.db.execute(select(TestSpec).where(TestSpec.id == spec_id))
        return r.scalar_one_or_none()

    async def get_task(self, task_id: str):
        r = await self.db.execute(select(Task).where(Task.id == task_id))
        return r.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Review phase — update / delete
    # ------------------------------------------------------------------

    async def delete_story(self, story_id: str) -> str:
        r = await self.db.execute(select(UserStory).where(UserStory.id == story_id))
        obj = r.scalar_one_or_none()
        if not obj:
            return f"Story {story_id} not found."
        await self.db.delete(obj)
        await self.db.commit()
        return f"Story deleted: {story_id}"

    async def update_component(self, args: UpdateComponentArgs) -> str:
        r = await self.db.execute(select(Component).where(Component.id == args.component_id))
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

    async def delete_component(self, component_id: str) -> str:
        r = await self.db.execute(select(Component).where(Component.id == component_id))
        obj = r.scalar_one_or_none()
        if not obj:
            return f"Component {component_id} not found."
        await self.db.delete(obj)
        await self.db.commit()
        return f"Component deleted: {component_id}"

    async def update_decision(self, args: UpdateDecisionArgs) -> str:
        r = await self.db.execute(
            select(ArchitectureDecision).where(ArchitectureDecision.id == args.decision_id)
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

    async def delete_decision(self, decision_id: str) -> str:
        r = await self.db.execute(
            select(ArchitectureDecision).where(ArchitectureDecision.id == decision_id)
        )
        obj = r.scalar_one_or_none()
        if not obj:
            return f"Decision {decision_id} not found."
        await self.db.delete(obj)
        await self.db.commit()
        return f"Decision deleted: {decision_id}"

    async def update_test_spec(self, args: UpdateTestSpecArgs) -> str:
        r = await self.db.execute(select(TestSpec).where(TestSpec.id == args.spec_id))
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

    async def delete_test_spec(self, spec_id: str) -> str:
        r = await self.db.execute(select(TestSpec).where(TestSpec.id == spec_id))
        obj = r.scalar_one_or_none()
        if not obj:
            return f"Test spec {spec_id} not found."
        await self.db.delete(obj)
        await self.db.commit()
        return f"Test spec deleted: {spec_id}"

    async def update_task(self, args: UpdateTaskArgs) -> str:
        r = await self.db.execute(select(Task).where(Task.id == args.task_id))
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

    async def delete_task(self, task_id: str) -> str:
        r = await self.db.execute(select(Task).where(Task.id == task_id))
        obj = r.scalar_one_or_none()
        if not obj:
            return f"Task {task_id} not found."
        await self.db.delete(obj)
        await self.db.commit()
        return f"Task deleted: {task_id}"

    async def get_full_review_context(self, project_id: str) -> str:
        """Return a formatted string of ALL artifacts with IDs for the reviewer LLM."""
        project = await self._get_project(project_id)
        stories    = await self.get_all_stories(project_id)
        components = await self.get_all_components(project_id)
        decisions  = await self.get_all_decisions(project_id)
        specs      = await self.get_all_test_specs(project_id)
        tasks      = await self.get_all_tasks(project_id)

        lines = [
            f"Project: {project.name}",
            f"Problem: {project.description or '(none)'}",
            "",
            "=" * 60,
            "ALL ARTIFACTS — review every category for duplicates and quality",
            "=" * 60,
        ]

        lines += [f"\n### STORIES ({len(stories)})"]
        for s in stories:
            lines.append(f"  [{s.id}]")
            lines.append(f"    As a {s.as_a}, I want {s.i_want}, so that {s.so_that}")
            lines.append(f"    Priority: {s.priority}")
            if s.acceptance_criteria:
                for ac in s.acceptance_criteria:
                    lines.append(f"    AC: {ac.criterion}")

        lines += [f"\n### COMPONENTS ({len(components)})"]
        for c in components:
            lines.append(f"  [{c.id}]")
            lines.append(f"    Name: {c.name}")
            lines.append(f"    Type: {c.component_type or '–'}")
            lines.append(f"    Responsibility: {c.responsibility}")

        lines += [f"\n### ARCHITECTURE DECISIONS ({len(decisions)})"]
        for d in decisions:
            lines.append(f"  [{d.id}]")
            lines.append(f"    Title: {d.title}")
            lines.append(f"    Decision: {d.decision}")
            if d.context:
                lines.append(f"    Context: {d.context}")

        lines += [f"\n### TEST SPECS ({len(specs)})"]
        for sp in specs:
            lines.append(f"  [{sp.id}]")
            lines.append(f"    Description: {sp.description}")
            lines.append(f"    Type: {sp.test_type}")
            lines.append(f"    Given: {sp.given_context or '–'}")
            lines.append(f"    When: {sp.when_action or '–'}")
            lines.append(f"    Then: {sp.then_expectation or '–'}")

        lines += [f"\n### TASKS ({len(tasks)})"]
        for t in tasks:
            lines.append(f"  [{t.id}]")
            lines.append(f"    Title: {t.title}")
            lines.append(f"    Complexity: {t.complexity}")
            lines.append(f"    Description: {t.description}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _get_project(self, project_id: str) -> Project:
        result = await self.db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if not project:
            raise ValueError(f"Project {project_id} not found")
        return project
