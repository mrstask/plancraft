"""SQLAlchemy ORM models — maps directly to SQLite tables."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Text, ForeignKey, Integer,
    DateTime, JSON,
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
    current_phase = Column(String, default="ba")  # ba | pm | architect | tdd
    mvp_story_ids = Column(JSON, default=list)
    mvp_rationale = Column(Text, nullable=True)
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


# ---------------------------------------------------------------------------
# Conversation
# ---------------------------------------------------------------------------

class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    role = Column(String, nullable=False)         # 'user' | 'assistant'
    content = Column(Text, nullable=False)
    active_persona = Column(String, nullable=True)  # 'ba' | 'pm' | 'architect' | 'tdd'
    role_tab = Column(String, nullable=True, default="ba")  # which phase tab this message belongs to
    created_at = Column(DateTime, default=_now)

    project = relationship("Project", back_populates="messages")


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


class UserStory(Base):
    __tablename__ = "user_stories"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    epic_id = Column(String, ForeignKey("epics.id"), nullable=True)
    as_a = Column(Text, nullable=False)
    i_want = Column(Text, nullable=False)
    so_that = Column(Text, nullable=False)
    priority = Column(String, default="should")   # must|should|could|wont
    status = Column(String, default="draft")      # draft|confirmed|deferred
    created_at = Column(DateTime, default=_now)

    project = relationship("Project", back_populates="user_stories")
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


class ComponentDependency(Base):
    __tablename__ = "component_dependencies"

    from_id = Column(String, ForeignKey("components.id", ondelete="CASCADE"), primary_key=True)
    to_id = Column(String, ForeignKey("components.id", ondelete="CASCADE"), primary_key=True)


class ArchitectureDecision(Base):
    __tablename__ = "architecture_decisions"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    title = Column(String, nullable=False)
    context = Column(Text, nullable=True)
    decision = Column(Text, nullable=False)
    consequences = Column(JSON, default=dict)  # {positive: [], negative: []}
    created_at = Column(DateTime, default=_now)

    project = relationship("Project", back_populates="decisions")


# ---------------------------------------------------------------------------
# TDD layer
# ---------------------------------------------------------------------------

class TestSpec(Base):
    __tablename__ = "test_specs"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    story_id = Column(String, ForeignKey("user_stories.id", ondelete="SET NULL"), nullable=True)
    component_id = Column(String, ForeignKey("components.id", ondelete="SET NULL"), nullable=True)
    description = Column(Text, nullable=False)
    test_type = Column(String, default="unit")    # unit|integration|e2e
    given_context = Column(Text, nullable=True)
    when_action = Column(Text, nullable=True)
    then_expectation = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now)

    project = relationship("Project", back_populates="test_specs")


# ---------------------------------------------------------------------------
# Task DAG (agent-consumable output)
# ---------------------------------------------------------------------------

class Task(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
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
