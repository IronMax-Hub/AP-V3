# LawSikho Assignment Portal API — User Workflows

> **Generated:** 2026-08-29
> **Branch surveyed:** `New-Dummy-Prod-0605`
> **Companion document:** [`documentation/DEVELOPER_DOCUMENTATION.md`](./DEVELOPER_DOCUMENTATION.md) — tech stack, module inventory, auth internals, full routes reference, database schema. This document assumes that one for reference data (guards, route lists, table names) and focuses instead on **what actually happens, in what order, when a real actor (student/admin/external system) does something.**

## How to read this document

Every workflow was traced directly from controller/trait/job source code (not inferred from route or class names alone) and follows this shape:

> **Actors** — who initiates/participates
> **Trigger** — what starts the workflow
> **Steps** — the real sequence, in order, including branches
> **Endpoints involved** — `METHOD /path` — `Controller@action`
> **Side effects** — jobs dispatched, events fired, emails/notifications sent, external calls made, DB writes
> **Notes/uncertainty** — anything the tracing agent could not fully confirm from code; treat these as explicit "verify before you build a test on this" flags, not filler

Five agents traced disjoint sets of modules in parallel; each flagged uncertainty honestly rather than guessing. Where two agents' findings overlap or correct each other (e.g. the `LawSikho` module's real purpose), that's noted inline.

## Table of Contents

1. [Student Identity & Enrollment Workflows](#1-student-identity--enrollment-workflows)
2. [Course & Program Catalog Workflows](#2-course--program-catalog-workflows)
3. [Assignment & Evaluation Lifecycle Workflows](#3-assignment--evaluation-lifecycle-workflows)
4. [Student Engagement, Coaching & Support Workflows](#4-student-engagement-coaching--support-workflows)
5. [Admin Operations & External Integration Workflows](#5-admin-operations--external-integration-workflows)
6. [Cross-Cutting Findings for QA Test Design](#6-cross-cutting-findings-for-qa-test-design)

---

## 6. Cross-Cutting Findings for QA Test Design

*(Placed early on purpose — read this before you design test suites for the workflows below.)*

### ⚠️ Modules confirmed NOT in current use (per team, 2026-08-29) — do not build QA coverage for these

The team confirmed the following 11 modules are no longer in active use, despite having working code/routes: **BookMaster, BookDeliveryLog, Class, ClassCSAT, Forum, StudentForum, PerformanceCoach, PerformanceCoachCSAT, ProjectManagement, StudentClasses, StudentTasks.**

**Update (2026-08-29):** the team confirmed `StudentPerformanceCoach` is also not in use (consistent with §4.8's `PerformanceCoach` allocation step being dead — a student can't get an active coach allocation, so the booking flow it gates is moot too). The team also confirmed **`StudentBookACall` IS live in production** — it integrates with a separate sub-project's own API (the `MEETING_API_BASE_URL`/`BOOK_A_CALL_API` external calls traced in §4.9 are calls to that sub-project, not dead external dependencies). So the full "not in use" list is now 12 modules: the 11 above plus `StudentPerformanceCoach`. `StudentBookACall` is the one call-booking-adjacent module that **is** worth QA coverage — but per §"External services" below, testing it end-to-end requires either staging credentials for that sub-project's API or a mock of it.

The corresponding workflow write-ups below (§2.7, §2.6's book-fulfillment cross-reference, §4.4, §4.6, §4.8 and its `StudentPerformanceCoach` sibling, §5.3, §5.8, §3.10) are kept for reference — the code paths are real and were traced accurately — but are marked **⚠️ NOT IN USE** at each heading. Do not spend QA effort on them unless the team says otherwise.

### External services you cannot test end-to-end without mocking or staging credentials

| Module / Workflow | External dependency | Why it blocks a self-contained test |
|---|---|---|
| Student Dashboard, Student Classes join | Edmingle (LMS) | Live proxy reads + JWT-based SSO token refresh (`LMS_SECRET`); some calls use **hardcoded fallback API keys/URLs** in code, not just `.env` |
| Forum, StudentForum | Vanilla Forum | All non-draft actions are a live HTTP proxy; no local persistence of forum content |
| ProjectManagement | Kanboard | Nearly every action synchronously calls the Kanboard API; task/column state lives in Kanboard, not this app's DB |
| ReferralSystem | `REFERRAL_BASE_URL` | Zero local tables — every action is a live proxy call; reward/earning logic is entirely external |
| StudentBookACall | `MEETING_API_BASE_URL` + `BOOK_A_CALL_API` (a separate sub-project's own API, confirmed live — not a third party) | Booking chains two external HTTP calls with no local-only path |
| AtsAPI (`SkillArbitrage` channel) | External SkillArbitrage portal | Request is proxied wholesale for that channel |
| AIEvaluation | `AUTO_EVALUATION_API_URL` | External auto-grading microservice call per evaluation job |

### A QA client must replicate the app's login crypto, not send plaintext

Both student and admin login/forgot-password flows expect the **password field pre-encrypted client-side** using a scheme keyed by `APP_PASS_PHRASE`. Sending plaintext will fail at server-side decrypt/compare, not cleanly reject with 401/422. Read `AuthController::encrypt`/`decrypt` before building a login harness. Multi-step flows (login, forgot-password) also **rotate short-lived verification tokens between steps** — don't reuse a token issued for step 1 in step 3.

### Known bugs worth a dedicated regression test

- **`AtsGateWay` middleware contains a double-processing defect in its code** for any `channel` value other than exactly `"Lawsikho"` or `"SkillArbitrage"` (including a missing/null channel) — it would fire the external SkillArbitrage proxy call *and* still process locally. **Correction (2026-08-29, see `documentation/API_SPECIFICATIONS.md` §7):** this middleware is registered as an alias but is **not attached to any live route** — `save-job-and-course-mapping` only carries `json.response`. The bug is real in the middleware's own code but currently unreachable through the running app; don't write a regression test expecting to reproduce it live.
- **`LawSikho` ingestion gateway (~25 endpoints) is mostly unauthenticated** — only `active-access`/`revoke-access` require the shared-secret token; endpoints like `add_student` and enrollment ingestion have no visible auth beyond request logging. Worth an explicit "call with no credentials" test to confirm whether that's intentional.
- **`RevenueAPI`'s `get_student_details`** has no visible auth check — student name/phone are retrievable by email guesswork if nothing else gates it upstream (e.g. an API gateway not visible in this codebase).
- **Grading is a two-step process**: saving scores does *not* set `StudentAssignment.status = EVALUATED` — only the separate finalize/`sendMail` action does. A test that checks status after only the score-save call will incorrectly fail.

### Dead or unreachable code — don't spend QA effort here until the team confirms intent

- `AssignmentSendingLog` — every write site is commented out; table is never populated by live code.
- Plagiarism/Unicheck checking — hardcoded `$plagiarism = false`; the `STATUS_RESUBMITTED` transition via this path is unreachable.
- Certificate-generation domain event — `triggerEventForGenerateCertificate()` exists but its call site is commented out; no event fires.
- `Modules/Bootcamp`'s `Bootcamp` model has no `store`/`create` action on its own `BootcampController`. **Correction (2026-08-29, see `documentation/API_SPECIFICATIONS.md` §7):** `Bootcamp::create()` IS called elsewhere — `POST /v1/bootcamp_from_lawsikho` in the `LawSikho` ingestion gateway (§5.6) creates/updates `bootcamps` rows when no existing row matches the caller-supplied `id`. So the table isn't orphaned, just populated from a different module than its own. "Bootcamp courses" remain a **separate, unrelated concept** — just `courses` rows with `course_type = BOOTCAMP_COURSE`, created via `Modules/Course`'s `BootcampCourseController`. Don't conflate the two.
- `CoursePlanType` — no confirmed consumer anywhere in the codebase (expected touchpoint was Enrollment/installments; not found).
- `Webhook` module's `webhooks`/`webhook_events` tables — pure CRUD scaffolding with nothing anywhere dispatching against them. The module's real live functionality is the unrelated `failed-api-responses` sink.

### Ambiguous or competing implementations — confirm with the team before writing coverage for "both"

- **Notifications**: three separate code paths look like inboxes (`Notification` admin broadcast side is legitimate; `StudentNotifications` and `StudentFrontendEnrollment`'s own `NotificationController` look functionally redundant with each other).
- **NPS surveys**: two separate trigger/submit implementations exist (`StudentDashboard`'s `getSurveyData`/`storeNPS` vs. `StudentFrontendEnrollment`'s `NPSController` v1/v2, the latter's `checkNpsDue`/`submitNps` naming suggesting it's the newer rewrite). Unclear which the current frontend actually calls.
- **EmailTemplate**: storage supports per-admin/per-student/per-role templates, but retrieval (`show`) only ever looks up by the current user's *role* — the admin/student-specific storage branches may be dead.
- **CSAT naming trap**: `StudentFrontendEnrollment`'s `submit_evaluation` endpoint submits an **evaluator** CSAT rating, not an assignment evaluation, despite the name. Test by actual route/payload shape, not method name.

---

## 1. Student Identity & Enrollment Workflows

> Scope note: the assigned module list included `RevenueAPI` and `StudentFrontendEnrollment` on the assumption they handle "new enrollment intake." Tracing the actual code shows this isn't the case — see the two corrections called out inline below. The real new-student/new-enrollment intake point is the `LawSikho` module (not in the original scope list, but included here because it's the necessary upstream trigger for the Enrollment module's `store_from_lawsikho` action).

### 1.1 New Student & Enrollment Intake (from LawSikho's main platform)
**Actors:** LawSikho's external revenue/website platform (server-to-server), the Assignment Portal API.
**Trigger:** LawSikho's platform calls this API after a customer completes a purchase/checkout on the main site.
**Steps:**
1. External platform calls `POST /add-student` with student details (name, email, phone, address fields, `countryCode` as a phone code, optional `password`, optional `lms_id`, terms-acceptance metadata).
2. `LawSikhoController::add_student` (via `StudentTrait`) looks up the student by email:
   - If found: updates address/contact fields only (state, city, address, pin, country, phone, lms_id) and returns the existing student record with `201` and message "Student Exist" — this is effectively an upsert-on-contact-info, not a true conflict error.
   - If not found: requires `full_name`, `phone`, `status`; resolves a `Country` row by matching `countryCode` against `phone_code` (falls back to India, phone_code 91, if no match); creates the `Student` row inside a DB transaction. Password is either taken from the request or auto-generated (`Str::random(8)`) and hashed; a `generatePassword()` call also queues a `StudentPasswordGeneration` email with the plaintext password to the student. Original registration metadata (IP/browser/OS/device/terms-checked-timestamp) is stored via `originalRegistrationDetails()`. Tags are attached via `attachTags`.
3. After creation, `SendStudentDataToExternalAPI::dispatch($student)` is queued (wrapped in try/catch so a failure here doesn't fail student creation) — syncs the new student to an external system.
4. Separately, `POST /v1/enrollments/from-lawsikho` → `EnrollmentController::store_from_lawsikho` creates the actual course/bootcamp/package `Enrollment` row(s) tied to the student (looked up again by email), handling course/batch resolution, tag attachment, and (for bootcamps) `ls_order_id`-based idempotency — if an enrollment already exists for that order id, it updates rather than duplicates.
**Endpoints involved:**
- `POST /v1/add-student` — `LawSikhoController@add_student` (via `StudentTrait`)
- `POST /v1/enrollments/from-lawsikho` — routed to `EnrollmentController@store_from_lawsikho`
- Middleware: `json.response`, `log.third.party` (no `auth:sanctum` — instead nominally gated by `CheckLawSikhoApiToken`; see §6 for the confirmed finding that this route is **not actually token-gated**)
**Side effects:** `StudentPasswordGeneration` email queued (new student only); `SendStudentDataToExternalAPI` job queued; `Activity` log entries for student/enrollment creation and reactivation elsewhere in the same trait; tags attached to the student model.
**Notes/uncertainty:** Didn't trace `SendStudentDataToExternalAPI`'s destination (likely Edmingle or a CRM — not confirmed).

### 1.2 Installment Payment → Enrollment Reactivation (RevenueAPI)
**Correction to original scope assumption:** `RevenueAPI` is NOT where new enrollments/students originate. Its only endpoints are a student lookup (`get_student_details`) and an installment-payment webhook that **reactivates already-pending enrollments** — it never creates a `Student` or `Enrollment` row.
**Actors:** LawSikho's revenue/billing system (server-to-server webhook).
**Trigger:** A student pays a pending installment on an existing (pending/paused) enrollment.
**Steps:**
1. Revenue system calls `POST /v1/installment-payment` with `X-Revenue-Secret` header (checked via `hash_equals` against `config('revenueapi.webhook_secret')`), `student_email`, `enrollment_type` (course/bootcamp/package), and the relevant `course_id`/`bootcamp_id`/`package_id`.
2. Request is validated synchronously; on success, `ProcessInstallmentPaymentJob` is dispatched to the `default_high` queue and an "in progress" response is returned immediately (fire-and-forget from the caller's perspective).
3. Job body: finds the `Student` by email (permanently fails the job via `$this->fail()` if not found — no retry); if the student isn't `ACTIVE`, reactivates them and logs an `Activity` entry; finds matching `PENDING` enrollments (filtered by type/course/bootcamp/package id and `deactivation_status = NORMAL_DEACTIVATION`) and sets each to `ACTIVE`, logging an `Activity` entry per enrollment; finally dispatches `StudentAddJob` (Enrollment module) to sync the reactivated enrollments to Edmingle, with a hardcoded admin CC list.
**Endpoints involved:**
- `GET /v1/get-student-details` — `RevenueAPIController@get_student_details` (name/phone lookup by email; no auth — see §6)
- `POST /v1/installment-payment` — `RevenueAPIController@handleInstallmentPayment`, gated by a shared-secret header, not Sanctum
**Side effects:** Student status update, N enrollment status updates, 2 `Activity` log writes per reactivation, `StudentAddJob` dispatched to `default_high` queue (Edmingle sync).
**Notes/uncertainty:** `get_student_details`'s route group middleware is just `json.response` — see §6 finding.

### 1.3 Student Login (two-step, email then password)
**Actors:** Student (via frontend/mobile client).
**Trigger:** Student attempts to log in.
**Steps:**
1. `POST /student/v1/login/email-verification` with `email` → server checks the student exists and is `ACTIVE`; issues a short-lived (5 min) opaque `tmp_verification_token` stored on the student row and returned to the client. Sets `first_time_login = 1` if the student has never logged in before.
2. Client encrypts the password client-side (matching scheme to `APP_PASS_PHRASE`) and calls `POST /student/v1/login/password-verification` with `token` + encrypted `password`. Server looks up the student by token, checks token expiry, decrypts the password server-side via `AuthController::decrypt` and compares against the stored hash. Failed attempts are logged via `addLoginActivityLog`.
3. On success: issues a Sanctum token via `createToken`, then explicitly sets `expires_at` — same-day 23:59 by default, or 30 days out (also pinned to 23:59) if `remember_me` was passed. Response includes the token plus onboarding-flow flags: `addressRequired`, `lms`, `enrollmentDataRequired`, profile image, and basic user info.
**Endpoints involved:**
- `POST /student/v1/login/email-verification` — `StudentAuthController@emailVerification`
- `POST /student/v1/login/password-verification` — `StudentAuthController@passwordVerification`
- `POST /student/v1/student/logout` — `StudentAuthController@destroy` (deletes all of the student's Sanctum tokens — logout-everywhere, not just the current session)
**Side effects:** `activity_logs` entries for both failed and successful login attempts.
**Notes/uncertainty:** See §6 for the client-side encryption requirement — don't send plaintext passwords in tests.

### 1.4 Student Forgot-Password Flow
**Actors:** Student.
**Trigger:** Student can't log in / requests a password reset.
**Steps:**
1. `POST /student/v1/forgot-password/email-verification` with `email` → issues a 5-min `tmp_verification_token` (same mechanism as login) and queues a `StudentForgetPasswordOTPMail` containing an OTP.
2. `POST /student/v1/forgot-password/otp-verification` with `token` + `otp` → validates token not expired and OTP matches `verification_otp`; issues a **new** short-lived token (rotates the token) for the final step.
3. `POST /student/v1/forgot-password/create-password` with the new token + encrypted `password`/`password_confirmation` (same client-side-encryption pattern as login) → decrypts both, confirms they match, and updates the password.
**Endpoints involved:** `PasswordResetController@emailVerification`, `@otpVerification`, `@createPassword`.
**Side effects:** One queued OTP email per attempt; token rotates twice across the flow — don't reuse the first token for step 3.
**Notes/uncertainty:** Didn't confirm whether `createPassword` also revokes existing Sanctum tokens for security — verify before relying on that behavior in tests.

### 1.5 Admin/Staff Login
**Actors:** Internal Admin/Staff user (`App\Models\User`).
**Trigger:** Staff member logs into the admin panel.
**Steps:**
1. Single-step `POST /v1/login` with `email` + client-side-encrypted `password` (same `APP_PASS_PHRASE` scheme as the student flow). Looks up user with `roles` eager-loaded; rejects if not found or `status == USER_DISABLED`; decrypts and checks password hash.
2. On success: queues `LogUserActivity`; if the user has no `edmingle_id` yet, queues `SyncUserWithLMS` (one-time LMS provisioning on first login); updates `last_login` via a direct query (bypassing model events); issues a Sanctum token (`remember_me`-aware, but without the same-day-expiry pinning seen on the student side).
3. Response includes the user's first role name only (`getRoleNames()->first()`) even though a user can have multiple roles via `spatie/laravel-permission`.
**Endpoints involved:** `POST /v1/login` — `AuthController@store`; `POST /v1/logout` — `AuthController@destroy` (auth:sanctum).
**Side effects:** `LogUserActivity` job, conditional `SyncUserWithLMS` job (Edmingle tutor account provisioning via a direct cURL call, not a Laravel HTTP client wrapper).
**Notes/uncertainty:** Registration (`POST /v1/register`) and email verification routes exist but weren't traced — the student side has these commented out, suggesting admin self-registration may or may not actually be enabled in practice.

### 1.6 Student Profile & Enrollment-Form Completion
**Actors:** Student (post-login, using the `enrollmentDataRequired`/`addressRequired` flags returned at login to decide whether to show these forms).
**Trigger:** First login, or any time the student updates their profile/address.
**Steps (endpoint-level; individual handler bodies not fully read):**
1. `GET /profile/personal-info` and `GET /profile/enrollment-form-details` — fetch current profile / enrollment-form state.
2. `GET /getAllCountry` / `GET /filter/country`, `GET /getAllState` / `GET /filter/state` — populate address dropdowns from the `Country`/`State` reference tables.
3. `POST /saveAddress` / `POST /address` (`StudentProfileController@addressSave`) — persists address fields.
4. `PATCH /personal-information` (`StudentProfileController@savePersonalInformation`) — updates name/contact/personal fields.
5. `POST /profile/cv/email`, `POST /profile/id-proof/email` — email a copy of an uploaded CV / ID proof.
**Endpoints involved:** all under `student/v1` prefix, module `StudentProfile`, guarded by the `student` guard.
**Side effects:** Not traced in detail — likely DB updates only, possibly document/email side effects for the CV/ID-proof endpoints.
**Notes/uncertainty:** Handler bodies for items 3–5 weren't read in depth — treat the steps above as route-level inference; recommend a follow-up pass before writing exact response-shape assertions.

### 1.7 Academic Reference Data (StudentDegree, StudentUniversity)
**What they are:** Both modules expose exactly one route each — `GET /search/degrees` and `GET /search/universities` — pure autocomplete/lookup endpoints over static reference tables, not something a student creates/edits directly.
**Notes/uncertainty:** Low-risk to test in isolation as simple search/autocomplete endpoints.

### 1.8 Job Role Reference Data (JobRole)
**What it is:** Reference/lookup data, not a student-facing workflow. Confirmed consumers: `Modules\User\Entities\UserJobRoleMapping` (staff job-role assignment) and `Modules\StudentBookACall`'s `BookACAllUtilityController` (likely populates a job-role dropdown for the book-a-call feature). Exposes `GET /search/job-roles` and `GET /search/specific-job-roles`.

### 1.9 Certificate Request & Delivery
**Actors:** Student (request), Admin/automated process (certificate generation, happens elsewhere — see §2.6), Student (download/resend).
**Trigger:** Student requests a course-completion certificate from their dashboard.
**Steps:**
1. `POST /enrollment/{enrollment}/request-for-certificate` — ownership-checked (`$enrollment->student_id` must match the authenticated student), sets `request_for_certificate = 1` on the enrollment, logs an `Activity` event, and queues two emails: `CertificateGenerate` to the student (acknowledgement) and `CertificateGenerateAdmin` to `support@lawsikho.in` with course/batch/contact details.
2. `POST /enrollment/{enrollment}/send-certificate` — same ownership check; requires `enrollment->certificate_file` to already be populated (422 "Certificate has not been generated yet" if not); emails a `CertificateEmail` with a link built from the stored `certificate_file` path.
**Endpoints involved:** `StudentFrontendEnrollmentController@enrollmentRequestForCertificate`, `@sendCertificate`.
**Side effects:** 2 queued emails on request, 1 queued email on send/resend, 1 `Activity` log entry.
**Notes/uncertainty:** Actual certificate *generation* happens in `CourseCompletionMaster` (§2.6), a separate module — treat this workflow as request/notify only.

### 1.10 Admin User & Role Management (brief)
**What's confirmed:** `User` module (`UserController`) manages staff accounts and their `UserJobRoleMapping`; role/permission assignment is handled by the separate `Role`/`Permission` modules (see §5.1–5.2). Any admin workflow is implicitly gated by the acting user's assigned permissions.

**Scope correction:** Despite its name, `StudentFrontendEnrollment` is **not** where new enrollments are created — it's the student-portal dashboard/aggregation layer (enrolled packages/bootcamps, tasks, project boards, CSAT/NPS surveys, certificate requests), and it also hosts what look like duplicate CSAT/NPS/Notification/Task/Filter controllers belonging to other modules (see §6).

---

## 2. Course & Program Catalog Workflows

> Traced directly from controller/trait/entity code. All actions below are **admin/staff-side** unless noted.

### 2.1 Create a Course
**Actors:** Admin
**Steps:**
1. Admin submits course fields: `course_name`, `course_category_id`, `duration_days`, evaluator/mentor/instructor IDs, optional AI-evaluation config (`ai_model_id`, `assignment_instruction_link`, `assignment_sample_feedback_link`, `is_ai_enabled`).
2. `CourseController@store` → `CourseTrait::createCourse()` runs inside a DB transaction: creates the `courses` row, then creates pivot rows in `course_evaluator_mapping`, `course_mentor_mapping`, `course_instructor_mapping` for each ID supplied.
3. If AI files were uploaded, they're pushed to S3.
4. A `Course` belongs to one `CourseCategory` and optionally has one `CourseCriteria` row (pass-mark rules) and many `CourseFaq` rows.
**Endpoints involved:** `POST /api/v1/course` — `CourseController@store`; category picker via `GET /api/v1/course-categories`.
**Side effects:** dispatches `SyncCourseWithCalendar` job (pushes the course to an external "course calendar" system). Activity logging exists but is currently commented out for `store` (still active for `update`/`destroy`).
**Notes/uncertainty:** `CourseController@update` also detects AI-config changes and propagates them — **correction (2026-08-29, see `documentation/BUSINESS_RULES.md` §3): propagation targets assignments that do NOT yet have AI enabled (`is_ai_enabled=0`), not already-AI-enabled ones as originally stated here** — verified directly against `CourseTrait.php:355-416`. See §3.6.

### 2.2 Bootcamp Course (created via the Course module, not the Bootcamp module)
**Steps:**
1. `BootcampCourseController@store` (lives in `Modules/Course`, not `Modules/Bootcamp`) calls the *same* `createCourse()` trait method as a normal course, but forces `course_type = Course::BOOTCAMP_COURSE`.
2. Listing/search/export/status-change use `/api/v1/bootcamp-course*` endpoints, which just filter `courses` by `course_type`.
**Endpoints involved:** `POST /api/v1/bootcamp-course` — `@store`; `POST /api/v1/bootcamp-course/status/change` — `@changeStatus`; `PUT /api/v1/bootcamp-course/{course}` — `@update`.
**Notes/uncertainty:** See §6 — this creates a row in `courses`, **not** the `bootcamps` table, which is a separate, apparently-unpopulated entity. Don't conflate the two.

### 2.3 Course Categories & Category/Course Pass-Mark Criteria
**Steps:**
1. `CourseCategoryController` manages `course_categories` (simple CRUD).
2. `CourseCategoryCriteriaController@store` creates a **template** of pass-mark rules scoped to a category: `minimum_exercises`, `each_exercises_marks`, `min_attempt_exercises_percent`, `no_writing_assignments`, `writing_assignments_marks`, `lms_mcq`, `pass_marks_needed_percent`, `pass_marks_needed`, `total_marks`.
3. `CourseCriteriaController@store` creates the same shape scoped to one specific `course_id` — this is what actually attaches via `Course::criteria()` (`hasOne`).
4. These criteria values are **not read live at completion time** — they're copied/snapshotted into `enrollments.passing_criteria` (JSON) at enrollment time, and it's that snapshot `marksheetCalculation()` uses (see §2.6). Category/course criteria are the *source template*, not a live join.
**Endpoints involved:** `POST /api/v1/course-categories`, `POST /api/v1/course-category-criteria`, `POST /api/v1/course-criteria`, `POST /api/v1/bootcamp-course-criteria` (course-scoped variant for bootcamp-type courses, read directly by `marksheetCalculation()`).
**Notes/uncertainty:** No code path was found auto-copying `course_category_criterias` → `course_criterias` — confirm whether admins must always set course-level criteria by hand.

### 2.4 Course Batches (Cohort Scheduling)
**Steps:**
1. `CourseBatchController@store` creates a `course_batches` row with `batch_date`, `start_date`, `date_of_compilation`, `status` (defaults `STATUS_ACTIVE`), `added_by`.
2. Separately, `EdmingleBatchController` manages `edmingle_batches` — batches synced from/to Edmingle. `CourseCalendarWebhookController` exposes inbound webhook-style endpoints (`batch-created`, `batch-updated`, `batch-cancel`, `batch-reschedule`, `batch-sync`) for an external "course calendar" system.
**Endpoints involved:** `POST /api/v1/course-batches` — `@store`; `POST /api/v1/course-calendar/batch-created` etc. — `CourseCalendarWebhookController@*`.
**Notes/uncertainty:** Relationship between `course_batches` and `edmingle_batches` (mirrored vs. distinct) wasn't fully resolved — worth a follow-up if it matters for QA seeding strategy.

### 2.5 Course Plan Types, Package, Bootcamp (module), Course FAQs, Topics
- **Course Plan Types** — plain CRUD on `course_plan_types`; see §6, no confirmed consumer found.
- **Package** — `PackageController@store` creates one `packages` row plus `package_course_mapping` pivot rows for each bundled course; searchable with courses attached (`packages.with-courses.search`). How a package purchase creates N `enrollments` is Enrollment-module territory, not traced here.
- **Bootcamp (`Modules/Bootcamp`)** — see §6: no `store`/`create` action exists anywhere for this entity; only listing and book-management (`storeBootcampBooks`/`updateBootcampBooks`) actions exist.
- **Course FAQs** — plain CRUD on `course_faqs`, scoped to a course.
- **Topics** — taxonomy shared across `Assignment`, `StudentAssignment`, and `Result` (`CourseFeaturedAssignmentMapping`) — a real cross-cutting concept, not just course content.

### 2.6 Course Completion & Certificate Generation
**Actors:** Admin (triggers marksheet/certificate actions), System (marks completion)
**Trigger:** Admin runs marksheet calculation for a student's enrollment, typically after assignments are graded.
**Steps:**
1. `GET .../marksheet_calculation/{enrollment}` → `marksheetCalculation()` reads `enrollment.passing_criteria` (JSON snapshot from enrollment time), sums the student's assignment scores, and — for bootcamp-type courses — additionally pulls the course's `CourseCriteria` row for writing-assignment thresholds.
2. If thresholds clear, `enrollment.completed_at` is set (once) and `current_percent`/`subjective_passing_percent` are updated regardless of pass/fail.
3. `generateCertificate` computes a letter grade from `current_percent` (A+ at ≥90 down to C at ≥40, nothing below), renders a certificate PDF, uploads to S3, and updates `certificate_file`/`is_certified`/`certified_by`/`certified_datetime`.
4. `removeCertificate` reverses the above; `sendEmail` queues a `CourseCompletionEmail`.
**Endpoints involved:** `GET .../marksheet_calculation/{enrollment}`, `GET .../generate-certificate/{enrollment}`, `GET .../remove-certificate/{enrollment}`, `POST .../{enrollment}/send/email` — all on `CourseCompletionMasterController` (logic in `CourseCompletionMasterTrait`).
**Side effects:** S3 file write, queued email, enrollment row updates. No domain event actually fires (call site commented out — see §6).
**Notes/uncertainty:** If your QA tests seed `CourseCriteria` expecting it to affect completion for a **non-bootcamp** course, it won't — you must seed `enrollments.passing_criteria` directly.

### 2.7 Live Classes & Class CSAT ⚠️ NOT IN USE (confirmed by team, 2026-08-29)
**Steps:**
1. `ClassController@store` checks for a Zoom-account-level scheduling conflict first (queries `ClassOccurranceDate` for overlapping active classes on the same Zoom account), then builds a real Zoom meeting via a `Zoom` facade, including recurrence support.
2. Class-to-course/batch associations come from the request payload; occurrences, participant sync, and manual re-sync are separate endpoints.
3. **Class CSAT**: student calls `checkAvailable` to see if feedback is due for a class occurrence, then `ClassCSATController@store` (re-checks for duplicate submission per student+occurrence — code comment notes this "will extend as the class module gets completed").
**Endpoints involved:** `POST /api/v1/class` — `@store`; `GET .../manual-sync`, `.../sync-zoom-user`; `POST /api/v1/class-csat/check-available`, `POST /api/v1/class-csat`.
**Side effects:** Live external Zoom API calls; DB writes for classes/occurrences/CSAT.
**Notes/uncertainty:** How/when class attendance gets recorded into a student-progress table wasn't located — a gap if you need to assert attendance-driven side effects.

---

## 3. Assignment & Evaluation Lifecycle Workflows

> Both `App\Models\User` (admin/staff) and `Modules\Student\Entities\Student` use Sanctum's `HasApiTokens` trait, so an `auth:sanctum`-guarded route can be hit by either actor depending on whose token is presented — the guard name alone doesn't tell you which actor is calling. Several routes below are guarded by `auth:sanctum` but the code inside logs the actor as a `User` (staff), suggesting staff-mediated action rather than true student self-service; called out explicitly where seen.

### 3.1 Assignment Library Setup (Admin)
**Steps:**
1. Admin creates an `Assignment` record (title, type — `TYPE_SUBJECTIVE` or `TYPE_WRITTEN`, instructions, topic linkage, plagiarism flag).
2. Optionally tagged via `AssignmentTag` (`spatie/laravel-tags`-backed).
3. A bootcamp-specific variant exists via `BootcampAssignmentController`.
**Notes/uncertainty:** The `plagiarism` flag is now inert — see 3.3 and §6.

### 3.2 Assignment Assignment to Students (Admin)
**Steps:**
1. Admin calls `assign-by-filters`, which dispatches `AssignAssignmentsByFiltersJob` (queued).
2. The job creates one `StudentAssignment` row per matched enrollment, each starting `ACTIVE`/`PENDING` (assigned, not yet submitted).
3. On completion, emails the admin a summary via `BulkAssignmentReportMail` and fires a `WebhookTriggered` event.
**Endpoints involved:** `POST /v1/student-assignments/assign-by-filters` — `StudentAssignmentController@assignByFilters` (auth:sanctum).
**Side effects:** `AssignAssignmentsByFiltersJob`; `BulkAssignmentReportMail`; `WebhookTriggered` event; a `FirstAssignmentSendLog` row tracked separately.
**Notes/uncertainty:** `AssignmentSendingLog` is dead — see §6.

### 3.3 Student Submission
**Actors:** Nominally the student (route requires `auth:sanctum`), but the code path logs the acting identity as a `User` (staff) and phrases its audit message "...has submitted student assignment successfully **on behalf of** student" — strongly suggesting this endpoint is normally staff-invoked, not genuine student self-service.
**Steps:**
1. `POST /v1/student-assignments/{student_assignment}/submit` — rejects if already `STATUS_SUBMITTED` (with an inert plagiarism-based override that can never fire), or if `submit_counter <= 0`.
2. Uploaded file stored to S3 under `uploads/assignments/submitted/`.
3. **Plagiarism check is hardcoded off** (`$plagiarism = false; // added because unicheck has been removed`).
4. Any prior active `Result` is deactivated, then a **new `Result` row is created immediately at submission time** — `evaluator_id` pre-filled from `enrollment.course.default_evaluator_id` (pre-assigned from course config, not chosen by a human yet).
5. Placeholder `ResultExerciseScore` rows created per exercise, `full_marks` from `passing_criteria` JSON or defaulted to 10.
6. `StudentAssignment.status → STATUS_SUBMITTED`; `submit_counter` decremented.
7. `Activity` log entry recorded, attributed to the staff `User`.
**Endpoints involved:** `POST /v1/student-assignments/{student_assignment}/submit` — `@submit`; `POST .../re-submit` — `@re_submit`.
**Side effects:** S3 write; new `Result` + `ResultExerciseScore` rows; status transition; activity log. Event dispatch calls exist but are commented out — no event fires.
**Notes/uncertainty:** No genuinely separate "student self-submits" endpoint was found — if students do submit via this same route with their own token, the "on behalf of" audit wording would be misleading in that case; confirm actual frontend usage.

### 3.4 Evaluator Assignment (Admin)
**Steps:**
1. Single reassignment sets `evaluator_id` on one `Result`, or bulk-reassigns every pending (`is_review_done = 0`) `Result` from an old evaluator to a new one (`change_all`).
2. Alternative: round-robin auto-assignment.
3. Each reassignment writes an `Activity` log entry.
**Notes/uncertainty:** The `Evaluator` module itself is pure master data (list of evaluators) — all assignment/grading logic lives in `Result`, not `EvaluatorController` (read-only listing only).

### 3.5 Evaluator Grading (Admin/Evaluator)
**Steps:**
1. `PUT` update on a `Result`: rejects if student/enrollment inactive. Accepts optional feedback file (S3), feedback link/reason, per-exercise `scores`.
2. **Resubmission gate:** if `TYPE_SUBJECTIVE` and any score is `< 4`, `Result` → `RESUBMIT`, `StudentAssignment` reopens (`status → ACTIVE`, `submit_counter` +1), and a `ResultFeedbackFileMail` is queued — grading stops here for this cycle (distinct from 3.3's dead resubmit path).
3. Otherwise, individual scores are written (sentinel `101` clears a score to `null`) — **this does not yet finalize** the result.
4. A separate finalize step (`sendMail`) marks `Result.status = EVALUATED`, `is_review_done = REVIEW_DONE`, `evaluation_date = now()`. **`StudentAssignment.status → STATUS_EVALUATED` happens only here**, not in the score-update step. Sends `ResultSendMail` + `ResultEvaluated` notification, then calls `CourseCompletionMasterController::marksheetCalculation($enrollment)` — this is what `CourseCompletionMaster` actually does.
**Endpoints involved:** `Result` update endpoint then a distinct finalize/send-mail endpoint.
**Side effects:** S3 feedback file; `ResultFeedbackFileMail` or `ResultSendMail`+notification; activity log; triggers marksheet recalculation on finalize.
**Notes/uncertainty:** See §6 — grading is a two-step process; a test that only calls `update` and checks for `STATUS_EVALUATED` will fail.

### 3.6 AI-Assisted Evaluation (Automated, admin-triggered)
**Actors:** System (queued job), triggered by admin/staff or a scheduled sync.
**Steps:**
1. `EvaluateStudentAssignmentJob`/`BulkEvaluateStudentAssignmentsJob` load the `StudentAssignment`, its latest active `Result` (must have a `submitted_file`), and rubric/sample-feedback links.
2. Aborts (logs error, no retry) if no active result/file or rubric links missing.
3. Resolves an "effective AI model" (defaults `gemini-2.5-pro`).
4. Calls an **external auto-evaluation microservice** (`AutoEvaluationService::triggerEvaluation`, multipart POST to `{AUTO_EVALUATION_API_URL}/v1/evaluate`) — not a direct call to a public LLM API from this codebase.
**Notes/uncertainty:** Appears to be a **pre-grading aid** for the human evaluator (populates/suggests scores ahead of §3.5), not a replacement — `STATUS_EVALUATED` is only ever set from `ResultTrait::sendMail`. Whether AI output is a suggestion or auto-applied wasn't confirmed.

### 3.7 Agentic Support System (External AI Agent Integration)
**Actors:** An external AI/agent system, authenticated via static bearer tokens (`AGENTIC_SUPPORT_SYSTEM_TOKEN`/`AGENTIC_SUPPORT_SYSTEM_LISTING_TOKEN`), rate-limited.
**What it is:** A **read-heavy data-access API**, not a fixed-sequence workflow — ~35+ GET endpoints exposing student/enrollment/course/assignment/result/certificate/notification/meeting data by email lookup, plus write actions: `create-enrollment-v2`, `assign-batch-v2`, `update-v2`, `update-enrollment-status-v2`, `deactivate`.
**Notes/uncertainty:** Best understood as an external-agent-facing read/write gateway that doesn't call into or get called by Workflows 3.1–3.6, despite living alongside them. Its logic lives in three multi-thousand-line trait files not fully traced here — likely deserves its own dedicated documentation pass.

### 3.8 Result Visibility (Student)
**What it is:** Student views their finalized result via `StudentResultsController` — a thin, read-only wrapper reflecting whatever §3.5's finalize step produced. No entities/jobs of its own.

### 3.9 Post-Evaluation CSAT Feedback (Student-initiated)
**Trigger:** Student voluntarily rates their assignment/evaluator experience — **no automated trigger was found**; appears surfaced client-side rather than server-driven.
**Steps:**
1. Student fetches CSAT form/questions, then submits (`AssignmentCSATForm` + reason mappings).
2. Separately, evaluator-specific satisfaction is collected via `POST /submit-evaluation` — despite the generic name, this writes an **`EvaluatorCSATForm`**, i.e. it's the evaluator CSAT flow, not an assignment grading action.
**Endpoints involved:** Hosted on `StudentFrontendEnrollment` (re-hosting the `AssignmentCSAT`/`EvaluatorCSAT` modules' own tables) rather than those modules' own controllers directly.
**Notes/uncertainty:** See §6 CSAT naming trap.

### 3.10 Student Project Tasks (Kanban board — unrelated to assignment grading) ⚠️ NOT IN USE (confirmed by team, 2026-08-29 — see §5.3, ProjectManagement)
**What it is:** Generic per-course project task tracking (a student-facing view into `ProjectManagement`'s columns/tasks, §5.3), not assignment-specific, despite sitting alphabetically near the Assignment-domain modules. List/view/move/comment/attach-file actions exist under both `StudentTasksController` directly and duplicated under `StudentFrontendEnrollment`.

### Summary: `StudentAssignment.status` transition ownership (useful for QA test design)

| Status | Set by |
|---|---|
| `ACTIVE` (1) / `PENDING` (2) | `AssignAssignmentsByFiltersJob` / `createStudentAssignment` |
| `SUBMITTED` (3) | `StudentAssignmentController@submit` |
| `RESUBMITTED` (4) | Dead code path only (plagiarism check disabled) — unreachable |
| → back to `ACTIVE` | `ResultController@update`, when a subjective score < 4 |
| `EVALUATED` (5) | Only `ResultTrait::sendMail` (finalize step), never the score-update step |

---

## 4. Student Engagement, Coaching & Support Workflows

### 4.1 Student Dashboard (home screen aggregation)
**Steps:**
1. Client calls dashboard endpoints in parallel: pending assignments, upcoming/latest classes, enrollments, LMS calendar, class updates, announcements, unread counts.
2. `StudentLmsController` proxies several calls **live to Edmingle** using a shared org-wide API key (`config('app.edmingle_api_key')`, with a hardcoded fallback value in code) plus the student's own `lms_id`.
3. `getTodayClass()` additionally mints a JWT (`Firebase\JWT\JWT`, secret `LMS_SECRET`) and calls Edmingle's `/sso` endpoint to refresh the student's personal `edmingle_api_key`/`edmingle_expire_at` — this is the real SSO handshake, separate from this app's own auth guards.
**Endpoints involved:** `GET /api/v1/student-dashboard`, `.../calendar`, `.../class-updates`, `.../announcements`, `.../unread-count`, `GET /api/student/v1/join-class` (→ Edmingle `liveclass/join/{id}`).
**Side effects:** Updates `students.edmingle_api_key`/`edmingle_expire_at` on token refresh; otherwise purely proxied reads, no local writes.
**Notes/uncertainty:** Several Edmingle calls use hardcoded fallback API keys and base URLs directly in code, not exclusively `.env`/config — see §6/known-issues.

### 4.2 Student Dashboard Management (admin-configured "student journey" steps)
**Steps:**
1. Admin defines "journey steps" (`saveJourneySteps`), persisted as `StudentDashboardJourneyStep`/mapping.
2. Student views their journey, marks a step complete/uncomplete, adds feedback/rating on a step, or deletes feedback. Each mutation logs to `ActivityLog`.
**Notes/uncertainty:** `getCategoriesWithAll`/`getOpportunities` exist on the same controller but their purpose (job/referral opportunities?) wasn't confirmed against `JobRole`/`ReferralSystem`.

### 4.3 Student My Courses (enrolled-course view & course pause/migration)
**Steps:**
1. `courseListForFilter` returns distinct enrolled courses (excluding `PENDING`) for filter dropdowns.
2. `index`/`show` list a student's courses with assignment/result/CSAT sub-resources.
3. Pause/resume/migrate flow: `pause`, `resume`, `pauseStatus`, `futureBatches`, `migrate` — this is the **course-pause/refund/waiver feature** documented authoritatively in the repo-root `CR10_COURSE_PAUSE_REFUND_WAIVER_*.md` files; treat those as the source of truth for exact business rules, not this summary.
**Endpoints involved:** `GET /api/student/v1/filter/course`, `GET /api/student/v1/student-my-courses`, pause/resume/migrate actions via route-model-binding on `StudentMyCoursesController` (exact URIs not individually spelled out in the routes doc — verify directly before building tests), `POST .../requestForCertificate`, `POST .../submit-assignment/{studentAssignment}`.
**Side effects:** Enrollment status changes on pause/resume/migrate.

### 4.4 Student Classes (schedule/listing only) ⚠️ NOT IN USE (confirmed by team, 2026-08-29)
**What it is:** Course/batch class listings. Class **joining** is handled by §4.1's `joinClass` (Edmingle), not this module.

### 4.5 Notifications — three overlapping code paths (see §6)
1. **`Notification` module (admin/staff, `auth:sanctum`)** — authoring/broadcast side: `create_notification_for_all`, `create_notification_for_specific_range`, tagging, comments, status changes.
2. **`StudentNotifications` module (`auth:student`)** — a student-facing inbox: `getAllNotification`, `getUnread`, `markAsRead`, `getTags`, plus comments.
3. **`StudentFrontendEnrollment`'s own `NotificationController` (`auth:student`, different route prefix)** — a **second** student-facing inbox with overlapping surface: `index`, `bell`, `latest_five`, `show`, `storeComment`, `readAll`.
**Notes/uncertainty:** (2) and (3) look functionally redundant but live at different route prefixes. Verify against actual frontend network calls which is live before writing regression tests against both.

### 4.6 Forum & StudentForum — proxy to an external Vanilla Forum ⚠️ NOT IN USE (confirmed by team, 2026-08-29)
**Steps:**
1. Both `ForumController` (admin/staff) and `StudentForumController` use the same `VanillaForumTrait`, wrapping HTTP calls to an external **Vanilla Forum** instance.
2. This app is a backend-for-frontend proxy — discussions, comments, categories, tags, bookmarks live in Vanilla Forum; only drafts are local-only.
**Notes/uncertainty:** `Forum`'s common middleware is listed as `Authenticate:student`, not `sanctum` — worth confirming whether staff actually authenticate as a "student" guard to use this module. Testing requires a live/staging Vanilla Forum instance or mocked HTTP calls — no local-only path.

### 4.7 NPS (Net Promoter Score) — two competing implementations (see §6)
**Implementation A (`StudentDashboard`, likely older):** Evaluated live on dashboard load inside `getSurveyData()` — Survey Type 1 (mid-course pulse) fires once a student's earliest assignment for an enrollment is >30 days old and no record exists yet; Survey Type 2 (completion survey) fires when `enrollment.completed == 1`. `storeNPS()` branches by rating: >8 → suggestions only; 7–8 → experience + `reason: 'N'`; ≤6 → experience + `reason: 'Y'` plus mapped reason IDs.
**Implementation B (`StudentFrontendEnrollment`'s `NPSController`, likely newer):** `GET/POST .../nps/{enrollment}` (v1) and a v2 pair `checkNpsDue`/`submitNps` — naming suggests a cleaner rewrite of the same "is a survey due" check.
**Notes/uncertainty:** Which of the two the current frontend actually calls wasn't confirmed — recommend confirming with the team before writing coverage for both.

### 4.8 Performance Coach — allocation & call scheduling ⚠️ NOT IN USE (confirmed by team, 2026-08-29 — this includes the student-facing `StudentPerformanceCoach` module below, also confirmed not in use)
**Steps:**
1. Admin allocates a coach (`POST /api/v1/pc-allocate`); views allocations (`pc-allocation`, `pc-details/{user}/allocation`).
2. Coach/admin manage availability slots (`markAvailable`/`markUnavailable`, `getSlotsAndRanges`, `checkConflictSchedule`).
3. Student books a call — **gated on having an ACTIVE coach allocation**: `bookSlot` resolves the student's active `PerformanceCoachStudents` record first; rejects if none. Accepts a specific `slotId[]` or a `rangeId`, plus a required `comment`.
4. Student can flag issues (`issue-report`) or share feedback (`share-feedback/{callId}`).
5. Post-call CSAT de-duplicates by `(student_id, result_id)`.
**Notes/uncertainty:** None significant — traced cleanly.

### 4.9 StudentBookACall — course/instructor call booking (separate from Performance Coach) ✅ CONFIRMED LIVE IN PRODUCTION (per team, 2026-08-29)
**Actors:** Student, Instructor (course mentor — not the dedicated performance coach, which is unused per §4.8), Team/Admin.
**Confirmed separate from §4.8** by distinct `courseId`/`instructor_id`/`team_id` fields and no relation to `performance_coach_students`. The team confirmed this module integrates with **a separate sub-project's own API** — the two external HTTP calls in step 2 below are calls to that sub-project, not to an unrelated/unknown third party.
**Steps:**
1. Student browses available instructors for a course and open slots.
2. `MeetingBookingController::createBooking` chains **two external HTTP calls**: `POST {MEETING_API_BASE_URL}bookings` (creates the meeting, returns a `meetingUrl`) then `POST {BOOK_A_CALL_API}booking/create` (persists the booking in a separate internal "BookACall" service, returns the booking id used in the response).
3. Edit/reschedule/cancel actions exist, each presumably emailing via blade templates.
4. Post-call: complete/no-show marking, rating, review.
5. Team bookings are a variant (`TeamController`/`EventController`).
**Notes/uncertainty:** See §6 — cannot be tested end-to-end without staging credentials or mocks for both external services. Zoom is configured (`config/zoom.php`) but no direct Zoom API usage was found in this module — "zoom" only appears in email copy, so treat any implication of direct Zoom integration here as unconfirmed.

---

## 5. Admin Operations & External Integration Workflows

### 5.1 Role Management
**Steps:**
1. Admin submits role name + permission names; `RolesController::store` creates the `Role` (guard `sanctum`) in a transaction, then `syncPermissions()`.
2. Editing diffs old vs. new permission sets and logs which were added/removed.
3. Deleting is blocked (422) if any users currently hold the role — must reassign via `transferToOther` first.
4. Bulk activate/deactivate (`changeStatus`) flips status and writes activity/comment logs.
**Endpoints involved:** `GET /api/v1/search/roles`, `POST /api/v1/roles/transfer-to-other`, `POST /api/v1/roles/status/change`, `POST /api/v1/roles/export`, `Route::apiResource('roles', ...)`, `GET /api/v1/roles/{role_id}/activity`.
**Side effects:** Activity log entries; CSV export dispatches `RolesCSVDownloadStart` (async, `default_medium` queue).

### 5.2 Permission Assignment & Lookup
**What it is:** Permissions are static/seeded — no create/update/destroy routes exist. The only mutation path is through Role's `syncPermissions`. `GET /permissions/users/{user?}` returns effective permissions grouped by parent name, and synthesizes two pseudo-permissions not backed by real rows (an `lms` flag, and conditional removal of `Schedule_My_Meeting_Managment`).
**Notes/uncertainty:** Treat the permission list as fixture data, not something to create via API.

### 5.3 Project Management (Kanboard-backed) ⚠️ NOT IN USE (confirmed by team, 2026-08-29)
**Steps:**
1. `ProjectManagementController::store` checks no project already exists for the (course_id, batch_id) pair, then — inside a transaction — calls the **external Kanboard API** to create the project, replicate categories, create a user group, reorder columns.
2. Locally persists a `Project` row storing Kanboard-side IDs plus mentor mappings; dispatches `ProjectGroupStudentMappingJob` and sends a `ProjectCreate` notification.
3. Task creation queues `StudentTaskCreationJob` per targeted student (or all students, looked up live from Kanboard group membership); "all students" also emails a hardcoded admin address.
4. Read/update/comment/column endpoints are thin synchronous proxies to the live Kanboard API — task state lives in Kanboard, not this app's DB.
**Notes/uncertainty:** See §6 — QA tests need a working or mocked Kanboard instance; this is not self-contained.

### 5.4 Internal Notes (staff-only, versioned)
**Steps:**
1. `store` creates a note tied to a student, stamped `created_by`.
2. `update` copies the *current* text into `InternalNotesHistory` first (append-only chain), then updates in place and flags `is_edited = 1`.
3. `destroy` also writes a history row before deleting — a full audit trail is reconstructable even after the live note is gone.

### 5.5 Referral System — thin proxy to an external service
**What it is:** Every student-facing action (`generalCode`, `courseSpecific`, `courseInfo`, `studentEarningDetail`, `studentMailSend`) is a live outbound call to `REFERRAL_BASE_URL`, relaying the response. **No referral data is stored locally** — the module has no migrations of its own. The one local exception is admin-facing `referralSystem()`, which searches students via a local scope.
**Notes/uncertainty:** Reward/earning logic is entirely external — untestable via this codebase alone without stubbing `REFERRAL_BASE_URL`. `studentMailSend` builds a URL with unescaped path interpolation — worth a boundary/injection test case even as a pure proxy.

### 5.6 LawSikho Integration Gateway (inbound ingestion)
**Confirms and corrects the earlier "ambiguous purpose" flag:** `LawSikho` is the inbound integration surface the LawSikho marketing/revenue site calls to push student, course, and enrollment data into this API.
**Steps (representative, ~25 actions across traits):**
1. Student ingestion: `add_student`, `update_student_address`, `get_student_address`, `check_student`.
2. Enrollment ingestion: `store_enrollment_form(_v2)`, `generate_enrollment_code`, `check_enrollment`, plus dedicated single-course/bootcamp/package enrollment endpoints.
3. File ingestion: `store_photo`, `store_id_proof`, `store_cv`.
4. LMS sync: `check_lms`/`update_lms`, `GET|PATCH /lms` — this is the real "Edmingle SSO" touchpoint (confirms JWT is not actually used for this, per §6/DEVELOPER_DOCUMENTATION.md §9).
5. Access control: `active_access`/`revoke_access` — the **only two routes** gated by `CheckLawSikhoApiToken` (shared-secret header), on top of module-wide `log.third.party` request/response logging.
6. Course/batch/category sync: `add-course` (delegates to `CourseController@store`), `update_course`, `course_batches`, `course_category`, `written_assignment_course`.
**Side effects:** Every call logged via `log.third.party`; student LMS updates write to the activity log; enrollment ingestion cascades into Enrollment-module side effects.
**Notes/uncertainty:** See §6 — only 2 of ~25 endpoints require the shared-secret token; the rest have no visible authentication beyond logging. Recommend an explicit "no credentials" test case.

### 5.7 Email Template Management
**Steps:**
1. `store` picks an owner model (`Admin`/`Student`/falls through to `Role`) based on `model_type`.
2. `show` looks up the template for the **current user's first role only** — retrieval is always role-scoped even though storage supports per-user/per-student templates.
3. `update` edits the body in place, no versioning.
**Notes/uncertainty:** No Mailable classes were found actually pulling a stored template's body at send time in this pass — see §6, the admin/student-specific storage branches may be dead.

### 5.8 Book Master & Book Delivery ⚠️ NOT IN USE (confirmed by team, 2026-08-29)
**Trigger A (catalog):**
1. `BookMasterController::store` creates a `Book` row plus `book_course_mapping` rows (course + delivery-start-date pairs).
2. `update` enforces SKU uniqueness (manual comparison, not a DB constraint) before replacing all mappings.
**Trigger B (delivery):** A bootcamp additional-enrollment event (`BootcampAdditionalEnrollmentAdded`) triggers listener `AddBootcampAdditionalEnrollmentToBookDelivery`, which auto-creates one `BookDeliveryLog` row per mapped book, pre-filled with the student's address/contact **snapshot at that point in time**.
**Notes/uncertainty:** Address is snapshotted, not live-joined — a later student address change won't retroactively update pending delivery logs. The exact automatic (non-manual) "sent" trigger lives in an `enrollments:books-dispatch` scheduled command not fully traced here.

### 5.9 AtsAPI (job/course mapping integration) — dormant bug, unreachable in the live app
**Actors:** Two external channels — `Lawsikho` (this platform's own job board) and `SkillArbitrage` (a sibling portal).
**⚠️ Correction (2026-08-29, see `documentation/API_SPECIFICATIONS.md` §7):** `AtsGateWay` middleware is registered as an alias (`ats.gateway`) in `AtsAPIServiceProvider` but **is never attached to any route** — `save-job-and-course-mapping` only carries `json.response`. The behavior below describes the middleware's own code, which does NOT currently run in production.
**Steps (as coded, not as currently exercised):** `$request->channel` would branch:
- `"Lawsikho"` → processes locally via `saveJobAndCourseMapping` (`updateOrCreate`s `CourseJobMapping`, hardcodes `channel => 'Lawsikho'` regardless of what was requested, defaults `user_id` to `1` if unauthenticated).
- `"SkillArbitrage"` → proxies the entire request externally and returns that response; does not call `$next()`.
- **Any other value (including missing/null)** → fires the SkillArbitrage proxy call **and** still calls `$next()`, double-processing the request.
**What actually runs today:** the route hits `AtsAPIController::saveJobAndCourseMapping` directly with no gateway middleware — see `documentation/API_SPECIFICATIONS.md` §6 AtsAPI for the real current behavior (no auth, `channel` only used to decide `status`, all rows hardcoded `channel: 'Lawsikho'` in storage).
**Notes/uncertainty:** Don't build a regression test expecting to reproduce the double-processing bug through the running application — it's dormant, dead code, not live behavior. Confirm with the team whether this was a recent regression (accidentally unwired) or always-dead scaffolding.

### 5.10 Webhook Module — admin config, not a live inbound receiver
**What it is:** `WebhookController` (CRUD over `webhooks`) and `EventController` (CRUD over `webhook_events`, a lookup of event names) have **no code anywhere dispatching against them** — confirmed via grep. The one endpoint behaving like a genuine integration point is unrelated: `POST /failed-api-responses` queues `LogFailedApiResponseJob`, likely a sink for this app's *own* outbound integration failures (Kanboard/Ats/Referral calls failing), not something external systems POST to. A leftover unprefixed `GET /webhook` route uses an undocumented `auth:api` guard and just returns the current user — likely dead.
**Notes/uncertainty:** See §6 — don't assume "webhook" here means "receives events from Stripe/Edmingle/etc."; if you need this app's own outbound webhook mechanism, this module doesn't appear to be it.
