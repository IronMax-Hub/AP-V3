import sentry_sdk
from fastapi import FastAPI
from sentry_sdk.integrations.fastapi import FastApiIntegration

from app.api.health import router as health_router
from app.core.config import get_settings
from app.core.logging import configure_logging


def _init_sentry(settings) -> None:
    """No-op if SENTRY_DSN is unset (e.g. local dev) — MIGRATION_PLAN.md §3."""
    if not settings.sentry_dsn:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        integrations=[FastApiIntegration()],
        traces_sample_rate=0.1,
    )


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    _init_sentry(settings)

    app = FastAPI(
        title="AP-V3 — Assignment Portal API",
        description="FastAPI/SQLAlchemy/Postgres rewrite of the Laravel Assignment Portal API. "
        "See Docs/MIGRATION_PLAN.md for the migration plan and phase-by-phase scope.",
        version="0.1.0",
        debug=settings.debug,
    )

    app.include_router(health_router)

    # Domain routers are registered here as each phase in
    # Docs/MIGRATION_PLAN.md §5 lands, e.g.:
    #   from app.domains.identity.router import router as identity_router
    #   app.include_router(identity_router, prefix="/v1")

    return app


app = create_app()
