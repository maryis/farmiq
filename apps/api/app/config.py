from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = "sqlite+aiosqlite:///./farmiq.db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "development-only-change-me"
    jwt_ttl_minutes: int = 720
    auto_create_db: bool = True
    seed_demo: bool = True
    cors_origins: str = "http://localhost:3000"

    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str = "Qwen/Qwen3-8B"
    embedding_base_url: str | None = None
    embedding_api_key: str | None = None
    embedding_model: str = "Qwen/Qwen3-Embedding-0.6B"

    lely_api_base_url: str | None = None
    lely_token_url: str | None = None
    lely_client_id: str | None = None
    lely_client_secret: str | None = None
    lely_scope: str | None = None
    lely_animals_path: str = "animals"
    lely_ruminations_path: str = "ruminations"
    lely_activities_path: str = "activities"
    lely_milk_visits_path: str = "milkvisitsquality"
    lely_feed_visits_path: str = "feedvisits"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
