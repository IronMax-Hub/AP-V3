import sentry_sdk
from celery import Celery
from sentry_sdk.integrations.celery import CeleryIntegration

from app.core.config import get_settings

settings = get_settings()

# Same Sentry project as the API process (MIGRATION_PLAN.md §3) — no-op if unset.
if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        integrations=[CeleryIntegration()],
        traces_sample_rate=0.1,
    )

# Celery + Redis + Flower — decided, MIGRATION_PLAN.md §7.7.
# Queues partitioned per bounded context (not just priority-tiered like AP-V2's
# Horizon setup) so one domain's backlog can't starve another's. Priority
# sub-tiers can still be layered within a domain queue later if needed.
celery_app = Celery(
    "ap_v3",
    broker=settings.resolved_celery_broker_url,
    backend=settings.resolved_celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_default_queue="default",
    task_queues=None,  # left implicit; explicit Queue objects added as domains land
    task_routes={
        "app.jobs.identity.*": {"queue": "identity"},
        "app.jobs.catalog_enrollment.*": {"queue": "enrollment"},
        "app.jobs.assessment.*": {"queue": "assessment"},
        "app.jobs.communication.*": {"queue": "communication"},
        "app.jobs.integrations.*": {"queue": "integrations"},
    },
)

# Task modules are registered here as each phase in MIGRATION_PLAN.md §5 lands.
# Empty on purpose at Phase 0 — see app/jobs/__init__.py.
celery_app.autodiscover_tasks(["app.jobs"])
