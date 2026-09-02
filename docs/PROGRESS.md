# AP-V3 Progress & Backlog

> **Update this file before every commit.** If your commit changes what's done, what's next, or
> surfaces a new problem, that belongs here — not just in the commit message. See
> [`TASK_ASSIGNMENTS.md`](TASK_ASSIGNMENTS.md) for who's working on what right now, and
> [`MIGRATION_PLAN.md`](MIGRATION_PLAN.md) for the phase definitions and reasoning this file
> tracks progress against.

**Last updated:** 2026-09-02 · **Current phase:** Phase 1 (Identity) — not yet started

---

## 1. Status at a glance

| Phase | Scope | Status | Notes |
|---|---|---|---|
| 0 | Foundations (FastAPI skeleton, Docker, Alembic, CI, Celery wiring) | ✅ Done | `fd2e118` |
| 1 | Identity & Access | ⬜ Not started | Hard serialization point — see MIGRATION_PLAN.md §12 |
| 2 | Catalog & Enrollment | ⬜ Not started | Blocked on Phase 1 |
| 3 | Assessment | ⬜ Not started | Blocked on Phase 1+2 |
| 4 | Communication | ⬜ Not started | Blocked on Phase 1–3 |
| 5 | Student Portal (BFF) | ⬜ Not started | Blocked on Phase 1–4 |
| 6 | Integrations | ⬜ Not started | Client scaffolding can start anytime (§12) — build-out blocked on data existing |

Status legend: ⬜ not started · 🔶 in progress · ✅ done · ⛔ blocked (note why)

---

## 2. Phase 0 — Foundations ✅

- [x] `pyproject.toml`, venv, dependency set
- [x] App skeleton: `core/config.py`, `core/logging.py`, `core/celery_app.py`, `core/security.py` (guard stubs, no real lookup yet)
- [x] `/health` endpoint
- [x] Alembic wired to async Postgres, empty baseline revision
- [x] Docker/compose (postgres, redis, api, celery-worker, flower) — **compose config validated, containers not yet run end-to-end** (see Backlog §5)
- [x] Sentry wiring (API + Celery, no-op if `SENTRY_DSN` unset)
- [x] CI workflow (ruff, black, alembic upgrade head, pytest)
- [x] Test scaffold (10/10 passing)
- [x] README

## 3. Phase 1 — Identity & Access ⬜

Scope: `Auth`, `StudentAuth`, `User`, `Role`, `Permission`, `JobRole`, `Student`, `StudentProfile`,
`StudentDegree`, `StudentUniversity`, `Country`, `State`, `InternalNotes`. Full detail:
`MIGRATION_PLAN.md` §5 Phase 1, §6 (auth design), §7.3 (CryptoJS-AES risk).

- [ ] **CryptoJS-AES round-trip spike** — do this first, before anything else in this phase (§7.3)
- [ ] `personal_access_tokens`-equivalent table + model (§6)
- [ ] Wire `get_current_admin`/`get_current_student` in `app/core/security.py` to the real lookup (currently 501 stubs)
- [ ] `User`/`Student` models + Alembic migration
- [ ] RBAC: `roles`/`permissions`/`model_has_roles` port + `Depends(require_permission(...))`
- [ ] Admin login/logout endpoints
- [ ] Student login (2-step) + forgot-password endpoints — **fresh OTP design**, neither AP-V2 OTP mechanism is live (§7.2)
- [ ] Edmingle SSO endpoint (issues a token in the same format as ordinary student login)
- [ ] Phone validation via `phonenumbers`
- [ ] FCM push-token registration
- [ ] Contract tests against `API_SPECIFICATIONS.md` for every endpoint above

## 4. Phase 2–6

Not yet broken into checklists — do that at the start of each phase, mirroring §3's format, once
Phase 1 is far enough along to know the real shape of what's blocked on it.

---

## 5. Backlog

Freeform, dated. Anything discovered mid-work that isn't a clean phase checklist item goes here —
bugs, follow-ups, questions that came up, things deferred on purpose.

- **2026-09-02** — Docker containers were never actually built/run end-to-end in the sandbox this
  scaffolding was built in (no `docker` group membership, no passwordless `sudo`). Compose config
  validated syntactically; `docker compose up --build` + a `curl localhost:8000/health` still needs
  a first real run. Low risk (nothing here is exotic), but worth doing once before Phase 1 work
  starts depending on the Postgres container being trustworthy.
- **2026-09-02** — `Docs/` → `docs/` casing rename happened outside a session; git currently shows
  it as a delete+add pending in the working tree. Will resolve itself as a rename in the next
  commit that touches it — no action needed, noting for anyone confused by `git status`.

---

## 6. Update log

Append a line each time this file changes meaningfully — newest first. Keep it short; git history
has the detail.

- **2026-09-02** — File created. Phase 0 marked done. Phase 1 checklist drafted from
  `MIGRATION_PLAN.md` §5.
