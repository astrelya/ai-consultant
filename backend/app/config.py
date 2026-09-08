from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./ai_consultant.db"
    secrets_key: str = ""

    gemini_api_key: str = ""
    default_chat_model: str = "gemini-2.5-pro"
    default_coding_model: str = "gemini-2.5-pro"

    api_host: str = "127.0.0.1"
    api_port: int = 8001
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    workspace_root: str = "./workspaces"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
