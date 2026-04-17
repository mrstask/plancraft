from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./planning.db"
    secret_key: str = "dev-secret-change-in-production"
    debug: bool = True

    # Ollama settings
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "gemma4:latest"

    # Conversation limits
    max_history_messages: int = 50
    max_tokens: int = 4096

    class Config:
        env_file = ".env"


settings = Settings()
