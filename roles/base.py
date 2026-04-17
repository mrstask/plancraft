"""Base class for all planning roles."""
from abc import ABC, abstractmethod


class BaseRole(ABC):
    name: str
    persona_key: str  # 'ba' | 'pm' | 'architect' | 'tdd'

    @property
    @abstractmethod
    def system_prompt_fragment(self) -> str:
        """Role-specific section injected into the combined system prompt."""
        ...

    @property
    def trigger_keywords(self) -> list[str]:
        """Keywords that hint this role is most relevant. Used for role badge."""
        return []
