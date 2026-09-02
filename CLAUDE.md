# AP-V3 — project instructions

Migration of the Laravel `Lawsikho-Assignment-Portal-API` to FastAPI/SQLAlchemy/PostgreSQL. Full
plan, phasing, and every architecture decision: `docs/MIGRATION_PLAN.md`. Source-system reference:
`AP-V2 Reference Documentation/`.

## Before every commit in this repo

Update these two files if the commit changes anything they track — what's done, what's next, who's
working on what, or a newly discovered problem:

- `docs/PROGRESS.md` — phase/task checklist status and backlog.
- `docs/TASK_ASSIGNMENTS.md` — who (Mayukh / Chhandak) is currently working on what.

This applies to every commit that touches project code or docs, not just ones that "feel" like
milestones. A commit that doesn't move either file's content should be rare enough to be worth a
second look, not the default.

## Compatibility mandate

This is a migration, not a redesign — API request params and response shapes must not change
(`docs/MIGRATION_PLAN.md` §2 principle 5). Verify any ported endpoint against
`AP-V2 Reference Documentation/API_SPECIFICATIONS.md` before considering it done.
