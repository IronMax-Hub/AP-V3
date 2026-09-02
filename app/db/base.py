from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for every ORM model in the app.

    Domain model modules (app/db/models/<domain>.py) import this and define
    their tables against it, so Alembic's autogenerate can see everything via
    a single target_metadata (Base.metadata) in alembic/env.py.

    Empty at Phase 0 by design — see Docs/MIGRATION_PLAN.md Phase 0 exit
    criteria ("empty Alembic migration history"). Phase 1 (Identity) adds the
    first real models here.
    """
