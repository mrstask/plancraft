"""Declarative BA clarification-point catalog.

Each entry drives one round of structured elicitation. The BA agent walks
through all required points before the phase gate opens.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ClarificationPointDef:
    id: str
    name: str
    description: str
    required: bool
    question_to_user: str
    expected_answer_format: str
    artifact_mapping: tuple[str, ...]
    validation_rules: tuple[str, ...]
    follow_up_conditions: tuple[str, ...]


CATALOG: tuple[ClarificationPointDef, ...] = (
    ClarificationPointDef(
        id="problem_goals",
        name="Problem & Goals",
        description=(
            "Understand the core problem the product solves and the business/user goals it pursues. "
            "Without this, every downstream artifact lacks grounding."
        ),
        required=True,
        question_to_user=(
            "What specific problem does this product solve, and what does success look like "
            "for the business and users once it's solved?"
        ),
        expected_answer_format="short prose — 2-5 sentences covering the problem and desired outcome",
        artifact_mapping=(
            "vision_scope.problem_statement",
            "vision_scope.business_goals",
            "vision_scope.success_metrics",
        ),
        validation_rules=(
            "problem_statement must be non-empty",
            "at least one business_goal captured",
            "at least one success_metric captured",
        ),
        follow_up_conditions=(
            "goals are vague (e.g. 'improve productivity') — ask for a measurable definition",
            "no success metric mentioned — ask 'how will you know it worked?'",
        ),
    ),
    ClarificationPointDef(
        id="personas_roles",
        name="Personas & Roles",
        description=(
            "Identify who uses the system, their context, and what they need. "
            "Personas anchor user stories and flows to real actors."
        ),
        required=True,
        question_to_user=(
            "Who are the primary people who will use this product? "
            "For each type of user, what is their role and what are they trying to accomplish?"
        ),
        expected_answer_format="list of user types with role + goals + pain points",
        artifact_mapping=(
            "personas[].name",
            "personas[].role",
            "personas[].goals",
            "personas[].pain_points",
            "vision_scope.target_users",
        ),
        validation_rules=(
            "at least one persona captured",
            "each persona has name, role, and at least one goal",
        ),
        follow_up_conditions=(
            "only one persona mentioned — ask 'are there other user types, e.g. admins or viewers?'",
            "pain points not mentioned — ask 'what frustrates them about the current way of doing this?'",
        ),
    ),
    ClarificationPointDef(
        id="core_user_flow",
        name="Core User Flow",
        description=(
            "Map the primary end-to-end journey a user takes to get value from the product. "
            "This becomes the baseline flow and the backbone of user stories."
        ),
        required=True,
        question_to_user=(
            "Walk me through the main journey a user takes from start to finish — "
            "what do they do first, what happens next, and what outcome do they reach?"
        ),
        expected_answer_format="ordered list of steps, each with actor and action",
        artifact_mapping=(
            "user_flows[].name",
            "user_flows[].steps",
        ),
        validation_rules=(
            "at least one flow with at least 3 steps",
            "each step has a description",
        ),
        follow_up_conditions=(
            "flow has fewer than 3 steps — ask for more detail",
            "flow only covers happy path — ask 'what happens if X fails?'",
        ),
    ),
    ClarificationPointDef(
        id="key_features",
        name="Key Features / Capabilities",
        description=(
            "Enumerate the discrete capabilities the product must have for MVP. "
            "This becomes the basis for functional requirements and stories."
        ),
        required=True,
        question_to_user=(
            "What are the core features or capabilities this product must have to be useful? "
            "List them — we'll prioritize in a later step."
        ),
        expected_answer_format="list of feature names with one-line descriptions",
        artifact_mapping=(
            "functional_requirements[].description",
            "vision_scope.in_scope",
        ),
        validation_rules=(
            "at least 3 features listed",
            "each feature has a clear description (not just a label)",
        ),
        follow_up_conditions=(
            "feature list is vague — ask for concrete user-facing behavior",
            "list contains infrastructure items — clarify if user-facing or technical",
        ),
    ),
    ClarificationPointDef(
        id="user_stories",
        name="User Stories",
        description=(
            "Translate features and flows into testable user stories in As a / I want / So that format. "
            "These are the primary unit of scope for all downstream phases."
        ),
        required=True,
        question_to_user=(
            "For the most important feature, complete this sentence: "
            "'As a [persona], I want to [action] so that [benefit].' "
            "What are the conditions that make this story done?"
        ),
        expected_answer_format="one story per feature, with acceptance criteria list",
        artifact_mapping=(
            "user_stories[].as_a",
            "user_stories[].i_want",
            "user_stories[].so_that",
            "user_stories[].acceptance_criteria",
            "user_stories[].priority",
        ),
        validation_rules=(
            "at least one story per major feature",
            "each story has at least one acceptance criterion",
            "priority set (must/should/could/wont)",
        ),
        follow_up_conditions=(
            "acceptance criteria missing — ask 'how do you verify this story is done?'",
            "story is too large — suggest splitting",
        ),
    ),
    ClarificationPointDef(
        id="inputs_outputs",
        name="Inputs & Outputs",
        description=(
            "Define what data enters the system and what it produces. "
            "Critical for functional requirements and data model."
        ),
        required=True,
        question_to_user=(
            "What data or information does a user provide to the system, "
            "and what does the system give back to them?"
        ),
        expected_answer_format="two lists: inputs (data the system receives) and outputs (data it produces)",
        artifact_mapping=(
            "functional_requirements[].inputs",
            "functional_requirements[].outputs",
            "data_model.entities[].attributes",
        ),
        validation_rules=(
            "at least one input and one output per functional requirement",
        ),
        follow_up_conditions=(
            "inputs/outputs described as 'the usual stuff' — ask for specific fields",
            "file uploads or binary data mentioned — flag as NFR too",
        ),
    ),
    ClarificationPointDef(
        id="llm_interaction",
        name="LLM Interaction Expectations",
        description=(
            "Clarify how the LLM component behaves: its role, conversation pattern, "
            "memory strategy, and failure modes. Required when the product includes an AI chat layer."
        ),
        required=False,
        question_to_user=(
            "Does this product include an AI or LLM component? If so, what role does it play, "
            "how does it interact with users (single-turn, multi-turn, guided), "
            "and what happens when it gives a wrong or incomplete response?"
        ),
        expected_answer_format="structured: role, interaction pattern, memory/context strategy, error handling",
        artifact_mapping=(
            "llm_interaction_model.llm_role",
            "llm_interaction_model.interaction_pattern",
            "llm_interaction_model.input_format",
            "llm_interaction_model.output_format",
            "llm_interaction_model.memory_strategy",
            "llm_interaction_model.error_handling",
        ),
        validation_rules=(
            "if LLM is in scope: llm_role and interaction_pattern must be set",
            "error_handling must have at least one entry if LLM is in scope",
        ),
        follow_up_conditions=(
            "LLM scope confirmed — ask about context window, tool use, and fallback behavior",
            "LLM explicitly out of scope — mark as skipped",
        ),
    ),
    ClarificationPointDef(
        id="data_entities",
        name="Data & Entities",
        description=(
            "Identify the main data objects the system creates, stores, and relates. "
            "Feeds the conceptual data model used by Architect."
        ),
        required=True,
        question_to_user=(
            "What are the main 'things' the system manages? For example, a project management "
            "tool might manage Projects, Tasks, and Users. What are the key attributes of each?"
        ),
        expected_answer_format="list of entities with key attributes and relationships",
        artifact_mapping=(
            "data_model.entities[].name",
            "data_model.entities[].attributes",
            "data_model.entities[].relationships",
        ),
        validation_rules=(
            "at least 2 entities defined",
            "each entity has at least one attribute",
            "at least one relationship between entities",
        ),
        follow_up_conditions=(
            "entities listed without attributes — ask for 3-5 key fields per entity",
            "no relationships mentioned — ask how entities connect",
        ),
    ),
    ClarificationPointDef(
        id="business_rules",
        name="Business Rules",
        description=(
            "Surface explicit rules that constrain system behavior, independent of UI. "
            "These become validation logic and guard rails for downstream engineers."
        ),
        required=True,
        question_to_user=(
            "Are there any rules the system must always enforce? For example: "
            "'a user can only belong to one team', or 'a task cannot move to Done without review'. "
            "What are the non-negotiable constraints?"
        ),
        expected_answer_format="list of rule statements, each with the feature/entity it applies to",
        artifact_mapping=(
            "business_rules[].rule",
            "business_rules[].applies_to",
        ),
        validation_rules=(
            "at least one business rule captured",
            "each rule names the entity or feature it constrains",
        ),
        follow_up_conditions=(
            "rules are vague — ask for the exact condition that triggers them",
            "rules involve external systems (payment, auth) — flag as constraint too",
        ),
    ),
    ClarificationPointDef(
        id="edge_cases",
        name="Edge Cases",
        description=(
            "Identify boundary conditions and failure scenarios. "
            "Prevents QA from discovering scope gaps late."
        ),
        required=True,
        question_to_user=(
            "What could go wrong or behave unexpectedly? For example: what happens "
            "if a user submits an empty form, loses connectivity mid-flow, or hits a rate limit?"
        ),
        expected_answer_format="list of scenarios with expected system behavior",
        artifact_mapping=(
            "user_stories[].acceptance_criteria",
            "business_rules[].rule",
        ),
        validation_rules=(
            "at least 3 edge cases identified across the core flow",
        ),
        follow_up_conditions=(
            "user says 'show an error' — ask what the error says and whether recovery is possible",
            "async operations present — ask about partial failure handling",
        ),
    ),
    ClarificationPointDef(
        id="nfr_lightweight",
        name="Non-Functional Requirements (lightweight)",
        description=(
            "Capture the most critical quality attributes for MVP. "
            "Not exhaustive — just what would break the product if ignored."
        ),
        required=False,
        question_to_user=(
            "Are there any hard requirements around performance, security, or scale for the first release? "
            "For example: 'must respond in under 2 seconds', or 'all data must be encrypted at rest'."
        ),
        expected_answer_format="list of constraints typed as technical/business/time",
        artifact_mapping=(
            "constraints[].type",
            "constraints[].description",
        ),
        validation_rules=(
            "if constraints mentioned: each has a type (technical/business/time) and concrete description",
        ),
        follow_up_conditions=(
            "security mentioned — ask about auth method and data sensitivity",
            "scale mentioned — ask for expected user/request volume",
        ),
    ),
    ClarificationPointDef(
        id="scope_boundaries",
        name="Scope (In / Out)",
        description=(
            "Explicitly define what is and is not in scope for this release. "
            "Prevents scope creep and gives PM a clear cut line."
        ),
        required=True,
        question_to_user=(
            "What is explicitly NOT part of this version? What have you decided to leave for later, "
            "and what is completely out of scope forever?"
        ),
        expected_answer_format="two lists: in_scope items and out_of_scope items",
        artifact_mapping=(
            "vision_scope.in_scope",
            "vision_scope.out_of_scope",
        ),
        validation_rules=(
            "at least one item in out_of_scope",
            "in_scope list matches features captured earlier",
        ),
        follow_up_conditions=(
            "user says 'everything else' — ask for 2-3 concrete examples",
            "out_of_scope overlaps with features — clarify the conflict",
        ),
    ),
    ClarificationPointDef(
        id="terminology",
        name="Terminology / Glossary",
        description=(
            "Capture domain-specific terms to ensure all roles use consistent language. "
            "Avoids misalignment between BA output and engineering implementation."
        ),
        required=False,
        question_to_user=(
            "Are there any terms or concepts in this domain that have a specific meaning "
            "your team uses differently from the common definition? "
            "For example, what do you mean by 'project', 'session', or 'workspace' in this context?"
        ),
        expected_answer_format="list of {term, definition} pairs",
        artifact_mapping=(
            "terminology[].term",
            "terminology[].definition",
        ),
        validation_rules=(
            "each term has a non-empty definition",
        ),
        follow_up_conditions=(
            "ambiguous terms found in stories — surface them for definition",
        ),
    ),
)

CATALOG_BY_ID: dict[str, ClarificationPointDef] = {p.id: p for p in CATALOG}
REQUIRED_IDS: frozenset[str] = frozenset(p.id for p in CATALOG if p.required)


def get_required_ids() -> frozenset[str]:
    return REQUIRED_IDS


def get_point(point_id: str) -> ClarificationPointDef | None:
    return CATALOG_BY_ID.get(point_id)
