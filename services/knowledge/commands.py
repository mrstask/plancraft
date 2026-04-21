"""Write-side commands for knowledge artifacts."""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from models.db import (
    AcceptanceCriterion,
    ArchitectureDecision,
    BusinessRule,
    ClarificationPoint,
    Component,
    ComponentDependency,
    Constraint,
    DataEntity,
    Epic,
    FunctionalRequirement,
    FunctionalRequirementStory,
    InterfaceContract,
    Persona,
    ProjectMission,
    ProjectRoadmapItem,
    Task,
    TaskDependency,
    TaskStory,
    TaskTestSpec,
    TechStackEntry,
    TestSpec,
    UserFlow,
    UserFlowStep,
    UserStory,
)
from models.domain import (
    AddRoadmapItemArgs,
    AddBusinessRuleArgs,
    AddComponentArgs,
    AddDataEntityArgs,
    AddEpicArgs,
    AddFunctionalRequirementArgs,
    AddGlossaryTermArgs,
    AddInterfaceContractArgs,
    AddPersonaArgs,
    AddTestSpecArgs,
    AddTechStackEntryArgs,
    AddUserFlowArgs,
    AddUserStoryArgs,
    AnswerClarificationPointArgs,
    DeleteComponentArgs,
    DeleteInterfaceContractArgs,
    DeleteDecisionArgs,
    DeleteStoryArgs,
    DeleteTaskArgs,
    DeleteTestSpecArgs,
    ProposeTaskArgs,
    RecordConstraintArgs,
    RecordDecisionArgs,
    SetProjectMissionArgs,
    SetLlmInteractionModelArgs,
    SetMvpScopeArgs,
    SetProblemStatementArgs,
    SetVisionScopeArgs,
    UpdateRoadmapItemArgs,
    UpdateComponentArgs,
    UpdateInterfaceContractArgs,
    UpdateDecisionArgs,
    UpdateTaskArgs,
    UpdateTechStackEntryArgs,
    UpdateTestSpecArgs,
    UpdateUserStoryArgs,
)
from roles.ba_clarifications import CATALOG_BY_ID
from .common import KnowledgeBase, decision_fingerprint, similarity
from .queries import ArtifactQueries


def _parse_step(raw: str) -> tuple[str | None, str]:
    """Split an optional 'Actor: description' prefix from a flow step string."""
    if ":" in raw:
        actor, _, description = raw.partition(":")
        actor = actor.strip()
        description = description.strip()
        if actor and description:
            return actor, description
    return None, raw.strip()


class ArtifactCommands(KnowledgeBase):
    def __init__(self, db, feature_id: str | None = None):
        super().__init__(db, feature_id=feature_id)
        self.queries = ArtifactQueries(db, feature_id=feature_id)

    async def set_project_mission(self, project_id: str, args: SetProjectMissionArgs) -> str:
        mission = await self.queries.get_project_mission(project_id)
        if mission is None:
            mission = ProjectMission(
                project_id=project_id,
                statement=args.statement,
                target_users=args.target_users,
                problem=args.problem,
            )
            self.db.add(mission)
            action = "created"
        else:
            mission.statement = args.statement
            mission.target_users = args.target_users
            mission.problem = args.problem
            action = "updated"
        await self.db.commit()
        return f"Project mission {action}."

    async def add_roadmap_item(self, project_id: str, args: AddRoadmapItemArgs) -> str:
        existing = await self.db.execute(
            select(ProjectRoadmapItem).where(
                ProjectRoadmapItem.project_id == project_id,
                ProjectRoadmapItem.title.ilike(args.title),
            )
        )
        item = existing.scalar_one_or_none()
        ordinal = args.ordinal if args.ordinal is not None else await self._next_roadmap_ordinal(project_id)

        if item:
            item.title = args.title
            item.description = args.description
            item.ordinal = ordinal
            item.mvp = args.mvp
            if args.linked_epic_id is not None:
                item.linked_epic_id = args.linked_epic_id
            action = "updated"
        else:
            item = ProjectRoadmapItem(
                project_id=project_id,
                ordinal=ordinal,
                title=args.title,
                description=args.description,
                linked_epic_id=args.linked_epic_id,
                mvp=args.mvp,
            )
            self.db.add(item)
            await self.db.flush()
            action = "added"

        await self._normalize_roadmap_ordinals(project_id)
        await self.db.commit()
        return f"Roadmap item {action}: {item.id}"

    async def update_roadmap_item(self, project_id: str, args: UpdateRoadmapItemArgs) -> str:
        item = await self.queries.get_roadmap_item(project_id, args.item_id)
        if not item:
            return f"Roadmap item {args.item_id} not found."

        if args.title is not None:
            item.title = args.title
        if args.description is not None:
            item.description = args.description
        if args.ordinal is not None:
            item.ordinal = args.ordinal
        if args.mvp is not None:
            item.mvp = args.mvp
        if args.linked_epic_id is not None:
            item.linked_epic_id = args.linked_epic_id or None

        await self._normalize_roadmap_ordinals(project_id)
        await self.db.commit()
        return f"Roadmap item updated: {args.item_id}"

    async def add_tech_stack_entry(self, project_id: str, args: AddTechStackEntryArgs) -> str:
        existing = await self.db.execute(
            select(TechStackEntry).where(
                TechStackEntry.project_id == project_id,
                TechStackEntry.layer.ilike(args.layer),
            )
        )
        entry = existing.scalar_one_or_none()
        if entry:
            entry.choice = args.choice
            entry.rationale = args.rationale
            action = "updated"
        else:
            entry = TechStackEntry(
                project_id=project_id,
                layer=args.layer,
                choice=args.choice,
                rationale=args.rationale,
            )
            self.db.add(entry)
            await self.db.flush()
            action = "added"
        await self.db.commit()
        return f"Tech stack entry {action}: {entry.id}"

    async def update_tech_stack_entry(self, project_id: str, args: UpdateTechStackEntryArgs) -> str:
        entry = await self.queries.get_tech_stack_entry(project_id, args.entry_id)
        if not entry:
            return f"Tech stack entry {args.entry_id} not found."

        if args.layer is not None:
            entry.layer = args.layer
        if args.choice is not None:
            entry.choice = args.choice
        if args.rationale is not None:
            entry.rationale = args.rationale

        await self.db.commit()
        return f"Tech stack entry updated: {args.entry_id}"

    async def seed_founder_from_existing_project(self, project_id: str) -> str:
        project = await self.get_project(project_id)
        mission = await self.queries.get_project_mission(project_id)
        roadmap_items = await self.queries.get_all_roadmap_items(project_id)
        tech_entries = await self.queries.get_all_tech_stack_entries(project_id)

        if mission is None:
            mission = ProjectMission(
                project_id=project_id,
                statement=self._draft_mission_statement(project),
                target_users=self._draft_target_users(project),
                problem=(project.description or "Existing project problem statement needs refinement."),
            )
            self.db.add(mission)

        if not roadmap_items:
            for index, item in enumerate(self._draft_roadmap_items(project), start=1):
                self.db.add(
                    ProjectRoadmapItem(
                        project_id=project_id,
                        ordinal=index,
                        title=item["title"],
                        description=item["description"],
                        mvp=(index == 1),
                    )
                )

        if not tech_entries:
            for item in self._draft_tech_stack_entries(project):
                self.db.add(
                    TechStackEntry(
                        project_id=project_id,
                        layer=item["layer"],
                        choice=item["choice"],
                        rationale=item["rationale"],
                    )
                )

        await self.db.flush()
        await self._normalize_roadmap_ordinals(project_id)
        await self._link_roadmap_items_to_existing_epics(project_id)
        await self.db.commit()
        return "Founder draft artifacts seeded from the existing project."

    async def scaffold_founder_manual_entry(self, project_id: str) -> str:
        mission = await self.queries.get_project_mission(project_id)
        if mission is None:
            self.db.add(
                ProjectMission(
                    project_id=project_id,
                    statement="",
                    target_users="",
                    problem="",
                )
            )

        if not await self.queries.get_all_roadmap_items(project_id):
            self.db.add(
                ProjectRoadmapItem(
                    project_id=project_id,
                    ordinal=1,
                    title="",
                    description="",
                    mvp=True,
                )
            )

        if not await self.queries.get_all_tech_stack_entries(project_id):
            self.db.add(
                TechStackEntry(
                    project_id=project_id,
                    layer="",
                    choice="",
                    rationale="",
                )
            )

        await self.db.commit()
        return "Founder placeholders created for manual entry."

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
            await self._link_epic_to_roadmap_items(project_id, epic)
            await self.db.commit()
            return f"Epic updated: {epic.id}"

        epic = Epic(project_id=project_id, title=args.title, description=args.description)
        self.db.add(epic)
        await self.db.commit()
        await self.db.refresh(epic)
        await self._link_epic_to_roadmap_items(project_id, epic)
        await self.db.commit()
        return f"Epic added: {epic.id}"

    async def add_user_story(self, project_id: str, args: AddUserStoryArgs) -> str:
        resolved_epic_id: str | None = None
        if args.epic_id:
            # Try exact UUID match first
            r = await self.db.execute(
                select(Epic).where(Epic.id == args.epic_id, Epic.project_id == project_id)
            )
            epic = r.scalar_one_or_none()
            if not epic:
                # LLM sometimes passes a slug/title instead of UUID — try by title
                r = await self.db.execute(
                    select(Epic).where(Epic.project_id == project_id, Epic.title.ilike(args.epic_id))
                )
                epic = r.scalar_one_or_none()
            resolved_epic_id = epic.id if epic else None

        story = UserStory(
            project_id=project_id,
            feature_id=self.feature_id,
            epic_id=resolved_epic_id,
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
        stmt = (
            select(UserStory)
            .options(selectinload(UserStory.acceptance_criteria))
            .where(UserStory.id == args.story_id, UserStory.project_id == project_id)
        )
        if self.feature_id is not None:
            stmt = stmt.where(UserStory.feature_id == self.feature_id)
        result = await self.db.execute(stmt)
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
            feature_id=self.feature_id,
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

    async def add_interface_contract(self, project_id: str, args: AddInterfaceContractArgs) -> str:
        stmt = select(InterfaceContract).where(
            InterfaceContract.project_id == project_id,
            InterfaceContract.component_id == args.component_id,
            InterfaceContract.kind == args.kind,
            InterfaceContract.name.ilike(args.name),
        )
        if self.feature_id is not None:
            stmt = stmt.where(InterfaceContract.feature_id == self.feature_id)
        else:
            stmt = stmt.where(InterfaceContract.feature_id.is_(None))
        existing = (await self.db.execute(stmt)).scalar_one_or_none()
        if existing:
            existing.body_md = args.body_md
            await self.db.commit()
            return f"Interface contract updated: {existing.id}"

        contract = InterfaceContract(
            project_id=project_id,
            feature_id=self.feature_id,
            component_id=args.component_id,
            kind=args.kind,
            name=args.name,
            body_md=args.body_md,
        )
        self.db.add(contract)
        await self.db.commit()
        await self.db.refresh(contract)
        return f"Interface contract added: {contract.id}"

    async def add_test_spec(self, project_id: str, args: AddTestSpecArgs) -> str:
        existing = await self.db.execute(
            select(TestSpec).where(
                TestSpec.project_id == project_id,
                TestSpec.feature_id == self.feature_id,
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
            feature_id=self.feature_id,
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
            feature_id=self.feature_id,
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
                    TestSpec.feature_id == self.feature_id,
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
        stmt = select(UserStory).where(UserStory.id == args.story_id, UserStory.project_id == project_id)
        if self.feature_id is not None:
            stmt = stmt.where(UserStory.feature_id == self.feature_id)
        r = await self.db.execute(stmt)
        obj = r.scalar_one_or_none()
        if not obj:
            return f"Story {args.story_id} not found."
        specs = await self.db.execute(
            select(TestSpec).where(TestSpec.story_id == args.story_id)
        )
        for spec in specs.scalars().all():
            spec.story_id = None
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
        # Clear FK references from test_specs (SQLite schema lacks ON DELETE SET NULL
        # on the legacy column; do it explicitly).
        specs = await self.db.execute(
            select(TestSpec).where(TestSpec.component_id == args.component_id)
        )
        for spec in specs.scalars().all():
            spec.component_id = None
        await self.db.delete(obj)
        await self.db.commit()
        return f"Component deleted: {args.component_id}"

    async def update_decision(self, project_id: str, args: UpdateDecisionArgs) -> str:
        stmt = select(ArchitectureDecision).where(
                ArchitectureDecision.id == args.decision_id,
                ArchitectureDecision.project_id == project_id,
            )
        if self.feature_id is not None:
            stmt = stmt.where(or_(ArchitectureDecision.feature_id == self.feature_id, ArchitectureDecision.feature_id.is_(None)))
        r = await self.db.execute(stmt)
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

    async def update_interface_contract(self, project_id: str, args: UpdateInterfaceContractArgs) -> str:
        stmt = select(InterfaceContract).where(
            InterfaceContract.id == args.contract_id,
            InterfaceContract.project_id == project_id,
        )
        if self.feature_id is not None:
            stmt = stmt.where(InterfaceContract.feature_id == self.feature_id)
        else:
            stmt = stmt.where(InterfaceContract.feature_id.is_(None))
        obj = (await self.db.execute(stmt)).scalar_one_or_none()
        if not obj:
            return f"Interface contract {args.contract_id} not found."
        if args.component_id is not None:
            obj.component_id = args.component_id
        if args.kind is not None:
            obj.kind = args.kind
        if args.name is not None:
            obj.name = args.name
        if args.body_md is not None:
            obj.body_md = args.body_md
        await self.db.commit()
        return f"Interface contract updated: {args.contract_id}"

    async def delete_decision(self, project_id: str, args: DeleteDecisionArgs) -> str:
        stmt = select(ArchitectureDecision).where(
                ArchitectureDecision.id == args.decision_id,
                ArchitectureDecision.project_id == project_id,
            )
        if self.feature_id is not None:
            stmt = stmt.where(or_(ArchitectureDecision.feature_id == self.feature_id, ArchitectureDecision.feature_id.is_(None)))
        r = await self.db.execute(stmt)
        obj = r.scalar_one_or_none()
        if not obj:
            return f"Decision {args.decision_id} not found."
        await self.db.delete(obj)
        await self.db.commit()
        return f"Decision deleted: {args.decision_id}"

    async def delete_interface_contract(self, project_id: str, args: DeleteInterfaceContractArgs) -> str:
        stmt = select(InterfaceContract).where(
            InterfaceContract.id == args.contract_id,
            InterfaceContract.project_id == project_id,
        )
        if self.feature_id is not None:
            stmt = stmt.where(InterfaceContract.feature_id == self.feature_id)
        else:
            stmt = stmt.where(InterfaceContract.feature_id.is_(None))
        obj = (await self.db.execute(stmt)).scalar_one_or_none()
        if not obj:
            return f"Interface contract {args.contract_id} not found."
        await self.db.delete(obj)
        await self.db.commit()
        return f"Interface contract deleted: {args.contract_id}"

    async def update_test_spec(self, project_id: str, args: UpdateTestSpecArgs) -> str:
        stmt = select(TestSpec).where(TestSpec.id == args.spec_id, TestSpec.project_id == project_id)
        if self.feature_id is not None:
            stmt = stmt.where(TestSpec.feature_id == self.feature_id)
        r = await self.db.execute(stmt)
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
        stmt = select(TestSpec).where(TestSpec.id == args.spec_id, TestSpec.project_id == project_id)
        if self.feature_id is not None:
            stmt = stmt.where(TestSpec.feature_id == self.feature_id)
        r = await self.db.execute(stmt)
        obj = r.scalar_one_or_none()
        if not obj:
            return f"Test spec {args.spec_id} not found."
        await self.db.delete(obj)
        await self.db.commit()
        return f"Test spec deleted: {args.spec_id}"

    async def update_task(self, project_id: str, args: UpdateTaskArgs) -> str:
        stmt = select(Task).where(Task.id == args.task_id, Task.project_id == project_id)
        if self.feature_id is not None:
            stmt = stmt.where(Task.feature_id == self.feature_id)
        r = await self.db.execute(stmt)
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
        stmt = select(Task).where(Task.id == args.task_id, Task.project_id == project_id)
        if self.feature_id is not None:
            stmt = stmt.where(Task.feature_id == self.feature_id)
        r = await self.db.execute(stmt)
        obj = r.scalar_one_or_none()
        if not obj:
            return f"Task {args.task_id} not found."
        await self.db.delete(obj)
        await self.db.commit()
        return f"Task deleted: {args.task_id}"

    # -----------------------------------------------------------------------
    # BA extended artifact handlers
    # -----------------------------------------------------------------------

    async def set_vision_scope(self, project_id: str, args: SetVisionScopeArgs) -> str:
        project = await self.get_project(project_id)
        if args.business_goals:
            project.business_goals = args.business_goals
        if args.success_metrics:
            project.success_metrics = args.success_metrics
        if args.in_scope:
            project.in_scope = args.in_scope
        if args.out_of_scope:
            project.out_of_scope = args.out_of_scope
        if args.target_users:
            project.target_users = args.target_users
        await self.db.commit()
        return "Vision & Scope updated."

    async def add_persona(self, project_id: str, args: AddPersonaArgs) -> str:
        existing = await self.db.execute(
            select(Persona).where(
                Persona.project_id == project_id,
                Persona.name.ilike(args.name),
            )
        )
        persona = existing.scalar_one_or_none()
        if persona:
            persona.role = args.role or persona.role
            if args.goals:
                persona.goals = args.goals
            if args.pain_points:
                persona.pain_points = args.pain_points
            await self.db.commit()
            return f"Persona updated: {persona.id}"

        persona = Persona(
            project_id=project_id,
            name=args.name,
            role=args.role,
            goals=args.goals,
            pain_points=args.pain_points,
        )
        self.db.add(persona)
        await self.db.commit()
        await self.db.refresh(persona)
        return f"Persona added: {persona.id}"

    async def add_user_flow(self, project_id: str, args: AddUserFlowArgs) -> str:
        existing = await self.db.execute(
            select(UserFlow).where(
                UserFlow.project_id == project_id,
                UserFlow.name.ilike(args.name),
            )
        )
        flow = existing.scalar_one_or_none()
        if flow:
            flow.description = args.description or flow.description
            if args.steps:
                # Replace steps on upsert
                await self.db.execute(
                    select(UserFlowStep).where(UserFlowStep.flow_id == flow.id)
                )
                r = await self.db.execute(
                    select(UserFlowStep).where(UserFlowStep.flow_id == flow.id)
                )
                for old_step in r.scalars().all():
                    await self.db.delete(old_step)
                for idx, desc in enumerate(args.steps):
                    actor, description = _parse_step(desc)
                    self.db.add(UserFlowStep(flow_id=flow.id, order_index=idx, description=description, actor=actor))
            await self.db.commit()
            return f"User flow updated: {flow.id}"

        flow = UserFlow(
            project_id=project_id,
            name=args.name,
            description=args.description,
        )
        self.db.add(flow)
        await self.db.flush()

        for idx, desc in enumerate(args.steps):
            actor, description = _parse_step(desc)
            self.db.add(UserFlowStep(flow_id=flow.id, order_index=idx, description=description, actor=actor))

        await self.db.commit()
        await self.db.refresh(flow)
        return f"User flow added: {flow.id} ({len(args.steps)} steps)"

    async def add_business_rule(self, project_id: str, args: AddBusinessRuleArgs) -> str:
        existing = await self.db.execute(
            select(BusinessRule).where(
                BusinessRule.project_id == project_id,
                BusinessRule.rule.ilike(args.rule),
            )
        )
        rule = existing.scalar_one_or_none()
        if rule:
            if args.applies_to:
                rule.applies_to = args.applies_to
            await self.db.commit()
            return f"Business rule updated: {rule.id}"

        rule = BusinessRule(
            project_id=project_id,
            rule=args.rule,
            applies_to=args.applies_to,
        )
        self.db.add(rule)
        await self.db.commit()
        await self.db.refresh(rule)
        return f"Business rule added: {rule.id}"

    async def add_data_entity(self, project_id: str, args: AddDataEntityArgs) -> str:
        existing = await self.db.execute(
            select(DataEntity).where(
                DataEntity.project_id == project_id,
                DataEntity.name.ilike(args.name),
            )
        )
        entity = existing.scalar_one_or_none()
        if entity:
            if args.attributes:
                entity.attributes = args.attributes
            if args.relationships:
                entity.relationships = args.relationships
            await self.db.commit()
            return f"Data entity updated: {entity.id}"

        entity = DataEntity(
            project_id=project_id,
            name=args.name,
            attributes=args.attributes,
            relationships=args.relationships,
        )
        self.db.add(entity)
        await self.db.commit()
        await self.db.refresh(entity)
        return f"Data entity added: {entity.id}"

    async def add_functional_requirement(self, project_id: str, args: AddFunctionalRequirementArgs) -> str:
        existing = await self.db.execute(
            select(FunctionalRequirement).where(
                FunctionalRequirement.project_id == project_id,
                FunctionalRequirement.description.ilike(args.description),
            )
        )
        fr = existing.scalar_one_or_none()
        if fr:
            if args.inputs:
                fr.inputs = args.inputs
            if args.outputs:
                fr.outputs = args.outputs
            await self.db.commit()
            return f"Functional requirement updated: {fr.id}"

        fr = FunctionalRequirement(
            project_id=project_id,
            description=args.description,
            inputs=args.inputs,
            outputs=args.outputs,
        )
        self.db.add(fr)
        await self.db.flush()

        for story_ref in args.related_user_stories:
            story_id = await self.queries.resolve_story_id(project_id, story_ref)
            if story_id:
                self.db.add(FunctionalRequirementStory(fr_id=fr.id, story_id=story_id))

        await self.db.commit()
        await self.db.refresh(fr)
        return f"Functional requirement added: {fr.id}"

    async def add_glossary_term(self, project_id: str, args: AddGlossaryTermArgs) -> str:
        project = await self.get_project(project_id)
        terms: list[dict] = list(project.terminology or [])
        for entry in terms:
            if entry.get("term", "").lower() == args.term.lower():
                entry["definition"] = args.definition
                project.terminology = terms
                await self.db.commit()
                return f"Glossary term updated: '{args.term}'"
        terms.append({"term": args.term, "definition": args.definition})
        project.terminology = terms
        await self.db.commit()
        return f"Glossary term added: '{args.term}'"

    async def set_llm_interaction_model(self, project_id: str, args: SetLlmInteractionModelArgs) -> str:
        project = await self.get_project(project_id)
        project.llm_interaction_model = {
            "llm_role": args.llm_role,
            "interaction_pattern": args.interaction_pattern,
            "input_format": args.input_format,
            "output_format": args.output_format,
            "memory_strategy": args.memory_strategy,
            "error_handling": args.error_handling,
        }
        await self.db.commit()
        return "LLM interaction model set."

    async def answer_clarification_point(self, project_id: str, args: AnswerClarificationPointArgs) -> str:
        if args.point_id not in CATALOG_BY_ID:
            return f"Unknown clarification point: {args.point_id}"

        stmt = select(ClarificationPoint).where(
            ClarificationPoint.project_id == project_id,
            ClarificationPoint.point_id == args.point_id,
        )
        if self.feature_id is not None:
            stmt = stmt.where(ClarificationPoint.feature_id == self.feature_id)
        else:
            stmt = stmt.where(ClarificationPoint.feature_id.is_(None))
        r = await self.db.execute(stmt)
        cp = r.scalar_one_or_none()
        if cp:
            cp.status = args.status
            cp.answer = args.answer
        else:
            cp = ClarificationPoint(
                project_id=project_id,
                feature_id=self.feature_id,
                point_id=args.point_id,
                status=args.status,
                answer=args.answer,
            )
            self.db.add(cp)
        await self.db.commit()
        return f"Clarification point '{args.point_id}' marked as {args.status}."

    async def _next_roadmap_ordinal(self, project_id: str) -> int:
        items = await self.queries.get_all_roadmap_items(project_id)
        if not items:
            return 1
        return max(item.ordinal for item in items) + 1

    async def _normalize_roadmap_ordinals(self, project_id: str) -> None:
        items = await self.queries.get_all_roadmap_items(project_id)
        for index, item in enumerate(items, start=1):
            item.ordinal = index
        await self.db.flush()

    async def _link_epic_to_roadmap_items(self, project_id: str, epic: Epic) -> None:
        roadmap_items = await self.queries.get_all_roadmap_items(project_id)
        epic_title = (epic.title or "").strip()
        if not epic_title:
            return

        for item in roadmap_items:
            if item.linked_epic_id:
                continue
            if self._roadmap_matches_epic(item.title, item.description, epic_title):
                item.linked_epic_id = epic.id
        await self.db.flush()

    async def _link_roadmap_items_to_existing_epics(self, project_id: str) -> None:
        epics = await self.queries.get_all_epics(project_id)
        for epic in epics:
            await self._link_epic_to_roadmap_items(project_id, epic)

    def _roadmap_matches_epic(self, title: str, description: str, epic_title: str) -> bool:
        haystack = f"{title} {description}".strip().lower()
        needle = epic_title.lower()
        if not haystack or not needle:
            return False
        if needle in haystack or haystack in needle:
            return True
        return max(similarity(title, epic_title), similarity(description, epic_title)) >= 0.45

    def _draft_mission_statement(self, project) -> str:
        if project.description:
            first = project.description.strip().splitlines()[0].strip()
            if first.endswith("."):
                return first
            return f"{first}."
        users = self._draft_target_users(project)
        return f"Build {project.name} for {users.lower()} to solve a clear planning workflow."

    def _draft_target_users(self, project) -> str:
        if project.target_users:
            return ", ".join(project.target_users)
        return "teams planning and shipping software"

    def _draft_roadmap_items(self, project) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        for goal in list(project.business_goals or [])[:3]:
            title = goal[:80].strip() or "Deliver core user value"
            items.append({
                "title": title,
                "description": f"Ship the first slice of '{goal}' and validate that it solves the project's main problem.",
            })

        if not items and project.description:
            items.append({
                "title": "Validate the core workflow",
                "description": f"Turn the current problem statement into a usable v1 flow: {project.description[:160]}",
            })

        if not items:
            items.append({
                "title": "Define the v1 product slice",
                "description": "Capture the smallest set of capabilities needed for the first valuable release.",
            })

        items.append({
            "title": "Operationalize feedback loops",
            "description": "Add the feedback, measurement, and iteration steps needed to improve the product after launch.",
        })
        items.append({
            "title": "Scale beyond the MVP",
            "description": "Prepare the next wave of product work once the MVP proves the mission and user demand.",
        })
        deduped: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in items:
            key = item["title"].lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped[:3]

    def _draft_tech_stack_entries(self, project) -> list[dict[str, str]]:
        base_rationale = (
            "Draft founder placeholder inferred from the current project state; "
            "review and replace with a concrete stack once architecture decisions settle."
        )
        return [
            {
                "layer": "frontend",
                "choice": "Web UI stack to be confirmed",
                "rationale": base_rationale,
            },
            {
                "layer": "backend",
                "choice": "Application service layer to be confirmed",
                "rationale": base_rationale,
            },
            {
                "layer": "storage",
                "choice": "Primary data store to be confirmed",
                "rationale": base_rationale,
            },
        ]
