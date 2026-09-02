# LawSikho Assignment Portal API — Database Schema

> **Generated:** 2026-08-29
> **Branch surveyed:** `New-Dummy-Prod-0605`
> **Companion documents:** [`documentation/DEVELOPER_DOCUMENTATION.md`](./DEVELOPER_DOCUMENTATION.md), [`documentation/USER_WORKFLOWS.md`](./USER_WORKFLOWS.md), [`documentation/API_SPECIFICATIONS.md`](./API_SPECIFICATIONS.md). This is the fourth and most granular doc: full column-level schema for every real table in the application, traced directly from migration files (CREATE plus every located ALTER, applied chronologically) rather than the 13-table summary in `DEVELOPER_DOCUMENTATION.md` §7.

## Scope & Method

**129 tables total** across `database/migrations/` and every `Modules/*/Database/Migrations/` directory (124 tables from single-table-per-file migrations, plus 5 from `spatie/laravel-permission`'s one multi-table migration). All are documented below, organized into the same 5 domains used throughout the other docs, plus a short infrastructure appendix for pure-framework tables (`failed_jobs`, `job_batches`) that carry no app-specific schema.

For heavily-evolved central tables (`users`, `students`, `enrollments`, `courses`, `assignments`, `student_assignments`, `results`, `course_batches`, `book_delivery_log`), every subagent traced the full ALTER-migration history to describe the **current** schema — not just the original CREATE migration, which for some of these tables is now missing more than half the real columns. For smaller/peripheral tables, the CREATE migration was sufficient.

**Tables belonging to confirmed-deprecated modules are still documented in full** (the tables and data are real, even though the app no longer routes traffic to create new rows in most of them) — each is marked **⚠️ Module not in production use**. See `documentation/DEVELOPER_DOCUMENTATION.md` §4 for the full deprecated-module list.

## Table of Contents

1. [Cross-Cutting Findings for QA Test Design](#1-cross-cutting-findings-for-qa-test-design)
2. [Identity, Enrollment & Reference Data](#2-identity-enrollment--reference-data)
3. [Course & Program Catalog](#3-course--program-catalog)
4. [Assignment & Evaluation Lifecycle](#4-assignment--evaluation-lifecycle)
5. [Student Engagement, Notifications, NPS, Coaching & Call Booking](#5-student-engagement-notifications-nps-coaching--call-booking)
6. [Admin Operations & External Integrations](#6-admin-operations--external-integrations)
7. [Infrastructure Tables](#7-infrastructure-tables)

---

## 1. Cross-Cutting Findings for QA Test Design

*(Placed first on purpose — these affect how you seed fixtures and write assertions across many different tests, not just one endpoint.)*

### The `assignment_id` naming trap is systemic, not an isolated quirk

Every column literally named `assignment_id` in the Assignment/Evaluation domain is a foreign key to **`student_assignments.id`**, NOT `assignments.id` — confirmed across `results.assignment_id`, `assignment_csat_form.assignment_id`, `first_assignment_send_log.assignment_id`, `course_featured_assignment_mapping.assignment_id`, `student_result_video_mapping.assignment_id`, and even `student_assignment_video_mapping.assignment_id` (a table that lives, confusingly, under the `Topic` module). **The only exception in the entire app is `assignment_log_mapping.assignment_id`** (a dead-code table, never populated), which correctly points at `assignments.id`. If you write a QA fixture or a raw SQL join based on the column name alone, assume `student_assignments` unless you've checked otherwise.

### Two confirmed-broken/duplicate migrations — don't trust these blindly

- **`Modules/Webhook`'s `webhooks` table has two byte-for-byte identical CREATE migrations** (`2025_01_07_172031...` and `2025_02_19_164706...`, classes `CreateWebhooksTable`/`CreateWebhooksTableV2`). Neither has a `Schema::hasTable()` guard, so both could never have successfully run against the same database — this is a duplicate/leftover file, not a deliberate schema change. If you're setting up a fresh test database with `migrate:fresh`, verify only one of these two actually applies without erroring.
- **`enrollments`' `deactivation_status` column has a commented-out data backfill.** The migration that added this column includes SQL to classify existing rows by their real deactivation cause, but that backfill block is entirely commented out in the migration file. **Every enrollment row that existed before this migration ran will read `deactivation_status = 0` (NORMAL_DEACTIVATION) regardless of its actual history**, unless a separate out-of-band script ran the real backfill. Don't build a QA assertion trusting this column on old/seeded data without confirming.
- **`enrollment_pause_log_new`'s `accepted`/`rejected` columns don't exist.** A migration meant to add them has its `up()` entirely commented out, but `down()` still tries to drop them — rolling back that specific migration would error. Those two columns are simply absent from the live schema.

### Two parallel/redundant mechanisms worth confirming before testing either

- **`students` has two OTP mechanisms**: the original `verification_otp` and a newer `otp`/`otp_expire_at` pair added 2026-02-05. Confirm which the live forgot-password flow actually uses before writing a test around either.
- **`results.is_evaluated`** (added 2026-03-26, "0=Pending, 1=Evaluated") looks redundant with the existing `status`/`Result::EVALUATED` pattern that's been driving the same concept since the table's creation. Not confirmed whether both are kept in sync by the same code paths — a QA check that they never disagree is a good defensive test.
- **NPS v1 (`nps_form`) vs v2 (`nps_form_v2`) are genuinely different schemas**, not duplicates: v1 hard-requires FKs to `enrollment_id`/`course_id`/`batch_id` in addition to `student_id`; v2 drops all three and only has `student_id`, uses `text` instead of `string` for free-text answers, and its reason-mapping pivot adds a second-level `reason_parent_id` hierarchy v1 lacks. Confirm with the team which the live frontend actually submits to before building fixtures for "the" NPS table.

### Status/enum values that matter for DB-level assertions

| Entity | Column | Confirmed values |
|---|---|---|
| `StudentAssignment` | `status` | `DEACTIVE=0`, `ACTIVE=1`, `PENDING=2`, `SUBMITTED=3`, `RESUBMITTED=4` (unreachable in the live app), `EVALUATED=5` |
| `Result` | `status` | `DEACTIVE=0`, `ACTIVE=1`, `PENDING=2`, `RESUBMIT=3`, `EVALUATED=5` (no `4` defined) |
| `Enrollment` | `status` | `PENDING=0`, `ACTIVE=1`, `PAUSED=2`, `RESUME_REQUESTED=3`, `PAUSE_REQUESTED=4` |
| `Enrollment` | `deactivation_status` | `NORMAL_DEACTIVATION=0`, `BATCH_MIGRATION_DEACTIVATION=1`, `COURSE_MIGRATION_DEACTIVATION=2`, `BOOTCAMP_MIGRATION_DEACTIVATION=3` (see backfill caveat above) |
| `AssignmentLog` | `sent_status` | `NOT_SENT='Not Sent'`, `NORMAL='N'`, `CSV='C'`, `SENT='Sent'` (table is dead code — see below) |

**Don't assume `StudentAssignment` and `Result` status ints line up positionally** even though several values coincide (both use `5` for "evaluated") — they're independent enums that happen to share some numbers.

### Confirmed dead tables — don't seed fixtures expecting real data

`assignment_log` / `assignment_log_mapping` (AssignmentSendingLog module — every write site is commented out in application code, per `documentation/USER_WORKFLOWS.md` §3.2). `webhooks` / `webhook_events` / `webhook_logs` (Webhook module — confirmed via grep that no code anywhere reads or dispatches against these tables, despite full CRUD existing). Also, a commented-out performance-index migration (`2024_12_19_000000_add_performance_indexes_to_result_tables.php`) shows intended composite indexes on `results`/`student_assignments`/`result_exercise_scores`/`assignments` that were **never actually applied** — don't assume those indexes exist when reasoning about query performance.

### Unconstrained "FK-shaped" columns — the DB will not enforce referential integrity here

A recurring pattern across many tables: a column named `*_id` that looks like a foreign key but is declared as a plain integer with no `->foreign()`/`constrained()` call. Confirmed instances include: `students.country_id`, `enrollments.bootcamp_id`, `course_categories.parent_id` (self-reference), `class_csat_form_reason.parent_id`, `assignment_csat_form_reasons.parent_id`, `evaluator_csat_form_reason.parent_id`, `nps_form_reason.parent_id`, `performance_coach_csat_form_reason.parent_id`, `student_dashboard_journey_steps_mapping.enrollment_id`, `course_job_mappings.course_id`. **A QA suite can insert an orphaned/invalid reference into any of these without the database rejecting it** — if you need referential-integrity testing, it has to happen at the application/validation layer, not the schema layer, for these specific columns.

---

## 2. Identity, Enrollment & Reference Data

> 28 tables. `students`, `enrollments`, and `users` were traced through their full alter-migration history (6, 9, and 8 alters respectively).

### `users`
**Owning module:** `App\Models\User` (core, not a `Modules/*` entity) **Purpose:** internal admin/staff accounts.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | bigint PK | no | — | |
| title | string(10) | yes | — | |
| first_name / last_name / full_name | string | no | — | |
| email | string | no | — | unique |
| calendly_link | string | yes | — | |
| country_id | bigint | no | — | FK → countries.id, cascade delete |
| phone | string | no | — | |
| status | tinyint | no | — | `User::USER_DISABLED`/active — check entity constants |
| edmingle_id | int | yes | — | set on first LMS sync |
| kanboard_id | int | yes | — | legacy, ProjectManagement (deprecated) |
| forum_text, forum_token_time | text/timestamp | yes | — | legacy, Forum (deprecated) |
| email_verified_at, last_login | timestamp | yes | — | |
| password, remember_token | string | no/yes | — | |
| created_by / updated_by | bigint | yes | — | self-referencing FK → users.id |
| **ats** | enum('0','1') | yes | '0' | added 2025-06-30 — ATS module participation flag |
| **meeting_id, meeting_schedule_id, has_event, meeting_status, meeting_link_status, meeting_email** | mixed | yes | — | 6 columns added across 2024 — all belong to StudentBookACall's instructor-booking feature; a `User` row becomes a bookable instructor when populated |
| **tmp_verification_token, tmp_verification_token_expire_at** | string/timestamp | yes | — | added 2024-07-31 — short-lived token, same pattern as `students` |
| timestamps, soft-deletes | — | — | — | |

**Relationships:** self-FK `created_by`/`updated_by`; `country_id` → countries.id; inbound FKs from most tables' `created_by`/`updated_by` app-wide.
**Notes:** `meeting_*` columns are the only truly recent additions; core identity shape stable since 2022.

### `students`
**Owning module:** `Student` **Purpose:** the learner-facing account, parallel to `users`.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | bigint PK | no | — | |
| reg_code | string | no | — | unique, format `STU{YYYYMMDD}/{id}` |
| full_name | string | no | — | indexed |
| email | string | no | — | unique + indexed |
| phone, date_of_birth, gender, father_name | mixed | mostly yes | — | |
| address, pin_code, city, state, country | string | yes | — | free-text address fields |
| linked_in_link, cv_title, id_image, image | mixed | yes | — | |
| password | string | no | — | |
| status | tinyint | no | — | indexed; `PENDING`/`ACTIVE`/`DISABLED` |
| kanboard_id | int | yes | — | legacy, ProjectManagement (deprecated) |
| lms_id | bigint unsigned | yes | — | Edmingle student id |
| forum_id, forum_pass, forum_access_token, forum_token_time | mixed | yes | — | legacy, Forum (deprecated) |
| tmp_verification_token, tmp_verification_token_expire_at | string/timestamp | yes | — | 5-min login/reset token |
| verification_otp | string | yes | — | forgot-password OTP (see §1 dual-OTP finding) |
| enrollment_form_filled_at | timestamp | yes | — | drives `enrollmentDataRequired` login flag |
| created_by / updated_by | bigint | yes | — | FK → users.id |
| **country_id** | int | yes | — | added 2023-06-27 — plain integer, **no DB-level FK constraint** despite the name |
| **otp, otp_expire_at** | string/timestamp | yes | — | added 2026-02-05 — second OTP mechanism, see §1 |
| **first_time_login** | int | no | 0 | added 2026-02-05 |
| **edmingle_api_key, edmingle_expire_at** | string/bigint | yes | — | added 2024-03-08 — per-student Edmingle SSO token |
| **meeting_accessible** | string | no | 1 | added 2025-09-24 — type is `string`, not boolean, despite the flag-like name |
| **zoho_contact_id** | string | yes | — | added 2026-01-28 |
| **is_terms_and_condition_checked, is_message_send_aggreed** | int | yes | — | added 2026-02-03 — literal misspelling `aggreed` is the real column name |
| **terms_and_conditions_details_json** | text | yes | — | added 2026-02-03 |
| timestamps | — | — | — | **no soft-deletes** (unlike `enrollments`) |

**Relationships:** `created_by`/`updated_by` → users.id. Inbound: `enrollments.student_id` and dozens of CSAT/result/assignment/coaching tables across every domain.
**Notes:** See §1 for the dual-OTP finding and the unconstrained `country_id`.

### `enrollments`
**Owning module:** `Enrollment` **Purpose:** the core record linking a student to a course/bootcamp/package purchase.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | bigint PK | no | — | |
| enrollment_code | string | yes | — | unique |
| course_id | bigint | no | — | FK → courses.id, cascade |
| batch_id | bigint | yes | — | FK → course_batches.id, cascade |
| status | int | no | — | `PENDING=0`, `ACTIVE=1`, `PAUSED=2`, `RESUME_REQUESTED=3`, `PAUSE_REQUESTED=4` |
| batch_assigning_eligibility | string | no | 'Eligible' | |
| bootcamp_id | int | yes | — | **plain int, no FK constraint** to bootcamps.id |
| bootcamp_name | string | yes | — | |
| batch_assigned_by, certified_by | bigint | yes | — | FK → users.id |
| course_plan_type_id | bigint | yes | — | FK → course_plan_types.id |
| student_id | bigint | no | — | FK → students.id, cascade |
| package_id, reference_package | bigint | yes | — | both FK → packages.id |
| is_certified | int | no | — | `CERTIFIED=1`/`NOT_CERTIFIED=0` |
| certificate_file | string | yes | — | |
| passing_criteria | json | yes | — | **point-in-time criteria snapshot** — see `documentation/API_SPECIFICATIONS.md` §3, this is what `marksheetCalculation()` reads, not a live join |
| current_percent | decimal(5,2) | no | 0.0 | |
| subjective_passing_percent, written_passing_percent | decimal(5,2) | yes | — | |
| completed, completed_at | boolean/timestamp | yes | false | completed_at set once |
| mcq_completed, mcq_score | mixed | yes | — | |
| ls_order_id | int | yes | — | LawSikho revenue-side order id — idempotency key |
| created_by / updated_by | bigint | yes | — | FK → users.id |
| **course_calendar_map** | tinyint | no | 0 | added 2026-06-01 |
| **is_batch_migrated** | tinyint | no | `BATCH_NOT_MIGRATED`(0) | added 2023-02-15 |
| **edmingle_batch_id** | bigint | yes | — | added 2024-01-11 — FK-shaped, not constrained |
| **dashboard_journey_steps** | json | yes | — | added 2024-02-08 |
| **deactivation_reason** | string(255) | yes | — | added 2025-09-17 |
| **original_enrollment_id, original_enrollment_date** | mixed | yes | — | added 2026-02-25 — links a migrated/paused enrollment back to its origin |
| **paused_at, pause_reason, paused_reason** | mixed | yes | — | added 2026-02-25 — **two separate similarly-named text columns**; confirm which is actually written to |
| **pause_status** | enum('paused','resume_requested','resumed','refund_eligible_paused_requested') | yes | — | added 2026-02-25 |
| **refund_eligible_pause_request_status, refund_eligible_pause_request_time** | mixed | yes | — | added 2026-03-02 |
| **deactivation_status** | unsigned int | no | 0 | added 2026-06-01 — see §1 for the commented-out backfill finding |
| timestamps, soft-deletes | — | — | — | |

**Relationships:** FKs to courses, course_batches, course_plan_types, students, packages (×2), users (×3). Inbound: student_assignments, enrollment_pause_log_new, bulk_enrollment_details, most CSAT tables.
**Notes:** See §1 for the `deactivation_status` backfill gap — a genuine data-quality trap for pre-2026-06-01 rows.

### Reference & lookup data

- **`countries`** (Country module) — `id`, `short`(2), `name`(80), `common_name`(80), `iso3`(3, nullable), `num_code`(nullable), `phone_code`. No timestamps. `id: 99` is hardcoded in the app to always represent India regardless of seeded data.
- **`edmingle_countries`** (root) — genuinely separate country table mirroring Edmingle's own list (`id`, `country_code_id`, `code`, `name`, `dial_code`, `flag_svg_url`) — don't assume it's kept in sync with `countries` or shares ids.
- **`states`** (State module) — `id`, `name`(80), `country_id` (FK → countries, cascade). No timestamps.
- **`job_roles`** (JobRole module) — `id`, `title`, `created_by`/`updated_by` (FK → users), timestamps.
- **`week_days`** (root) — `id`, `name` — static Mon–Sun lookup, no timestamps.

### User & Student auxiliary tables

- **`user_details`** (User) — `id`, `user_id` (FK → users), `third_party_id`/`third_party_type` (nullable), timestamps.
- **`user_job_role_mappings`** (User) — pivot, `user_id`/`job_role_id` (both FK, cascade), timestamps.
- **`user_emails`** (root, used by StudentBookACall) — `id`, `user_id` (FK → users, cascade), `email`, `domain`, timestamps, **deleted_at** (soft-deletes retrofitted 2025-04-08 by a different module than the one that created the table).
- **`student_other_details`** (Student) — mirrors `user_details`: `id`, `student_id` (FK), `third_party_id`/`third_party_type` (nullable), timestamps.
- **`student_week_day_availabilities`** (Student module, but structurally tied to the deprecated PerformanceCoach domain) — `id`, `student_id` (FK → students, cascade), `range_id` (FK → **performance_coach_ranges**.id, cascade — ⚠️ hard dependency on a deprecated module's table), `weekday_id` (FK → week_days, cascade), `timezone` (added 2024-12-16), `start_time`/`end_time` (added 2025-04-07, same migration also first added timestamps to this table). Given the FK into a deprecated domain, confirm with the team whether this is still written to before building fixtures.
- **`student_original_registration_details`** (StudentProfile) — `id`, `student_id` (FK, nullable), `original_registration_details_json` (text), soft-deletes, timestamps.
- **`know_about_lawsikho_question`** / **`know_about_lawsikho_student_answer`** (StudentProfile — note **singular** table names, non-standard Laravel convention) — question bank (`id`, `question`, `status`) and student answers (`id`, `student_id` FK, `answer_id` FK, `is_other` nullable), both with timestamps.

### Enrollment auxiliary tables

- **`enrollment_questions`** / **`enrollment_question_answers`** (Enrollment) — question bank (`id`, `question` longText) and answers (`id`, `user_type`, `student_id` FK, `question_id` FK, `answer` json, `is_other` nullable). ⚠️ This is a *different* Q&A system from the `resp_<question_number>` convention-based one used by `store-enrollment-form` (`documentation/API_SPECIFICATIONS.md` §6) — not confirmed whether that endpoint's answers persist here.
- **`enrollment_csv_report`** — export audit log: `id`, `user_id` (FK), `file_name`, `IP`/`browser` (nullable), timestamps.
- **`bulk_enrollment_reports`** / **`bulk_enrollment_details`** (Enrollment) — bulk-CSV-enrollment job tracking. Reports: `id`, `user_id` (FK), `bootcamp_id` (FK → bootcamps, **set null** on delete — one of the few genuinely DB-enforced FKs to `bootcamps`), `course_ids` (json), `status` enum(processing/completed/failed), counts. Details: per-row outcome, `bulk_enrollment_report_id` (FK cascade), `student_id`/`enrollment_id` (nullable, set null), `status` enum(success/failed).
- **`enrollment_pause_log_new`** (Enrollment) — audit trail for the course-pause/refund/waiver feature (see repo-root `CR10_COURSE_PAUSE_REFUND_WAIVER_*.md` for business rules): `id`, `enrollment_id` (FK cascade), `paused_by_student_id` (FK, nullable), `paused_at`, `paused_reason`, `resumed_at`, `resumed_by_admin_id` (FK, set null), `status` enum (**required, no default**), `support_ticket_id` ("Zoho ticket ID"), `request_source`, timestamps. See §1 for the missing `accepted`/`rejected` columns.
- **`csv_export_templates`** (Enrollment) — saved column-selection presets: `id`, `user_id` (FK), `name`, `export_type` (default `'pause_resume_history'`), `fields` (json), timestamps.

### Framework & cross-cutting infra (identity-adjacent)

- **`personal_access_tokens`** (Sanctum) — backs every issued `auth:sanctum`/`auth:student` token, polymorphic `tokenable` (User or Student). Standard package shape: `tokenable_type`/`tokenable_id`, `name`, `token` (unique), `abilities`, `last_used_at`, `expires_at`, timestamps.
- **`password_resets`** (Laravel default) — `email` (indexed), `token`, `created_at`, no `id`. Likely vestigial — the app's actual reset flows use `tmp_verification_token` on `students`/`users` instead; confirm before assuming this is live.
- **`table_deactivating_comments`** (migration filename) → actual table **`deactivating_comments`** (root) — generic polymorphic comment log for any "deactivatable" entity via `commentable` morph: `id`, `comment`, `status` (1=activating/0=deactivating), `created_by` (FK), `commentable_type`/`commentable_id`, timestamps. Note the filename/table-name mismatch when grepping migrations.
- **`fcm_tokens`** (root) — push-notification device tokens, polymorphic `tokenable`: `id`, `tokenable_type`/`tokenable_id`, `token`, timestamps.
- **`media`** (spatie/laravel-medialibrary package) — generic polymorphic file attachment, used app-wide (e.g. course AI files). Standard package shape; not app-specific, not deep-dived further.

---

## 3. Course & Program Catalog

> 31 tables. Two migration files (`add_edmingle_id_to_courses_table`, `add_curriculum_id_to_courses_table`) are **no-ops** — their `up()` bodies are commented out — so `edmingle_id`/`curriculum_id` do NOT exist on `courses` despite the filenames.

### `courses`
**Owning module:** Course **Purpose:** central course/bootcamp-course catalog entity.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | bigint PK | no | — | |
| ai_model_id | bigint FK | yes | null | added 2026-03-10, nullOnDelete |
| assignment_instruction_link, assignment_sample_feedback_link | text | yes | null | added 2026-03-10 |
| status | boolean | no | `STATUS_PENDING` | |
| course_name | string | no | — | |
| duration_days | integer | no | — | |
| image_path | text | yes | null | added 2022-06-22 |
| course_category_id | bigint FK | yes | null | → course_categories.id, cascade |
| default_evaluator_id, default_written_evaluator_id | bigint FK | no | `1` | → users.id, cascade |
| student_coach_id, student_writing_coach_id, freelance_id, placement_id | bigint FK | yes | null | → users.id, cascade |
| course_type | tinyint | no | `SIMPLE_COURSE` | vs. `BOOTCAMP_COURSE` |
| is_ai_enabled | boolean | no | false | added 2026-03-19 |
| created_by / updated_by | bigint FK | yes | null | → users.id, cascade |
| deleted_at | timestamp | yes | — | soft-deletes |

**Relationships:** belongs to course_categories, ai_models; many users FKs; referenced by course_evaluator_mappings, course_mentor_mappings, course_criterias, course_batches (indirectly), packages (via pivot), assignments, enrollments.
**Notes:** ⚠️ `edmingle_id`/`curriculum_id` migrations are commented-out no-ops — those columns don't exist despite the filenames.

### Course pivots & sub-entities
- **`course_evaluator_mappings`** / **`course_mentor_mappings`** — pivots, course ↔ users (evaluator/mentor). `id`, `course_id` FK cascade, `evaluator_id`/`mentor_id` FK cascade, timestamps. No unique constraint on the pair — duplicate mappings possible.
- **`course_optional_questions`** (migration filename: `mock_question`) / **`course_optional_question_answers`** (migration filename: `mock_answer`) — ⚠️ **table names don't match migration filenames**, search by table name not filename. Questions: `course_id` FK, `question` text, `is_mandatory` boolean default true, `status` boolean. Answers: `enrollment_id`/`student_id` FK, `question`/`answer` text (stores question text redundantly rather than FK'ing back — a schema-drift risk if question text is edited later).

### Pass-mark criteria (three tables, one snapshot column — see `documentation/USER_WORKFLOWS.md` §2.3)
- **`course_criterias`** — the one actually read live by completion logic. `course_id` FK cascade; `minimum_exercises`/`each_exercises_marks`/`min_attempt_exercises_percent`/`no_writing_assignments`/`writing_assignments_marks` (nullable int); `lms_mcq` boolean; `pass_marks_needed_percent`/`pass_marks_needed`/`total_marks` (not nullable); soft-deletes (added 2023-11-10). No DB-level unique constraint on `course_id` despite app-level "one per course" expectation.
- **`course_categories`** — `id`, `parent_id` (**plain integer, no FK** — self-referential hierarchy not DB-enforced), `category_name` (unique), `status`, `type` (default `TYPE_COURSE`), `created_by`/`updated_by` FK, soft-deletes.
- **`course_category_criterias`** — same shape as `course_criterias` but scoped to `category_id` FK cascade; no soft-deletes; no DB-level unique constraint despite app-level "one per category" validation.

### `course_batches`
**Owning module:** CourseBatch **Purpose:** cohort/batch scheduling, globally unique by date.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | bigint PK | no | — | |
| batch_date | string | no | — | **unique** across ALL courses — a real DB-level unique index, not just app validation |
| start_date, date_of_compilation | date | yes | null | |
| added_by | bigint FK | yes (relaxed 2026-06-01) | — | → users.id; **was NOT NULL originally** |
| updated_by | bigint FK | yes | null | → users.id |
| status | boolean | no | false | |
| course_calendar_map | tinyint | no | 0 | added 2026-06-01 |
| is_draft | boolean | yes | null | added 2026-07-08 |
| deleted_at | timestamp | yes | — | soft-deletes |

- **`edmingle_batches`** — genuinely **separate** from `course_batches` (resolves earlier uncertainty in `documentation/USER_WORKFLOWS.md` §2.4): `batch_id` FK → course_batches cascade, `course_id` FK → courses cascade, `edmingle_batch_id`/`tutor_id`/`tutor_name`/`edmingle_batch_name`, `created_by` FK (relaxed to nullable 2026-06-01).

### Course FAQs, Plan Types, Packages, Bootcamp
- **`course_faqs`** — `course_id` FK cascade, `question`/`answer` longText, `status` boolean default true, soft-deletes.
- **`course_plan_types`** — `name` (unique), soft-deletes (added 2023-11-10). Confirmed no live consumer at enrollment time.
- **`packages`** — `name`, `duration_days`, `image_path` (nullable, added 2022-06-22), soft-deletes. No unique constraint on `name`.
- **`package_course_mappings`** — pivot, `package_id`/`course_id` FK cascade.
- **`bootcamps`** — `name`, `refund_eligible_course` (int default 1, added 2025-09-16), `title` (nullable, added 2026-04-23). No `created_by`/soft-deletes — notably thinner than other catalog tables, consistent with being populated by an external ingestion path (`LawSikho`'s `bootcamp_from_lawsikho`, see `documentation/API_SPECIFICATIONS.md` §7) rather than a full admin CRUD module.
- **`bootcamp_books`** — pivot, `book_id` FK → books (⚠️ deprecated BookMaster table) cascade, `bootcamp_id` FK cascade, `delivery_start_date` (default `'2022-01-01'`).

### Topics
- **`topics`** — `title`, `created_by`/`updated_by` FK. No soft-deletes, no status/active flag. Confirmed real cross-cutting usage by Assignment/StudentAssignment/Result, not just course content.
- **`topic_doc_details`** — `topic_id` FK cascade, `title`, `link` (nullable), `note` (nullable longText).
- **`student_assignment_video_mapping`** — ⚠️ lives under the `Topic` module despite the name suggesting Assignment/Result ownership. `student_id` FK, `topic_doc_details_id` FK, **`assignment_id` FK → `student_assignments`** (nullable — same naming-trap pattern as §1), `comment`/`rating` (required).

### ⚠️ Class & ClassCSAT tables — modules not in production use

10 tables under `Class`: `classes` (Zoom-backed live class definition — `zoom_id`/`zoom_join_url`/etc., `zoom_account` int with no real FK despite an inline comment intending one, `RecurrenceData` PascalCase column breaking the table's otherwise snake_case convention), `class_occurrance_date`, `class_expert`/`class_host` (same shape), `class_topic_and_type`, `class_package` (FK into still-active `packages` — deleting a package would cascade-delete rows here even though Class itself is dead), `class_course_mapping` (FK into still-active `courses`, same caveat), `class_course_batch` (FK into still-active `course_batches`, same caveat), `class_participants` (`zoom_meetng_id` — literal typo in the column name; `join_time`/`leave_time` stored as strings not timestamps; `classDate` PascalCase), `zoom_users`.

3 tables under `ClassCSAT`: `class_csat_form`, `class_csat_form_reason` (`parent_id` unconstrained self-reference), `class_csat_form_reason_maping`.

---

## 4. Assignment & Evaluation Lifecycle

> 21 tables. **Systemic finding: see §1 — every `assignment_id` column in this domain except `assignment_log_mapping.assignment_id` actually points to `student_assignments.id`.**

### `assignments`
**Owning module:** Assignment **Purpose:** the reusable, course-scoped assignment-library template.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | bigint PK | no | — | |
| ai_model_id | bigint FK→ai_models | yes | null | added 2026-03-19, nullOnDelete |
| assignment_instruction_link, assignment_sample_feedback_link | text | yes | null | added 2026-03-19 |
| course_id, topic_id | bigint FK | no | — | cascade |
| assignment_code | string | no | — | |
| assignment_type | int | no | — | `TYPE_SUBJECTIVE=0`, `TYPE_WRITTEN=1` |
| number_of_exercises, word_count | int | no | — | |
| assignment_download_file | string | yes | null | |
| plagiarism | int | no | — | `PLAGIARISM_NO=0`/`YES=1` — **inert at submission time** |
| ref_assignment_no | int | yes | null | |
| status | int | no | `STATUS_ACTIVE`(1) | `STATUS_DEACTIVE=0`/`ACTIVE=1` |
| is_bootcamp_written | tinyint | no | 0 | |
| package_id | bigint FK | yes | null | cascade |
| allowed_file_types | json | yes | null | added 2025-08-22 |
| is_ai_enabled | boolean | no | false | added 2026-03-19 |
| created_by / updated_by | bigint FK | no/yes | — | cascade |

**Notes:** 4 ALTER migrations after creation (AI config, `allowed_file_types`) — original CREATE undersells current shape. `is_ai_enabled` duplicated onto `student_assignments` as a per-instance override.

### `tags` / `taggables` (AssignmentTag — spatie/laravel-tags shape)
`tags`: `id`, `name`/`slug` (json, multi-locale), `type` (nullable — distinguishes `ASSIGNMENT_TAG`/`USER_TAG`/`STUDENT_TAG`), `order_column`, `status` (default true), `created_by`/`updated_by`, soft-deletes. `taggables`: `tag_id` FK cascade, `taggable_id`+`taggable_type` (morph), unique on `(tag_id, taggable_id, taggable_type)`.

### `assignment_log` / `assignment_log_mapping` — ⚠️ DEAD CODE, never populated
Full CRUD controller exists, but every write site is commented out (`documentation/USER_WORKFLOWS.md` §3.2/§6). `assignment_log`: `process_id`, `assignment_type`(char), `server_request`/`csv_file_location` (text, nullable). `assignment_log_mapping`: `assignment_log_id` FK nullable, **`assignment_id` FK → `assignments.id`** (the one exception to the naming trap), `enrollment_id`/`student_id` FK nullable, `sent_status` (`NOT_SENT='Not Sent'`/`NORMAL='N'`/`CSV='C'`/`SENT='Sent'`).

### `assignment_csat_form` / `_reasons` / `_reasons_mapping` (AssignmentCSAT)
Form: `student_id` FK, `enrollment_id` FK nullable, **`assignment_id` FK → `student_assignments`**, `course_id` FK, `batch_id`/`package_id` FK nullable, `rating` int, `other`/`comment` nullable. Reasons: `question`, `parent_id` (unconstrained). Mapping: pivot.

### `student_assignments`
**Owning module:** StudentAssignment **Purpose:** the per-student, per-enrollment instance of an assigned assignment — the central table of the grading pipeline.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | bigint PK | no | — | |
| assignment_instruction_link, assignment_sample_feedback_link | text | yes | null | added 2026-03-10 |
| enrollment_id | bigint FK→enrollments | no | — | cascade |
| assignment_id | bigint FK→**assignments** | no | — | cascade — correctly points at assignments, unlike every other `assignment_id` in this domain |
| ai_model_id | bigint FK→ai_models | yes | null | added 2026-03-19, nullOnDelete |
| submission_last_date | date | yes | null | |
| submit_counter | int | no | 4 | decremented per submission attempt (mirrors `RESUBMIT_COUNTER=4`) |
| status | int (indexed) | no | `STATUS_ACTIVE`(1) | see §1 enum table |
| is_ai_enabled | boolean | no | false | added 2026-03-19 |
| number_of_exercises | int | no | — | |
| mandatory | boolean | no | true | |
| created_by / updated_by | bigint FK | no/yes | — | cascade |
| deleted_at | timestamp | yes | — | soft-deletes added 2023-11-10 |

**Relationships:** belongs to enrollments, assignments, optionally ai_models; has many results, assignment_csat_form rows, first_assignment_send_log rows.

### `first_assignment_send_log` (StudentAssignment)
Reporting-only: `enrollment_id` FK, **`assignment_id` FK → `student_assignments`**, `course_id`/`batch_id` FK, `first_assignment_send_at` (date, required), `status` (string, required).

### `evaluator_csat_form` / `_reason` / `_reason_maping` (EvaluatorCSAT)
Distinct from AssignmentCSAT — rates the *evaluator*, not the assignment. Form: `student_id`, `result_id`, `evaluator_id` FK; `rating` int; `other_option`/`comment`/`status` nullable. Reason/mapping: same pattern as AssignmentCSAT's.

### `results`
**Owning module:** Result **Purpose:** the grading record for one submission attempt — the single most heavily-evolved table in this domain (9 ALTER migrations after creation).

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | bigint PK | no | — | |
| ai_evaluation_uuid | uuid | yes | null | added 2026-03-10, unique |
| ai_evaluation_status, ai_score, ai_feedback, ai_feedback_pdf_url | mixed | yes | null | added 2026-03-10 |
| ai_model_id | bigint FK | yes | null | added 2026-03-10, nullOnDelete |
| ai_evaluated_at, ai_instruction_source, ai_feedback_sample_source | mixed | yes | null | added 2026-03-10 |
| reviewer_edited_score, reviewer_edited_feedback, reviewed_by, reviewed_at | mixed | yes | null | added 2026-03-10 |
| student_id | bigint FK | no | — | cascade |
| assignment_id | bigint FK→**student_assignments** | no | — | cascade — the original, most-cited naming-trap instance |
| evaluator_id | bigint FK→users | yes | null | cascade |
| status | int | no | `ACTIVE`(1) | see §1 enum table |
| is_evaluated | boolean | no | 0 | added 2026-03-26 — see §1, possibly redundant with `status` |
| plagiarism_result, plagiarism_result_file | mixed | yes | null | 1–100 range |
| submitted_date, submitted_file | mixed | yes | null | |
| feedback_file, feedback_file_original_name, feedback_link | string | yes | null | |
| evaluation_date, evaluation_due_date | datetime | yes | null | |
| is_email_sent | int | no | `EMAIL_NOT_SENT`(0) | |
| feedback_to_student | text | yes | null | |
| is_review_done | boolean | no | `REVIEW_NOT_DONE`(0) | |
| waive_marks | int | yes | null | stored as literal `3` when truthy, per API layer |
| feature_assignment | boolean | no | false | |
| reason, resubmission_feedback | mixed | yes | null | see REASON_NEW_* constants below |
| bootcamp_id | int | yes | null | **not FK-constrained** |
| unicheck_details, unicheck_file_details, unicheck_check_details | text | yes | null | added 2022-05-17 — ⚠️ **dead columns**, Unicheck integration removed |
| latest | tinyint | yes | null | added 2022-06-16 — flags the current active result among a student_assignment's history |
| updated_by | bigint FK | yes | null | added 2024-05-24, cascade |
| deleted_at | timestamp | yes | null | soft-deletes added 2024-07-11 |
| feedback_edit_reason | text | yes | null | added 2026-03-26 |

Resubmission-reason constants (free text, not enum): `REASON_ONE`–`REASON_FOUR` (older wording), `REASON_NEW_1`–`REASON_NEW_6` (current, e.g. `"Incorrect File Format (.bin / .zip)"`, `"Handwritten Submission"`) — use the `REASON_NEW_*` set for current-state assertions.

**Notes:** See §1 for the never-applied performance-index migration.

### `result_exercise_scores`, `course_featured_assignment_mapping`, `student_result_video_mapping`
- **`result_exercise_scores`** — `result_id` FK cascade, `serial_number` (required), `obtain_marks` (float, nullable — sentinel `101` clears to null), `full_marks` (default 10).
- **`course_featured_assignment_mapping`** — `course_id`/`result_id` FK, **`assignment_id` FK → student_assignments**, `topic_id` FK nullable, `status` (required).
- **`student_result_video_mapping`** — `student_id` FK, **`assignment_id` FK → student_assignments**, `evaluator_id` FK nullable, `course_id`/`result_id` FK, `rating_value` (required).

### AI Evaluation tables
- **`ai_models`** — `model_name`/`model_version`/`model_description`, `gemini_model_id` (required), `is_default`/`is_active` (int), soft-deletes.
- **`ai_evaluation_audit_logs`** — `result_id` FK nullOnDelete, `event`, `actor_id` FK nullable, `actor_type`, `original_ai_score`/`edited_score` (decimal), `original_ai_feedback`/`edited_feedback` (longtext), `metadata` (json), **created_at only — append-only log**.
- **`ai_course_material_syncs`** — `course_id` FK nullable **unique** (one sync row per course), `auto_eval_course_id` (required — external service's course id), `sync_status`, `instruction_link_hash`/`feedback_file_hash` (required — change-detection hashes), `last_synced_at`, `sync_error`.

### ⚠️ `student_task_file_mapping` — module not in production use
StudentTasks module. `student_id` FK cascade, `file_name` (required). Table exists but driving module is deprecated.

---

## 5. Student Engagement, Notifications, NPS, Coaching & Call Booking

> 40 tables. Includes the deprecated `PerformanceCoach`/`PerformanceCoachCSAT` domain (14 tables, documented for completeness only) and `StudentBookACall`'s one local table (confirmed live).

### Student Dashboard Journey Steps (StudentDashboardManagement)
- **`student_dashboard_journey_steps`** — admin-defined onboarding checklist. Heavily incrementally altered (9 migrations after creation: `description`, self-referencing `reference_id`, `is_parent_step`, and 4 separate boolean audience-visibility flags each added in their own migration — `is_for_new`/`is_for_old`/`is_hide_for_new`/`is_hide_for_old`). Verify current columns empirically before exact-shape DB assertions.
- **`student_dashboard_journey_steps_mapping`** — per-student progress: `student_id`/`step_id` FK cascade, `status`, polymorphic `subject_type`/`subject_id`, `rating`, `enrollment_id` (**not a real FK** despite the name), plus later-added sequence/parent int columns.
- **`student_dashboard_journey_comments`** — `step_mapping_id`/`step_id` FK cascade (nullable), `feedback` (text), `type`, soft-deletes (added later).

### Notifications (Notification module — shared read/write store with StudentNotifications)
- **`notification`** (custom entity, singular — NOT the same as `notifications` below) — `title`, `content`, `category_id` FK, `scheduled_time`/`sent_at` (originally `date`, later widened to `dateTime` via separate alters — use full datetime values in fixtures), `status` (added later, "0=pending,1=sent"), soft-deletes (added later).
- **`notification_category`, `notification_channel`, `notification_tags`** — simple lookups (`id`, `title`, `created_by`/`updated_by`).
- **Fan-out pivots** (each: `notification_id` FK cascade + one target FK cascade): `batch_notification`→course_batches, `channel_notification`→notification_channel, `course_notification`→courses, `package_notification`→packages, `notification_tag`→notification_tags, **`notification_user`→students** (⚠️ column is literally named `user_id` but FK-constrained to `students.id`, not `users.id`). `notification_user` additionally has `read_at`/`new_comments` (backs unread-count/mark-as-read behavior).
- **`notification_comments`** — `notification_id` FK, `parent_id` (unconstrained, threaded), `comment`, `created_by` (plain int — can hold either a `users.id` or `students.id` depending on `user_type` enum(`admin`|`student`); joining without checking `user_type` first will silently mismatch), soft-delete pair.
- **`notifications`** (root, Laravel's OWN queued-notification table, plural — unrelated data model to `notification` above) — UUID PK, `type`, `notifiable_id`/`notifiable_type` morph, `data` (JSON text), `read_at`. Don't confuse the two tables despite the near-identical name.

### NPS — v1 vs v2, genuinely different schemas (see §1)
- **`nps_form`** (v1) — `student_id`/`enrollment_id`/`course_id`/`batch_id` all FK **required**; `survey_type` (default `SURVEY_TYPE_1`); `rating`/`reason`/`experience`/`suggestions` (string).
- **`nps_form_reason`** — shared by both v1 and v2, the one common table. `question`, `parent_id` (unconstrained, added later).
- **`nps_form_reason_maping`** (v1 pivot — literal "maping" typo in table name) — `nps_id`/`reason_id` FK.
- **`nps_form_v2`** — `student_id` FK **only** (no enrollment/course/batch FK at all); `survey_type` required with no default (unlike v1's default); `experience`/`suggestions` are **text**, not string (tolerates longer answers).
- **`nps_form_reason_mapping_v2`** — `nps_id` FK → **nps_form_v2**, `reason_id` FK → nps_form_reason, plus `reason_parent_id` (added later) for a two-level reason hierarchy v1's pivot lacks.
- **`nps_package_data`, `nps_course_data`, `nps_bootcamp_data`** — pre-aggregated reporting rollups (not raw responses): `<entity>_id` (unconstrained), `<entity>_name` (denormalized snapshot), `promoters`/`detractors`/`total_responses`/`total_students`, `nps` (double). Likely populated by a scheduled job, not by individual NPS submissions.

### ⚠️ Performance Coach & Performance Coach CSAT — modules not in production use

*(14 tables, documented for completeness/historical-data reference only.)*

`performance_coach_call_categories`, `performance_coach_call_schedules` (`student_id`/`performance_coach_id` FK, `category_id` FK nullable, `status` default `ACTIVE`, `due_on`/`overdue_on` dates), `performance_coach_students` (the allocation table that gated call booking — `student_id`/`performance_coach_id` FK, `status` default 1, soft-deletes), `performance_coach_call_outcomes`, `performance_coach_slots` (`start_time`/`end_time` both **unique**), `performance_coach_ranges` (`range_time` unique — this is the table `student_week_day_availabilities` still has a hard FK into, per §2), `performance_coach_block_slots`, `performance_coach_call_suspended_categories`, `performance_coach_call_schedule_slots`, `performance_coach_student_reports`, `performance_coach_start_and_pauses` (pause/resume/cancel workflow timestamps), `performance_coach_csat_form` + `_reason` + `_reason_mapping`.

### ✅ `course_instructor_mappings` — live (StudentBookACall)
`course_id`/`instructor_id` FK cascade — which staff `User`s are eligible instructors for a course, backing the "browse instructors" step of the call-booking flow. **Purely local**: the actual meeting/booking records live in the external sub-project (`MEETING_API_BASE_URL`/`BOOK_A_CALL_API`), not in this app's DB — no local `bookings` table exists for this module at all.

---

## 6. Admin Operations & External Integrations

> 20 tables, including the 5-table RBAC package migration and the deprecated BookMaster/BookDeliveryLog/ProjectManagement domains.

### RBAC (spatie/laravel-permission, all 5 tables from one migration)
- **`permissions`** — `parent_id` FK self-reference cascade; `name`+`guard_name` unique together; `display_name`/`display_endpoint`/`description`; `created_by`/`updated_by` (FK-shaped, not constrained). Static/seeded — no create/update/destroy API routes.
- **`roles`** — `name`+`guard_name` unique together; `status`; soft-deletes; `created_by`/`updated_by` (not constrained). `teams` feature is off — no `team_id` column.
- **`model_has_permissions`** / **`model_has_roles`** — polymorphic pivots (`model_type`+`model_id`), composite PKs, no timestamps.
- **`role_has_permissions`** — pivot, composite PK `(permission_id, role_id)`, no timestamps.

### Internal Notes (versioned)
- **`students_internal_notes`** — `student_id` FK cascade, `history_tab_id` (chains to history, **no DB FK**, app-level link only), `notes`, `status` (default 1), `is_edited`, `created_by`/`updated_by` FK, soft-deletes.
- **`internal_notes_history`** — append-only: `student_id` FK cascade, `internal_note_id` (**no DB FK**, app-level reference), `notes`, `status` (0 on delete-triggered writes), `created_by` FK. No `updated_by`, no soft-deletes — immutable by design.

### `email_templates`
Polymorphic owner (`model_id`+`model_type` via `morphs()` — Admin/Student/Role), `email_type`, `mail_template` (longText), `status`, `created_by`/`updated_by` FK. Per `documentation/API_SPECIFICATIONS.md` §6, retrieval is always role-scoped regardless of the owner type actually stored here — a storage/retrieval mismatch worth testing.

### ⚠️ Books & Delivery — modules not in production use
- **`books`** (BookMaster) — `name`, `sku`, `is_send_able` (default constant). Referenced by `course_books.book_id`, `book_delivery_log.book_id`.
- **`course_books`** (BookMaster) — pivot, `book_id`/`course_id` FK cascade, `delivery_start_date` (default `'2022-01-01'`). `courses` itself remains fully active — only this mapping layer is dead.
- **`book_delivery_log`** (BookDeliveryLog, create + 3 alters) — `enrollment_id`/`book_id`/`bootcamp_id`/`student_id`/`course_id` FK (all cascade); a full **snapshot** of student contact/address at log-creation time (`student_code`/`student_name`/`phone_number`/`student_email`/`address`/`city`/`state`/`country`/`pin_code` — not live-joined, a later student address change won't retroactively update pending rows); `is_sent`/`is_deliverable`/`sent_on`; `is_additional` (added 2023-01-19); `enrollment_creation_date` (added 2023-02-03); `generation_type` (boolean, `MANUAL` vs automatic, added 2023-03-23 alongside `comment`/`updated_by` — this one uses `nullOnDelete`, inconsistent with the cascade pattern used elsewhere in this table).

### AtsAPI
**`course_job_mappings`** — `job_id` (external id, not a local FK), `course_id` (**plain integer, no FK constraint** despite the name), **`channel` — DB-level `enum('Lawsikho','SkillArbitrage')`** (stricter than the app-layer validation described in `documentation/API_SPECIFICATIONS.md` §6, which treats `channel` as an unconstrained string — since the app also hardcodes storage to `'Lawsikho'` regardless of input, this DB constraint likely never gets exercised with a rejected value in practice, but it's a real boundary worth its own DB-level test), `status`/`is_draft` (both `enum(0,1)`, not plain tinyint), `expiry_date`, `user_id` FK cascade nullable.

### ⚠️ Webhook Integration — tables exist, no observed consumer (see §1)
- **`webhooks`** — two identical CREATE migrations, see §1. `webhook_url`/`webhook_name`/`webhook_secret`, `event_id` FK → webhook_events (**NOT NULL at the DB level**, so even though the app never validates this field, the DB will reject an insert with no valid `event_id`), `status`, `failure_count`, `app_name`, `created_by`/`updated_by` FK.
- **`webhook_events`** — `event_name`, `event_type`, `description` (**required**, unusual for a description field).
- **`webhook_logs`** — `webhook_id` FK cascade, `status`, `status_code` (**string, not integer** — unusual), `payload`/`response` (**both required JSON columns** — a manual/test insert must supply valid JSON, e.g. `'{}'`, not NULL, despite no live code ever writing here).

### LawSikho Integration
**`third_party_logs`** — flat audit log for the `log.third.party` middleware, no FK columns at all (not tied to a specific student/enrollment row): `service_name`, `request_url`, `request_method`, `request_headers`/`request_body`/`response_body` (json, nullable), `response_status`, `called_at`. This is what actually backs LawSikho's near-universal request logging even on the ~23 unauthenticated endpoints.

### ⚠️ Project Management — module not in production use
*(Kanboard-backed even when in use — these local tables only ever stored Kanboard-side ID references and local mentor/category mirrors, never full task state.)*
- **`projects`** — `course_id`/`batch_id` FK cascade, `kan_project_id`/`kan_group_id` (the external Kanboard ids), `created_by`/`updated_by` FK.
- **`project_mentors`** — pivot, `project_id`/`mentor_id` FK cascade.
- **`project_categories`** — flat, **no FK to `projects`** — categories are project-independent (replicated into Kanboard per-project at creation time, not scoped locally).
- **`projects_tasks_student_files`** — `student_id` FK cascade, `file_id` (**no FK constraint** — a Kanboard-side file id, consistent with task/file state living in Kanboard), `file_name`. No `project_id`/`task_id` column at all — association tracked entirely on the Kanboard side.

---

## 7. Infrastructure Tables

Pure Laravel/queue framework tables, no app-specific business schema — included for completeness.

- **`failed_jobs`** — `id`, `uuid` (unique), `connection`/`queue` (text), `payload`/`exception` (longText), `failed_at` (timestamp, default current).
- **`job_batches`** — `id` (string PK), `name`, `total_jobs`/`pending_jobs`/`failed_jobs` (int), `failed_job_ids` (text), `options` (nullable text), `cancelled_at`/`created_at`/`finished_at` (integer Unix timestamps, not Laravel's usual `timestamp` type).

Not documented in detail: Laravel's `migrations`, `cache`, `cache_locks`, `sessions` tables (standard framework defaults, config-driven, not app-specific) — these exist per the configured drivers in `config/cache.php`/`config/session.php` but weren't part of the migration files traced for this document.

---

*End of database schema documentation. For request/response contracts see `documentation/API_SPECIFICATIONS.md`; for behavioral workflows see `documentation/USER_WORKFLOWS.md`; for module purposes and the full routes list see `documentation/DEVELOPER_DOCUMENTATION.md`.*
