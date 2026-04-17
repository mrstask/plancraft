"""Pydantic domain models — the knowledge model projected from the DB.

These are used for:
  - Passing structured data to Claude (knowledge snapshot in system prompt)
  - Serializing the knowledge model to JSON for export
  - Validating Claude tool call arguments
"""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Snapshot — what Claude sees as project context
# ---------------------------------------------------------------------------

class KnowledgeSnapshot(BaseModel):
    """Compact representation of the current project state injected into Claude's context."""
    project_name: str
    problem_statement: str | None = None
    story_count: int = 0
    epic_count: int = 0
    component_count: int = 0
    decision_count: int = 0
    test_spec_count: int = 0
    task_count: int = 0

    # Recent items (last 5 of each) for Claude's context
    recent_stories: list[StorySnapshot] = Field(default_factory=list)
    recent_components: list[ComponentSnapshot] = Field(default_factory=list)
    recent_decisions: list[DecisionSnapshot] = Field(default_factory=list)

    def to_context_string(self) -> str:
        lines = [f"Project: {self.project_name}"]
        if self.problem_statement:
            lines.append(f"Problem: {self.problem_statement}")
        lines.append(
            f"Captured so far: {self.story_count} stories, {self.epic_count} epics, "
            f"{self.component_count} components, {self.decision_count} decisions, "
            f"{self.test_spec_count} test specs, {self.task_count} tasks"
        )
        if self.recent_stories:
            lines.append("\nRecent stories:")
            for s in self.recent_stories:
                lines.append(f"  - [{s.id[:8]}] As a {s.as_a}, I want {s.i_want}")
        if self.recent_components:
            lines.append("\nComponents defined:")
            for c in self.recent_components:
                lines.append(f"  - [{c.id[:8]}] {c.name}: {c.responsibility}")
        if self.recent_decisions:
            lines.append("\nArchitecture decisions:")
            for d in self.recent_decisions:
                lines.append(f"  - [{d.id[:8]}] {d.title}: {d.decision}")
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


# ---------------------------------------------------------------------------
# Tool call argument models (validated when Claude calls a knowledge tool)
# ---------------------------------------------------------------------------

class AddUserStoryArgs(BaseModel):
    as_a: str = Field(description="The role/persona (e.g. 'logged-in user')")
    i_want: str = Field(description="The action or feature desired")
    so_that: str = Field(description="The benefit or goal")
    acceptance_criteria: list[str] = Field(default_factory=list)
    priority: Literal["must", "should", "could", "wont"] = "should"
    epic_id: str | None = Field(None, description="ID of an existing epic to attach to")


class UpdateUserStoryArgs(BaseModel):
    story_id: str
    as_a: str | None = None
    i_want: str | None = None
    so_that: str | None = None
    acceptance_criteria: list[str] | None = None
    priority: Literal["must", "should", "could", "wont"] | None = None


class AddEpicArgs(BaseModel):
    title: str
    description: str = ""


class RecordConstraintArgs(BaseModel):
    type: Literal["technical", "business", "time"]
    description: str


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
    description: str
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
