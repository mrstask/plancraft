"""Read-side queries for knowledge artifacts."""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from models.db import (
    ArchitectureDecision,
    BusinessRule,
    ClarificationPoint,
    Component,
    Constraint,
    DataEntity,
    Epic,
    Feature,
    FunctionalRequirement,
    InterfaceContract,
    Persona,
    ProjectMission,
    ProjectRoadmapItem,
    Task,
    TechStackEntry,
    TestSpec,
    UserFlow,
    UserStory,
)
from .common import KnowledgeBase


class ArtifactQueries(KnowledgeBase):
    def _feature_exact_filter(self, model, feature_id: str | None = None):
        scoped_feature_id = self.feature_id if feature_id is None else feature_id
        if scoped_feature_id is None:
            return None
        return model.feature_id == scoped_feature_id

    def _feature_plus_cross_cutting_filter(self, model, feature_id: str | None = None):
        scoped_feature_id = self.feature_id if feature_id is None else feature_id
        if scoped_feature_id is None:
            return None
        return or_(model.feature_id == scoped_feature_id, model.feature_id.is_(None))

    def _clarification_scope_filter(self, feature_id: str | None = None):
        scoped_feature_id = self.feature_id if feature_id is None else feature_id
        if scoped_feature_id is None:
            return ClarificationPoint.feature_id.is_(None)
        return ClarificationPoint.feature_id == scoped_feature_id

    async def get_project_mission(self, project_id: str):
        r = await self.db.execute(
            select(ProjectMission).where(ProjectMission.project_id == project_id)
        )
        return r.scalar_one_or_none()

    async def get_all_roadmap_items(self, project_id: str):
        r = await self.db.execute(
            select(ProjectRoadmapItem)
            .where(ProjectRoadmapItem.project_id == project_id)
            .order_by(ProjectRoadmapItem.ordinal.asc(), ProjectRoadmapItem.updated_at.asc())
        )
        return r.scalars().all()

    async def get_roadmap_item(self, project_id: str, item_id: str):
        r = await self.db.execute(
            select(ProjectRoadmapItem).where(
                ProjectRoadmapItem.project_id == project_id,
                ProjectRoadmapItem.id == item_id,
            )
        )
        return r.scalar_one_or_none()

    async def get_all_tech_stack_entries(self, project_id: str):
        r = await self.db.execute(
            select(TechStackEntry)
            .where(TechStackEntry.project_id == project_id)
            .order_by(TechStackEntry.updated_at.asc())
        )
        return r.scalars().all()

    async def get_tech_stack_entry(self, project_id: str, entry_id: str):
        r = await self.db.execute(
            select(TechStackEntry).where(
                TechStackEntry.project_id == project_id,
                TechStackEntry.id == entry_id,
            )
        )
        return r.scalar_one_or_none()

    async def get_all_epics(self, project_id: str):
        r = await self.db.execute(
            select(Epic).where(Epic.project_id == project_id).order_by(Epic.created_at)
        )
        return r.scalars().all()

    async def get_all_stories(self, project_id: str):
        stmt = (
            select(UserStory)
            .options(selectinload(UserStory.acceptance_criteria), selectinload(UserStory.epic))
            .where(UserStory.project_id == project_id)
            .order_by(UserStory.created_at)
        )
        feature_filter = self._feature_exact_filter(UserStory)
        if feature_filter is not None:
            stmt = stmt.where(feature_filter)
        r = await self.db.execute(stmt)
        return r.scalars().all()

    async def get_all_components(self, project_id: str):
        r = await self.db.execute(
            select(Component).where(Component.project_id == project_id).order_by(Component.created_at)
        )
        return r.scalars().all()

    async def get_all_decisions(self, project_id: str):
        stmt = (
            select(ArchitectureDecision)
            .where(ArchitectureDecision.project_id == project_id)
            .order_by(ArchitectureDecision.created_at)
        )
        feature_filter = self._feature_plus_cross_cutting_filter(ArchitectureDecision)
        if feature_filter is not None:
            stmt = stmt.where(feature_filter)
        r = await self.db.execute(stmt)
        return r.scalars().all()

    async def get_all_interface_contracts(self, project_id: str):
        stmt = (
            select(InterfaceContract)
            .options(selectinload(InterfaceContract.component))
            .where(InterfaceContract.project_id == project_id)
            .order_by(InterfaceContract.updated_at.asc(), InterfaceContract.name.asc())
        )
        feature_filter = self._feature_exact_filter(InterfaceContract)
        if feature_filter is not None:
            stmt = stmt.where(feature_filter)
        r = await self.db.execute(stmt)
        return r.scalars().all()

    async def get_all_constraints(self, project_id: str):
        r = await self.db.execute(
            select(Constraint).where(Constraint.project_id == project_id).order_by(Constraint.created_at)
        )
        return r.scalars().all()

    async def get_all_test_specs(self, project_id: str):
        stmt = select(TestSpec).where(TestSpec.project_id == project_id).order_by(TestSpec.created_at)
        feature_filter = self._feature_exact_filter(TestSpec)
        if feature_filter is not None:
            stmt = stmt.where(feature_filter)
        r = await self.db.execute(stmt)
        return r.scalars().all()

    async def get_all_tasks(self, project_id: str):
        stmt = select(Task).where(Task.project_id == project_id).order_by(Task.created_at)
        feature_filter = self._feature_exact_filter(Task)
        if feature_filter is not None:
            stmt = stmt.where(feature_filter)
        r = await self.db.execute(stmt)
        return r.scalars().all()

    async def get_story(self, project_id: str, story_id: str):
        stmt = (
            select(UserStory)
            .options(selectinload(UserStory.acceptance_criteria), selectinload(UserStory.epic))
            .where(UserStory.project_id == project_id, UserStory.id == story_id)
        )
        feature_filter = self._feature_exact_filter(UserStory)
        if feature_filter is not None:
            stmt = stmt.where(feature_filter)
        r = await self.db.execute(stmt)
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
        stmt = select(ArchitectureDecision).where(
                ArchitectureDecision.project_id == project_id,
                ArchitectureDecision.id == decision_id,
            )
        feature_filter = self._feature_plus_cross_cutting_filter(ArchitectureDecision)
        if feature_filter is not None:
            stmt = stmt.where(feature_filter)
        r = await self.db.execute(stmt)
        return r.scalar_one_or_none()

    async def get_interface_contract(self, project_id: str, contract_id: str):
        stmt = (
            select(InterfaceContract)
            .options(selectinload(InterfaceContract.component))
            .where(InterfaceContract.project_id == project_id, InterfaceContract.id == contract_id)
        )
        feature_filter = self._feature_exact_filter(InterfaceContract)
        if feature_filter is not None:
            stmt = stmt.where(feature_filter)
        r = await self.db.execute(stmt)
        return r.scalar_one_or_none()

    async def get_test_spec(self, project_id: str, spec_id: str):
        stmt = select(TestSpec).where(TestSpec.project_id == project_id, TestSpec.id == spec_id)
        feature_filter = self._feature_exact_filter(TestSpec)
        if feature_filter is not None:
            stmt = stmt.where(feature_filter)
        r = await self.db.execute(stmt)
        return r.scalar_one_or_none()

    async def get_task(self, project_id: str, task_id: str):
        stmt = select(Task).where(Task.project_id == project_id, Task.id == task_id)
        feature_filter = self._feature_exact_filter(Task)
        if feature_filter is not None:
            stmt = stmt.where(feature_filter)
        r = await self.db.execute(stmt)
        return r.scalar_one_or_none()

    async def resolve_story_id(self, project_id: str, story_ref: str) -> str | None:
        stmt = select(UserStory.id).where(
                UserStory.project_id == project_id,
                UserStory.id.ilike(f"{story_ref}%"),
            )
        feature_filter = self._feature_exact_filter(UserStory)
        if feature_filter is not None:
            stmt = stmt.where(feature_filter)
        r = await self.db.execute(stmt)
        rows = r.scalars().all()
        # Exact match or unique prefix match — reject ambiguous short prefixes
        return rows[0] if len(rows) == 1 else None

    async def get_all_features(self, project_id: str):
        r = await self.db.execute(
            select(Feature).where(Feature.project_id == project_id).order_by(Feature.ordinal.asc(), Feature.created_at.asc())
        )
        return r.scalars().all()

    async def get_feature(self, project_id: str, feature_id: str):
        r = await self.db.execute(
            select(Feature).where(Feature.project_id == project_id, Feature.id == feature_id)
        )
        return r.scalar_one_or_none()

    # -----------------------------------------------------------------------
    # BA extended artifact queries
    # -----------------------------------------------------------------------

    async def get_all_personas(self, project_id: str):
        r = await self.db.execute(
            select(Persona).where(Persona.project_id == project_id).order_by(Persona.created_at)
        )
        return r.scalars().all()

    async def get_all_user_flows(self, project_id: str):
        r = await self.db.execute(
            select(UserFlow)
            .options(selectinload(UserFlow.steps))
            .where(UserFlow.project_id == project_id)
            .order_by(UserFlow.created_at)
        )
        return r.scalars().all()

    async def get_all_business_rules(self, project_id: str):
        r = await self.db.execute(
            select(BusinessRule)
            .where(BusinessRule.project_id == project_id)
            .order_by(BusinessRule.created_at)
        )
        return r.scalars().all()

    async def get_all_data_entities(self, project_id: str):
        r = await self.db.execute(
            select(DataEntity)
            .where(DataEntity.project_id == project_id)
            .order_by(DataEntity.created_at)
        )
        return r.scalars().all()

    async def get_all_functional_requirements(self, project_id: str):
        r = await self.db.execute(
            select(FunctionalRequirement)
            .options(selectinload(FunctionalRequirement.story_links))
            .where(FunctionalRequirement.project_id == project_id)
            .order_by(FunctionalRequirement.created_at)
        )
        return r.scalars().all()

    async def get_all_clarification_points(self, project_id: str):
        r = await self.db.execute(
            select(ClarificationPoint)
            .where(
                ClarificationPoint.project_id == project_id,
                self._clarification_scope_filter(),
            )
            .order_by(ClarificationPoint.updated_at.asc(), ClarificationPoint.created_at.asc())
        )
        return r.scalars().all()

    async def get_clarification_point(self, project_id: str, clarification_id: str):
        r = await self.db.execute(
            select(ClarificationPoint).where(
                ClarificationPoint.project_id == project_id,
                ClarificationPoint.id == clarification_id,
                self._clarification_scope_filter(),
            )
        )
        return r.scalar_one_or_none()

    async def get_pending_clarification_ids(self, project_id: str) -> list[str]:
        """Return catalog IDs of required points that are not yet answered/skipped."""
        from roles.ba_clarifications import REQUIRED_IDS
        r = await self.db.execute(
            select(ClarificationPoint).where(
                ClarificationPoint.project_id == project_id,
                self._clarification_scope_filter(),
                ClarificationPoint.status.in_(["answered", "skipped"]),
            )
        )
        resolved = {cp.point_id for cp in r.scalars().all()}
        return [pid for pid in REQUIRED_IDS if pid not in resolved]
