# AP-V3 Migration Plan — Assignment Portal API (Laravel → Django)

> **Status:** Draft for review — no code written yet.
> **Source system:** `Lawsikho-Assignment-Portal-API` (Laravel 8.75, branch `New-Dummy-Prod-0605`), as described in `AP-V2 Reference Documentation/`.
> **Method:** Built directly from the coupling data, schema audit, business-rule audit, and event-system audit already captured in that documentation folder — not from the module folder structure, which the source docs explicitly warn is not a real dependency graph (every `module.json`'s `requires` array is empty).
> **Note on prior art:** AP-V3 previously scaffolded a FastAPI/SQLAlchemy version of this same plan (git history, now reverted). That plan's analysis of the source system — coupling data, phasing rationale, risk register — is still correct and is reused here verbatim where it doesn't depend on the framework choice. Only the technology-specific sections (§3, §6) are rewritten for Django. Scope here is **backend only**: this plan assumes the existing Angular frontend keeps consuming this API, unchanged in every respect except the one explicit exception in §2 principle 5.

---

## 1. Executive summary

AP-V2 is a single-deployable Laravel modular monolith: 62 "modules," one MySQL database, one Redis instance, no per-module isolation. `CONTEXT_MAP.md` measured 377 real cross-module import edges and found a **near-complete mesh** — `Enrollment`, `Student`, and `Course` function as a de facto shared kernel that 30+ other modules depend on directly, and `Enrollment` and `Course`/`CourseBatch` are in a near-symmetric dependency **cycle** (22↔20 edges), not a layered relationship.

That has two direct consequences for this migration, independent of framework:

1. **Do not attempt a clean microservice-style migration.** `SERVICE_BOUNDARIES.md` §4 already scored this: only the Integrations context (`AtsAPI`, `AgenticSupportSystem`, `LawSikho`) is extraction-ready today. Everything else shares one schema with no ownership boundary. AP-V3 should ship as **one well-modularized Django monolith** (one app per bounded context, one Postgres database) — matching the architecture we're actually capable of building safely, not an aspirational microservice topology.
2. **Phasing has to follow the coupling graph, not the module list.** Identity is the only context nothing else can be built without. Enrollment and Learning/Catalog cannot be built as separate phases — they have to land together. Assessment is a genuinely separable pipeline and can follow. Communication is a federation of independent verticals and can be parallelized. Integrations is a thin consumer and comes last.

Why Django specifically (over the previously-scaffolded FastAPI approach): AP-V2's actual shape — one database, a shared-kernel of tightly-coupled entities, a back-office needing role/permission management, standard CRUD-heavy admin workflows — is exactly what Django's batteries (ORM, migrations, admin, auth/permission framework) are built for. FastAPI would have required hand-assembling the equivalent of several of these from separate libraries (SQLAlchemy + Alembic + a custom RBAC layer) for no benefit this system actually needs (there is no async-I/O-bound workload here that justifies FastAPI's main advantage). This is a **backend-only** decision — it does not require the Angular frontend team's involvement, except for the one auth wire-format change in §2 principle 5 / §6.

12 of 62 modules (`Class`, `ClassCSAT`, `StudentClasses`, `Forum`, `StudentForum`, `ProjectManagement`, `StudentTasks`, `PerformanceCoach`, `PerformanceCoachCSAT`, `StudentPerformanceCoach`, `BookMaster`, `BookDeliveryLog`) are confirmed dead in product terms (team-confirmed, 2026-08-29) and are **out of scope for AP-V3** — see §4. The formal event/webhook-subscription system (`EVENT_LIST.md`) is also 100% disabled in production; the real "event bus" is direct job dispatch, and that's the pattern AP-V3 should port, not the dead formal-events layer.

---

## 2. Guiding principles

1. **Port behavior, not code shape.** This is a rewrite (Eloquent → Django ORM, sync PHP-FPM → sync Django/WSGI), not a transliteration. Where the source docs identify something as a bug, a dead code path, or an unimplemented proposal (§8), AP-V3 should not reproduce it faithfully — it should fix it, unless there's a data-compatibility reason not to.
2. **The coupling graph is the project plan.** Every phase boundary below is justified by a specific in-degree/out-degree number from `CONTEXT_MAP.md`/`BOUNDED_CONTEXT_*.md`, not by aesthetic module grouping.
3. **One schema, modularized code.** Postgres schema mirrors the "one database" reality of the source system. Code is organized into Django apps (`apps/identity`, `apps/catalog_enrollment`, …) with views/viewsets, serializers, and services per app — internal-only boundaries enforced by import discipline and lint rules, not by network calls.
4. **Never build against a source-doc claim you haven't re-verified against current code.** The reference docs themselves say this repeatedly — they're a snapshot from 2026-08-29, and several root-level planning docs in the source repo were found to describe features that were never built. Treat `AP-V2 Reference Documentation/` as the starting map, not ground truth to port blindly. Before implementing any specific rule, re-check it against the actual AP-V2 source if/when that repo is available.
5. **API compatibility is the goal everywhere except one deliberate, scoped exception: the auth token scheme.** The team's standing mandate is *"migrate the API's code and data in such a way that neither the API param nor the API response changes a bit"* — the Angular frontend depends on this contract, and this plan keeps that promise for every endpoint, every response envelope, every quirky status code (inconsistency and all — see §7.2). **The one carved-out exception, decided this round:** authentication moves to a **Django-native token scheme** (§6) rather than reproducing Sanctum's `Authorization: Bearer {id}|{token}` wire format. This is a conscious tradeoff — it means the Angular frontend's auth layer (how it stores and sends the token) needs a small, scoped update, coordinated with the frontend team, even though nothing else about the API contract changes. Treat this as the one item that needs a cross-team heads-up before cutover; everything else in this plan is backend-only.

---

## 3. Target architecture

| Concern | AP-V2 (Laravel) | AP-V3 (this plan) |
|---|---|---|
| Framework | Laravel 8.75 | Django 5.x + Django REST Framework |
| ORM | Eloquent | Django ORM |
| Migrations | Laravel migrations | Django migrations (`makemigrations`/`migrate`) |
| Database | MySQL | PostgreSQL |
| API docs | Hand-maintained `API_SPECIFICATIONS.md` | `drf-spectacular` → auto-generated OpenAPI/Swagger |
| Schemas/validation | Laravel Form Requests | DRF serializers |
| Task queue | Redis + Horizon (priority-tiered, not per-domain — flagged as a gap to fix, §7.7) | Celery + Redis + Flower, queues partitioned per domain (§7.7 — decided, unchanged from prior plan) |
| Admin auth | Sanctum | **Django-native token auth** (custom, hash-stored, multi-token) — decided this round, wire format changes; see §6 |
| Student auth | Sanctum + a second guard (JWT/Edmingle claims never actually used — `tymon/jwt-auth` was installed-but-dead in AP-V2) | Same native token scheme, separate token table/model, separate DRF authentication class — see §6 |
| RBAC | `spatie/laravel-permission`, admin-only (student guard has none) | Django's built-in `auth.Group`/`Permission` framework, admin-only — native equivalent, avoids hand-rolling a permissions system Django already ships (see §6.3) |
| Back-office admin UI | None (separate Admin API consumer) | **None added as a requirement — decided, unchanged.** The Admin API consumer stays a separate frontend project. Django admin exists "for free" as an internal/ops convenience (data inspection, one-off fixes) but is **not** a substitute for or change to the Admin API consumer's contract. |
| File storage | Flysystem → S3 | `django-storages` (S3 backend) |
| Media attachments | `spatie/laravel-medialibrary` | Port the existing polymorphic media table schema + `Pillow`, thin custom model (no need for a heavyweight library here) |
| PDF generation | `laravel-mpdf` | WeasyPrint |
| Excel import/export | `maatwebsite/excel` | `openpyxl` / `pandas` |
| Tagging | `spatie/laravel-tags` (JSON-locale `name` column — see §7.2 item 5 landmine) | Plain join table, plain-text tag name |
| Audit log | `spatie/laravel-activitylog` | `django-simple-history` (evaluate against a lighter custom audit middleware only if full field-level version history isn't actually needed) |
| Error monitoring | `sentry-laravel` | `sentry-sdk[django]`, same Sentry project |
| Outbound integrations | Guzzle + OAuth | `httpx` + `authlib` |
| CryptoJS-AES payload compat | `cryptojs-aes-php` | `pycryptodome` — **round-trip this first, before any other Identity work** (§7.3) |
| Phone validation | `laravel-phone` | `phonenumbers` |
| Testing | PHPUnit | `pytest-django` + DRF `APIClient` |
| Containers | Docker + nginx + PHP-FPM | Docker + nginx + gunicorn (sync WSGI workers — see note below) |

**Sync, not async Django — decided.** Django's async views/ORM support is still maturing relative to its sync stack, and nothing in this workload needs it: there's no high-concurrency I/O-bound hot path that async would meaningfully help, and Celery already offloads every slow operation (external API calls, PDF/Excel generation, evaluation webhooks) off the request/response cycle. Sync Django behind gunicorn is the most battle-tested option and has the best compatibility with the library choices above (`django-simple-history`, `django-rest-knox`-style token patterns, `drf-spectacular`). Revisit only if a specific endpoint's profiling data justifies it later — not a day-one requirement.

### 3.1 Project structure (proposed)

```
config/
  settings/                  # base/dev/prod split
  urls.py                    # root URL conf, mounts each app's urls.py
  celery.py                  # Celery app instance
  wsgi.py
apps/
  identity/                  # Auth, StudentAuth, User, Role/Permission mapping, JobRole,
                              # Student, StudentProfile, StudentDegree, StudentUniversity,
                              # Country, State, InternalNotes, the two token models (§6)
  catalog_enrollment/        # Course*, CourseBatch, Package, Bootcamp, Evaluator, Topic,
                              # Enrollment, RevenueAPI, ReferralSystem, StudentFrontendEnrollment
  assessment/                 # Assignment*, StudentAssignment, Result, AIEvaluation, StudentResults
  communication/               # AssignmentCSAT, EvaluatorCSAT, NPS, Notification, EmailTemplate, Webhook
  student_portal/               # StudentDashboard*, StudentMyCourses, StudentNotifications, StudentBookACall
  integrations/                  # AtsAPI, AgenticSupportSystem, LawSikho
jobs/ or apps/<x>/tasks.py     # Celery task definitions, one module per app (see §7.7)
tests/
  contract/                    # parity tests against API_SPECIFICATIONS.md-documented behavior
manage.py
```

Each `apps/<x>/` package holds `models.py`, `serializers.py`, `views.py` (or `viewsets.py`), `urls.py`, `services.py` (business logic — keep it out of views/serializers), `permissions.py` (DRF permission classes), `tasks.py` (Celery). Cross-app calls go through the other app's `services.py`, never straight through its ORM models — this is the one discipline AP-V2 never had (§1's "shared-kernel monolith, not bounded contexts" finding), so a future extraction (per `SERVICE_BOUNDARIES.md`) stays possible later even though nothing is being extracted now.

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
Django project skeleton, Docker/compose, initial migration against a fresh Postgres schema, settings split (base/dev/prod), Sentry wiring, CI (lint + `pytest-django`), DRF authentication scaffolding (token model + lookup plumbing per §6, no real login logic yet), Celery+Redis+Flower wiring (empty task registry). Exit criteria: a deployable "hello world" Django app with a health-check endpoint, structured logging, and an empty migration history that CI runs against.

### Phase 1 — Identity & Access
`Auth`, `StudentAuth`, `User`, `Role`, `Permission`, `JobRole`, `Student`, `StudentProfile`, `StudentDegree`, `StudentUniversity`, `Country`, `State`, `InternalNotes`.

Why first: every other context reads `Student`/`User` directly (`Student` is the system's #2 in-degree module at 33 dependents; `BOUNDED_CONTEXT_IDENTITY.md` calls it a de facto shared kernel). Nothing else can be meaningfully built or tested without real identities and both auth chains working.

Includes: CryptoJS-AES round-trip (§7.3, do this literally first — it's the highest-risk single item in the whole plan), the Django-native token scheme (§6 — two token models/two DRF authentication classes, mirroring the two-guard split in AP-V2), RBAC via Django's `Group`/`Permission` (§6.3 — mapping the source `roles`/`permissions`/`model_has_roles` data onto Django's native tables), phone validation via `phonenumbers`, FCM push-token registration.

Exit criteria: both login flows (admin, student — including the OTP path, and picking one of the two OTP mechanisms per §7.2) work end-to-end against a migrated Postgres copy of real user/student data; permission check proven on at least one protected admin route.

### Phase 2 — Catalog & Enrollment (the big one — built together, not sequentially)
`Course`, `CourseBatch`, `CourseCategory`, `CourseCategoryCriteria`, `CourseCriteria`, `CourseFaq`, `CoursePlanType`, `CourseCompletionMaster`, `Topic`, `Package`, `Bootcamp`, `Evaluator` **+** `Enrollment`, `RevenueAPI`, `ReferralSystem`, `StudentFrontendEnrollment`.

Why together: `BOUNDED_CONTEXT_LEARNING.md` §5 measured this precisely — 22 edges Enrollment→Learning, 20 Learning→Enrollment, "a real cycle, not a layering... treat 'Course catalog' and 'Enrollment' as one tightly-coupled unit for change-impact purposes, regardless of which document they're filed under." Building one before the other means building throwaway stubs for half the phase.

This phase also has to resolve `StudentFrontendEnrollment`'s scope drift (§7.2 item 4) — decide in AP-V3's design whether student-facing CSAT/NPS/Notification/Task endpoints live in `catalog_enrollment` or their "proper" home app, and pick one, rather than porting the duplication forward.

Exit criteria: full enrollment lifecycle (create → activate → pause → resume → deactivate) working against real catalog data, including the inbound Revenue/Billing webhook receiver and Edmingle batch sync stub (real integration wiring can follow in a later pass — see §7.5).

### Phase 3 — Assessment
`Assignment`, `AssignmentTag`, `StudentAssignment`, `Result`, `AIEvaluation`, `StudentResults`. (`AssignmentSendingLog` excluded — `DATABASE_SCHEMA.md` confirms its tables are dead code, every write site commented out.)

Why third: `BOUNDED_CONTEXT_ASSESSMENT.md` calls this "the most internally cohesive of the 6 contexts... a genuine grading pipeline," with 51 inbound edges from elsewhere but a tight internal mesh of just 4-5 modules. It depends on Phase 1 (who submitted) and Phase 2 (which course/batch it's attached to) but nothing later.

Must implement the `results.assignment_id → student_assignments.id` FK correctly from day one (§7.1) — this is the single most concrete landmine in the whole source system, and getting it wrong here means every downstream report/dashboard is silently wrong.

Exit criteria: submission → evaluator grading → AI-evaluation-webhook path all working, with the correct FK model and the two AI-evaluation webhook endpoints resolved to one canonical implementation (§8).

### Phase 4 — Communication (parallelizable internally)
`AssignmentCSAT`, `EvaluatorCSAT`, `NPS`, `Notification`, `EmailTemplate`, `Webhook`.

`BOUNDED_CONTEXT_COMMUNICATION.md` found only 2 intra-context edges across 9 modules — "several small services wearing one label." Each CSAT vertical and NPS can be built independently once Phase 1–3 land, by different people at the same time, without stepping on each other. Resolve NPS v1/v2 (§7.2 item 2) to one schema rather than porting both. `Webhook` here means the generic outbound dispatch primitive only (used by 11+ other modules) — the dead business-event catalog itself is out of scope (§4).

### Phase 5 — Student Portal (BFF layer)
`StudentDashboard`, `StudentDashboardManagement`, `StudentMyCourses`, `StudentNotifications`, `StudentBookACall`.

These are aggregation layers by design (high fan-out, low fan-in — `CONTEXT_MAP.md` §4) that read across every prior phase. Building them last means the underlying domain APIs they aggregate already exist and are stable.

### Phase 6 — Integrations
`AtsAPI`, `AgenticSupportSystem`, `LawSikho`.

Ironically the *easiest* context to extract (`SERVICE_BOUNDARIES.md` §4: 29 outbound edges, only 2 inbound) but it can only be **finished** last because it's a pure consumer of everything else — `AgenticSupportSystem` alone reads 17 modules across 4 other contexts. Its outbound-gateway shape means the actual client code (`httpx` + `authlib` wrappers for ATS/Agentic Support/LawSikho ingestion) could be scaffolded early in parallel, but wiring real endpoints has to wait for the data it reads to exist.

---

## 6. Auth strategy (detail) — decided this round: Django-native token scheme, not Sanctum-compatible

**Decision (settled this session):** unlike the earlier FastAPI-era plan, AP-V3 does **not** attempt to reproduce Sanctum's wire format. Authentication stays stateful (same functional shape as before — DB-row-backed tokens, immediate revocation) but is implemented as a Django-idiomatic custom token scheme rather than a compatibility shim. This is a deliberate, scoped exception to the otherwise-strict API-compatibility mandate (§2 principle 5) — everything else about the contract is unchanged, but the client's `Authorization` header handling needs a small update.

### 6.1 Why not just use DRF's built-in `TokenAuthentication` or `django-rest-knox` directly

- **DRF's built-in `TokenAuthentication`** issues exactly one token per user with no expiry and no concept of multiple concurrent devices/sessions — AP-V2's Sanctum-based PATs support multiple named tokens per principal (multi-device login, per-token revocation). Built-in `TokenAuthentication` alone would be a functional regression.
- **`django-rest-knox`** solves the multi-token/hashed-storage/logout-everywhere problem well, but it's built around Django's single `AUTH_USER_MODEL`. AP-V2 has **two structurally separate principal types** — admin `User` (would map to Django's real auth user) and `Student` (a completely separate model, not integrated with Django's auth system, matching `BOUNDED_CONTEXT_IDENTITY.md`'s finding that these are "unrelated models with no shared 'person' concept" — real product behavior worth preserving, not a gap to fix). Knox can't natively authenticate a second, non-`AUTH_USER_MODEL` principal type without being fought against its grain.
- **Conclusion:** build one small custom app (`apps/identity/tokens.py` or similar) with two parallel token models and two DRF authentication classes, borrowing knox's *pattern* (prefix + hash, not knox itself) rather than depending on either library. This is a small amount of code, well-understood, and avoids bending a library around a two-principal-type design it wasn't built for.

### 6.2 Design

**Token wire format:** `Authorization: Token <prefix>.<secret>` — a DRF-idiomatic scheme, opaque to the client beyond "store this string, send it back." (Naming the scheme `Token` rather than `Bearer` matches DRF/knox convention; purely a naming choice, easy to change if the team prefers `Bearer` for consistency with other internal services — flag for confirmation.) **This is the one wire-format change the Angular team needs to make** — swap out however it currently constructs/stores the `Bearer {id}|{token}` header for the new `Token <prefix>.<secret>` string. Everything else about every endpoint's request/response shape is unaffected.

**Storage — two models, same shape:**
- `AdminAuthToken`: FK → `auth.User` (or the project's actual admin user model), `key_prefix` (8 chars, stored plaintext — enables O(1) row lookup before doing any hash comparison, same trick knox uses), `token_hash` (SHA-256 of the secret half, never store the plaintext secret), `name`/label (optional, for "which device" UX), `expires_at` (nullable — AP-V2 tokens never expire by default unless revoked; preserve that default, don't silently introduce forced expiry), `last_used_at`, `created_at`.
- `StudentAuthToken`: identical shape, FK → `Student`.

**Two DRF authentication classes, two dependency-injection points:** `AdminTokenAuthentication` and `StudentTokenAuthentication`, each doing prefix lookup against its own table, then hash comparison, then attaching the resolved principal to `request.user`/`request.student`. A token issued under one guard is structurally incapable of authenticating the other (separate tables, separate classes) — same guarantee AP-V2's two-guard split gave.

**Revocation:**
- Single-session logout: delete/disable that one token row.
- Logout-everywhere / password reset / account suspension: bulk-delete every token row belonging to that user/student — mirrors AP-V2's `$user->tokens()->delete()` pattern (confirmed in `API_SPECIFICATIONS.md` for student logout).
- Expiry: supported per-token via `expires_at`, but not required — matches AP-V2's default of non-expiring tokens unless revoked.

**Edmingle SSO:** in AP-V2 this goes through the ordinary student Sanctum guard. Port SSO validation as its own endpoint that issues a token in the same `StudentAuthToken` format as ordinary student login — no separate token type.

**Webhook/integration auth (Phase 6):** AP-V2 uses static shared-secret bearer tokens for `AgenticSupportSystem`/`LawSikho` (not Sanctum) — port as a separate `verify_static_token` dependency/permission class, kept out of both token-auth classes, unchanged (this was never part of the Sanctum-compatibility question and isn't affected by this section's decision).

### 6.3 RBAC — Django's native `Group`/`Permission`, not a ported `roles`/`permissions` schema

AP-V2 uses `spatie/laravel-permission`'s `roles`/`permissions`/`model_has_roles` tables, admin-only (student guard has no RBAC). Rather than porting that schema 1:1, use Django's built-in `auth.Group` (≈ "role") and `auth.Permission` (≈ "permission") tables directly — this is exactly the kind of "batteries included" win that motivated choosing Django in the first place (§1): no custom schema, no custom admin UI needed to manage roles (Django admin already has a Groups/Permissions screen), and every third-party Django package that checks permissions understands this model natively.

**ETL implication (§9):** the migration step needs to map each AP-V2 `role` → a Django `Group`, and each AP-V2 `permission` string → a Django `Permission` (custom permissions can be declared per-model via `Meta.permissions`, or globally via a migration, if AP-V2's permission names don't map cleanly onto Django's default `app_label.add_/change_/delete_/view_<model>` convention — expect to need a mix of both). Confirm with the team before Phase 1 exit whether any admin-facing "manage roles" UI in the separate Admin API consumer reads role/permission data directly (in which case its response shape is still frozen by §2 principle 5, and the mapping needs to preserve whatever names/IDs that UI expects) or only calls backend endpoints that this project controls (in which case the internal representation is free to be idiomatic Django).

---

## 7. Risk register

Ordered by how much damage getting it wrong silently does, not by implementation order. Items 7.1–7.6 and 7.8 are carried forward unchanged from the prior FastAPI-era analysis — they're properties of the *source system*, not the target framework. 7.9 is new this round.

### 7.1 `results.assignment_id` FK trap — HIGH, silent-failure risk
Every column literally named `assignment_id` in the Assignment/Evaluation domain (`results.assignment_id`, `assignment_csat_form.assignment_id`, `course_featured_assignment_mapping.assignment_id`, etc.) is a foreign key to **`student_assignments.id`**, not `assignments.id`. Only exception: `assignment_log_mapping.assignment_id` (itself dead code). Get this wrong in the Django model and every join silently returns wrong-but-plausible data instead of erroring. **Mitigation:** name the Django model field/relationship something unambiguous (e.g. `student_assignment`) rather than porting the confusing original name forward.

### 7.2 Ambiguities from the audit — resolved by the team (carried forward)
1. **Dual OTP mechanisms** on `students` (`verification_otp` vs newer `otp`/`otp_expire_at`) — **neither is actually live**. Design one fresh OTP flow for AP-V3's forgot-password path; confirm whether the *response shape* of the OTP endpoints still needs to match `API_SPECIFICATIONS.md` even though the underlying mechanism is rebuilt.
2. **NPS v1 vs v2** — both are live, asymmetrically. `nps_form` (v1) is deprecated-in-UI but holds real historical data; `nps_form_v2` is the live write path. Migrate v1's data read-only/archival; build all new functionality against v2 only.
3. **`ai-assignments/webhook` (unauthenticated)** — confirmed live and used in production. Per §2 principle 5, ships forward unauthenticated exactly as-is; document as an accepted, known risk rather than silently fixing it.
4. **`StudentFrontendEnrollment`'s scope drift — intentional, but reorganize internally.** Move the CSAT/NPS/Notification/Task logic hosted there to its proper domain app (Communication, Assessment, Student Portal per §5) as an internal code-organization change only — route paths and response shapes stay identical.
5. **`AssignmentTag`'s JSON-locale tag storage** — a consequence of `spatie/laravel-tags`, not a deliberate design choice. Plain join table with a plain-text tag name column. The ETL must normalize any *stored data* keyed on the literal JSON string (e.g. Enrollment's refund-eligibility check against `'{"en":"Refund Eligible"}'`) to plain text, not just the schema going forward.

### 7.3 CryptoJS-AES password payload — HIGH, do first
Student login step 2 requires the client to pre-encrypt the password (OpenSSL `aes-256-cbc`, key derived EVP_BytesToKey-style from `APP_PASS_PHRASE`) before sending it. This is the one place AP-V3 cannot simply "clean up" — web/mobile clients already implement this independently, and it is unaffected by the §6 auth-token decision (this is about the login *payload*, not the *session token* issued afterward). **Action:** build a standalone `pycryptodome` round-trip test against real AP-V2-encrypted payloads (or the PHP `cryptojs-aes-php` library directly) in Phase 0/1, before any other Identity work.

### 7.4 Confirmed-broken source artifacts — don't port the brokenness
- `webhooks` table has two identical CREATE migrations (`CreateWebhooksTable`/`CreateWebhooksTableV2`) — a leftover, not a deliberate schema. Port one clean table.
- `enrollments.deactivation_status` has a commented-out historical backfill — pre-migration rows all read `NORMAL_DEACTIVATION` regardless of real history. The ETL (§9) needs an explicit decision: carry this known-wrong value forward as-is, or attempt a real backfill if the business needs it corrected.
- `enrollment_pause_log_new.accepted`/`.rejected` don't exist in the live schema despite being read by a resource class — don't model these columns in AP-V3 at all.
- A commented-out performance-index migration on `results`/`student_assignments`/`result_exercise_scores`/`assignments` was never applied — don't assume those indexes exist; **do** add the equivalent indexes for real in the new Postgres schema.

### 7.5 Live-but-fragile external integrations
Several integrations have real ambiguity in AP-V2 itself: Edmingle credential env vars aren't clearly named, `COURSE_CALENDER_API_URL` is a misspelled key that's nonetheless load-bearing, `sql_migration`/`staging` are direct cross-database reads into another system's live schema with zero contract (read-only today, worth retiring rather than porting forward as a pattern). Each external integration should get its own small discovery pass (confirm real base URLs/credentials with the team) at the start of the phase that owns it.

### 7.6 Unenforced "FK-shaped" columns
Confirmed instances (`students.country_id`, `enrollments.bootcamp_id`, `course_categories.parent_id`, several `*_csat_form_reason.parent_id` columns, `course_job_mappings.course_id`, etc.) are integer columns with no real FK constraint in AP-V2 — production data may already contain orphaned references. **Action:** before adding real Postgres FK constraints (recommended), the ETL step (§9) must audit and report on orphaned rows so the team can decide per-column how to handle each one.

### 7.7 Task queue: Celery + Redis + Flower (unchanged decision)
Horizon's queues in AP-V2 are priority-tiered, not partitioned by domain. **Decision: Celery + Redis + Flower** — mature, well-understood, works fine called from sync Django views (`.delay()`/`.apply_async()`). Partition queues **by domain** from day one (`identity`, `enrollment`, `assessment`, `communication`, `integrations`), keeping priority sub-tiers within each domain queue if the `_high`/`_medium`/`_long` distinction still matters operationally. Port the **job-dispatch pattern**, not the dead formal-Events layer — `EVENT_LIST.md`'s 128-job inventory is the real list of background work to replicate as Celery tasks, one per phase as that phase is built.

### 7.8 Security items — one accepted risk, one to close
- The AI-evaluation webhook (`POST /api/v1/ai-assignments/webhook`) has no auth middleware in AP-V2. Per §7.2 item 3, ships forward unchanged as an accepted, documented risk.
- A hardcoded-looking API key default exists in AP-V2's `config/services.php` (`EXTERNAL_PORTAL_UPDATE_API_KEY`) — a secret-value concern, not a contract concern; fine to rotate in AP-V3 config.

### 7.9 NEW — Auth wire-format change requires a coordinated (small) frontend update
Because §6 chose a Django-native token scheme over Sanctum-compatibility, the Angular frontend's auth interceptor/service needs a scoped update (how it reads the login response's token field and constructs the `Authorization` header on subsequent requests) before cutover. **This is the one place in this entire plan where "backend-only" isn't strictly true.** Scope it precisely: only the token-handling code path, not a frontend rewrite. Flag to the frontend team as a heads-up as soon as Phase 1's token format is finalized, so their small change can land in parallel rather than blocking cutover.

---

## 8. Explicitly not implementing (proposed-but-never-built features)

`BUSINESS_RULES.md` found three root-level planning documents in the source repo describe features that were never actually built: **CR-10 course pause/refund waiver** (45-day window logic, self-service waiver-and-pause), **enrollment/batch capacity limits** (no cap exists anywhere today), and the **KYC verification gate** on certificate downloads. None of these should be treated as "the real spec to port" — if the product wants any of them in AP-V3, that's new-feature scoping, not migration, and should be raised separately.

---

## 9. Data migration approach

129 tables, one MySQL database, heavy cross-table interdependency (§1) — this rules out a piecemeal live strangler at the database level; dual-writing across two different database engines mid-migration is high risk for low benefit given how tightly the shared kernel is wired.

**Recommended approach:**

1. **One-time schema-and-data ETL, MySQL → Postgres**, built and run repeatedly against a staging copy throughout the build (not a single cutover-day event). Python-based (source reflection + Django ORM/`bulk_create` on the target side), not a generic tool like `pgloader` alone, because several tables need real transformation:
   - Resolve every unenforced FK-shaped column (§7.6) — decide per-column whether to enforce, null, or drop orphans.
   - Rename the `assignment_id`-that's-really-`student_assignment_id` columns (§7.1) at the schema level, remapping data accordingly.
   - Decide, per §7.4, whether to carry forward or attempt to fix the `deactivation_status` backfill gap.
   - Map `roles`/`permissions`/`model_has_roles` rows onto Django `Group`/`Permission` (§6.3).
   - Deprecated-module data (§4/§9.2): archive-only, not modeled as live entities.
2. **Deprecated-module data handling — decided: leave it behind.** `Student.php` and `Enrollment.php` in AP-V2 declare live Eloquent relationships into 5 of the 12 dead modules. There's no compliance/audit reason to migrate this data — it stays in the decommissioned AP-V2 database, not archived into Postgres in any form. AP-V3's `Student`/`Enrollment` models carry **no** relationships into these 12 modules' data. Explicitly exclude all 12 dead modules' tables from ETL scope.
3. **Parity testing:** build a `tests/contract/` suite driven by `API_SPECIFICATIONS.md`'s documented request/response shapes, run against both AP-V2 (where still running) and AP-V3 for the same seeded data, per phase, before that phase is considered done.
4. **Cutover strategy — parallel-build-per-surface.** Build AP-V3 fully against a continuously-refreshed migrated copy of AP-V2 data, then cut over one client-facing surface at a time (Admin API, then Student API, or vice versa) once that surface's full dependency chain is built and parity-tested. Given the shared-kernel finding (§1), a true per-*module* strangler isn't realistic — the granularity of cutover is "client surface," not "module." **The one item that must land before either surface cuts over is the frontend's auth-header update (§7.9)** — sequence it early, not as a last-minute blocker.

---

## 10. Testing strategy

- **Unit/service tests:** `pytest-django`, one test module per `apps/<x>/services.py`.
- **API contract tests — the primary acceptance gate, given the compatibility mandate (§2 principle 5):** DRF `APIClient` against `API_SPECIFICATIONS.md`'s documented shapes, asserting exact field names, exact status codes (including the AP-V2 quirks — the 400-not-422 expired-token case, the guard-dependent 401 body shape, `status` as string vs. integer depending on endpoint), and exact response envelope per endpoint, **except** the auth endpoints explicitly carved out in §6/§7.9. Where possible during the parallel-build window, run the same request against live/staging AP-V2 and AP-V3 and diff the JSON responses directly rather than trusting a hand-written assertion to have captured every quirk. The **only** endpoints allowed to diverge are the ones named in §7.2 (if the team decides OTP response shape can change too) and the auth token endpoints (§6) — every other divergence found this way is a bug to fix.
- **Data-layer tests:** seed fixtures per `DATABASE_SCHEMA.md` §1 cross-cutting findings (status enum values, the `assignment_id` FK direction, NPS v1/v2 field differences) so the landmines in §7 have regression coverage from day one.
- **Migration/ETL tests:** a dedicated suite asserting row counts, orphan-reference counts, and spot-checked value transformations survive the MySQL→Postgres ETL run.

---

## 11. Decisions log

| # | Question | Decision |
|---|---|---|
| 1 | Framework | **Django + Django REST Framework**, not FastAPI (reverses the earlier scaffolded attempt) — §1. |
| 2 | Auth token scheme | **Django-native custom token scheme** (two models, two DRF auth classes, `Token <prefix>.<secret>` wire format) — **not** Sanctum-compatible. Reverses the earlier plan's compatibility carve-out. Requires a small, coordinated Angular auth-layer change. §6, §7.9. |
| 3 | RBAC | Django's native `Group`/`Permission`, not a ported `roles`/`permissions` schema. §6.3. |
| 4 | Sync vs. async Django | **Sync**, behind gunicorn — no workload here justifies async, and it has the most mature library support. §3. |
| 5 | Task queue | Celery + Redis + Flower, partitioned by domain. §7.7 (unchanged from prior plan). |
| 6 | Cutover strategy | Parallel-build-per-surface, sequenced so the auth-header frontend change lands before any surface cuts over. §9.4. |
| 7 | Four schema/behavior ambiguities (OTP, NPS, unauthenticated webhook, `StudentFrontendEnrollment`, tagging) | Resolved individually, unchanged from prior plan. §7.2. |
| 8 | Deprecated-module data retention | Leave it in the decommissioned AP-V2 database — not migrated in any form. §9.2. |
| 9 | Django admin | Available as an internal/ops convenience; **not** a replacement for or change to the separate Admin API consumer's contract. §3. |
| 10 | Repo topology / frontend framework (monorepo question) | **Out of scope for this document — open, tracked separately.** This plan assumes the current two-repo, Angular-frontend-unchanged topology. See the separate discussion on repo consolidation options before treating that question as settled. |

---

## 12. Team & parallelization notes

*(Carried forward from prior planning as an assumption — reconfirm current team size/composition before relying on this section.)*

- **Phase 1 (Identity) is a hard serialization point** — everyone is effectively blocked on it (or on stubbing it) until real auth + `Student`/`User` data exist, since almost everything else reads those tables. Do the CryptoJS-AES round-trip (§7.3) and the token scheme (§6) first, as a single-threaded spike, before splitting up work.
- **Phase 2 (Catalog+Enrollment) is the one phase worth explicitly splitting** — e.g. one person on the catalog side, another on the enrollment side, syncing frequently given how tightly the two sides cite each other's models.
- **Integrations (Phase 6) client scaffolding can start early**, in parallel with any other phase, since it's a pure consumer with no dependents — the `httpx`/`authlib` wrapper shells don't need real data to exist yet, only their *endpoints* do.
- **Communication (Phase 4)'s independent verticals** are genuinely parallelizable once Phase 1–3 are stable.
- Track progress by phase exit criteria (§5) rather than calendar dates; revisit sequencing after Phase 1 actually ships, since that's the first point real velocity data exists.

---

## 13. Related source documents

Every claim above traces back to one of: `CONTEXT_MAP.md`, `BOUNDED_CONTEXT_{IDENTITY,LEARNING,ENROLLMENT,ASSESSMENT,COMMUNICATION,INTEGRATIONS}.md`, `SERVICE_BOUNDARIES.md`, `DATABASE_SCHEMA.md`, `BUSINESS_RULES.md`, `API_SPECIFICATIONS.md`, `EVENT_LIST.md`, in `AP-V2 Reference Documentation/`. Where this plan makes a judgment call not directly stated in those docs (the Django framework choice itself, the native-token-scheme decision, the sync-vs-async call), that's this plan's own synthesis — treat it as the part most worth pushing back on in review.
