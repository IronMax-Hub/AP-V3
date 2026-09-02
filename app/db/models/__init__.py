# Domain model modules land here one per bounded context, in the phase order
# set out in Docs/MIGRATION_PLAN.md §5:
#   identity.py            (Phase 1)
#   catalog_enrollment.py  (Phase 2)
#   assessment.py          (Phase 3)
#   communication.py       (Phase 4)
#   student_portal.py      (Phase 5)
#   integrations.py        (Phase 6)
#
# Each module imports app.db.base.Base and defines its tables against it.
# Import every model module here once it exists, so Alembic's autogenerate
# (target_metadata = Base.metadata in alembic/env.py) can see it.
