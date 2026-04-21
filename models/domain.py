"""Pydantic domain models — the knowledge model projected from the DB.

These are used for:
  - Passing structured data to Claude (knowledge snapshot in system prompt)
  - Serializing the knowledge model to JSON for export
  - Validating Claude tool call arguments
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Snapshot — what Claude sees as project context
# ---------------------------------------------------------------------------

class KnowledgeSnapshot(BaseModel):
    """Compact representation of the current project state injected into Claude's context."""
    project_name: str
    mission_statement: str | None = None
    mission_target_users: str | None = None
    mission_problem: str | None = None
    problem_statement: str | None = None
    founder_evaluator_passed: bool = False
    roadmap_item_count: int = 0
    tech_stack_count: int = 0
    mvp_story_count: int = 0
    mvp_rationale: str | None = None
    story_count: int = 0
    epic_count: int = 0
    component_count: int = 0
    decision_count: int = 0
    contract_count: int = 0
    test_spec_count: int = 0
    task_count: int = 0
    # BA extended artifact counts
    persona_count: int = 0
    flow_count: int = 0
    business_rule_count: int = 0
    entity_count: int = 0
    fr_count: int = 0
    pending_clarification_ids: list[str] = Field(default_factory=list)
    # Vision/scope populated flag
    vision_scope_set: bool = False

    # Recent items (last 5 of each) for Claude's context
    recent_stories: list[StorySnapshot] = Field(default_factory=list)
    recent_components: list[ComponentSnapshot] = Field(default_factory=list)
    recent_decisions: list[DecisionSnapshot] = Field(default_factory=list)
    recent_contracts: list["ContractSnapshot"] = Field(default_factory=list)
    recent_personas: list["PersonaSnapshot"] = Field(default_factory=list)
    recent_flows: list["FlowSnapshot"] = Field(default_factory=list)
    recent_roadmap_items: list["RoadmapItemSnapshot"] = Field(default_factory=list)
    recent_tech_stack_entries: list["TechStackSnapshot"] = Field(default_factory=list)
    feature_id: str | None = None
    feature_title: str | None = None
    feature_status: str | None = None
    feature_ordinal: int | None = None
    feature_story_count: int = 0
    feature_test_spec_count: int = 0
    feature_task_count: int = 0
    feature_decision_count: int = 0
    prior_features: list["FeatureSummarySnapshot"] = Field(default_factory=list)

    def to_context_string(self) -> str:
        lines = [f"Project: {self.project_name}"]
        if self.mission_statement:
            lines.append(f"Mission: {self.mission_statement}")
        if self.mission_target_users:
            lines.append(f"Mission target users: {self.mission_target_users}")
        if self.mission_problem:
            lines.append(f"Mission problem: {self.mission_problem}")
        if self.problem_statement:
            lines.append(f"Problem: {self.problem_statement}")
        if self.feature_title:
            lines.append(
                f"Current feature: {self.feature_ordinal or '?':03d} {self.feature_title} "
                f"({self.feature_status or 'drafting'})"
            )
        lines.append(
            f"Founder artifacts: {self.roadmap_item_count} roadmap items, "
            f"{self.tech_stack_count} tech-stack entr{'y' if self.tech_stack_count == 1 else 'ies'}"
        )
        lines.append(
            f"Founder evaluator: {'passed' if self.founder_evaluator_passed else 'pending'}"
        )
        lines.append(
            f"Captured so far: {self.story_count} stories, {self.epic_count} epics, "
            f"{self.component_count} components, {self.decision_count} decisions, "
            f"{self.contract_count} contracts, "
            f"{self.test_spec_count} test specs, {self.task_count} tasks"
        )
        lines.append(
            f"BA artifacts: {self.persona_count} personas, {self.flow_count} flows, "
            f"{self.business_rule_count} business rules, {self.entity_count} data entities, "
            f"{self.fr_count} functional requirements"
        )
        if self.vision_scope_set:
            lines.append("Vision & Scope: populated")
        if self.pending_clarification_ids:
            lines.append(f"Pending clarifications: {', '.join(self.pending_clarification_ids)}")
        if self.mvp_story_count:
            lines.append(
                f"MVP scope selected: {self.mvp_story_count} stor"
                f"{'y' if self.mvp_story_count == 1 else 'ies'}"
            )
            if self.mvp_rationale:
                lines.append(f"MVP rationale: {self.mvp_rationale}")
        if self.recent_stories:
            lines.append("\nRecent stories:")
            for s in self.recent_stories:
                lines.append(f"  - [{s.id}] As a {s.as_a}, I want {s.i_want}")
        if self.recent_personas:
            lines.append("\nPersonas defined:")
            for p in self.recent_personas:
                lines.append(f"  - {p.name} ({p.role})")
        if self.recent_flows:
            lines.append("\nUser flows defined:")
            for f in self.recent_flows:
                lines.append(f"  - {f.name} ({f.step_count} steps)")
        if self.recent_roadmap_items:
            lines.append("\nRoadmap items:")
            for item in self.recent_roadmap_items:
                prefix = "[MVP] " if item.mvp else ""
                lines.append(f"  - {prefix}{item.title}")
        if self.recent_tech_stack_entries:
            lines.append("\nTech stack:")
            for entry in self.recent_tech_stack_entries:
                lines.append(f"  - {entry.layer}: {entry.choice}")
        if self.recent_components:
            lines.append("\nComponents defined:")
            for c in self.recent_components:
                lines.append(f"  - [{c.id}] {c.name}: {c.responsibility}")
        if self.recent_decisions:
            lines.append(
                f"\nARCHITECTURE DECISIONS ALREADY RECORDED ({len(self.recent_decisions)}) "
                "— do NOT record a new decision if it is similar to any of these:"
            )
            for d in self.recent_decisions:
                lines.append(f"  - [{d.id}] {d.title}: {d.decision}")
        if self.recent_contracts:
            lines.append(f"\nINTERFACE CONTRACTS ALREADY RECORDED ({len(self.recent_contracts)})")
            for contract in self.recent_contracts:
                lines.append(
                    f"  - [{contract.id}] {contract.name} ({contract.kind}) on {contract.component_name}"
                )
        if self.prior_features:
            lines.append("\nPrior features:")
            for feature in self.prior_features:
                lines.append(
                    f"  - {feature.ordinal:03d} {feature.title} [{feature.status}]"
                    + (f": {feature.summary}" if feature.summary else "")
                )
        return "\n".join(lines)


class StorySnapshot(BaseModel):
    id: str
    as_a: str
    i_want: str
    priority: str


class ComponentSnapshot(BaseModel):
    id: str
    name: str
    responsibility: str


class DecisionSnapshot(BaseModel):
    id: str
    title: str
    decision: str


class ContractSnapshot(BaseModel):
    id: str
    name: str
    kind: str
    component_name: str


class PersonaSnapshot(BaseModel):
    name: str
    role: str


class FlowSnapshot(BaseModel):
    name: str
    step_count: int


class RoadmapItemSnapshot(BaseModel):
    title: str
    mvp: bool


class TechStackSnapshot(BaseModel):
    layer: str
    choice: str


class FeatureSummarySnapshot(BaseModel):
    id: str
    ordinal: int
    title: str
    status: str
    summary: str | None = None


# ---------------------------------------------------------------------------
# Tool call argument models (validated when Claude calls a knowledge tool)
# ---------------------------------------------------------------------------

def _coerce_criteria(v: object) -> object:
    """Allow a bare string where a list[str] is expected.

    The LLM sometimes passes a single acceptance criterion as a plain string
    or a newline-delimited blob instead of a JSON array. Normalize both to
    list[str] so Pydantic validation succeeds.
    """
    if v is None or isinstance(v, list):
        return v
    if isinstance(v, str):
        parts = [line.strip(" -•*\t") for line in v.splitlines() if line.strip()]
        return parts if len(parts) > 1 else [v.strip()]
    return v


class AddUserStoryArgs(BaseModel):
    as_a: str = Field(description="The role/persona (e.g. 'logged-in user')")
    i_want: str = Field(description="The action or feature desired")
    so_that: str = Field(description="The benefit or goal")
    acceptance_criteria: list[str] = Field(default_factory=list)
    priority: Literal["must", "should", "could", "wont"] = "should"
    epic_id: str | None = Field(None, description="ID of an existing epic to attach to")

    @field_validator("acceptance_criteria", mode="before")
    @classmethod
    def _ac_coerce(cls, v: object) -> object:
        return _coerce_criteria(v) or []


class UpdateUserStoryArgs(BaseModel):
    story_id: str
    as_a: str | None = None
    i_want: str | None = None
    so_that: str | None = None
    acceptance_criteria: list[str] | None = None
    priority: Literal["must", "should", "could", "wont"] | None = None

    @field_validator("acceptance_criteria", mode="before")
    @classmethod
    def _ac_coerce(cls, v: object) -> object:
        return _coerce_criteria(v)


class AddEpicArgs(BaseModel):
    title: str
    description: str = ""


class AddFeatureArgs(BaseModel):
    title: str
    description: str = ""
    roadmap_item_id: str | None = None


class UpdateFeatureArgs(BaseModel):
    feature_id: str
    title: str | None = None
    description: str | None = None
    status: Literal["drafting", "ready", "in_progress", "done", "archived"] | None = None
    roadmap_item_id: str | None = None


class RecordConstraintArgs(BaseModel):
    type: Literal["technical", "business", "time"]
    description: str

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, v: object) -> str:
        lowered = str(v).lower().replace("_", " ").replace("/", " ").strip()
        if any(kw in lowered for kw in ("tech", "security", "architect", "language", "framework", "platform", "system", "infrastructure")):
            return "technical"
        if any(kw in lowered for kw in ("business", "legal", "compliance", "regulatory", "market")):
            return "business"
        if any(kw in lowered for kw in ("time", "deadline", "schedule", "sprint", "budget", "resource")):
            return "time"
        return "technical"


class AddComponentArgs(BaseModel):
    name: str
    responsibility: str
    component_type: str | None = None
    file_paths: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(
        default_factory=list,
        description="List of component IDs this component depends on"
    )


class RecordDecisionArgs(BaseModel):
    title: str
    context: str = ""
    decision: str
    consequences_positive: list[str] = Field(default_factory=list)
    consequences_negative: list[str] = Field(default_factory=list)


class AddInterfaceContractArgs(BaseModel):
    component_id: str
    kind: Literal["rest", "graphql", "event", "function", "cli"] = "rest"
    name: str
    body_md: str = Field(description="Full markdown body with shape, examples, and errors.")


class AddTestSpecArgs(BaseModel):
    description: str
    test_type: Literal["unit", "integration", "e2e"] = "unit"
    story_id: str | None = None
    component_id: str | None = None
    given_context: str = ""
    when_action: str = ""
    then_expectation: str = ""


class ProposeTaskArgs(BaseModel):
    title: str
    description: str = ""
    complexity: Literal["trivial", "small", "medium", "large"] = "medium"
    file_paths: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(
        default_factory=list,
        description="List of task IDs this task depends on"
    )
    story_ids: list[str] = Field(default_factory=list)
    test_spec_ids: list[str] = Field(default_factory=list)


class SetProblemStatementArgs(BaseModel):
    statement: str = Field(description="Concise problem statement (2-4 sentences)")


class SetMvpScopeArgs(BaseModel):
    story_ids: list[str] = Field(description="Story IDs included in the MVP")
    rationale: str = ""


# ---------------------------------------------------------------------------
# Founder artifact arg models
# ---------------------------------------------------------------------------

class SetProjectMissionArgs(BaseModel):
    statement: str = Field(description="Short mission statement, max two sentences")
    target_users: str = Field(description="Who the product serves")
    problem: str = Field(description="What painful problem the product solves")


class AddRoadmapItemArgs(BaseModel):
    title: str = Field(description="Roadmap item title")
    description: str = Field(description="Short description of the outcome")
    ordinal: int | None = Field(default=None, description="Display order, starting at 1")
    mvp: bool = False
    linked_epic_id: str | None = None


class UpdateRoadmapItemArgs(BaseModel):
    item_id: str
    title: str | None = None
    description: str | None = None
    ordinal: int | None = None
    mvp: bool | None = None
    linked_epic_id: str | None = None


class AddTechStackEntryArgs(BaseModel):
    layer: str = Field(description="Layer such as frontend, backend, storage, infra")
    choice: str = Field(description="Selected tool or technology")
    rationale: str = Field(description="Why this choice fits the project")


class UpdateTechStackEntryArgs(BaseModel):
    entry_id: str
    layer: str | None = None
    choice: str | None = None
    rationale: str | None = None


# ---------------------------------------------------------------------------
# BA extended artifact arg models
# ---------------------------------------------------------------------------

class SetVisionScopeArgs(BaseModel):
    business_goals: list[str] = Field(default_factory=list)
    success_metrics: list[str] = Field(default_factory=list)
    in_scope: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    target_users: list[str] = Field(default_factory=list)


class AddPersonaArgs(BaseModel):
    name: str = Field(description="Short identifier for this persona, e.g. 'Power User'")
    role: str = Field(description="Job title or role in context of the system")
    goals: list[str] = Field(default_factory=list)
    pain_points: list[str] = Field(default_factory=list)


class AddUserFlowArgs(BaseModel):
    name: str = Field(description="Flow name, e.g. 'Create project'")
    description: str = ""
    steps: list[str] = Field(
        default_factory=list,
        description="Ordered list of step descriptions; actor prefix optional e.g. 'User: clicks Submit'"
    )


class AddBusinessRuleArgs(BaseModel):
    rule: str = Field(description="The business rule statement")
    applies_to: list[str] = Field(
        default_factory=list,
        description="Feature names, story IDs, or entity names this rule constrains"
    )


class AddDataEntityArgs(BaseModel):
    name: str = Field(description="Entity name, e.g. 'Project'")
    attributes: list[str] = Field(default_factory=list, description="Key attributes, e.g. 'id: UUID'")
    relationships: list[str] = Field(default_factory=list, description="e.g. 'has many UserStories'")


class AddFunctionalRequirementArgs(BaseModel):
    description: str = Field(description="What the system must do")
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    related_user_stories: list[str] = Field(
        default_factory=list,
        description="Story IDs this FR traces to"
    )


class AddGlossaryTermArgs(BaseModel):
    term: str
    definition: str


class SetLlmInteractionModelArgs(BaseModel):
    llm_role: str = Field(description="e.g. 'Business Analyst agent'")
    interaction_pattern: str = Field(description="e.g. 'conversational clarification loop'")
    input_format: str = Field(description="What the LLM receives")
    output_format: str = Field(description="What the LLM must produce")
    memory_strategy: str = Field(description="e.g. 'project knowledge snapshot injected each turn'")
    error_handling: list[str] = Field(default_factory=list)


class AnswerClarificationPointArgs(BaseModel):
    point_id: str = Field(description="Catalog point ID, e.g. 'problem_goals'")
    answer: str = Field(description="Canonical answer captured from the conversation")
    status: Literal["answered", "skipped"] = "answered"


class DeleteStoryArgs(BaseModel):
    story_id: str
    reason: str = ""


class DeleteComponentArgs(BaseModel):
    component_id: str
    reason: str = ""


class DeleteDecisionArgs(BaseModel):
    decision_id: str
    reason: str = ""


class DeleteInterfaceContractArgs(BaseModel):
    contract_id: str
    reason: str = ""


class DeleteTestSpecArgs(BaseModel):
    spec_id: str
    reason: str = ""


class DeleteTaskArgs(BaseModel):
    task_id: str
    reason: str = ""


# ---------------------------------------------------------------------------
# Review phase — update / delete tools
# ---------------------------------------------------------------------------

class UpdateComponentArgs(BaseModel):
    component_id: str
    name: str | None = None
    responsibility: str | None = None
    component_type: str | None = None


class UpdateDecisionArgs(BaseModel):
    decision_id: str
    title: str | None = None
    context: str | None = None
    decision: str | None = None


class UpdateInterfaceContractArgs(BaseModel):
    contract_id: str
    component_id: str | None = None
    kind: Literal["rest", "graphql", "event", "function", "cli"] | None = None
    name: str | None = None
    body_md: str | None = None


class UpdateTestSpecArgs(BaseModel):
    spec_id: str
    description: str | None = None
    given_context: str | None = None
    when_action: str | None = None
    then_expectation: str | None = None
    test_type: Literal["unit", "integration", "e2e"] | None = None


class UpdateTaskArgs(BaseModel):
    task_id: str
    title: str | None = None
    description: str | None = None
    complexity: Literal["trivial", "small", "medium", "large"] | None = None


# ---------------------------------------------------------------------------
# Phase flow
# ---------------------------------------------------------------------------

@dataclass
class PhaseInfo:
    key: str
    label: str
    icon: str
    unlocked: bool
    complete: bool

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "icon": self.icon,
            "unlocked": self.unlocked,
            "complete": self.complete,
        }


def compute_phase_status(snapshot: "KnowledgeSnapshot") -> list[PhaseInfo]:
    """Derive which phases are unlocked / complete from the knowledge snapshot."""
    founder_done = (
        bool(snapshot.mission_statement and snapshot.mission_statement.strip())
        and bool(snapshot.mission_target_users and snapshot.mission_target_users.strip())
        and bool(snapshot.mission_problem and snapshot.mission_problem.strip())
        and snapshot.roadmap_item_count > 0
        and snapshot.tech_stack_count > 0
        and snapshot.founder_evaluator_passed
    )
    ba_done = (
        bool(snapshot.problem_statement)
        and snapshot.story_count > 0
        and snapshot.persona_count > 0
        and snapshot.flow_count > 0
        and snapshot.vision_scope_set
        and len(snapshot.pending_clarification_ids) == 0
    )
    pm_done   = snapshot.epic_count > 0 and snapshot.mvp_story_count > 0
    arch_done = snapshot.component_count > 0 and snapshot.decision_count > 0
    tdd_done  = snapshot.test_spec_count > 0 and snapshot.task_count > 0

    return [
        PhaseInfo("founder",   "Founder",          "🚀", unlocked=True,         complete=founder_done),
        PhaseInfo("ba",        "Business Analyst", "🔍", unlocked=founder_done, complete=ba_done),
        PhaseInfo("pm",        "Product Manager",  "📋", unlocked=ba_done,      complete=pm_done),
        PhaseInfo("architect", "Architect",        "🏗️",  unlocked=pm_done,      complete=arch_done),
        PhaseInfo("tdd",       "TDD Tester",       "✅",  unlocked=arch_done,    complete=tdd_done),
        PhaseInfo("review",    "Reviewer",         "🔎", unlocked=tdd_done,     complete=False),
    ]


def current_tab_from_phases(phases: list[PhaseInfo]) -> str:
    """Return the key of the first unlocked+incomplete phase (the 'active' one)."""
    last_complete = phases[0].key
    for phase in phases:
        if phase.complete:
            last_complete = phase.key
        elif phase.unlocked:
            return phase.key
    return last_complete


def compute_feature_phase_status(snapshot: "KnowledgeSnapshot") -> list[PhaseInfo]:
    """Feature loop gating — independent from the one-time project loop."""
    feature_exists = bool(snapshot.feature_id)
    ba_done = snapshot.feature_story_count > 0
    arch_done = snapshot.feature_decision_count > 0
    tdd_done = snapshot.feature_test_spec_count > 0 and snapshot.feature_task_count > 0

    return [
        PhaseInfo("ba", "Business Analyst", "🔍", unlocked=feature_exists, complete=ba_done),
        PhaseInfo("architect", "Architect", "🏗️", unlocked=ba_done, complete=arch_done),
        PhaseInfo("tdd", "TDD Tester", "✅", unlocked=arch_done, complete=tdd_done),
        PhaseInfo("review", "Reviewer", "🔎", unlocked=tdd_done, complete=False),
    ]
