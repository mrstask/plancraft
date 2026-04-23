import logging
import warnings
from pathlib import Path

from pydantic_settings import BaseSettings

_log = logging.getLogger(__name__)

_DEFAULT_SECRET_KEY = "dev-secret-change-in-production"


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./planning.db"
    secret_key: str = _DEFAULT_SECRET_KEY
    debug: bool = True

    # Ollama settings
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "gemma4:31b"

    # Conversation limits
    max_history_messages: int = 50
    max_tokens: int = 4096
    # Model context window size (tokens). Used for the context-usage indicator
    # and to decide when to suggest /compact. Approximate for Ollama models.
    context_window: int = 131072
    # Keep this many most-recent messages untouched when /compact runs.
    compact_keep_tail: int = 4

    # Root directory where per-project workspace folders are created
    projects_root: Path = Path("./projects")
    profiles_root: Path = Path("~/.plancraft/profiles")
    feature_scoping_enabled: bool = False

    # ReAct evaluator loop (M0). With evaluator_enabled=false every role
    # uses NullEvaluator: traces are still written but no retry happens.
    evaluator_enabled: bool = False
    evaluator_max_iterations: int = 3
    evaluator_score_threshold: float = 0.8
    evaluator_escalate_after: int = 2
    evaluator_model: str = "gemma4:31b"
    trace_retention_days: int = 30

    class Config:
        env_file = ".env"


settings = Settings()
settings.projects_root = settings.projects_root.resolve()
settings.profiles_root = settings.profiles_root.expanduser().resolve()

if not settings.debug and settings.secret_key == _DEFAULT_SECRET_KEY:
    warnings.warn(
        "SECRET_KEY is set to the default development value in a non-debug environment. "
        "Set the SECRET_KEY environment variable before deploying.",
        stacklevel=1,
    )
