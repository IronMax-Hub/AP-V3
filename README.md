# AP-V3

A new version of Assignment Portal — a FastAPI/SQLAlchemy/PostgreSQL rewrite of the Laravel-based
`Lawsikho-Assignment-Portal-API`.

- Migration plan, phasing, and every architecture decision: [`Docs/MIGRATION_PLAN.md`](Docs/MIGRATION_PLAN.md).
- Source-system reference docs (schema, business rules, API contracts, bounded-context audit):
  [`AP-V2 Reference Documentation/`](<AP-V2 Reference Documentation>).

**Compatibility mandate:** this is a migration, not a redesign — API request params and response
shapes must not change (`Docs/MIGRATION_PLAN.md` §2 principle 5). Verify any endpoint you port
against `AP-V2 Reference Documentation/API_SPECIFICATIONS.md` before considering it done.

## Stack

FastAPI · SQLAlchemy 2.0 (async, `asyncpg`) · Alembic · PostgreSQL · Pydantic v2 · Celery + Redis +
Flower · Sanctum-compatible Personal Access Tokens (not JWT — see `Docs/MIGRATION_PLAN.md` §6) ·
`pytest` + `pytest-asyncio` + `httpx`.

## Project layout

```
app/
  main.py              # FastAPI app factory
  core/                # settings, logging, DB session, Celery app, auth scaffolding
  db/
    base.py             # SQLAlchemy declarative base
    models/              # one module per bounded context, added phase by phase
  domains/
    identity/             # Phase 1
    catalog_enrollment/    # Phase 2
    assessment/             # Phase 3
    communication/           # Phase 4
    student_portal/          # Phase 5
    integrations/              # Phase 6
  jobs/                # Celery task modules, one per bounded context
alembic/               # migrations
tests/
```

Phase order and the reasoning behind it (coupling data, not folder aesthetics) is in
`Docs/MIGRATION_PLAN.md` §5.

## Local development

### Option A — Docker Compose (closest to how it'll run in CI/prod)

```bash
cp .env.example .env   # fill in real secrets for TOKEN_HASH_SECRET / APP_PASS_PHRASE
docker compose up --build
```

This starts Postgres, Redis, the API (after running `alembic upgrade head`), a Celery worker, and
Flower (`http://localhost:5555`). API is at `http://localhost:8000`, docs at
`http://localhost:8000/docs`.

### Option B — Local virtualenv

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env   # point DATABASE_URL/REDIS_URL at local or docker-compose-exposed services

alembic upgrade head
uvicorn app.main:app --reload
```

Run a Celery worker separately if you need background jobs locally:

```bash
celery -A app.core.celery_app.celery_app worker --loglevel=info
```

## Tests, lint, migrations

```bash
pytest                      # tests/
ruff check .                # lint
black --check .             # format check (drop --check to auto-format)
alembic revision -m "..."   # new migration (add --autogenerate once real models exist)
alembic upgrade head        # apply migrations
```

CI (`.github/workflows/ci.yml`) runs all of the above (plus `alembic upgrade head` against a
throwaway Postgres) on every push/PR to `main`/`development`.

## Environment variables

See `.env.example` for the full list. Two are worth calling out because they're not obviously
guessable from their name:

- `TOKEN_HASH_SECRET` — keys the hash used to store issued Personal Access Tokens (never the
  plaintext). See `Docs/MIGRATION_PLAN.md` §6.
- `APP_PASS_PHRASE` — mirrors AP-V2's key for the CryptoJS-AES student-login password
  pre-encryption round-trip. See `Docs/MIGRATION_PLAN.md` §7.3 — this is flagged as the
  highest-risk single item in the whole migration; get the round-trip test passing before
  building anything else in Phase 1.
