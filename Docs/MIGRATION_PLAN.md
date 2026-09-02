# AP-V3 Migration Plan — Assignment Portal API (Laravel → FastAPI)

> **Status:** Draft for review — no code written yet.
> **Source system:** `Lawsikho-Assignment-Portal-API` (Laravel 8.75, branch `New-Dummy-Prod-0605`), as described in `AP-V2 Reference Documentation/`.
> **Method:** This plan is built directly from the coupling data, schema audit, business-rule audit, and event-system audit already captured in that documentation folder — not from the module folder structure, which the source docs explicitly warn is not a real dependency graph (every `module.json`'s `requires` array is empty).

---

## 1. Executive summary

AP-V2 is a single-deployable Laravel modular monolith: 62 "modules," one MySQL database, one Redis instance, no per-module isolation. `CONTEXT_MAP.md` measured 377 real cross-module import edges and found a **near-complete mesh** — `Enrollment`, `Student`, and `Course` function as a de facto shared kernel that 30+ other modules depend on directly, and `Enrollment` and `Course`/`CourseBatch` are in a near-symmetric dependency **cycle** (22↔20 edges), not a layered relationship.

That has two direct consequences for this migration:

1. **Do not attempt a clean microservice-style migration.** `SERVICE_BOUNDARIES.md` §4 already scored this: only the Integrations context (`AtsAPI`, `AgenticSupportSystem`, `LawSikho`) is extraction-ready today. Everything else shares one schema with no ownership boundary. AP-V3 should ship as **one well-modularized FastAPI monolith first** (routers/services per bounded context, one Postgres database), matching the architecture we're actually capable of building safely, not an aspirational microservice topology.
2. **Phasing has to follow the coupling graph, not the module list.** Identity is the only context nothing else can be built without. Enrollment and Learning/Catalog cannot be built as separate phases — they have to land together. Assessment is a genuinely separable pipeline (`Assignment → StudentAssignment → Result`, 51 inbound edges but high internal cohesion) and can follow. Communication is a federation of independent verticals and can be parallelized. Integrations is a thin consumer and comes last.

12 of 62 modules (`Class`, `ClassCSAT`, `StudentClasses`, `Forum`, `StudentForum`, `ProjectManagement`, `StudentTasks`, `PerformanceCoach`, `PerformanceCoachCSAT`, `StudentPerformanceCoach`, `BookMaster`, `BookDeliveryLog`) are confirmed dead in product terms (team-confirmed, 2026-08-29) and are **out of scope for AP-V3** — see §9. The formal event/webhook-subscription system (`EVENT_LIST.md`) is also 100% disabled in production; the real "event bus" is direct job dispatch, and that's the pattern AP-V3 should port, not the dead formal-events layer.

---

## 2. Guiding principles

1. **Port behavior, not code shape.** This is a rewrite (Eloquent → SQLAlchemy, sync PHP-FPM → async FastAPI), not a transliteration. Where the source docs identify something as a bug, a dead code path, or an unimplemented proposal (§8), AP-V3 should not reproduce it faithfully — it should fix it, unless there's a data-compatibility reason not to.
2. **The coupling graph is the project plan.** Every phase boundary below is justified by a specific in-degree/out-degree number from `CONTEXT_MAP.md`/`BOUNDED_CONTEXT_*.md`, not by aesthetic module grouping.
3. **One schema, modularized code.** Postgres schema mirrors the "one database" reality of the source system. Code is organized into domain packages (`app/domains/identity`, `app/domains/enrollment`, …) with routers, services, and Pydantic schemas per domain — internal-only boundaries enforced by import discipline and lint rules, not by network calls.
4. **Never build against a source-doc claim you haven't re-verified against current code.** The reference docs themselves say this repeatedly — they're a snapshot from 2026-08-29, and several root-level planning docs in the source repo were found to describe features that were never built. Treat `AP-V2 Reference Documentation/` as the starting map, not ground truth to port blindly. Before implementing any specific rule, re-check it against the actual AP-V2 source if/when that repo is available.
5. **API compatibility is the primary goal — not just where it's load-bearing.** This is a settled team decision, not a default: *"Our main goal here is to migrate the API's code and data in such a way that neither the API param nor the API response changes a bit."* A separate Admin API consumer frontend depends on this contract. This overrides the earlier draft's instinct to "standardize" inconsistent response envelopes, quirky status codes, or the guard-dependent 401 body shape — **all of that inconsistency ships forward into AP-V3 unchanged**, verified endpoint-by-endpoint against `API_SPECIFICATIONS.md`. The only compatibility exception the team has explicitly carved out is internal code organization (§7.2 item 4) and the auth token's *implementation* (still emits the same `Authorization: Bearer {id}|{token}` wire format — see §6). Cleanup is still welcome *underneath* an unchanged contract (fixing the `assignment_id` naming internally, adding real Postgres FK constraints, partitioning queues) — never *in* the contract itself.

---

## 3. Target architecture

| Concern | AP-V2 (Laravel) | AP-V3 (this plan) |
|---|---|---|
| Framework | Laravel 8.75 | FastAPI |
| ORM | Eloquent | SQLAlchemy 2.0, async engine, `asyncpg` driver |
| Migrations | Laravel migrations | Alembic |
| Database | MySQL | PostgreSQL |
| API docs | Hand-maintained `API_SPECIFICATIONS.md` | Auto-generated OpenAPI/Swagger |
| Schemas/validation | Laravel Form Requests | Pydantic v2 |
| Task queue | Redis + Horizon (priority-tiered, not per-domain — flagged as a gap to fix, §7.7) | Celery + Redis + Flower, queues partitioned per domain (§7.7 — decided) |
| Admin auth | Sanctum | **Sanctum-compatible Personal Access Tokens** (decided — not JWT), via `Depends()`; see §6 |
| Student auth | Sanctum + a second guard (JWT/Edmingle claims never actually used — `tymon/jwt-auth` was installed-but-dead in AP-V2) | Same Sanctum-compatible PAT scheme, second `Depends()` chain, separate token/claim namespace |
| RBAC | `spatie/laravel-permission`, admin-only (student guard has none) | Port the `roles`/`permissions`/`model_has_roles` tables directly, checked via `Depends(require_permission(...))` |
| Back-office admin UI | None (separate Admin API consumer) | **None — decided.** The Admin API consumer stays a separate frontend project, unchanged. SQLAdmin is not being adopted; scope is API + data parity, not new UI surface |
| File storage | Flysystem → S3 | `aioboto3` or `s3fs` |
| Media attachments | `spatie/laravel-medialibrary` | Port the existing polymorphic media table schema + Pillow |
| PDF generation | `laravel-mpdf` | WeasyPrint |
| Excel import/export | `maatwebsite/excel` | `openpyxl` / `pandas` |
| Tagging | `spatie/laravel-tags` (JSON-locale `name` column — see §7.2 landmine) | Plain join table |
| Audit log | `spatie/laravel-activitylog` | Custom audit middleware (evaluate SQLAlchemy-Continuum only if full version history, not just an event log, is actually needed) |
| Error monitoring | `sentry-laravel` | `sentry-sdk[fastapi]`, same Sentry project |
| Outbound integrations | Guzzle + OAuth | `httpx` (async) + `authlib` |
| CryptoJS-AES payload compat | `cryptojs-aes-php` | `pycryptodome` — **round-trip this first, before any other Identity work** (§7.3) |
| Phone validation | `laravel-phone` | `phonenumbers` |
| Testing | PHPUnit | `pytest` + `pytest-asyncio` + `httpx.AsyncClient` |
| Containers | Docker + nginx + PHP-FPM | Docker + nginx (unchanged) + uvicorn/gunicorn workers |

### 3.1 Project structure (proposed)

```
app/
  main.py                    # FastAPI app, router registration, middleware
  core/                      # settings, DB session, security primitives, exceptions
  db/
    base.py                  # SQLAlchemy declarative base, session factory
    models/                  # one module per bounded context, mirroring §5 phases
  domains/
    identity/                # Auth, StudentAuth, User, Role, Permission, JobRole,
                              # Student, StudentProfile, StudentDegree, StudentUniversity,
                              # Country, State, InternalNotes
    catalog_enrollment/       # Course*, CourseBatch, Package, Bootcamp, Evaluator, Topic,
                              # Enrollment, RevenueAPI, ReferralSystem, StudentFrontendEnrollment
    assessment/               # Assignment*, StudentAssignment, Result, AIEvaluation, StudentResults
    communication/             # AssignmentCSAT, EvaluatorCSAT, NPS, Notification, EmailTemplate, Webhook
    student_portal/            # StudentDashboard*, StudentMyCourses, StudentNotifications, StudentBookACall
    integrations/               # AtsAPI, AgenticSupportSystem, LawSikho
  jobs/                        # background task definitions (see §7.7)
alembic/
tests/
  contract/                    # parity tests against AP_SPECIFICATIONS.md-documented behavior
```

Each `domains/<x>/` package holds `router.py`, `service.py`, `schemas.py`, `models.py` (or imports from `db/models/`). Cross-domain calls go through the other domain's `service.py`, never straight through its ORM models — this is the one place we deliberately impose a discipline AP-V2 never had (§1's "shared-kernel monolith, not bounded contexts" finding), so that a future extraction (per `SERVICE_BOUNDARIES.md`) is at least possible later.

---

## 4. What NOT to migrate

Confirmed dead in product terms (`CONTEXT_MAP.md` §3/§5, team-confirmed 2026-08-29) — **excluded from AP-V3 entirely**:

`Class`, `ClassCSAT`, `StudentClasses`, `Forum`, `StudentForum`, `ProjectManagement`, `StudentTasks`, `PerformanceCoach`, `PerformanceCoachCSAT`, `StudentPerformanceCoach`, `BookMaster`, `BookDeliveryLog`.

This is a data-modeling decision, not just a feature decision — see §9 for how their still-live relationships from `Student`/`Enrollment` get handled during data migration.

Also **not ported as designed**: the formal webhook-event-catalog mechanism (`WebhookTriggered`, 30 named business events, DB-backed subscription/retry model) — `EVENT_LIST.md` confirms **all 53 trigger call sites are commented out**, zero live. AP-V3 should port the pattern that's actually alive today — direct background-job dispatch on business occurrences (§7.7) — and treat "a real pub/sub business-event bus" as a post-MVP epic if the product ever wants external webhook subscribers, not a day-one requirement.

---

## 5. Phasing (by coupling, not by module folder)

Each phase is scoped so nothing in it depends on a module from a later phase. Sizes are approximate module counts, not effort estimates — Enrollment/Catalog will dominate the timeline regardless of module count, because it's the shared kernel.

### Phase 0 — Foundations (no product code)
FastAPI skeleton, Docker/compose, Alembic baseline against a fresh Postgres schema, config/settings module, Sentry wiring, CI (lint + `pytest`), base `Depends()` auth scaffolding (Sanctum-compatible PAT lookup plumbing, no real login logic yet), Celery+Redis+Flower wiring (empty task registry). Exit criteria: a deployable "hello world" FastAPI app with health check, structured logging, and empty Alembic migration history that CI runs against.

### Phase 1 — Identity & Access
`Auth`, `StudentAuth`, `User`, `Role`, `Permission`, `JobRole`, `Student`, `StudentProfile`, `StudentDegree`, `StudentUniversity`, `Country`, `State`, `InternalNotes`.

Why first: every other context reads `Student`/`User` directly (`Student` is the system's #2 in-degree module at 33 dependents; `BOUNDED_CONTEXT_IDENTITY.md` calls it a de facto shared kernel). Nothing else can be meaningfully built or tested without real identities and both auth chains working.

Includes: CryptoJS-AES round-trip (§7.3, do this literally first — it's the highest-risk single item in the whole plan), the Sanctum-compatible PAT scheme (§6 — two guards, two `Depends()` chains, same token mechanism, mirroring the two-guard split in AP-V2), RBAC port (`roles`/`permissions`/`model_has_roles` tables → `Depends(require_permission(...))`), phone validation via `phonenumbers`, FCM push-token registration.

Exit criteria: both login flows (admin, student — including the OTP path, and picking one of the two OTP mechanisms per §7.2) work end-to-end against a migrated Postgres copy of real user/student data; RBAC gate proven on at least one protected admin route.

### Phase 2 — Catalog & Enrollment (the big one — built together, not sequentially)
`Course`, `CourseBatch`, `CourseCategory`, `CourseCategoryCriteria`, `CourseCriteria`, `CourseFaq`, `CoursePlanType`, `CourseCompletionMaster`, `Topic`, `Package`, `Bootcamp`, `Evaluator` **+** `Enrollment`, `RevenueAPI`, `ReferralSystem`, `StudentFrontendEnrollment`.

Why together: `BOUNDED_CONTEXT_LEARNING.md` §5 measured this precisely — 22 edges Enrollment→Learning, 20 Learning→Enrollment, "a real cycle, not a layering... treat 'Course catalog' and 'Enrollment' as one tightly-coupled unit for change-impact purposes, regardless of which document they're filed under." Building one before the other means building throwaway stubs for half the phase.

This phase also has to resolve `StudentFrontendEnrollment`'s scope drift (§7.6) — decide in AP-V3's design whether student-facing CSAT/NPS/Notification/Task endpoints live in `catalog_enrollment` or their "proper" home domain, and pick one, rather than porting the duplication forward.

Exit criteria: full enrollment lifecycle (create → activate → pause → resume → deactivate) working against real catalog data, including the inbound Revenue/Billing webhook receiver and Edmingle batch sync stub (real integration wiring can follow in a later pass — see §7.5).

### Phase 3 — Assessment
`Assignment`, `AssignmentTag`, `StudentAssignment`, `Result`, `AIEvaluation`, `StudentResults`. (`AssignmentSendingLog` excluded — `DATABASE_SCHEMA.md` confirms its tables are dead code, every write site commented out.)

Why third: `BOUNDED_CONTEXT_ASSESSMENT.md` calls this "the most internally cohesive of the 6 contexts... a genuine grading pipeline," with 51 inbound edges from elsewhere but a tight internal mesh of just 4-5 modules. It depends on Phase 1 (who submitted) and Phase 2 (which course/batch it's attached to) but nothing later.

Must implement the `results.assignment_id → student_assignments.id` FK correctly from day one (§7.1) — this is the single most concrete landmine in the whole source system, and getting it wrong here means every downstream report/dashboard is silently wrong.

Exit criteria: submission → evaluator grading → AI-evaluation-webhook path all working, with the correct FK model and the two AI-evaluation webhook endpoints resolved to one canonical implementation (§8).

### Phase 4 — Communication (parallelizable internally)
`AssignmentCSAT`, `EvaluatorCSAT`, `NPS`, `Notification`, `EmailTemplate`, `Webhook`.

`BOUNDED_CONTEXT_COMMUNICATION.md` found only 2 intra-context edges across 9 modules — "several small services wearing one label." Each CSAT vertical and NPS can be built independently once Phase 1–3 land, by different people at the same time, without stepping on each other. Resolve NPS v1/v2 (§8) to one schema rather than porting both. `Webhook` here means the generic outbound dispatch primitive only (used by 11+ other modules) — the dead business-event catalog itself is out of scope (§4).

### Phase 5 — Student Portal (BFF layer)
`StudentDashboard`, `StudentDashboardManagement`, `StudentMyCourses`, `StudentNotifications`, `StudentBookACall`.

These are aggregation layers by design (high fan-out, low fan-in — `CONTEXT_MAP.md` §4) that read across every prior phase. Building them last means the underlying domain APIs they aggregate already exist and are stable.

### Phase 6 — Integrations
`AtsAPI`, `AgenticSupportSystem`, `LawSikho`.

Ironically the *easiest* context to extract (`SERVICE_BOUNDARIES.md` §4: 29 outbound edges, only 2 inbound) but it can only be **finished** last because it's a pure consumer of everything else — `AgenticSupportSystem` alone reads 17 modules across 4 other contexts. Its outbound-gateway shape means the actual client code (httpx + authlib wrappers for ATS/Agentic Support/LawSikho ingestion) could be scaffolded early in parallel, but wiring real endpoints has to wait for the data it reads to exist.

---

## 6. Auth strategy (detail) — decided: Sanctum-compatible tokens, not JWT

**Decision (settled):** AP-V3 does not switch to JWT. Authentication stays stateful, matching Sanctum's model and — critically — its wire format, so the existing Admin API consumer frontend needs zero changes to how it sends the `Authorization` header. This also simplifies revocation: no refresh-token rotation, no denylist table, because every request is checked against a live DB row, so revocation is immediate by construction (delete/disable the row) rather than something that has to wait out a JWT's lifetime.

**Token format:** `Authorization: Bearer {id}|{token}` — same shape Sanctum emits today (`{personal_access_token.id}|{plaintext_token}`). The `id` prefix lets the server look up the specific token row by primary key before hashing/comparing, rather than scanning every stored hash.

**Storage:**
- A `personal_access_tokens`-equivalent table: `id`, `tokenable_type`/`tokenable_id` (or two explicit FK columns, one per guard, since AP-V3 keeps admin/student as two distinct tables rather than introducing Sanctum's polymorphic pattern — see below), `token_hash` (store only a secure hash, e.g. SHA-256, never the plaintext), `name`/`abilities` if scoping is needed, `expires_at` (nullable — supports both never-expiring and time-boxed tokens), `last_used_at`, `created_at`.
- **Two guards, two dependency chains, same underlying token mechanism** — matching AP-V2's real two-guard split (`BOUNDED_CONTEXT_IDENTITY.md` §6/§8: admin `User` and `Student` are unrelated models with no shared "person" concept, and that's real product behavior worth preserving, not a gap to fix). `Depends(get_current_admin)` and `Depends(get_current_student)` both look up the same token-table shape, scoped to the correct tokenable type, and reject a token issued for the other guard.
- **RBAC:** unchanged from the original plan — `Depends(require_permission("permission.name"))` on the admin chain only, reading the ported `roles`/`permissions`/`model_has_roles` tables. Student guard has no RBAC layer, matching AP-V2.

**Revocation (per the team's proposed design):**
- Single-session logout: delete/disable that one token row.
- Logout-everywhere / password reset / account suspension: bulk-revoke every token row belonging to that user/student — mirrors AP-V2's `$user->tokens()->delete()` pattern (confirmed in `API_SPECIFICATIONS.md` for student logout).
- Expiry: `expires_at` supported per-token, but not required — AP-V2 tokens never expire by default unless revoked, and AP-V3 should preserve that default rather than silently introducing forced expiry, since that would be an observable behavior change for existing clients.

**Edmingle SSO:** in AP-V2 this goes through the ordinary student Sanctum guard (`CONTEXT_MAP.md` §6 — `tymon/jwt-auth` was installed but never used for this). Port SSO validation as its own endpoint that issues a token in the same format as ordinary student login — no separate token type.

**Webhook/integration auth (Phase 6):** AP-V2 uses static shared-secret bearer tokens for `AgenticSupportSystem`/`LawSikho` (not Sanctum) — port as a separate `Depends(verify_static_token)`, kept out of both PAT guard chains, unchanged.

---

## 7. Risk register

Ordered by how much damage getting it wrong silently does, not by implementation order.

### 7.1 `results.assignment_id` FK trap — HIGH, silent-failure risk
Every column literally named `assignment_id` in the Assignment/Evaluation domain (`results.assignment_id`, `assignment_csat_form.assignment_id`, `course_featured_assignment_mapping.assignment_id`, etc.) is a foreign key to **`student_assignments.id`**, not `assignments.id`. Only exception: `assignment_log_mapping.assignment_id` (itself dead code). Get this wrong in the SQLAlchemy model and every join silently returns wrong-but-plausible data instead of erroring. **Mitigation:** name the SQLAlchemy relationship/column something unambiguous in the new schema (e.g. `student_assignment_id`) rather than porting the confusing original name forward — this is exactly the kind of cosmetic-but-load-bearing cleanup §2 principle 1 argues for.

### 7.2 Ambiguities from the audit — resolved by the team
All five were open questions in the draft; the team has now settled each:

1. **Dual OTP mechanisms** on `students` (`verification_otp` vs newer `otp`/`otp_expire_at`) — **neither is actually live**. Do not port either column/mechanism as-is; design one fresh OTP flow for AP-V3's forgot-password path. Since neither is load-bearing today, this is one of the few places where "unchanged API response" doesn't constrain the internal implementation — confirm with the team whether the *response shape* of the OTP endpoints (token format, field names in `API_SPECIFICATIONS.md`) still needs to match, even though the underlying mechanism is being rebuilt.
2. **NPS v1 vs v2** — **both are live, but asymmetrically.** `nps_form` (v1) is shown in the frontend menu as deprecated but still holds real historical data; `nps_form_v2` is the actual live write path today. **Action:** migrate v1's historical data (read/archival only — no new v1 submission endpoints in AP-V3) and build full NPS functionality only against the v2 schema. Any AP-V3 endpoint that currently reads from v1 for display purposes needs to keep working against the migrated v1 data; don't drop v1 data even though it's not written to going forward.
3. **`ai-assignments/webhook` (unauthenticated)** — **confirmed live and used in production.** Per §2 principle 5 (unchanged API contract), this endpoint ships forward **unauthenticated, exactly as-is** — this reverses the draft's §7.8 recommendation to fix it during migration. Track it as an accepted, known risk (documented here and in the code) rather than silently closing it; if the team wants to add auth later, that's a deliberate follow-up change to the API contract, not part of this migration.
4. **`StudentFrontendEnrollment`'s scope drift — intentional, but reorganize internally.** The CSAT/NPS/Notification/Task controllers hosted there are meant to be there today, but in AP-V3 they should move to their proper domain packages (Communication, Assessment, Student Portal per §5's phase groupings) as an **internal code-organization change only**. Per §2 principle 5, the actual route paths and response shapes must stay identical — this is a `domains/` package reassignment, not an API redesign. Call this out explicitly in Phase 2/4 planning so whoever picks up each route knows the URL is fixed even though the file that implements it has moved.
5. **`AssignmentTag`'s JSON-locale tag storage** — this was a consequence of using `spatie/laravel-tags` (which stores `name` as a JSON multi-locale blob) rather than a deliberate design choice; the team confirmed any equivalent plain-tagging approach is fine. Confirms the original plan (§3): a plain join table with a plain-text tag name column, no JSON-locale encoding carried forward. The one place this needs care: any *stored data* keyed on the literal JSON string (e.g. `Enrollment`'s refund-eligibility check, `'{"en":"Refund Eligible"}'`) needs its ETL step to normalize existing tag rows to plain text as part of migration, not just the schema going forward.

### 7.3 CryptoJS-AES password payload — HIGH, do first
Student login step 2 requires the client to pre-encrypt the password (OpenSSL `aes-256-cbc`, key derived EVP_BytesToKey-style from `APP_PASS_PHRASE`) before sending it. This is the one place AP-V3 cannot simply "clean up" — web/mobile clients already implement this independently. **Action:** build a standalone `pycryptodome` round-trip test against real AP-V2-encrypted payloads (or the PHP `cryptojs-aes-php` library directly) in Phase 0/1, before any other Identity work, per the original tech-stack table's own flag on this row.

### 7.4 Confirmed-broken source artifacts — don't port the brokenness
- `webhooks` table has two identical CREATE migrations (`CreateWebhooksTable`/`CreateWebhooksTableV2`) — a leftover, not a deliberate schema. Port one clean table.
- `enrollments.deactivation_status` has a commented-out historical backfill — pre-migration rows all read `NORMAL_DEACTIVATION` regardless of real history. **The ETL (§10) needs an explicit decision**: carry this known-wrong value forward as-is (documented as a known data-quality gap), or attempt a real backfill from other signals if the business needs it corrected during migration.
- `enrollment_pause_log_new.accepted`/`.rejected` don't exist in the live schema despite being read by a resource class — don't model these columns in AP-V3 at all; the concept these were meant to capture may need a fresh design if the product actually wants it.
- A commented-out performance-index migration on `results`/`student_assignments`/`result_exercise_scores`/`assignments` was never applied — don't assume those indexes exist; **do** add the equivalent indexes for real in the new Postgres schema, since there's no reason to carry forward a missed optimization.

### 7.5 Live-but-fragile external integrations
Several integrations have real ambiguity in AP-V2 itself (`CONTEXT_MAP.md` §7): Edmingle credential env vars aren't clearly named, `COURSE_CALENDER_API_URL` is a misspelled key that's nonetheless load-bearing, `sql_migration`/`staging` are direct cross-database reads into another system's live schema with zero contract (`SERVICE_BOUNDARIES.md` §2 — read-only today, but worth explicitly retiring rather than porting forward as a pattern). Each external integration should get its own small discovery pass (confirm real base URLs/credentials with the team) at the start of the phase that owns it, not assumed from `.env` variable names alone.

### 7.6 Unenforced "FK-shaped" columns
Confirmed instances (`students.country_id`, `enrollments.bootcamp_id`, `course_categories.parent_id`, several `*_csat_form_reason.parent_id` columns, `course_job_mappings.course_id`, etc.) are integer columns with no real FK constraint in AP-V2 — meaning production data may already contain orphaned references. **Action:** before adding real Postgres FK constraints (recommended — this is a place worth fixing, not porting forward), the ETL step (§10) must audit and report on orphaned rows in these columns so the team can decide how to handle each one (null out, delete, or backfill) rather than having the import fail opaquely.

### 7.7 Task queue: decided — Celery + Redis + Flower
Horizon's queues in AP-V2 are priority-tiered (`default`, `default_high`, `default_medium`, `default_long`) — not partitioned by domain, which `SERVICE_BOUNDARIES.md` §5 flags as something to fix before any future extraction. **Decision: Celery + Redis + Flower** — closest like-for-like replacement for Horizon's priority-queue-plus-dashboard model, mature ecosystem, well-understood ops story, works fine called from async FastAPI route handlers (dispatch via `.delay()`/`.apply_async()`, don't block the event loop). Partition queues **by domain** from day one (`identity`, `enrollment`, `assessment`, `communication`, `integrations`) rather than by priority tier only, addressing the gap the source docs flagged; keep priority sub-tiers within each domain queue if the equivalent of `_high`/`_medium`/`_long` distinctions still matter operationally.

Port the **job-dispatch pattern**, not the dead formal-Events layer (§4) — `EVENT_LIST.md`'s 128-job inventory (`EnrollmentActivatedJob`, `CreateEdmingleBatch`, `EvaluateStudentAssignmentJob`, etc.) is the real list of background work to replicate as Celery tasks, one per phase as that phase is built.

### 7.8 Security items — one accepted risk, one to close
- The AI-evaluation webhook (`POST /api/v1/ai-assignments/webhook`) has no auth middleware in AP-V2. **Per §7.2 item 3, this ships forward unchanged** — confirmed live/used, and the migration's compatibility mandate (§2 principle 5) takes precedence. Document it as a known, accepted risk in the AP-V3 codebase (a code comment plus an entry in whatever security backlog the team keeps) rather than silently fixing it or silently forgetting about it.
- A hardcoded-looking API key default exists in AP-V2's `config/services.php` (`EXTERNAL_PORTAL_UPDATE_API_KEY`) — this is a **secret-value** concern, not an API-contract concern, so it's still fine to rotate/not-reuse in AP-V3 config without violating the compatibility mandate.

---

## 8. Explicitly not implementing (proposed-but-never-built features)

`BUSINESS_RULES.md` found three root-level planning documents in the source repo describe features that were never actually built: **CR-10 course pause/refund waiver** (45-day window logic, self-service waiver-and-pause), **enrollment/batch capacity limits** (no cap exists anywhere today), and the **KYC verification gate** on certificate downloads. None of these should be treated as "the real spec to port" — if the product wants any of them in AP-V3, that's new-feature scoping, not migration, and should be raised separately rather than assumed as in-scope here.

---

## 9. Data migration approach

129 tables, one MySQL database, heavy cross-table interdependency (§1) — this rules out a piecemeal live strangler at the database level; dual-writing across two different database engines mid-migration is high risk for low benefit given how tightly the shared kernel is wired.

**Recommended approach:**

1. **One-time schema-and-data ETL, MySQL → Postgres**, built and run repeatedly against a staging copy throughout the build (not a single cutover-day event). Python-based (SQLAlchemy source reflection + target ORM), not a generic tool like `pgloader` alone, because several tables need real transformation, not a straight copy:
   - Resolve every unenforced FK-shaped column (§7.6) — decide per-column whether to enforce, null, or drop orphans.
   - Rename the `assignment_id`-that's-really-`student_assignment_id` columns (§7.1) at the schema level, remapping data accordingly.
   - Decide, per §7.4, whether to carry forward or attempt to fix the `deactivation_status` backfill gap.
   - **Deprecated-module data** (§4/§9 below): archive-only, not modeled as live entities.
2. **Deprecated-module data handling — decided: leave it behind.** `Student.php` and `Enrollment.php` in AP-V2 declare live Eloquent relationships into 5 of the 12 dead modules (`ClassParticipants`, `ClassCSATForm`, four `PerformanceCoach*` entities, `ProjectTaskStudentFiles`, `BookDeliveryLog`, `Book`, `Project`/Kanboard). The team has confirmed there's no compliance/audit reason to migrate this data — it stays in the decommissioned AP-V2 database, not archived into Postgres in any form. AP-V3's `Student`/`Enrollment` models carry **no** relationships into these 12 modules' data at all. Practical implication for the ETL script (§10): explicitly exclude all 12 dead modules' tables from the migration scope, and don't spend time building an archive-table shape for them.
3. **Parity testing:** build a `tests/contract/` suite driven by `API_SPECIFICATIONS.md`'s documented request/response shapes, run against both AP-V2 (where still running) and AP-V3 for the same seeded data, per phase, before that phase is considered done — not just unit tests against AP-V3 in isolation.
4. **Cutover strategy — decided: parallel-build-per-surface.** Build AP-V3 fully against a continuously-refreshed migrated copy of AP-V2 data, then cut over one client-facing surface at a time (Admin API, then Student API, or vice versa — order to be set once Phase 1–2 scope is clearer) once that surface's full dependency chain (every phase it touches) is built and parity-tested against `API_SPECIFICATIONS.md`. This is lower-risk than a single big-bang event and matches the compatibility mandate (§2 principle 5) well: each surface only cuts over once its contract has been verified endpoint-by-endpoint to be unchanged. Given the shared-kernel finding (§1), a true per-*module* strangler (routing individual endpoints to old vs. new backend while both share live state) is still not realistic — the granularity of cutover is "client surface," not "module."

---

## 10. Testing strategy

- **Unit/service tests:** `pytest` + `pytest-asyncio`, one test module per `domains/<x>/service.py`.
- **API contract tests — the primary acceptance gate, given the compatibility mandate (§2 principle 5):** `httpx.AsyncClient` against `API_SPECIFICATIONS.md`'s documented shapes, asserting exact field names, exact status codes (including the AP-V2 quirks — the 400-not-422 expired-token case, the guard-dependent 401 body shape, `status` as string vs. integer depending on endpoint), and exact response envelope per endpoint. Where possible during the parallel-build window (§10.4), run the same request against live/staging AP-V2 and AP-V3 and diff the JSON responses directly rather than trusting a hand-written assertion to have captured every quirk — `API_SPECIFICATIONS.md` is thorough but was itself produced by an audit, not the spec AP-V2 was built from, so treat live-response diffing as the higher-authority check when the two disagree. The **only** endpoints allowed to diverge are the ones explicitly named in §7.2 (OTP mechanism internals, if the team decides the response shape can change too) — every other divergence found this way is a bug to fix, not a design decision to document.
- **Data-layer tests:** seed fixtures per the `DATABASE_SCHEMA.md` §1 cross-cutting findings (status enum values, the `assignment_id` FK direction, NPS v1/v2 field differences) so the landmines in §7 have regression coverage from day one, not discovered again later.
- **Migration/ETL tests:** a dedicated suite asserting row counts, orphan-reference counts, and spot-checked value transformations survive the MySQL→Postgres ETL run.

---

## 11. Decisions log

All seven items originally raised here have been settled by the team; kept as a log rather than deleted, since several other sections cross-reference these decisions by number.

| # | Question | Decision |
|---|---|---|
| 1 | JWT revocation strategy | **Not applicable — no JWT.** Sanctum-compatible stateful Personal Access Tokens instead; revocation is immediate DB-row deletion/disable. Full design in §6. |
| 2 | Task queue: Celery or arq? | **Celery + Redis + Flower.** §7.7. |
| 3 | Cutover strategy | **Parallel-build-per-surface** (Admin API / Student API cut over independently once each is fully parity-tested), not big-bang. §10.4. |
| 4 | Four schema/behavior ambiguities | Resolved individually — dual OTP (neither live, rebuild fresh), NPS v1/v2 (migrate v1 data, build only v2 functionality), `ai-assignments/webhook` (live, ships forward unauthenticated as an accepted risk), `StudentFrontendEnrollment` (move to proper domains internally, routes unchanged), tagging (plain join table, no JSON-locale). Full detail in §7.2. |
| 5 | Deprecated-module data retention | **Leave it in the decommissioned AP-V2 database** — not migrated in any form, including archive tables. §9.2. |
| 6 | SQLAdmin | **Skip.** Admin API consumer stays a separate frontend project; scope is strictly API + data parity. |
| 7 | Team size / timeline | **Two people, both pairing with Claude Code.** See §12 for what this implies about parallelization. |

## 12. Team & parallelization notes

Two people, both co-working with Claude Code, changes the practical shape of the phasing in §5 more than it changes the phase *order* — the dependency graph is real and doesn't shrink because there are two of you, but a few things genuinely can run in parallel once their prerequisites land:

- **Phase 1 (Identity) is a hard serialization point** — both people are effectively blocked on it (or on stubbing it) until real auth + `Student`/`User` data exist, since almost everything else reads those tables. Do the CryptoJS-AES round-trip (§7.3) and the token scheme (§6) first, as a single-threaded spike, before splitting up work.
- **Phase 2 (Catalog+Enrollment) is the one phase worth explicitly splitting between the two of you** — e.g. one person on the catalog side (`Course`/`CourseBatch`/`Package`/`Bootcamp`/`Topic`/`Evaluator`), the other on the enrollment side (`Enrollment`/`RevenueAPI`/`ReferralSystem`/the `StudentFrontendEnrollment` reorg from §7.2 item 4), syncing frequently given how tightly the two sides cite each other's models (§5 Phase 2's cycle finding). Don't split it by "one person, one phase" the way later phases can be.
- **Integrations (Phase 6) client scaffolding can start early**, in parallel with any other phase, since it's a pure consumer with no dependents (`SERVICE_BOUNDARIES.md` §4) — the httpx/authlib wrapper shells for `AtsAPI`/`AgenticSupportSystem`/`LawSikho` don't need real data to exist yet, only their *endpoints* do.
- **Communication (Phase 4)'s independent verticals** (each CSAT type, NPS, Notification, EmailTemplate) are genuinely parallelizable across two people once Phase 1–3 are stable, per `BOUNDED_CONTEXT_COMMUNICATION.md`'s near-zero internal cohesion finding.
- Given a two-person team, this plan intentionally doesn't attempt calendar estimates — track progress by phase exit criteria (§5) rather than dates, and revisit sequencing after Phase 1 actually ships, since that's the first point real velocity data exists.

---

## 13. Related source documents

Every claim above traces back to one of: `CONTEXT_MAP.md`, `BOUNDED_CONTEXT_{IDENTITY,LEARNING,ENROLLMENT,ASSESSMENT,COMMUNICATION,INTEGRATIONS}.md`, `SERVICE_BOUNDARIES.md`, `DATABASE_SCHEMA.md`, `BUSINESS_RULES.md`, `API_SPECIFICATIONS.md`, `EVENT_LIST.md`, in `AP-V2 Reference Documentation/`. Where this plan makes a judgment call not directly stated in those docs (e.g. the Celery recommendation, the phase ordering itself), that's this plan's own synthesis, not a source-doc claim — treat it as the part most worth pushing back on in review.
