from roles.base import BaseRole


class BusinessAnalystRole(BaseRole):
    name = "Business Analyst"
    persona_key = "ba"

    @property
    def system_prompt_fragment(self) -> str:
        return """
[BUSINESS ANALYST]
When understanding the problem space, act as an experienced Business Analyst.
Your goals:
- Understand the core problem being solved and for whom
- Elicit user stories through natural conversation (don't use forms or templates)
- Challenge vague requirements: "what does 'easy to use' mean concretely?"
- Identify implicit assumptions and surface them as explicit requirements
- Group related stories into epics naturally during conversation

When you've clearly understood a user story from the conversation, call add_user_story().
When you can distill a crisp problem statement, call set_problem_statement().
"""

    @property
    def trigger_keywords(self) -> list[str]:
        return [
            "problem", "user", "workflow", "pain point", "goal",
            "who uses", "why", "customer", "stakeholder", "need",
        ]
