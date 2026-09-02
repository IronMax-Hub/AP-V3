# LawSikho Assignment Portal API — API Specifications

> **Generated:** 2026-08-29
> **Branch surveyed:** `New-Dummy-Prod-0605`
> **Companion documents:** [`documentation/DEVELOPER_DOCUMENTATION.md`](./DEVELOPER_DOCUMENTATION.md) (tech stack, module inventory, auth internals, full routes list, DB schema) and [`documentation/USER_WORKFLOWS.md`](./USER_WORKFLOWS.md) (traced end-to-end workflows, cross-cutting QA findings). This document is the missing third piece for a QA-test-project author: the actual **request/response contract** per endpoint — field names, types, validation rules, response shapes, and error conditions — traced directly from FormRequest validation classes, API Resource/Transformer classes, and controller/trait bodies, not inferred from route names.

## Scope

Covers the ~50 modules confirmed in active use, grouped into 5 domains below. **Excluded entirely** (confirmed not in production use — see `documentation/DEVELOPER_DOCUMENTATION.md` §4 and `documentation/USER_WORKFLOWS.md` §6): `BookMaster`, `BookDeliveryLog`, `Class`, `ClassCSAT`, `Forum`, `StudentForum`, `PerformanceCoach`, `PerformanceCoachCSAT`, `ProjectManagement`, `StudentClasses`, `StudentTasks`, `StudentPerformanceCoach`. `StudentBookACall` is confirmed live and specced in full.

Coverage depth is intentionally uneven by design: high-traffic/business-critical endpoints (login, submission, grading, LawSikho ingestion, course-batch creation) get full field-by-field detail; low-stakes reference/CRUD endpoints get a shorter treatment. Where an endpoint's exact behavior wasn't confirmed from code, that's flagged explicitly as **Notes/uncertainty** — verify empirically before writing an assertion against it.

## Table of Contents

1. [Common API Conventions](#1-common-api-conventions)
2. [Student Identity & Enrollment APIs](#2-student-identity--enrollment-apis)
3. [Course & Program Catalog APIs](#3-course--program-catalog-apis)
4. [Assignment & Evaluation Lifecycle APIs](#4-assignment--evaluation-lifecycle-apis)
5. [Student Engagement, Notifications, NPS & Call Booking APIs](#5-student-engagement-notifications-nps--call-booking-apis)
6. [Admin Operations & External Integration APIs](#6-admin-operations--external-integration-apis)
7. [Corrections to Earlier Documentation](#7-corrections-to-earlier-documentation)

---

## 7. Corrections to Earlier Documentation

*(Placed early on purpose — two findings from this pass overturn conclusions stated as confirmed in `documentation/USER_WORKFLOWS.md` and `documentation/DEVELOPER_DOCUMENTATION.md`. Both source docs have also been updated in place; this section explains why.)*

1. **`Bootcamp::create()` IS called somewhere — the "orphaned model" finding was wrong.** Earlier tracing concluded the `Bootcamp` entity is never created via any code path (only listing/book-mapping actions exist on `BootcampController`). That's true for the `Bootcamp` module's own controller, but `POST /v1/bootcamp_from_lawsikho` (in the `LawSikho` ingestion gateway, §6) does call `Bootcamp::query()->create([...])` when no existing row matches the caller-supplied `id`. So `bootcamps` rows genuinely are created by live application code — just via LawSikho's ingestion endpoint, not `Modules/Bootcamp` itself. If you need to seed a `Bootcamp` row for a QA test, use this endpoint (or replicate its `id`-is-caller-supplied behavior), not a direct DB insert assuming the table is dead.

2. **The `AtsGateWay` double-processing bug is real in code but currently unreachable — it is not live behavior.** Both `documentation/USER_WORKFLOWS.md` §5.9 and the original `DEVELOPER_DOCUMENTATION.md` audit described this as a confirmed, reproducible production bug. Tracing the actual route registration for this spec found that `ats.gateway` middleware alias is registered in `AtsAPIServiceProvider` but **never attached to any route** — `POST /v1/save-job-and-course-mapping` only carries `json.response` middleware. The buggy branching logic still exists in `AtsGateWay.php`'s code, but no live route runs it. **Do not write a regression test expecting to reproduce this bug through the running application** — it won't fire. If the team intends to re-wire the middleware, this becomes live again; until then, treat it as dormant dead code, not an active defect. (What actually runs today for that route is documented under §6 AtsAPI below — plain `channel`-string handling with no gateway middleware involved at all.)

Both `documentation/DEVELOPER_DOCUMENTATION.md` and `documentation/USER_WORKFLOWS.md` should be read with these two corrections in mind if you already reviewed them before this document existed.

---

## 1. Common API Conventions

*Traced from `app/Http/Controllers/Controller.php`, `app/Helpers/functions.php`, and `app/Exceptions/Handler.php` — applies app-wide except where a specific controller bypasses it (called out per-endpoint throughout this doc).*

**Standard success envelope:** `{"data": ..., "message": "...", "status": "success"}`, HTTP 200 by default. Produced by either the global helper `apiResponse($data, $message = 'Success', $status = 'success', $statusCode = 200)` (`app/Helpers/functions.php:17`) or the identical `Controller::apiResponse()` method (`app/Http/Controllers/Controller.php:22`) — both used interchangeably, same shape either way.

**A second envelope exists but is effectively unused:** `studentApiResponse($data, $error = null, $status = 1)` → `{"status": 1|0, "data": ..., "error": ...}` (`app/Helpers/functions.php:33`). Confirmed called only inside the deprecated (not-in-use) `Forum` module. **Do not expect this shape from any endpoint documented below.**

**Standard error shapes** (from `app/Exceptions/Handler.php::render()`):
- **422 validation failure** (`ValidationException`): `{"status": "error", "message": "<comma-joined first errors>", "data": {"errors": {"field": ["message", ...], ...}}}`. The per-field `errors` object is nested under `data.errors`, not top-level.
- **404 route not found** (`NotFoundHttpException`): `{"status": "error", "message": "Url Not Found!", "data": []}`.
- **404 model not found** (`ModelNotFoundException`, e.g. a route-model-binding miss): `{"status": "error", "message": "Resource Not Found", "data": []}`.
- **Other HTTP exceptions** (manually-thrown 403/409/etc.): `{"status": "error", "message": "<exception message>", "data": []}` at that status code.
- **401 unauthenticated — guard-dependent shape, a real inconsistency:** if the `student` guard failed, response is `{"status": 0, "message": "User is Unauthenticated"}` (**no `data` key**, `status` is the integer `0`). For every other guard (`sanctum`/`web`), it's `{"data": [], "status": "error", "message": "User is Unauthenticated"}`. **A QA client must branch on which guard it's testing when asserting 401 body shape.**

**Many individual controllers bypass both helpers and hand-roll `response()->json([...])`.** This is common enough that you should never assume a `data` key is present, or that `status` is a string, without checking the specific endpoint — dozens of concrete examples are called out throughout this document (e.g. `data: null` vs `""` vs `[]` vs omitted; `status` as string `"success"` vs integer `1` vs integer `200`).

**Pagination:** No single consistent wrapper. Two families exist:
- **Resource-collection endpoints** (most `search`/reference-lookup endpoints): `{"data": [...], "meta": {"total": N}}` — no `message`/`status` key at all.
- **Cursor-paginated `index()` endpoints** (most catalog/admin listing endpoints): query params `rows` (page size, default 15) and `cursor` (opaque base64 token from a prior response's `meta`, not a page number); response `{"data": [...], "meta": {"total": N, "range": {"from": N, "to": N, "total": N}}}`. A malformed/tampered `cursor` triggers `abort(500, 'Cursor value tempered')` — a 500, not a 4xx, on bad client input.

**Cross-cutting QA caution:** several endpoints throughout this API return a 2xx status with a "success"-looking body (`status: 1`, `status: "success"`) even on a semantic no-op or failure path (e.g. NPS submission, certificate request, external-proxy failures in `StudentBookACall`). **Never treat "2xx + success-shaped body" as sufficient proof an action succeeded** — check the accompanying `error`/`message` field, and where the action has real consequence, verify via a follow-up read rather than trusting the write response alone. Specific instances are flagged inline throughout.

---

## 2. Student Identity & Enrollment APIs

### Student Login (StudentAuth module)

#### `POST /student/v1/login/email-verification` — start student login (step 1 of 2)
- **Auth:** none (route group is `guest`-gated at the Laravel level, not an app auth guard)
- **Request body:** `email` — string, required, must match `students.email` (`LoginAndPasswordForgetEmailVerificationRequest::rules()`: `['required', 'email', 'exists:students,email']`)
- **Success response:** 200, `apiResponse({"token": "<40+ char opaque string>"}, "Email verified.")`
- **Error responses:**
  - 422 if `email` missing/invalid/not found: `"Email doesn't exists."` (custom message on `email.exists`)
  - 422 `"You are not an authorized user to do this action"` if the email exists but `student.status != Student::ACTIVE` (a separate in-controller check after the FormRequest's `exists` rule already passed)
- **Notes:** The returned `token` is a **plaintext short-lived verification token** (`tmp_verification_token`, expires in 5 minutes), not a Sanctum auth token — pass it to step 2, don't use it as a Bearer token.

#### `POST /student/v1/login/password-verification` — complete student login (step 2 of 2)
- **Auth:** none
- **Request body:** `token` — string, required, must exist as a current `students.tmp_verification_token`; `password` — string, required, **must be pre-encrypted by the client** using `AuthController::decrypt`/`evpKDF`'s scheme (OpenSSL `aes-256-cbc`, key derived EVP_BytesToKey-style from `APP_PASS_PHRASE`) — sending plaintext fails `Hash::check`, not a clean error; `remember_me` — optional, truthy value extends token expiry to 30 days (pinned to 23:59) instead of same-day 23:59
- **Success response:** 200, `apiResponse(data, "Password verified.")` where `data` = `{"token": "<Sanctum plaintext token>", "addressRequired": "Y"|"N", "lms": "Y"|"N", "enrollmentDataRequired": "Y"|"N", "profileImage": "<url, hardcoded default S3 URL if none>", "userInfo": {"id","name","email","phone"}, "meeting_accessible": <raw column value>}`
- **Error responses:**
  - 400 (not 422) `apiResponse('', 'Token invalid.', 'error', 400)` if token exists but expired — **non-standard status code for this specific case**
  - 422 `ValidationException` on `token.exists` failure: `"Token invalid."` (same message text as the 400 case above but a different code path — check status code, not message, to distinguish "never existed" from "expired")
  - 422 `password: ["Password is incorrect."]` if decrypt+hash-check fails
- **Notes:** Every failed attempt writes an `activity_logs` row.

#### `POST /student/v1/student/logout`
- **Auth:** `auth:student`
- **Success response:** 200, `apiResponse([], "User logged out successfully")`
- **Notes:** Deletes **all** of the student's Sanctum tokens (`$user->tokens()->delete()`) — logout-everywhere, not single-session.

### Student Forgot-Password (`PasswordResetController`)

#### `POST /student/v1/forgot-password/email-verification`
- **Request body:** `email` — required, `exists:students,email` (same FormRequest as login step 1)
- **Success response:** 200, `apiResponse({"token": "..."}, "OTP sent to your email inbox.")`
- **Notes:** Unlike the login version, does **not** check `student.status == ACTIVE` — a pending/disabled student can still request a reset OTP.
- **Side effects:** queues `StudentForgetPasswordOTPMail` with a numeric OTP.

#### `POST /student/v1/forgot-password/otp-verification`
- **Request body:** `token` — required, `exists:students,tmp_verification_token`; `otp` — required
- **Success response:** 200, `apiResponse({"token": "<new rotated token>"}, "OTP verified.")`
- **Error responses:** both hand-rolled `apiResponse('', ..., 'error', 422)`, **not** thrown `ValidationException`s — so they produce `{"data": "", "message": "...", "status": "error"}` (`data` is an empty **string**, not `[]`): `"Token invalid."` / `"Invalid otp."`
- **Notes:** Issues a **new** token — the step-1 token is dead for step 3; use the token from *this* response.

#### `POST /student/v1/forgot-password/create-password`
- **Request body:** `token` — required, `exists:students,tmp_verification_token`; `password` — required, `Password::defaults()` (min 8 chars) + pre-encrypted like login; `password_confirmation` — same rules/encryption
- **Success response:** 200, `apiResponse([], "Password created successfully")`
- **Error responses:** `apiResponse('', 'Token invalid.', 'error', 422)` if token missing/expired; a hand-rolled 422 matching the standard validation shape if decrypted passwords don't match: `{"status": "error", "message": "Form Validation failed", "data": {"errors": {"password": ["The password confirmation doesn't match"]}}}`
- **Notes:** Password mismatch checked **after decryption** — Laravel's `confirmed` rule is NOT used, so mismatched ciphertext decrypting to the same plaintext would pass, and vice versa. Not confirmed whether existing Sanctum tokens are revoked on password change.

### Admin/Staff Login (Auth module)

#### `POST /v1/login`
- **Request body:** `email`, `password` (pre-encrypted, same scheme), `remember_me` (optional). **Finding:** the route binds to `AuthController::store(Request $request)` — the generic `Request`, NOT the `LoginRequest` FormRequest class that exists in the same module with proper rules and rate-limiting. `LoginRequest` is dead/unused code for this route — a missing `email`/`password` won't produce a clean 422, it'll fail the lookup/decrypt and surface as the generic "credentials incorrect" error below.
- **Success response:** 200, `apiResponse(data, "User logged in successfully")` where `data` = `{"id","email","title","first_name","last_name","role": "<first role name only>","is_registered_in_scheduling_app": 0|1,"token": "<Sanctum plaintext token>"}`
- **Error responses:** both via `ValidationException::withMessages(['email' => [...]])` (standard 422): `"The provided credentials are incorrect."` / `"Your account is not active."` (if `status == USER_DISABLED`)
- **Notes:** No rate-limiting/lockout (the dead `LoginRequest`'s `RateLimiter` logic never runs). No `expires_at` override confirmed on the admin token (unlike the student flow's same-day pinning) — verify directly.

#### `POST /v1/logout`
- **Auth:** `auth:sanctum`
- **Success response:** 200, `apiResponse([], "User logged out successfully")`; also logs a `spatie/laravel-activitylog` "log out" activity. Deletes all tokens (logout-everywhere).

*(`/v1/register`, `/v1/forgot-password`, `/v1/reset-password` admin routes exist but weren't confirmed live/used per `documentation/USER_WORKFLOWS.md` §1.5 — not specced; verify with the team before building coverage.)*

### Student Profile (`auth:student`)

#### `GET /student/v1/profile/personal-info`
- **Success response:** 200, **hand-rolled** `{"status": "success", "data": {...}}` — no `message` key. `data` includes duplicate/aliased keys (`cv`/`cv_title`, `linkedin_link`/`linked_in_link`) and a misspelled field `is_message_send_aggreed` ("aggreed" — literal field name, not a typo in this doc). Pick one canonical key per field rather than asserting both stay in sync.

#### `POST /student/v1/address` (`student_profile.addressSave`)
- **Request body** (`AddressRequest`): `name` required; `phone` required + country-aware phone format; `address`/`city`/`country`/`pincode` required strings; `country_id` required `exists:countries`; `is_message_send_aggreed`/`is_terms_and_condition_checked` required, `in:[0,1]`; `cv` optional file (`pdf,doc,docx`, max 5120KB); `linkedin_link` optional URL max:255
- **Success response:** 200 — **plain PHP array**, `{"message": "Registration form submited successfully" (typo preserved), "status": "success"}` — **not via `apiResponse()`, no `data` key at all**
- **Side effects:** synchronous Edmingle contact-info update call if student has `lms_id` (adds latency/failure risk to this endpoint); S3 CV upload; activity log
- **Notes:** A separate `POST /student/v1/saveAddress` route (different path, similar name) routes to a different, untraced action — don't conflate the two.

#### `PATCH /student/v1/personal-information` (`savePersonalInformation`)
- **Request body** (`PersonalInformationRequest`): `name` required max:200; `phone` required + phone format; `address`/`city`/`country`/`pincode` required; `status` optional; `profileImage` optional image max:10240KB; `cv` optional (`pdf,doc,docx`, max:10240KB); `id_proof` optional image max:10240KB; `country_id` required `exists:countries`; `linkedin_link` optional URL; `gender` optional
- **Notes:** Exact response shape not confirmed — given the sibling `addressSave` bypasses `apiResponse()`, don't assume this one uses the standard envelope without checking.

### RevenueAPI

#### `GET /v1/get-student-details`
- **Auth:** none
- **Query params:** `email` — no format validation
- **Success response:** 200, `apiResponse({"name","phone"}, "success")`
- **Error responses (inconsistent status/message pairing — read carefully):**
  - Email present, no match: `apiResponse("Email doesn't exist in assignment portal", "success", statusCode: 422)` — `data` is a bare **string**, `status` is `"success"` despite being 422 and a failure
  - Email missing: `apiResponse("Please enter the email address", "error", "error", statusCode: 422)` — `data` again a bare string, `status` correctly `"error"` this time
- **Notes:** No authentication at all — good candidate for an explicit "is this intentional" test (see `documentation/USER_WORKFLOWS.md` §6).

#### `POST /v1/installment-payment`
- **Auth:** shared-secret header `X-Revenue-Secret`, `hash_equals()`-compared against `config('revenueapi.webhook_secret')`
- **Request body:** `student_email` required email; `enrollment_type` required, one of `course|bootcamp|package`; exactly one of `course_id`/`bootcamp_id`/`package_id` required per type (`required_if`), int, min:1
- **Success response:** 200, `apiResponse([], "Payment received. Access reactivation is in progress.")` — returns immediately; actual reactivation happens **async** in `ProcessInstallmentPaymentJob` (`default_high` queue) — **cannot assert reactivation state from this response**, must poll afterward.
- **Error responses:** 401 if secret header missing/wrong/unconfigured (fails closed); 422 `apiResponse([], "<first validation error only>", "error", 422)` — single string, **differs from the app-wide nested `data.errors` shape**.
- **Notes:** Every call logged with full request body via `Log::info`/`Log::error` — mind test-data secrets ending up in shared logs.

### Certificate Request & Delivery (`StudentFrontendEnrollment` module — one of three implementations, see §5 for the second)

#### `POST /enrollment/{enrollment}/request-for-certificate`
- **Auth:** `auth:student`
- **Error response:** `response()->json(['status'=>'error','message'=>'Unauthorized to do this action','data'=>null], 422)` if `enrollment.student_id` doesn't match the caller — **422 for what's semantically a 403 ownership check**, `data` is `null` (not `[]`)
- **Side effects:** sets `request_for_certificate = 1`; activity log; queues `CertificateGenerate` (student) + `CertificateGenerateAdmin` (support address) emails

#### `POST /enrollment/{enrollment}/send-certificate`
- **Success response:** 200, `{"status": "success", "message": "Certificate sent successfully via email"}` — **no `data` key**
- **Error responses:** same ownership 422 as above; 422 `{"status":"error","message":"Certificate has not been generated yet","data":null}` if `certificate_file` empty

### Reference/Lookup Data (Country, State, JobRole, StudentDegree, StudentUniversity)

All `auth:sanctum` on their own modules' routes (a *different* pair, `auth:student`-guarded `filter/country`/`filter/state`, lives under `StudentProfile` hitting the same data).

- `GET /v1/search/countries|states|job-roles|degrees|universities` — Resource-collection `{"data":[...],"meta":{"total":N}}`. `CountryController@search` always prepends a **hardcoded India row** (`{id:99, short:"IN", name:"INDIA", ...}`) and filters out any real `id:99` — expect India present/first regardless of the underlying table's actual id-99 row.
- `StudentDegreeController@index` / `StudentUniversityController@index` — **not** plain record lists; parse a free-text `answer` column, split/de-dupe. Response key casing is **inconsistent between the two**: `{"Degree": "..."}` (capital D) vs `{"university": "..."}` (lowercase).

### Admin Student Management (`auth:sanctum`)

- **`apiResource('students', ...)`** — `store` (`StoreStudentRequest`): `country_id` required exists; `full_name` required max:255; `email` required unique; `phone` required + phone format; `password` nullable `confirmed`; `status` required int (`PENDING|ACTIVE|DISABLED`); `kanboard_id`/`forum_*` fields nullable (legacy, tied to deprecated modules); `tags` optional `{key:int, value:string}[]`. `update` (`UpdateStudentRequest`) is much smaller — only `linked_in_link`/`date_of_birth`/`father_name`/`gender`/`lms_id`/`tags`/`remove_tags` (notably not `email`/`phone`/`status` — those go through dedicated endpoints).
- **`POST /v1/students/activate|deactivate`** — `student_ids` required array each `exists:students,id`; `comment` required. Heavy side effects: per-student Edmingle archive/unarchive calls, a queued `ActivateStudentEdmingleBatches` job, a status-change email per student.
- **`POST /v1/students/get-reg-code`** — public. `email` required valid format. **Hand-rolled**, returns HTTP 200 even on not-found: `{"status":"error","data":[],"message":"Student registration code not found"}` — **a status-code-only check will misread this as success.**
- **`GET /v1/search/students`** — `SearchStudentResource` collection, `{"data":[...],"meta":{"total":N}}`.

### Enrollment (admin-facing CRUD; LawSikho ingestion endpoints are in §6)

#### `POST /v1/enrollments`
- **Request body** (`StoreEnrollmentRequest`): `course_id` required exists; `reference_package` optional exists; `status` required (`PENDING|ACTIVE`); `country_id` required exists; `email` required; `phone` required + phone format; `name` required max:255; `batch_id` optional exists; `bootcamp_name` optional max:255; `refund_eligible` optional bool; `tags` optional array
- **Notes:** This is the **direct/manual admin path**, distinct from `LawSikho`'s ingestion endpoints that the live external revenue site actually calls (§6) — both create `Enrollment` rows via different validation/side-effect paths. Sibling FormRequests exist (`StoreBootcampEnrollmentRequest`, `StorePackageEnrollmentRequest`, `StoreBatchRequest`, `EnrollmentCsvImportRequest`) — check directly if testing those flows.

---

## 3. Course & Program Catalog APIs

> All endpoints use `auth:sanctum` + `json.response` unless noted. Response envelope for hand-written responses is `apiResponse()`; Resource-collection endpoints return `{"data":[...],"meta":{...}}` with no `message`/`status`.

### `POST /api/v1/course` — Create a course
**Request body** (`Modules\Course\Http\Requests\Store`):

| Field | Type | Required | Rule |
|---|---|---|---|
| `course_name` | string | required | `max:255`, unique |
| `status` | int | required | `STATUS_ACTIVE` or `STATUS_PENDING` |
| `duration_days` | integer | required | — |
| `course_category_id` | integer | optional | `exists:course_categories,id` |
| `default_evaluator_id` / `default_written_evaluator_id` | integer | optional | `exists:users,id` |
| `student_coach_id` / `student_writing_coach_id` / `freelance_id` / `placement_id` | integer | optional | `exists:users,id` |
| `evaluators` / `mentors` | array\<int\> | optional | each `exists:users,id` |
| `ai_model_id` | integer | optional | `exists:ai_models,id` |
| `is_ai_enabled` | boolean | optional | — |
| `assignment_instruction_link` / `assignment_sample_feedback_link` | string | optional | — |
| `assignment_instruction_file` / `assignment_sample_feedback_file` | file or string | optional | if file: `mimes:pdf,doc,docx`, `max:10240`KB |

**Error responses:** `422` standard Laravel shape on any rule violation (e.g. duplicate `course_name`).
**Notes:** `evaluators`/`mentors` have no `distinct` rule — duplicate IDs pass validation.

### `PUT/PATCH /api/v1/course/{course}` — Update a course
Same fields as Store, but: `course_id` becomes **required** (send both path param and body field); `course_name`/`status`/`duration_days` become optional; **`default_evaluator_id`/`default_written_evaluator_id` become required** (opposite of Store) — omitting them on update 422s even if already set. Plus `remove_evaluators`/`remove_mentors` (`nullable|in:1`) to clear pivots.

### `CourseResource` fields (GET responses)
All raw columns except excluded/renamed ones, plus: `created_at` reformatted `Y-m-d h:i:s`; `no_of_assignments`, `enrollments_count`; `evaluators`/`mentors` (nested arrays); `instructors` (array, excludes soft-deleted mappings); `category`, `default_evaluator`, `default_written_evaluator`, `freelancer`, `placement`, `student_writing_coach`, `student_coach` (each nested object or null); `ai_model` (nested or null); `criteria` (nested `CourseCriteriaResourse` or empty); `question` (active mock-question strings). Raw FK id columns are **excluded** in favor of nested objects.

### Bootcamp-flavored Course
`POST/PUT /api/v1/bootcamp-course*` — same shape as Course Store/Update; `course_type` forced server-side to `BOOTCAMP_COURSE`, not itself a field. **This creates a `courses` row, not a `bootcamps` row** — see §3 Bootcamp (module) below for the actually-separate entity, and §7 for the correction that `bootcamps` rows ARE created elsewhere (via LawSikho, §6).

### `POST /api/v1/course-batches` — Create a course batch
| Field | Type | Required | Rule |
|---|---|---|---|
| `batch_date` | string | required | format **`M-d-Y`** (e.g. `Jun-01-2026`), **globally unique across ALL courses** |
| `status` | int | optional | `STATUS_ACTIVE`/`STATUS_PENDING` |
| `start_date` | date | optional | `Y-m-d` |
| `date_of_compilation` | date | optional | `Y-m-d`, must be after `start_date` |

**Notes:** Two different courses cannot share a `batch_date` — a strong collision-test candidate. `CourseBatchResource` only passes through `id`/`batch_date`/`start_date`/`date_of_compilation`/`status` plus computed `total_enrollment` and a field with a literal typo in its own JSON key: **`edminlge_batch_name`** (not `edmingle_batch_name` — copy exactly).

### Course Categories & Pass-Mark Criteria — three ways to set the same shape of data
1. `POST /api/v1/course-categories` — `category_name` required unique; `status` required bool; `parent_id` optional. **Also accepts the full pass-mark-criteria field set inline** (`minimum_exercises`, `each_exercises_marks`, `pass_marks_needed_percent`, `pass_marks_needed`, `total_marks` — `required_with` each other; `min_attempt_exercises_percent`/`no_writing_assignments`/`writing_assignments_marks` optional `min:0`; `lms_mcq` optional bool) — meaning category criteria can be set here OR via the dedicated endpoint below. Confirm which is the source of truth; test whether one path's write is visible via the other's read.
2. `POST /api/v1/course-category-criteria` — `category_id` required exists+**unique** (one row per category); same criteria fields, several now individually `required` rather than `required_with`.
3. `POST /api/v1/course-criteria` — `course_id` required exists+unique. **`minimum_exercises`/`each_exercises_marks` use `required_unless:course_id,!=,1`** — a **literal hardcoded check against course id `1`**, almost certainly a bug (likely meant "unless bootcamp"), not general business logic. Test explicitly with `course_id=1` vs. any other id.
4. `POST /api/v1/bootcamp-course-criteria` — course-scoped variant that **omits** `minimum_exercises`/`each_exercises_marks`/`min_attempt_exercises_percent`/`lms_mcq` entirely — purely for the writing-assignment-only bootcamp completion path.

### `GET /api/v1/course-completion-master/marksheet_calculation/{enrollment}` — compute completion
⚠️ **Not a standard envelope.** If `passing_criteria` is `null`: `apiResponse([], 'No criteria found', 403)`. Otherwise **returns the raw result of an internal `update()` call** — very likely a boolean/row-count, **not** a JSON marksheet object. **A test expecting `current_percent`/`completed` fields back from this response will fail** — those are written to the `enrollments` row as a side effect; re-fetch the enrollment to verify. (Unconfirmed empirically — verify with a direct call before asserting.)
**Side effects:** updates `current_percent`, `subjective_passing_percent`, `written_passing_percent`, `completed`, `is_passing_condition_added`, `completed_at` (once). Bootcamp-type courses branch to read `CourseCriteria` directly.

### `GET /api/v1/course-completion-master/generate-certificate/{enrollment}`
Letter grade from `current_percent`: A+ ≥90, A 80–89, B+ 70–79, B 60–69, C+ 50–59, C 40–49, **no grade below 40** (code default `$grade = ''`). Renders/uploads PDF to S3, updates `certificate_file`/`is_certified`/`certified_by`/`certified_datetime`. No domain event fires (see §7 of `DEVELOPER_DOCUMENTATION.md`).

### `POST /api/v1/packages` — Create a package
`name` required max:255; `duration_days` required; `courses` optional array\<int\> each `exists:courses,id` (custom message: *"Course id does not exist in the database"*). **Update uses the identical rule set** — `name`/`duration_days` become required again, not nullable, on update. `PackageResource`: `id`,`name`,`duration_days`, plus `courses` (nested), `courses_count`, `enrollments_count`. Activity log written via direct `Activity::create()`, bypassing the usual `activity()` helper.

### Bootcamp (`Modules/Bootcamp` module)
`GET /api/v1/bootcamps` — list only. **No create action exists for the `Bootcamp` entity in this module** (see §7 correction — it IS created, just via LawSikho's `bootcamp_from_lawsikho`). `POST/PUT .../books` — attach/replace book mappings; `bootcamp_id` required exists; PUT variant **deletes-all-then-recreates**, not a merge — a partial-update test expecting preserved entries will fail.

### Course FAQs, Plan Types, Topics — lighter CRUD
- **CourseFaq:** `course_id`/`question`/`answer`/`status` required on store; all but `course_id` nullable on update.
- **CoursePlanType:** `name` required unique max:255. No confirmed consumer anywhere (see `documentation/USER_WORKFLOWS.md` §6) — low QA priority beyond CRUD correctness.
- **Topic:** no dedicated Store/Update FormRequest found for the `Topic` entity itself (only for its doc-details sub-resource) — likely inline-validated; `searchTopicsWithArray` returns a raw `apiResponse()` array, a **different shape** from the other two Topic search variants (which return Resource collections).

---

## 4. Assignment & Evaluation Lifecycle APIs

> Cross-reference `documentation/USER_WORKFLOWS.md` §3 for *why*/*when*. `AssignmentSendingLog` and `StudentTasks` excluded/flagged dead — see notes.

### `POST /api/v1/assignment-library` — create an assignment
**Request body** (`StoreAssignmentRequest`): `course_id` required exists; `assignment_topic` required max:255; `number_of_exercises` numeric required (1–10); `assignment_type` required int (`0`=subjective/`1`=written); `allowed_file_types` optional array (`pdf|doc|docx|zip`); `plagiarism` required bool (**inert at submission time**, see below); `word_count` required int; `ai_model_id` optional exists; `is_ai_enabled` optional bool; `assignment_instruction_link`/`assignment_sample_feedback_link` optional string; `assignment_instruction_file`/`assignment_sample_feedback_file` — file (`pdf/doc/docx`, max 10240KB) OR string URL, branches on `hasFile()`; `status` required bool; `topic_content`/`tags` optional structured arrays.
**`AssignmentResource` shape:** `id`,`status`,`word_count`,`assignment_download_file`,`number_of_exercises`,`assignment_code`,`allowed_file_types`,`is_ai_enabled`, link fields, `ai_model` (nested/null), `created_at`, **`plagiarism` as string `"Yes"`/`"No"` (not boolean)**, **`assignment_type` as string `"Written"`/`"Subjective"` (not the raw int)**, `topic` (nested), `tags` (collection).

### `POST /api/v1/student-assignments/assign-by-filters` — bulk-assign to enrollments
**Request body** (`AssignByFiltersRequest`): `course_id` required exists; `batch_id` required array (min 1) — **auto-splits a comma-separated string via `prepareForValidation()`**, so either `batch_id=1,2,3` or `batch_id[]=1&batch_id[]=2` works; `submission_last_date` required date `Y-m-d`; `number_of_exercises` numeric 1–10; `assignment_download_file` **required only if `assignment_type==0`**; `assignment_topic` required max:255; `assignment_type` required; `plagiarism` required (inert); `word_count` required; `allowed_file_types` required array min 1; AI fields optional (mirrors Assignment).
**Success response:** empty `data`, "Assignment added successfully" — ⚠️ **fire-and-forget**: `StudentAssignment` rows are created **asynchronously** by `AssignAssignmentsByFiltersJob` (`default_high` queue) — a test must poll/wait, not assert row creation immediately from this response.
**Side effects:** `BulkAssignmentReportMail` to admin on completion; `WebhookTriggered` event; `FirstAssignmentSendLog` row; if `is_ai_enabled` false, AI-related fields are explicitly nulled in the job payload server-side regardless of what was sent.

### `GET /api/v1/student-assignments/validate-enrollments` — pre-flight eligibility check
**Query params:** `course_id` required, `batch_id` array required, `enrollment_status`/`topic_id` optional.
**Success response:** `{total_enrollments, eligible_enrollments:[...], ineligible_enrollments:[...]}` — each ineligible entry has `reasons` (exact strings): `"Batch not assigned"`, `"Enrollment is deactive"`, `"Package enrollment"`, `"Same topic already exists for this enrollment"`.

### `POST /api/v1/student-assignments/{student_assignment}/submit` — staff-mediated submission
> See `documentation/USER_WORKFLOWS.md` §3.3/§5.9's §4 note — the ACTUAL student self-service submission is a different endpoint, `POST /api/student/v1/student-my-courses/submit-assignment/{studentAssignment}` (§5 below).

**Request body** (`SubmitStudentAssignmentRequest`, multipart): `file` — **required**, exact field name `file` (singular), max 10240KB, extension checked against the assignment's `allowed_file_types`.
**Error responses:** 403 `"Can not submit an already submitted assignment"`; 403 `"Submission counter full. Assignment expired"`.
**Side effects:** file → S3; prior active `Result` deactivated; new `Result` created (`evaluator_id` from `enrollment.course.default_evaluator_id`); one `ResultExerciseScore` per exercise (`full_marks` from `passing_criteria` JSON or default 10); `StudentAssignment.status → SUBMITTED`, `submit_counter` −1.

### `POST /api/student/v1/student-my-courses/submit-assignment/{studentAssignment}` — the REAL student self-service submission
**Request body**, multipart, **no FormRequest** — raw PHP `$_FILES` access:
- `uploadfile` — file, required; rejects files **> 10,000,000 bytes** (~9.5MB, not round 10MB) with `{"status":1,"error":"Not success! File size more than 10mb","message":""}` — **`status` is `1` even on this rejection**, don't treat `status==1` as success.
- `rating`, `desc`, `selectedOrderIds` (comma-separated, not JSON array) — bundled Assignment CSAT submission in the same call.
**Behavior:** rejects duplicate submission (same status-check as the staff path); **plagiarism check is conditionally still live here** if `assignment.plagiarism == 1` — **contradicts the hardcoded-off check in the staff-mediated endpoint above.** Confirm with the team which path the live frontend actually uses before assuming plagiarism checking is universally dead.
**Success response:** `{"status":1,"msg":"success"}` (+ `"plag":{...}` on the plagiarism branch).

### `PUT /api/v1/results/{result}` — save/edit scores (step 1 of grading, does NOT finalize)
**Request body** (`UpdateResultRequest`, multipart if uploading): `_method` required literal `PUT`/`PATCH` (needed for multipart file upload); `scores` array optional — **exact shape: `scores[].serial_number` (int, 1–10) + `scores[].obtain_marks` (numeric)**, sentinel `obtain_marks: 101` clears a score to `null`; `feedback_file` optional file; `waive_marks` optional bool (stored as literal `3` if truthy, else `null` — not a plain bool in DB); `feedback_edit_reason` optional string.
**Error responses:** 403 `"Cannot update result. Student is inactive."`; 403 `"...Enrollment is inactive."`
**Resubmission gate** (subjective assignments, any score <4): `Result.status → RESUBMIT`, `StudentAssignment.status → ACTIVE`, `submit_counter` +1, `ResultFeedbackFileMail` queued — grading stops here. **Skipped entirely for written assignments.**
**Normal success:** `{"result": <ResultResource>}` — **`StudentAssignment.status` is NOT changed here**, even on a fully-scored update.

### `GET /api/v1/results/send-email/{result}` — finalize grading (step 2, GET not POST)
**Side effects:** `ResultSendMail` to student; `ResultEvaluated` notification to student + acting admin; `Result`: `is_email_sent=EMAIL_SENT`, `is_review_done=REVIEW_DONE`, `status=EVALUATED`, `evaluation_date=now()`; **`StudentAssignment.status → EVALUATED` — the ONLY place this transition happens**; synchronously invokes `marksheetCalculation($enrollment)`.
**QA note:** a test asserting `EVALUATED` after only calling the `update` (step 1) will fail — both calls required in sequence.

### `POST /api/v1/results/assign-evaluator-single/{result_id}` — reassign evaluator
`evaluator_id` required exists; `change_all` optional truthy — reassigns **every** `is_review_done=0` `Result` from the *current* evaluator, not just this one. Response `data` is a **raw array**, not a named key. 500 `"Something went Wrong"` if the underlying update returns falsy.

### `POST /api/v1/results/assign-evaluator-round-robin`
`evaluator_id` array required; `result_id` array **required_without `current_cond`**; `current_cond` **required_without `result_id`** (means "apply to current filtered set"). 403 `"Please add filter / search conditions"` if `current_cond` set without `course_id`. Distributes `i % totalEvaluators`; response includes per-evaluator `{evaluator_id, updated_count, result_ids}`.

### `Route::apiResource('results', ...)` → `store` — direct Result creation
`student_id` required exists; **`assignment_id` validates against `student_assignments`, not `assignments`** — confirms the known FK-naming trap at the request-validation layer, not just the DB schema; `plagiarism_result` optional 1–100; `submitted_file` required URL.

### Evaluator, EvaluatorCSAT, AssignmentCSAT — simpler CRUD
- **Evaluator** is read-mostly master data (`GET /api/v1/evaluator` + `meta.total_evaluator`/`total_active_evaluator`); all real assignment-logic lives in Result, not here, despite `apiResource` scaffolding existing.
- **EvaluatorCSAT store**: `student_id`/`result_id`/`evaluator_id` required exists; `rating` int required; `details` string required; `reason` array required each `exists:evaluator_csat_form_reason`.
- **AssignmentCSAT store**: `enrollment_id` **required_without `package_id`** and vice versa (exactly one); `course_id`/`batch_id` required; `rating` — **string, not numeric** (unlike EvaluatorCSAT's int rating); `selectedOrderIds` array required.

### AIEvaluation
**Scope note:** `AIEvaluationController` is unused scaffolding; real logic is `AutoEvaluationService` + 3 job classes. Two webhook endpoints (`ai-evaluation/webhook`, `ai-assignments/webhook`) are inbound receivers from the external AI service — not specced (external contract, not this codebase's).
- `POST /api/v1/ai-assignments/evaluate` — `student_assignment_id` required exists; queues `EvaluateStudentAssignmentJob`; response `{"status":"success","message":"AI evaluation triggered for student assignment ID: {id}."}`.
- `POST /api/v1/ai-assignments/bulk-evaluate` — `student_assignment_ids` array required; 422 `"No valid student assignments found for evaluation."` for IDs failing the `is_ai_enabled=1` + un-evaluated filter (silently excluded, not individually erred).
- `POST /api/v1/ai-assignments/reevaluate` — route handler force-injects `is_evaluated:1` server-side; resets `ai_evaluation_status→PENDING` and re-dispatches the evaluate job.
- `POST /api/v1/ai-assignments/edit-feedback` — `result_id` required exists; `feedback_content` string required (HTML); `ai_score` optional 0–100.

### AgenticSupportSystem — external AI-agent gateway
**Two static-bearer-token tiers — the one domain not using `auth:sanctum`/`auth:student`:**
- **Tier 1** (`agentic.static.token`, most reads): `X-API-Token` or `Authorization: Bearer` vs `AGENTIC_SUPPORT_SYSTEM_TOKEN`. 401 `"Authentication token required"` / `"Invalid authentication token"`; 500 `"Authentication not configured"` if unset server-side.
- **Tier 2** (`agentic.listing.static.token`, create/update/migrate writes): same contract vs `AGENTIC_SUPPORT_SYSTEM_LISTING_TOKEN` — **a different token from Tier 1.** A QA client needs both to exercise the full surface.

Highest-value endpoints (of ~40+ total — the rest are lower-risk read-only listings, enumerate directly from the routes file if full coverage is needed):
- `GET /api/v1/students/{email}/student-details` (Tier 1) — 404 `"Student not found"`; success returns the **raw Student model**, not Resource-wrapped.
- `POST /api/v1/students/create-enrollment-v2` (Tier 2) — `email` required; `enrollment_type` required (`course`/`bootcamp`/`bootcamp_additional`); `country_id` required exists; `phone` required + phone format; auto-creates a `Student` with generated password if none exists (course type only).
- `POST /api/v1/students/assign-batch-v2` (Tier 2) — plain `response()->json()` errors, not `apiResponse()`: 400 `"email is required"` / `"batch_id is required"`; 404 `"Student not found"`.
- `POST /api/v1/students/update-v2` (Tier 2) — field is `lms_user_id`, **not `lms_id`**; activity log `causer_id = env('AGENTIC_USER_ID', 1)` (fixed system actor, not the real caller — no per-caller identity in this auth scheme).
- `POST /api/v1/students/update-enrollment-status-v2` (Tier 2) — 422 `"Enrollment cannot be activated when the student is deactivated."` guard.
- `POST /api/v1/support-hub/students/deactivate` (Tier 1, not Tier 2, despite being a write) — deletes all Sanctum tokens (forced logout), `Student.status → PENDING`.

---

## 5. Student Engagement, Notifications, NPS & Call Booking APIs

> Excludes the 6 confirmed-deprecated engagement modules (`StudentClasses`, `Forum`, `StudentForum`, `PerformanceCoach`, `PerformanceCoachCSAT`, `StudentPerformanceCoach`). `StudentBookACall` is confirmed live and specced in full.

### StudentDashboard

- `GET /api/v1/add-nps` → **`POST /api/v1/add-nps`** — student NPS submission, **dashboard v1 path**: no FormRequest, raw `json_decode(php://input)`; required keys accessed directly (undefined-index error if missing, not clean 422): `rating`,`answer`,`enrollId`,`courseId`,`batchId`,`surveyType` (`1`/`2`),`reason[]`. Success `{"status":1}` — **`status` stays `1` even on a nominal-failure branch** (no created row), check `error` too. ⚠️ **Field-naming mismatch**: this is genuinely a different payload shape from `NPS`'s own `POST /v2/nps` (`enrollment_id`/`course_id`/`batch_id`/`survey_type`/`reasons[]`, FormRequest-validated) — not interchangeable, and this v1 path has **no duplicate-submission check** at all.
- `GET /api/v1/student-dashboard/nps-survey-data/{enrollment}` — due-check. If due: includes a literal typo'd key **`resones`** (not `reasons`) — must be used verbatim. If not due: `{"status":1,"data":[],"error":"survey Not needed "}` (trailing space is literal, in source).
- Edmingle-proxy reads (`calendar`,`today-classes`,`class-updates`,`announcements`,`unread-count`,`join-class`) — response body is **whatever Edmingle returns**; don't hardcode exact fields without a live/staging account. `getTodayClass` mints a JWT and refreshes `students.edmingle_api_key`/`edmingle_expire_at` as a side effect — repeated test calls will keep rotating the stored token. **Mock at the `Http::` facade level rather than asserting real Edmingle shapes.**

### StudentDashboardManagement (journey steps)
`POST .../save-journey-steps` (`StoreJourneyStepRequest`): `type` required (rule is literally `'required|'` — trailing-pipe no-op, **any non-empty value passes**, no actual type constraint despite the name); `is_draft` required int; `steps` required array with `title`/`stepId` required, `subSteps` nested (nullable) with `title`/`isVisible` required, `imageFile` optional image max:2048KB. A test asserting 422 for an "invalid type" will fail — only presence is checked.

### StudentMyCourses
- `submit-assignment/{studentAssignment}` — see §4 above (the real student self-submission endpoint).
- `POST .../requestForCertificate` — a **third** certificate-request implementation (distinct from `StudentFrontendEnrollment`'s, §2). Raw JSON, no FormRequest: `enrollment_code` (string, required — looked up by code, not numeric id), `bootcampId` optional. `{"status":1}` on success, `{"status":1,"error":"Some issue occurred"}` on failure — **`status` stays `1` either way.** Only queues one email to a hardcoded admin address — no student acknowledgement (unlike the `StudentFrontendEnrollment` variant's two emails). A non-matching `enrollment_code` likely produces a 500 (null-model access), not a clean 404 — worth a boundary test.

### StudentNotifications & Notification
> Both read/write the **same underlying tables** — refining the "three overlapping systems" note in `documentation/USER_WORKFLOWS.md` §4.5: these two actually share one backing store; only `StudentFrontendEnrollment`'s separate `NotificationController` is a genuinely distinct third surface.

- `POST /api/v1/create-notification-for-all` and `.../create-notification-for-specific-range` — identical validation (`StoreNotificationRequest`: `title`/`content`/`category_id`/`tag_id`/`channel_id` required, `radio` required but unconstrained). ⚠️ **Both endpoints run functionally identical code** — neither implements a distinct "broadcast to literally everyone" behavior beyond whatever `course_id`/`batch_id`/`package_id` filters produce; the two named jobs imported for each aren't visibly dispatched. Confirm actual behavior with the team before assuming "for-all" truly means unconditional broadcast.
- `PUT /api/v1/notification-status/{notification_id}` — ⚠️ misleadingly named; **hard-deletes** the row unconditionally, doesn't toggle a status field.
- Student comment endpoint (`store-comment`) has a likely bug: filters `NotificationUser` by `->where('user_id', $input['notification_id'])` — using the **notification's id** where the authenticated user's id belongs; worth a dedicated regression test.
- `mark-as-read` — optional `id`; **no ownership check** that the id belongs to the caller — worth an authorization boundary test (can student A mark student B's notification read?). Response is identical `{"status":1,"data":[],"error":null}` whether or not anything was actually updated.

### NPS (admin/system side)
`POST /api/v2/nps` (`auth:sanctum`, NOT `auth:student` despite creating what looks like a student response): `rating`/`answer` required string max:255; `enrollment_id`/`course_id`/`batch_id` required exists; **`student_id` required exists, taken directly from the request body, not the authenticated identity** — test whether a caller can submit on behalf of an arbitrary student; `reasons[]` required each exists; `survey_type` required (`1`/`2`). ⚠️ **Duplicate check bug**: `checkIfDuplicate()` reads `$request->courseId`/`$request->batchId` (camelCase) while the validated fields are `course_id`/`batch_id` (snake_case) — since the FormRequest never defines the camelCase names, they're `null` on the request object, so **the duplicate check likely always compares against `null` and may never catch a real duplicate.** Worth a dedicated test: submit twice with identical ids, confirm whether the second is actually blocked. Duplicate-found response is `201` (not 409) with message "NPS Already submitted".

### StudentBookACall — ✅ confirmed live, integrates with a separate sub-project's own API

> Every endpoint below has **no FormRequest/no `validate()` call** — bodies pass through largely as `$request->all()` to the external sub-project APIs (`MEETING_API_BASE_URL`, `BOOK_A_CALL_API`), which do their own validation. Malformed input mostly surfaces as an error *from the sub-project*, relayed back — treat this app's input handling as a thin pass-through and focus tests on (a) what gets forwarded and (b) how success/error is translated back.

#### `POST /api/student/v1/booking/create`
- **Request body:** `startTime`/`endTime`/`timeZone` required (parsed/converted to UTC); `userId` required — the **instructor's `meeting_id`**, not this app's own user id; `courseId` resolves course/package name + student batches; `eventId`, `description`, `teamId`, `type` (`package`/course). Any extra keys forward verbatim.
- **Behavior:** two chained external calls — `POST {MEETING_API_BASE_URL}bookings` (injects `student_name`/`student_email`/`student_phone` from the authenticated student server-side — **not client-overridable**) then `POST {BOOK_A_CALL_API}booking/create`.
- **"No slots" case:** `200 {"status":"success","data":[],"message":"No slots found."}` — **200, not 404/409** — check message content, not status code, to detect a failed booking attempt.
- **Success:** `201`, `data` mixes externally-sourced fields (`id`,`meeting_id`,`start_time`/`end_time`,`attendeeTimeZone` — don't assume you control these) with locally-sourced `course_name`.
- **Notes:** No local-only success path exists — end-to-end testing needs staging credentials or `Http::` mocks for both external services.

#### `PUT /api/student/v1/booking/edit/{bookingId}`
- `bookingId` is the **sub-project's** id (from create's `data.id`), not a local id. Chains the same two external calls (edit variants). Possible latent bug: on a missing-`data.id` error branch, the code does array-access (`$response['message']`) on what may be a raw `Illuminate\Http\Client\Response` object — worth a boundary test mocking that exact external response shape.

#### `POST /api/student/v1/booking/{bookingId}/cancel`
Single external call to `BOOK_A_CALL_API` only (no meeting-API call for cancellation, unlike create/edit). Success: `{"data":[],"status":"success","message":"Booking has been cancelled"}`.

#### `POST /api/student/v1/student/review` (`storeStudentReview`)
⚠️ **If the external call fails, this still returns `200 {"status":"success",...}`** unless the external response has a JSON body or throws — the local response does not reliably reflect whether the review was actually persisted externally. Can't verify success/failure purely from this endpoint's response.

#### `PUT /api/student/v1/meeting/add-rating/{meeting_id}`
Returns the raw `Illuminate\Http\Client\Response` from the external call directly (`return $bookACallResponse;`), not wrapped in `response()->json()` — confirm this actually serializes as expected JSON in practice; unusual controller return type.

**Cross-cutting note for this whole section:** several endpoints return `"status":1`/`"success"` even on semantic no-op/error paths (`add-nps`, `requestForCertificate`, `markAsRead`, `storeStudentReview` on external failure). Never treat 2xx + success-shaped body as sufficient proof of success for these — inspect `error`/`message`, and follow up with a read where it matters.

---

## 6. Admin Operations & External Integration APIs

> Excludes confirmed-deprecated `ProjectManagement`, `BookMaster`, `BookDeliveryLog`.

### Role Management (`auth:sanctum`)
- `POST /v1/roles` — `name` required unique; `status` required `in:0,1`; `permissions` required array. Success `201`, `RoleResource` (nested `permissions` with `checked`/`child`, `users_count`, `creator`/`updater`).
- `DELETE /v1/roles/{role}` — `422` `"Roles is assigned to users"` if any user holds the role — must `transfer-to-other` first.
- `POST /v1/roles/status/change` — `roles_ids` array required exists; `comment` required; `status` one of `activate`/`deactivate`. **Does not itself deactivate the users holding the role**, despite an inline code comment suggesting that was intended — verify with the team before asserting cascading deactivation.
- `POST /v1/roles/export` — async; `RolesCSVDownloadStart` job — poll/wait, don't expect a file synchronously.
- Tampered `cursor` on `GET /v1/roles` → `abort(500, 'Cursor value tempered')` — 500, not 4xx.

### Permission (read-only, static/seeded data — no create/update/destroy)
`GET /v1/permissions/users/{user?}` — **not the standard envelope**: `{"data":{"permissions":{"<parent>":["<child>",...]},"redirect_url":"..."},"message":"Success","status":"success"}`. Synthesizes two pseudo-entries not backed by real rows: `permissions.lms` (present iff target user has `edmingle_id`), `Schedule_My_Meeting_Managment` (removed unless `meeting_status === 'Completed'`) — test both presence and absence conditions.

### Internal Notes (`auth:sanctum`, versioned)
⚠️ `GET /v1/internal_notes/{id}` — **`{id}` is a `student_id`, not a note id** — returns ALL notes for that student. Hitting it with an actual note id silently returns an empty collection, not an error. `PUT/PATCH` copies current text to `internal_notes_history` first, then overwrites + `is_edited=1`. `DELETE` also writes history (`status=0`) — history remains queryable even after the live note is gone, but its 404 error message says `"Student Not Found"` even when the actual condition is note-not-found — misleading text.

### Referral System — thin proxy, no local tables
⚠️ **None of this module's endpoints are testable without a reachable `REFERRAL_BASE_URL` or a mock.** `GET /v1/referral-system/students` (admin) has **no auth guard at all** — only `json.response` — recommend an explicit unauthenticated-access test. Student-facing endpoints (`generalCode`, `courseSpecific`, `courseInfo`, `studentEarningDetail`) proxy live GETs; error shape on `RequestException` is `{"error":"<message>"}` — **not the standard app envelope**. `POST .../mailSend` interpolates `referralId` directly into the outbound URL path with **no validation/escaping** — worth a boundary/injection-style test even as a pure proxy.

### LawSikho Integration Gateway — highest QA priority
All routes: `['json.response','log.third.party']`, prefix `v1`. **Only 2 of ~25 routes require any auth token; the rest rely solely on request logging.**

- **Protected-route auth:** header `X-Auth-Token` must exactly equal `config('lawsikho.api_token')`, compared with **`===`, not `hash_equals`** — not timing-safe. On failure: `401 {"status":"error","error":"Unauthorized","message":"Token does not match"}`. Applies to `POST /v1/revoke-access` and `POST /v1/active-access` **only**.
- `POST /v1/add-student` — **no auth at all** (recommend an explicit "no credentials" test). `StoreStudentRequest`: `email` required valid; `password` nullable `confirmed`; `status` required int (`PENDING|ACTIVE|DISABLED`); several fields (`full_name`,`phone`,`countryCode`,`address`, etc.) are **read directly in the controller, not validated by the FormRequest** — a missing `full_name`/`phone`/`status` fails a manual null-check with `422 {"data":{"message":"Full Name, Phone, Status Can't be null"},"message":"Field Required"}` instead of a per-field Laravel validation error. Existing-email branch returns **`201`** (not 200) even when only updating contact fields, message `"Student Exist"`.
- `POST /v1/update-student-address` — response shape does **not** match the app-wide envelope: `{"status":"success","error":null,"data":"Address Updated"}` (`status` before `data`, no `message` key). Two distinct 422 literal messages for the optional batch-assignment branch.
- `GET /v1/check-lms` — **always HTTP 200** regardless of found/not-found/no-lms-id — distinguish only by `message` text, not status code.
- `GET /v1/lms` / `PATCH /v1/lms` — responses are **completely unwrapped raw values**: `GET` returns the bare `lms_id` int or `null` as the entire body; `PATCH` returns the bare int `1` or `0`. No JSON envelope of any kind.
- `POST /v1/active-access` / `revoke-access` (token-gated) — activity events always attributed to `User::find(1)` regardless of actual caller. `revoke-access` branches on whether other enrollments exist: if not, the student itself is deactivated **and**, if `lms_id` is set, triggers a **live outbound Edmingle deactivation call** — not mockable at this app's boundary alone.
- `POST /v1/store-photo|store-id-proof|store-cv` — **no auth**; success response is a **raw unwrapped array** of file metadata; these endpoints only store to S3, they do **not** attach the file to any student record (that happens separately via the enrollment-form endpoints). Missing file field → an undefined-variable condition, not a clean 4xx.
- `POST /v1/store-enrollment-form` (v1) vs `-v2` — v1 has zero validation; v2 validates only the two optional image uploads. **Real difference**: v1 expects `hidUserImage(IdProof)` as already-uploaded URL strings (and does nothing further with them — dead code); v2 accepts them as actual file uploads and persists the resulting S3 URLs. `response` object keys must follow convention `resp_<question_number>` — no schema validation; confirm exact keys the live form sends before constructing test payloads.
- `GET /v1/check-enrollment` — ⚠️ **likely bug**: `course_id` param is validated against `exists:course_batches,id`, not `courses,id`, despite the field name — a valid `courses.id` that isn't coincidentally also a `course_batches.id` would fail validation before even reaching the lookup logic.
- `POST /v1/bootcamp_from_lawsikho` — see §7 correction: **does** call `Bootcamp::create()`. Caller-supplies the `id` (not auto-increment); branches update-if-exists / create-if-not. Both branches return HTTP 200, including the create case (not 201).
- `GET /v1/generate-enrollment-code` — response is a **raw string** (e.g. `"LS/12/34/56"`), not JSON-wrapped at all.

### AtsAPI — see §7 for the unreachable-middleware correction
`POST /v1/save-job-and-course-mapping` — **no auth**, no gateway middleware involved despite prior documentation. `channel` (string, required) is only checked for exact equality to `'Lawsikho'` to decide the stored `status` — **all rows are hardcoded `channel:'Lawsikho'` regardless of what's actually sent**, so a submitted `SkillArbitrage` value is never reflected in storage. `user_id` sent in the body is ignored — always `auth()->user()->id ?? 1`, meaning an unauthenticated call stores `user_id: 1`. Success: `{"success":true,"message":"..."}` — **`success` boolean field, not the app-wide `status` string.**
`GET /v1/atsapi/get-all-jobs` — requires a custom `ats-token: Bearer <token>` header (not `Authorization`) AND a resolvable `auth()->user()` despite no guard middleware on the route — will throw on a genuinely unauthenticated call; test this edge case explicitly. Depends on a live external ATS search service for the "jobs found" path — mock or stage it.

### Webhook Module — admin config CRUD + an unrelated failure-sink, NOT a live inbound receiver
- `POST /v1/webhooks` — ⚠️ **imports but never applies `StoreWebhookRequest`** — controller signature is plain `Request`, so **no validation runs at all**; any fields are mass-assigned. Response has a malformed shape: `{"message":"...","webhook":<raw model>,201}` where the literal integer `201` is a body member, **not** the actual HTTP status (which defaults to 200) — a test asserting `status_code==201` will fail.
- `webhook-events` CRUD — same no-validation pattern; confirmed via grep that **no code anywhere reads or dispatches against `webhooks`/`webhook_events`** — testing here validates CRUD mechanics only, not any real integration.
- `POST /v1/failed-api-responses` — the one endpoint with real validation and purpose (`StoreFailedApiResponseRequest`); queues `LogFailedApiResponseJob`; looks like a sink for this app's *own* outbound-integration failures logging themselves, not something external callers hit. Correct envelope, `202` status.
- `GET /webhook` (unprefixed, `auth:api`) — this guard isn't otherwise confirmed configured anywhere else in the app; test whether it even authenticates before assuming this route is live. Likely dead.

---

*End of API specification. For workflow context (why/when these endpoints get called in sequence) see `documentation/USER_WORKFLOWS.md`; for schema/route-list/module-purpose ground truth see `documentation/DEVELOPER_DOCUMENTATION.md`.*
