from roles.base import BaseRole


class ArchitectRole(BaseRole):
    name = "Architect"
    persona_key = "architect"

    @property
    def system_prompt_fragment(self) -> str:
        return """
[ARCHITECT]
When designing the system structure, act as a pragmatic Software Architect.
Your goals:
- Decompose the problem into cohesive, loosely-coupled components
- Define clear interfaces and responsibilities (not implementation details)
- Propose a concrete file/module structure
- Make and record explicit architecture decisions with trade-offs (ADRs)
- Identify integration points with external systems
- Flag risks: "this approach has a scalability ceiling at ~10k users"
- Prefer boring technology unless there's a clear reason not to

When you propose a component, call add_component().
When you make an architecture decision, call record_decision().
"""

    @property
    def trigger_keywords(self) -> list[str]:
        return [
            "component", "module", "database", "api", "interface",
            "pattern", "structure", "architecture", "service", "layer",
            "dependency", "technology", "framework",
        ]
