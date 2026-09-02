from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central app configuration, sourced from environment / .env.

    See Docs/MIGRATION_PLAN.md §3/§6 for why each of these exists.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"
    debug: bool = True
    app_name: str = "ap-v3"

    # Postgres (async, asyncpg driver) — MIGRATION_PLAN.md §3
    database_url: str = "postgresql+asyncpg://ap:ap@localhost:5432/ap_v3"

    # Redis / Celery — MIGRATION_PLAN.md §7.7 (Celery + Redis + Flower, decided)
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None

    # Sentry — MIGRATION_PLAN.md §3
    sentry_dsn: str | None = None

    # Auth — MIGRATION_PLAN.md §6 (Sanctum-compatible Personal Access Tokens, not JWT)
    # Secret used to hash issued tokens before storing them (never store plaintext).
    token_hash_secret: str = "change-me-in-env"

    # CryptoJS-AES compatibility — MIGRATION_PLAN.md §7.3 (highest-risk item, Phase 1)
    # Mirrors AP-V2's APP_PASS_PHRASE, used to derive the EVP_BytesToKey AES key
    # for the student login password pre-encryption round-trip.
    app_pass_phrase: str = "change-me-in-env"

    @property
    def resolved_celery_broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def resolved_celery_result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
