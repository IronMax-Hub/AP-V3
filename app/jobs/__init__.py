# Background task modules land here one per bounded context, mirroring
# app/db/models/. Ports AP-V2's real "event bus" — direct job dispatch on a
# business occurrence (see Docs/MIGRATION_PLAN.md §4 and §7.7) — not the dead
# formal-Events/webhook-catalog layer, which is explicitly out of scope.
