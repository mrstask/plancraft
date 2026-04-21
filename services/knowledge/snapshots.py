"""Snapshot builder for LLM and UI state."""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from config import settings
from models.db import (
    ArchitectureDecision,
    BusinessRule,
    ClarificationPoint,
    Component,
    DataEntity,
    Epic,
    Feature,
    FunctionalRequirement,
    InterfaceContract,
    Persona,
    ProjectMission,
    ProjectRoadmapItem,
    RoleExecutionTrace,
    Task,
    TechStackEntry,
    TestSpec,
    UserFlow,
    UserStory,
)
from models.domain import (
    ComponentSnapshot,
    ContractSnapshot,
    DecisionSnapshot,
    FlowSnapshot,
    KnowledgeSnapshot,
    PersonaSnapshot,
    RoadmapItemSnapshot,
    StorySnapshot,
    TechStackSnapshot,
)
from roles.ba_clarifications import REQUIRED_IDS
from .common import KnowledgeBase


class SnapshotBuilder(KnowledgeBase):
    async def get_snapshot(self, project_id: str) -> KnowledgeSnapshot:
        project = await self.get_project(project_id)
        feature = None
        if self.feature_id:
            feature_result = await self.db.execute(
                select(Feature).where(Feature.project_id == project_id, Feature.id == self.feature_id)
            )
            feature = feature_result.scalar_one_or_none()

        story_stmt = select(UserStory).where(UserStory.project_id == project_id)
        if self.feature_id:
            story_stmt = story_stmt.where(UserStory.feature_id == self.feature_id)
        story_result = await self.db.execute(story_stmt.order_by(UserStory.created_at.desc()).limit(5))
        stories = list(reversed(story_result.scalars().all()))

        comp_result = await self.db.execute(
            select(Component)
            .where(Component.project_id == project_id)
            .order_by(Component.created_at.desc())
            .limit(5)
        )
        components = list(reversed(comp_result.scalars().all()))

        dec_stmt = select(ArchitectureDecision).where(ArchitectureDecision.project_id == project_id)
        if self.feature_id:
            dec_stmt = dec_stmt.where(
                or_(ArchitectureDecision.feature_id == self.feature_id, ArchitectureDecision.feature_id.is_(None))
            )
        dec_result = await self.db.execute(
            dec_stmt.order_by(ArchitectureDecision.created_at.desc()).limit(5)
        )
        decisions = list(reversed(dec_result.scalars().all()))

        contract_stmt = (
            select(InterfaceContract)
            .options(selectinload(InterfaceContract.component))
            .where(InterfaceContract.project_id == project_id)
        )
        if self.feature_id:
            contract_stmt = contract_stmt.where(InterfaceContract.feature_id == self.feature_id)
        else:
            contract_stmt = contract_stmt.where(InterfaceContract.feature_id.is_(None))
        contract_result = await self.db.execute(
            contract_stmt.order_by(InterfaceContract.updated_at.desc()).limit(5)
        )
        contracts = list(reversed(contract_result.scalars().all()))

        persona_result = await self.db.execute(
            select(Persona)
            .where(Persona.project_id == project_id)
            .order_by(Persona.created_at.desc())
            .limit(5)
        )
        personas = list(reversed(persona_result.scalars().all()))

        flow_result = await self.db.execute(
            select(UserFlow)
            .options(selectinload(UserFlow.steps))
            .where(UserFlow.project_id == project_id)
            .order_by(UserFlow.created_at.desc())
            .limit(5)
        )
        flows = list(reversed(flow_result.scalars().all()))

        mission = await self.db.execute(
            select(ProjectMission).where(ProjectMission.project_id == project_id)
        )
        mission = mission.scalar_one_or_none()

        roadmap_result = await self.db.execute(
            select(ProjectRoadmapItem)
            .where(ProjectRoadmapItem.project_id == project_id)
            .order_by(ProjectRoadmapItem.ordinal.desc(), ProjectRoadmapItem.updated_at.desc())
            .limit(5)
        )
        roadmap_items = list(reversed(roadmap_result.scalars().all()))

        tech_result = await self.db.execute(
            select(TechStackEntry)
            .where(TechStackEntry.project_id == project_id)
            .order_by(TechStackEntry.updated_at.desc())
            .limit(5)
        )
        tech_entries = list(reversed(tech_result.scalars().all()))

        pending_ids = await self._get_pending_clarification_ids(project_id)
        counts = await self._get_counts(project_id)
        founder_evaluator_passed = await self._founder_evaluator_passed(project_id)
        prior_features = await self._get_prior_features(project_id)

        return KnowledgeSnapshot(
            project_name=project.name,
            mission_statement=mission.statement if mission else None,
            mission_target_users=mission.target_users if mission else None,
            mission_problem=mission.problem if mission else None,
            problem_statement=project.description,
            founder_evaluator_passed=founder_evaluator_passed,
            mvp_story_count=len(project.mvp_story_ids or []),
            mvp_rationale=project.mvp_rationale,
            vision_scope_set=bool(project.business_goals or project.in_scope),
            pending_clarification_ids=pending_ids,
            feature_id=feature.id if feature else None,
            feature_title=feature.title if feature else None,
            feature_status=feature.status if feature else None,
            feature_ordinal=feature.ordinal if feature else None,
            prior_features=prior_features,
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
            recent_contracts=[
                ContractSnapshot(
                    id=contract.id,
                    name=contract.name,
                    kind=contract.kind,
                    component_name=contract.component.name if contract.component else "Unknown component",
                )
                for contract in contracts
            ],
            recent_personas=[
                PersonaSnapshot(name=p.name, role=p.role)
                for p in personas
            ],
            recent_flows=[
                FlowSnapshot(name=f.name, step_count=len(f.steps))
                for f in flows
            ],
            recent_roadmap_items=[
                RoadmapItemSnapshot(title=item.title, mvp=bool(item.mvp))
                for item in roadmap_items
            ],
            recent_tech_stack_entries=[
                TechStackSnapshot(layer=entry.layer, choice=entry.choice)
                for entry in tech_entries
            ],
        )

    async def _get_pending_clarification_ids(self, project_id: str) -> list[str]:
        r = await self.db.execute(
            select(ClarificationPoint).where(
                ClarificationPoint.project_id == project_id,
                ClarificationPoint.feature_id == self.feature_id if self.feature_id else ClarificationPoint.feature_id.is_(None),
                ClarificationPoint.status.in_(["answered", "skipped"]),
            )
        )
        resolved = {cp.point_id for cp in r.scalars().all()}
        return [pid for pid in REQUIRED_IDS if pid not in resolved]

    async def _get_counts(self, project_id: str) -> dict:
        async def count(model):
            stmt = select(func.count()).where(model.project_id == project_id)
            if self.feature_id and hasattr(model, "feature_id"):
                stmt = stmt.where(model.feature_id == self.feature_id)
            r = await self.db.execute(stmt)
            return r.scalar()

        data = {
            "story_count": await count(UserStory),
            "epic_count": await count(Epic),
            "roadmap_item_count": await count(ProjectRoadmapItem),
            "tech_stack_count": await count(TechStackEntry),
            "component_count": await count(Component),
            "decision_count": await count(ArchitectureDecision),
            "contract_count": await count(InterfaceContract),
            "test_spec_count": await count(TestSpec),
            "task_count": await count(Task),
            "persona_count": await count(Persona),
            "flow_count": await count(UserFlow),
            "business_rule_count": await count(BusinessRule),
            "entity_count": await count(DataEntity),
            "fr_count": await count(FunctionalRequirement),
        }
        if self.feature_id:
            data["feature_story_count"] = data["story_count"]
            data["feature_test_spec_count"] = data["test_spec_count"]
            data["feature_task_count"] = data["task_count"]
            data["feature_decision_count"] = await self._count_feature_decisions(project_id)
        return data

    async def _count_feature_decisions(self, project_id: str) -> int:
        r = await self.db.execute(
            select(func.count()).where(
                ArchitectureDecision.project_id == project_id,
                ArchitectureDecision.feature_id == self.feature_id,
            )
        )
        return r.scalar() or 0

    async def _get_prior_features(self, project_id: str):
        if not self.feature_id:
            return []
        r = await self.db.execute(
            select(Feature)
            .where(Feature.project_id == project_id, Feature.id != self.feature_id)
            .order_by(Feature.ordinal.asc())
        )
        rows = r.scalars().all()
        from models.domain import FeatureSummarySnapshot

        return [
            FeatureSummarySnapshot(
                id=feature.id,
                ordinal=feature.ordinal,
                title=feature.title,
                status=feature.status,
                summary=(feature.description or "").strip()[:120] or None,
            )
            for feature in rows
        ]

    async def _founder_evaluator_passed(self, project_id: str) -> bool:
        r = await self.db.execute(
            select(RoleExecutionTrace)
            .where(
                RoleExecutionTrace.project_id == project_id,
                RoleExecutionTrace.role == "founder",
                RoleExecutionTrace.final.is_(True),
            )
            .order_by(RoleExecutionTrace.created_at.desc())
            .limit(1)
        )
        trace = r.scalar_one_or_none()
        return bool(trace and (trace.evaluator_score or 0.0) >= settings.evaluator_score_threshold)
