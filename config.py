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
    ollama_model: str = "gemma4:latest"
    # Larger model used for TDD phase — needs stronger tool-calling ability
    tdd_model: str = "gemma4:31b"

    # Conversation limits
    max_history_messages: int = 50
    max_tokens: int = 4096

    # Root directory where per-project workspace folders are created
    projects_root: Path = Path("./projects")

    class Config:
        env_file = ".env"


settings = Settings()
settings.projects_root = settings.projects_root.resolve()

if not settings.debug and settings.secret_key == _DEFAULT_SECRET_KEY:
    warnings.warn(
        "SECRET_KEY is set to the default development value in a non-debug environment. "
        "Set the SECRET_KEY environment variable before deploying.",
        stacklevel=1,
    )
