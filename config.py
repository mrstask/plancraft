from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str
    database_url: str = "sqlite+aiosqlite:///./planning.db"
    secret_key: str = "dev-secret-change-in-production"
    debug: bool = True

    # Claude model — quality matters more than cost here
    claude_model: str = "claude-sonnet-4-5"

    # Conversation limits
    max_history_messages: int = 50   # messages kept in Claude context
    max_tokens: int = 4096

    class Config:
        env_file = ".env"


settings = Settings()
