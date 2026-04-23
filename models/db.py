"""SQLAlchemy ORM models — maps directly to SQLite tables."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Text, ForeignKey, Integer,
    DateTime, JSON, Float, Boolean, Index,
)
from sqlalchemy.orm import relationship

from database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------

class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String, default="planning")   # planning | scaffolded | handed-off
    root_path = Column(String, nullable=True)      # set after scaffolding
    current_phase = Column(String, default="founder")  # founder | ba | pm | architect | tdd
    mvp_story_ids = Column(JSON, default=list)
    mvp_rationale = Column(Text, nullable=True)
    # BA vision/scope structured fields
    business_goals = Column(JSON, default=list)
    success_metrics = Column(JSON, default=list)
    in_scope = Column(JSON, default=list)
    out_of_scope = Column(JSON, default=list)
    target_users = Column(JSON, default=list)
    terminology = Column(JSON, default=list)      # [{term, definition}]
    llm_interaction_model = Column(JSON, nullable=True)  # {role, pattern, input_format, ...}
    constitution_md = Column(Text, nullable=False, default="")  # project constitution (M1)
    profile_ref = Column(String(128), nullable=True)             # cross-project profile slug (M3)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    messages = relationship("Message", back_populates="project", cascade="all, delete-orphan")
    epics = relationship("Epic", back_populates="project", cascade="all, delete-orphan")
    user_stories = relationship("UserStory", back_populates="project", cascade="all, delete-orphan")
    constraints = relationship("Constraint", back_populates="project", cascade="all, delete-orphan")
    components = relationship("Component", back_populates="project", cascade="all, delete-orphan")
    decisions = relationship("ArchitectureDecision", back_populates="project", cascade="all, delete-orphan")
    test_specs = relationship("TestSpec", back_populates="project", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")
    # BA layer
    personas = relationship("Persona", back_populates="project", cascade="all, delete-orphan")
    user_flows = relationship("UserFlow", back_populates="project", cascade="all, delete-orphan")
    business_rules = relationship("BusinessRule", back_populates="project", cascade="all, delete-orphan")
    data_entities = relationship("DataEntity", back_populates="project", cascade="all, delete-orphan")
    functional_requirements = relationship("FunctionalRequirement", back_populates="project", cascade="all, delete-orphan")
    clarification_points = relationship("ClarificationPoint", back_populates="project", cascade="all, delete-orphan")
    # Founder layer
    mission = relationship("ProjectMission", back_populates="project", cascade="all, delete-orphan", uselist=False)
    roadmap_items = relationship("ProjectRoadmapItem", back_populates="project", cascade="all, delete-orphan")
    tech_stack_entries = relationship("TechStackEntry", back_populates="project", cascade="all, delete-orphan")
    features = relationship("Feature", back_populates="project", cascade="all, delete-orphan")
    interface_contracts = relationship("InterfaceContract", back_populates="project", cascade="all, delete-orphan")


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String(128), nullable=False, unique=True)
    description = Column(Text, nullable=False, default="")
    version = Column(String(32), nullable=False, default="1.0.0")
    constitution_md = Column(Text, nullable=False, default="")
    tech_stack_template = Column(Text, nullable=False, default="[]")
    conventions_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)


class Feature(Base):
    __tablename__ = "features"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    slug = Column(String(128), nullable=False)
    ordinal = Column(Integer, nullable=False)
    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=False, default="")
    status = Column(String(32), nullable=False, default="drafting")
    roadmap_item_id = Column(String, ForeignKey("project_roadmap_items.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    project = relationship("Project", back_populates="features")
    roadmap_item = relationship("ProjectRoadmapItem")
    stories = relationship("UserStory", back_populates="feature")
    test_specs = relationship("TestSpec", back_populates="feature")
    tasks = relationship("Task", back_populates="feature")
    decisions = relationship("ArchitectureDecision", back_populates="feature")
    clarification_points = relationship("ClarificationPoint", back_populates="feature")
    interface_contracts = relationship("InterfaceContract", back_populates="feature")


# ---------------------------------------------------------------------------
# Founder layer
# ---------------------------------------------------------------------------

class ProjectMission(Base):
    __tablename__ = "project_missions"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True)
    statement = Column(Text, nullable=False, default="")
    target_users = Column(Text, nullable=False, default="")
    problem = Column(Text, nullable=False, default="")
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    project = relationship("Project", back_populates="mission")


class ProjectRoadmapItem(Base):
    __tablename__ = "project_roadmap_items"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    ordinal = Column(Integer, nullable=False)
    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=False, default="")
    linked_epic_id = Column(String, ForeignKey("epics.id", ondelete="SET NULL"), nullable=True)
    mvp = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    project = relationship("Project", back_populates="roadmap_items")
    linked_epic = relationship("Epic", back_populates="roadmap_items")


class TechStackEntry(Base):
    __tablename__ = "tech_stack_entries"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    layer = Column(String(64), nullable=False)
    choice = Column(String(256), nullable=False)
    rationale = Column(Text, nullable=False, default="")
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    project = relationship("Project", back_populates="tech_stack_entries")


# ---------------------------------------------------------------------------
# Conversation
# ---------------------------------------------------------------------------

class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    role = Column(String, nullable=False)         # 'user' | 'assistant'
    content = Column(Text, nullable=False)
    active_persona = Column(String, nullable=True)  # 'founder' | 'ba' | 'pm' | 'architect' | 'tdd'
    role_tab = Column(String, nullable=True, default="founder")  # which phase tab this message belongs to
    feature_id = Column(String, ForeignKey("features.id", ondelete="CASCADE"), nullable=True)
    archived = Column(Boolean, nullable=False, default=False)
    kind = Column(String, nullable=True)  # 'summary' when produced by /compact
    created_at = Column(DateTime, default=_now)

    project = relationship("Project", back_populates="messages")
    feature = relationship("Feature")


# ---------------------------------------------------------------------------
# Business Analyst layer
# ---------------------------------------------------------------------------

class Epic(Base):
    __tablename__ = "epics"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now)

    project = relationship("Project", back_populates="epics")
    stories = relationship("UserStory", back_populates="epic")
    roadmap_items = relationship("ProjectRoadmapItem", back_populates="linked_epic")


class UserStory(Base):
    __tablename__ = "user_stories"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    feature_id = Column(String, ForeignKey("features.id", ondelete="CASCADE"), nullable=True)
    epic_id = Column(String, ForeignKey("epics.id"), nullable=True)
    as_a = Column(Text, nullable=False)
    i_want = Column(Text, nullable=False)
    so_that = Column(Text, nullable=False)
    priority = Column(String, default="should")   # must|should|could|wont
    status = Column(String, default="draft")      # draft|confirmed|deferred
    created_at = Column(DateTime, default=_now)

    project = relationship("Project", back_populates="user_stories")
    feature = relationship("Feature", back_populates="stories")
    epic = relationship("Epic", back_populates="stories")
    acceptance_criteria = relationship(
        "AcceptanceCriterion", back_populates="story", cascade="all, delete-orphan"
    )


class AcceptanceCriterion(Base):
    __tablename__ = "acceptance_criteria"

    id = Column(String, primary_key=True, default=_uuid)
    story_id = Column(String, ForeignKey("user_stories.id"), nullable=False)
    criterion = Column(Text, nullable=False)
    order_index = Column(Integer, default=0)

    story = relationship("UserStory", back_populates="acceptance_criteria")


class Persona(Base):
    __tablename__ = "personas"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    name = Column(String, nullable=False)
    role = Column(String, nullable=False)
    goals = Column(JSON, default=list)       # list[str]
    pain_points = Column(JSON, default=list) # list[str]
    created_at = Column(DateTime, default=_now)

    project = relationship("Project", back_populates="personas")


class UserFlow(Base):
    __tablename__ = "user_flows"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now)

    project = relationship("Project", back_populates="user_flows")
    steps = relationship("UserFlowStep", back_populates="flow", cascade="all, delete-orphan", order_by="UserFlowStep.order_index")


class UserFlowStep(Base):
    __tablename__ = "user_flow_steps"

    id = Column(String, primary_key=True, default=_uuid)
    flow_id = Column(String, ForeignKey("user_flows.id"), nullable=False)
    order_index = Column(Integer, nullable=False)
    description = Column(Text, nullable=False)
    actor = Column(String, nullable=True)    # who performs this step

    flow = relationship("UserFlow", back_populates="steps")


class BusinessRule(Base):
    __tablename__ = "business_rules"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    rule = Column(Text, nullable=False)
    applies_to = Column(JSON, default=list)  # list[str] — e.g. story IDs, feature names
    created_at = Column(DateTime, default=_now)

    project = relationship("Project", back_populates="business_rules")


class DataEntity(Base):
    __tablename__ = "data_entities"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    name = Column(String, nullable=False)
    attributes = Column(JSON, default=list)    # list[str]
    relationships = Column(JSON, default=list) # list[str]
    created_at = Column(DateTime, default=_now)

    project = relationship("Project", back_populates="data_entities")


class FunctionalRequirement(Base):
    __tablename__ = "functional_requirements"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    description = Column(Text, nullable=False)
    inputs = Column(JSON, default=list)   # list[str]
    outputs = Column(JSON, default=list)  # list[str]
    created_at = Column(DateTime, default=_now)

    project = relationship("Project", back_populates="functional_requirements")
    story_links = relationship("FunctionalRequirementStory", cascade="all, delete-orphan")


class FunctionalRequirementStory(Base):
    __tablename__ = "functional_requirement_stories"

    fr_id = Column(String, ForeignKey("functional_requirements.id", ondelete="CASCADE"), primary_key=True)
    story_id = Column(String, ForeignKey("user_stories.id", ondelete="CASCADE"), primary_key=True)


class ClarificationPoint(Base):
    """Tracks per-project status of each catalog clarification point."""
    __tablename__ = "clarification_points"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    feature_id = Column(String, ForeignKey("features.id", ondelete="CASCADE"), nullable=True)
    point_id = Column(String, nullable=False)   # matches catalog id e.g. "problem_goals"
    status = Column(String, default="pending")  # pending | answered | skipped
    answer = Column(Text, nullable=True)        # captured canonical answer
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    project = relationship("Project", back_populates="clarification_points")
    feature = relationship("Feature", back_populates="clarification_points")


# ---------------------------------------------------------------------------
# PM layer
# ---------------------------------------------------------------------------

class Constraint(Base):
    __tablename__ = "constraints"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    type = Column(String, nullable=False)         # technical|business|time
    description = Column(Text, nullable=False)
    created_at = Column(DateTime, default=_now)

    project = relationship("Project", back_populates="constraints")


# ---------------------------------------------------------------------------
# Architecture layer
# ---------------------------------------------------------------------------

class Component(Base):
    __tablename__ = "components"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    name = Column(String, nullable=False)
    responsibility = Column(Text, nullable=False)
    component_type = Column(String, nullable=True)  # service|store|gateway|ui|etc.
    file_paths = Column(JSON, default=list)
    created_at = Column(DateTime, default=_now)

    project = relationship("Project", back_populates="components")
    outgoing_deps = relationship(
        "ComponentDependency",
        foreign_keys="ComponentDependency.from_id",
        cascade="all, delete-orphan",
    )
    interface_contracts = relationship("InterfaceContract", back_populates="component", cascade="all, delete-orphan")


class ComponentDependency(Base):
    __tablename__ = "component_dependencies"

    from_id = Column(String, ForeignKey("components.id", ondelete="CASCADE"), primary_key=True)
    to_id = Column(String, ForeignKey("components.id", ondelete="CASCADE"), primary_key=True)


class ArchitectureDecision(Base):
    __tablename__ = "architecture_decisions"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    feature_id = Column(String, ForeignKey("features.id", ondelete="CASCADE"), nullable=True)
    title = Column(String, nullable=False)
    context = Column(Text, nullable=True)
    decision = Column(Text, nullable=False)
    consequences = Column(JSON, default=dict)  # {positive: [], negative: []}
    created_at = Column(DateTime, default=_now)

    project = relationship("Project", back_populates="decisions")
    feature = relationship("Feature", back_populates="decisions")


class InterfaceContract(Base):
    __tablename__ = "interface_contracts"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    feature_id = Column(String, ForeignKey("features.id", ondelete="CASCADE"), nullable=True)
    component_id = Column(String, ForeignKey("components.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String(32), nullable=False)
    name = Column(String(256), nullable=False)
    body_md = Column(Text, nullable=False, default="")
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    project = relationship("Project", back_populates="interface_contracts")
    feature = relationship("Feature", back_populates="interface_contracts")
    component = relationship("Component", back_populates="interface_contracts")


# ---------------------------------------------------------------------------
# TDD layer
# ---------------------------------------------------------------------------

class TestSpec(Base):
    __tablename__ = "test_specs"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    feature_id = Column(String, ForeignKey("features.id", ondelete="CASCADE"), nullable=True)
    story_id = Column(String, ForeignKey("user_stories.id", ondelete="SET NULL"), nullable=True)
    component_id = Column(String, ForeignKey("components.id", ondelete="SET NULL"), nullable=True)
    description = Column(Text, nullable=False)
    test_type = Column(String, default="unit")    # unit|integration|e2e
    given_context = Column(Text, nullable=True)
    when_action = Column(Text, nullable=True)
    then_expectation = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now)

    project = relationship("Project", back_populates="test_specs")
    feature = relationship("Feature", back_populates="test_specs")


# ---------------------------------------------------------------------------
# Task DAG (agent-consumable output)
# ---------------------------------------------------------------------------

class Task(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    feature_id = Column(String, ForeignKey("features.id", ondelete="CASCADE"), nullable=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    complexity = Column(String, default="medium")  # trivial|small|medium|large
    status = Column(String, default="pending")
    file_paths = Column(JSON, default=list)
    acceptance_criteria = Column(JSON, default=list)
    # Room for dev_team feedback loop integration:
    devteam_task_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=_now)

    project = relationship("Project", back_populates="tasks")
    feature = relationship("Feature", back_populates="tasks")


class TaskDependency(Base):
    __tablename__ = "task_dependencies"

    task_id = Column(String, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)
    depends_on_id = Column(String, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)


class TaskStory(Base):
    __tablename__ = "task_stories"

    task_id = Column(String, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)
    story_id = Column(String, ForeignKey("user_stories.id", ondelete="CASCADE"), primary_key=True)


class TaskTestSpec(Base):
    __tablename__ = "task_test_specs"

    task_id = Column(String, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)
    spec_id = Column(String, ForeignKey("test_specs.id", ondelete="CASCADE"), primary_key=True)


# ---------------------------------------------------------------------------
# ReAct evaluator loop traces (M0)
# ---------------------------------------------------------------------------

class RoleExecutionTrace(Base):
    """One row per actor iteration inside a role turn.

    With NullEvaluator (default in M0) there is exactly one row per turn,
    final=True. Real evaluators added in later milestones may produce
    multiple rows per turn as the loop retries.
    """
    __tablename__ = "role_execution_traces"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    feature_id = Column(String, nullable=True)                  # populated from M4 onwards
    role = Column(String, nullable=False)                        # "ba" | "pm" | "architect" | "tdd" | "review"
    iteration = Column(Integer, nullable=False)                  # 1-based
    actor_prompt = Column(Text, nullable=False, default="")
    actor_output = Column(Text, nullable=False, default="")
    evaluator_score = Column(Float, nullable=True)
    evaluator_critique = Column(Text, nullable=True)
    rubric_version = Column(String, nullable=True)
    final = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=_now)


Index(
    "idx_traces_project_role_created",
    RoleExecutionTrace.project_id,
    RoleExecutionTrace.role,
    RoleExecutionTrace.created_at,
)

Index("idx_features_project_ordinal", Feature.project_id, Feature.ordinal, unique=True)
Index("idx_features_project_slug", Feature.project_id, Feature.slug, unique=True)
Index("idx_contracts_feature", InterfaceContract.feature_id)
