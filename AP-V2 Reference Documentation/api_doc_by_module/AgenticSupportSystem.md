# AgenticSupportSystem

External AI-agent / automation gateway module: a flat, static-bearer-token-protected API surface (no `auth:sanctum`/`auth:student`) that exposes student, enrollment, course-catalog, course-calendar and Support-Hub data to external AI-agent and automation clients, plus a set of write endpoints (enrollment creation, batch/bootcamp migration, status changes) that mirror the equivalent authenticated-admin flows in other modules but re-implement them with their own self-contained helper copies.

See [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for the shared response-envelope/error/pagination vocabulary used below (`apiResponse()` helper, hand-rolled `response()->json()`, the 422/404/401 shapes, etc.). This module does **not** use `Http/Requests/` (no FormRequest classes exist) or `Http/Resources/` (except one direct use of `Modules\Enrollment\Http\Resources\EnrollmentResource` in a handful of write endpoints, noted per-endpoint) — validation, where present, is inline `$request->validate([...])` / `Validator::make(...)` inside the trait methods.

## Structural summary

- Controller: `Modules/AgenticSupportSystem/Http/Controllers/AgenticSupportSystemController.php` — constructor-only, injects `EnrollmentRepositoryInterface`, `StudentController`, `StudentRepositoryInterface`, `Excel`, `PackageCourseMappingRepositoryInterface`, `TagRepositoryInterface`. All method bodies come from six `use`-imported traits (plus `Modules\Enrollment\Http\Traits\EnrollmentTrait`, imported but whose methods are only used internally by some of the six — no route calls into `EnrollmentTrait` directly):
  - `AgenticSupportSystemTrait` (`Http/Traits/AgenticSupportSystemTrait.php`, 1164 lines) — "V1" student/course reads.
  - `AgenticSupportSystemTraitV2` (`Http/Traits/AgenticSupportSystemTraitV2.php`, 3357 lines) — "V2" student reads, enrollment creation/update, listings, sanctum validation, student search, registration details.
  - `CourseCalenderAPITrait` (`Http/Traits/CourseCalenderAPITrait.php`, 231 lines) — course-calendar master-data reads.
  - `OtherTeamAutomationTrait` (`Http/Traits/OtherTeamAutomationTrait.php`, 99 lines) — one bulk-export endpoint (`enrollments-v3`) for a different consuming team.
  - `BatchBootcampMigrationTrait` (`Http/Traits/BatchBootcampMigrationTrait.php`, 1407 lines) — batch/bootcamp migration write endpoints; itself `use`s `AgenticSupportSystemTraitV2`.
  - `SupportHubTrait` (`Http/Traits/SupportHubTrait.php`, 3120 lines) — Support Hub read listings + enrollment status/resume writes, with its own self-contained `*Agentic`-suffixed copies of Edmingle/refund-eligibility/enrollment-code helpers so it doesn't depend on `EnrollmentTrait` being mixed in for those two endpoints.

- **Route count — structural surprise vs. the brief:** `Modules/AgenticSupportSystem/Routes/api.php` defines **61 routes**, not "~41" — confirmed by both a full read of the route file and `grep -c "Route::\(get\|post\|...\)("`. This file documents all 61.

## Auth

Two independent static-bearer-token middlewares gate this module — the one domain in the app that doesn't use `auth:sanctum`/`auth:student`. Both middlewares (`Http/Middleware/StaticTokenAuth.php`, `Http/Middleware/ListingStaticTokenAuth.php`) share identical logic, differing only in which config key/env var they check:

- **Tier 1 — `agentic.static.token`** (most reads): checks `config('agenticsupportsystem.static_token')`, sourced from **`AGENTIC_SUPPORT_SYSTEM_TOKEN`** with **no default** — if unset, `abort(500, 'Authentication not configured')`.
- **Tier 2 — `agentic.listing.static.token`** (create/update/migrate writes + the `listing/*` catalog endpoints): checks `config('agenticsupportsystem.listing_static_token')`, sourced from **`AGENTIC_SUPPORT_SYSTEM_LISTING_TOKEN`** — **but with a hardcoded fallback default of `'Kp7rX2Yg4b9M8cTQW0sJz5dN1vLhA6kF3eUqDtyV'`** (`Modules/AgenticSupportSystem/Config/config.php:17`) if the env var is unset. **Security-relevant quirk:** unlike Tier 1, Tier 2 never 500s for "not configured" — if the env var is missing in any environment, Tier 2 silently accepts this well-known hardcoded string as a valid token.

Both middlewares read the token from `X-API-Token` header, falling back to `Authorization` (with an optional `Bearer ` prefix stripped) if `X-API-Token` is absent. Behavior on failure, identical for both tiers:
- Missing token → `abort(401, 'Authentication token required')`.
- Token present but doesn't match → `abort(401, 'Invalid authentication token')`.
- Server-side token unset (Tier 1 only, see above) → `abort(500, 'Authentication not configured')`.

Both middlewares log every attempt (`Log::info` on success, `Log::warning` on missing/invalid token, `Log::error` on missing server config) with IP/user-agent/endpoint — no per-caller identity is established beyond that; the two tokens are shared secrets, not per-client credentials. A QA/parity client needs both tokens to exercise the full surface. All routes also carry `json.response` (forces JSON error rendering) and, in every group but the last (`sanctumTokenValidation`), a `throttle:N,1` (N requests/minute), noted per section below.

Abort responses from `abort(401/500, $message)` are rendered by the app's standard exception handler (see `_COMMON_CONVENTIONS.md` "Standard error shapes") as `{"status": "error", "message": "<message>", "data": []}` at that status code, since `json.response` forces JSON rendering — not confirmed against a live request in this pass; verify directly if the exact abort-response shape matters for a test.

---

## 1. Student Data Reads — V1 (Tier 1, throttle 10/min)

Prefix `v1/`. All handlers in `AgenticSupportSystemTrait`. All responses are hand-rolled `response()->json([...])` (never `apiResponse()`), returning raw Eloquent models/arrays, not Resource-wrapped. None of these endpoints have any inline validation beyond the 404 existence checks described — no FormRequest, no `$request->validate()`.

### 1. `GET /api/v1/students/all-data/{emailId}` — full student data dump
**Handler:** `getStudentAllDataByEmailId($emailId)`
**Params:** `emailId` (path) — a plain string compared with `where('email', $emailId)`, no format validation.
**Success (200):** `{"student": {...student columns..., "enrollments": {"course_enrollment": [...], "package_enrollment": [...], "bootcamp_enrollment": [...]}, "meetings": [...], "journey": [...]}}`. `student` is `Student::toArray()` plus injected keys; each enrollment array element is the raw enrollment `toArray()` plus an injected `Certificates` sub-object (`is_certified`, `certified_by`, `certified_datetime`, `certificate_file`, `request_for_certificate`). Student eager-loads `enrollmentQuestionAnswers.question`, `notification_user.notification`, `assignmentCSATForm...`, `evaluatorcsatform...`, `npsform...`.
**Errors:** 404 `{"status":"error","message":"Student not found"}` if no student matches.
**Side effects / external calls:** Calls private `getStudentMeetings($student)` → `Http::get(env('BOOK_A_CALL_API') . 'student/meetings/{studentId}/1')` (channel id hardcoded `"1"`, "LSAP channel id for book a call"); on failure logs and returns an error-shaped array that still gets treated as `$meetings['data'] ?? []` (silently becomes `[]`). Calls private `getStudentJourney($student)` → `Http::get(env('STUDENT_JOURNEY_API', 'https://j5kitog7zd.execute-api.us-east-1.amazonaws.com/dev/api/v1/') . 'student-journey/get-log/{email}/group-by-day?channel=LawSikho')`, no failure handling — an exception here would propagate as a 500.
**Notes:** Two external HTTP calls per request, both synchronous (no queue) — response latency is coupled to `BOOK_A_CALL_API` and `STUDENT_JOURNEY_API` availability.

### 2. `GET /api/v1/students/{email}/student-details` — single student
**Handler:** `getStudentDetails($email)`
**Success (200):** `{"student": <raw Student model>}` with `enrollmentQuestionAnswers.question` eager-loaded. Matches the already-specced entry in `API_SPECIFICATIONS.md`.
**Errors:** 404 `{"status":"error","message":"Student not found"}`.

### 3. `GET /api/v1/students/{email}/enrollments` — enrollments by type
**Handler:** `getStudentEnrollmentDetails($email, Request $request)`
**Params:** `type` (query, optional) — one of `course`/`package`/`bootcamp`, mapped to `Enrollment::NORMAL_ENROLLMENT`/`PACKAGE_ENROLLMENT`/`BOOTCAMP_ENROLLMENT`.
**Success (200):** If `type` given: `{"enrollments": {"<type>_enrollment": [...]}}` (single key). If omitted: `{"enrollments": {"course_enrollment": [...], "package_enrollment": [...], "bootcamp_enrollment": [...]}}` (all three keys, each a raw `Enrollment` collection, no eager loads).
**Errors:** 404 `"Student not found"`; 400 `{"status":"error","message":"Invalid enrollment type"}` if `type` doesn't match the map.

### 4. `GET /api/v1/students/{email}/get-course-details/{courseId}` — enrollments for one course
**Handler:** `getEnrollmentsByCourseId($email, $courseId)`
**Success (200):** `{"course": <Course with 'criteria' eager-loaded>, "enrollments": [<raw Enrollment>, ...]}`.
**Errors:** 404 `"Student not found"`; 404 `"Course not found"`; 404 `{"status":"error","message":"No enrollments found"}` if the student has none for that course.

### 5. `GET /api/v1/students/{email}/assignments/{enrollment_id}` — assignments for one enrollment
**Handler:** `getAssignmentsByEnrollmentId($email, $enrollmentId, Request $request)`
**Params:** `topic` (query, optional) — `LIKE '%topic%'` filter joined against `topics.title`.
**Success (200):** `{"assignments": [...]}` — `StudentAssignment` rows joined to `assignments`/`topics`, with `assignment` (columns `id,topic_id,assignment_code,assignment_type,number_of_exercises,status`) and `assignment.topic` (`id,title`) eager-loaded.
**Errors:** 404 `{"status":"error","message":"Student not found or enrollment does not belong to this student"}` — single combined check (`whereHas('enrollments', ...)`), so a valid-email/invalid-enrollment case and an invalid-email case return the identical message.

### 6. `GET /api/v1/students/{email}/results/{enrollment_id}` — results for one enrollment
**Handler:** `getResultsByEnrollmentId($email, $enrollmentId, Request $request)`
**Params:** `topic` (query, optional), `assignmentId` (query, optional) — filters against `student_assignments.assignment_id`.
**Success (200):** `{"results": [...]}`, ordered `results.created_at desc`, with `resultExerciseScores` (subset of columns), `student_assignment`, `student_assignment.assignment`, `student_assignment.assignment.topic` eager-loaded.
**Errors:** Same combined "Student not found or enrollment does not belong to this student" 404 as #5.

### 7. `GET /api/v1/students/{email}/notifications`
**Handler:** `getNotifications($email)`
**Success (200):** `{"notifications": <student->notification_user collection, with .notification eager-loaded>}`.
**Errors:** 404 `"Student not found"`.

### 8. `GET /api/v1/students/{email}/certificates/{enrollment_id}`
**Handler:** `getCertificates($email, $enrollmentId)`
**Success (200):** `{"certificate": <Enrollment row, columns limited to id, enrollment_code, is_certified, certified_by, certified_datetime, certificate_file, request_for_certificate, current_percent, subjective_passing_percent, written_passing_percent, completed, completed_at, mcq_completed, mcq_score, course_expiry_date>}`. Note: `$certificate` is fetched by a second, separate `Enrollment::select(...)->where('id', $enrollmentId)->first()` query — not reused from the ownership-check query — so `certificate` can technically be `null` in the JSON if the row vanished between the two queries (race condition, not otherwise guarded).
**Errors:** Same combined "Student not found or enrollment does not belong to this student" 404 pattern as #5/#6.

### 9. `GET /api/v1/students/{email}/meetings`
**Handler:** `getMeetings($email)`
**Success (200):** `{"meetings": <raw JSON body from Book-a-Call API>}`.
**Errors:** 404 `"Student not found"`.
**External call:** `Http::get(env('BOOK_A_CALL_API') . 'student/meetings/{studentId}/1')`. On failure, returns `{"message":"Something went wrong, try again later.","status":"success"}` at the **upstream failure status code** (`$bookACallResponse->status()`) — note the `status: "success"` string sits inside what is semantically an error body; see `_COMMON_CONVENTIONS.md` "Cross-cutting QA caution".
**Notes:** This is functionally identical to the private `getStudentMeetings()` helper used inside `getStudentAllDataByEmailId` (endpoint #1) and `getEnrollmentFormDataForAISupportV2` machinery — duplicated logic, not a shared call.

### 10. `GET /api/v1/students/{email}/enrolled-courses`
**Handler:** `getEnrolledCoursesByStudentEmail($email)`
**Success (200):** A **bare array/object keyed by enrollment type** — `{"standalone_enrollment": [...], "bootcamp_enrollment": [...], ...}` (no wrapping `status`/`data` envelope at all; built via raw `DB::table()` queries, not Eloquent). Each course-details array has `enrollment_id` and `enrollment_type` merged in. Enrollment type strings come from private `getEnrollmentType()`: `standalone_enrollment` / `package_enrollment` / `bootcamp_enrollment` / `package_batch_enrollment` — note this method has **no `default`/`else` branch**, so an `Enrollment::type` value outside these four constants leaves `$enrollmentType` an **undefined variable** (PHP warning, not a 500, in most configs) when used as an array key.
**Errors:** 404 `{"status":"error","message":"Student not found"}`. If the student exists with zero enrollments, response is `response()->json([])` — an empty JSON array/object, not `{"status":"error",...}`.

### 11. `GET /api/v1/courses/all`
**Handler:** `getAllCourses()` → `{"courses": [{"id":..., "course_name":...}, ...]}` — all courses, no status filter, no pagination.

### 12. `GET /api/v1/bootcamps/all`
**Handler:** `getAllBootcamps()` → `{"bootcamps": [{"id":..., "bootcamp_name": <display_name>}, ...]}` — all bootcamps, no filter.

### 13. `GET /api/v1/packages/all`
**Handler:** `getAllPackages()` → `{"packages": [{"id":..., "package_name": <name>}, ...]}`.

### 14. `GET /api/v1/batches/all`
**Handler:** `getAllBatches()` → `{"batches": [{"id":..., "batch_name": <batch_date>}, ...]}` — all batches regardless of status.

### 15. `GET /api/v1/students/{email}/course-details/{courseId}`
**Handler:** `getCourseDetailsByEmailAndCourseId($email, $courseId)`
**Success (200):** `{"student": {id + reg_code, full_name, email, phone, date_of_birth, gender, father_name, address, pin_code, city, state, country, country_id}, "courses": [{"course": {id + status, course_name, duration_days, course_category_id, default_evaluator_id}, "enrollments": [<mapped enrollment>, ...]}]}`. The enrollment mapping (shared private `mapEnrollmentsData()`) produces a large per-enrollment object including a nested `certificate` sub-object and an `assignments` array (each with a nested `topic`).
**Errors:** via shared private `fetchAndValidateCourseData()`: 404 `"Student not found"` (checked first) or `"Course not found"`; 404 `{"status":"error","message":"No enrollments found"}` if the student has zero enrollments for that course.

### 16. `GET /api/v1/students/{email}/student-details-for-ai-support`
**Handler:** `getStdentDetailsForAISupport($email)` — note the method name typo (`Stdent`) is the actual, permanent symbol name; not fixable without a breaking route/trait change.
**Success (200):** `{"student_name", "student_email", "student_phone", "student_country_code" (default '+91'), "enrollments": {"standalone": [...], "packages": [{"package_name","package_courses":[...]}], "bootcamps": [{"bootcamp_name","bootcamp_courses":[...]}]}, "assignments": [...], "result": [...], "certificate": [...], "meetings": [...]}`. Assembled from `course.defaultEvaluator`, `batch`, `package`, `batchAssigner`, `creator` eager-loaded on all the student's enrollments, formatted by private helpers `formatEnrollmentsForAISupport`/`getAssignmentsForAISupport`/`getResultsForAISupport`/`getCertificatesForAISupport`, plus `getStudentMeetings()` (same Book-a-Call HTTP call as #9).
**Errors:** 404 `"Student not found"`.
**External call:** Same synchronous Book-a-Call GET as #1/#9.

### 17. `GET /api/v1/students/{email}/all-course-details-by-email`
**Handler:** `getAllCourseDetailsByEmail($email)` — same response shape as #15 (`{"student":..., "courses":[...]}`) but for **every** course the student has enrollments in (grouped by `course_id`), not just one `courseId`.
**Errors:** 404 `"Student not found"`. A course whose relation failed to load (`!$course`) is silently `continue`d, not surfaced as an error — a student with only orphaned/deleted-course enrollments gets `"courses": []` with a 200, not a 404.

### 18. `GET /api/v1/students/course-details-by-email` — dispatcher
**Handler:** `getCourseDetailsByEmail(Request $request)`
**Params:** `email` (query, required), `course_id` (query, optional).
**Behavior:** Pure dispatcher — no `course_id` → delegates to `getAllCourseDetailsByEmail($email)` (#17's exact logic); `course_id` given → delegates to `getCourseDetailsByEmailAndCourseId($email, $courseId)` (#15's exact logic). Same response shapes and error messages as whichever it delegates to.
**Errors:** 400 `{"status":"error","message":"Email is required"}` if `email` missing (this endpoint's own check, before delegating).

---

## 2. Student Data Reads — V2 (Tier 1, throttle 10/min)

Prefix `v1/`. All handlers in `AgenticSupportSystemTraitV2`. All take `email` as a **query** param (not a path segment, unlike the V1 group above) and all hand-roll `response()->json()`. Every one of these nine endpoints does the identical `email` presence/student-existence check first: 400 `{"status":"error","message":"Email is required"}` if `email` missing from the query string, 404 `{"status":"error","message":"Student not found"}` if no match — repeated per-endpoint below only where it differs.

### 19. `GET /api/v1/students/details-v2`
**Handler:** `getStudentsDetailsV2(Request $request)`
**Success (200):** Flat object: `student_id, student_name, student_email, student_phone, student_country_code (default '+91'), student_reg_code, student_status ("Active"/"Deactive"), address, city, state, country, pincode`. If status is Deactive, an extra `deactivation_details: {deactivated_by, deactivated_at, deactivation_reason}` key is added, sourced from the latest matching `Activity` log entry (`log_name = 'student_activation_and_deactivation'` with event `'student deactivated'` or `'Revoked From Revenue System'`).

### 20. `GET /api/v1/students/details/for-transcript`
**Handler:** `getStudentsDetailsForTranscript(Request $request)`
**Params:** `email` — **must be an array** (`?email[]=a@x.com&email[]=b@x.com`), not a single string; 400 `{"status":"error","message":"Emails are required and must be an array"}` otherwise.
**Success (200):** A **bare array** (no envelope key) — one entry per input email, in the same order as the input array; missing students yield `{"status":"error","message":"Student not found","student_email": "<email>"}` inline (not a 404 for the whole request), found students yield `{"student_id","student_name","student_email","student_phone","student_country_code" (default '+91')}`. So a single call can return a 200 with a mix of found/not-found rows.

### 21. `GET /api/v1/students/enrollments-v2`
**Handler:** `getStudentEnrollmentsV2(Request $request)` — **also the handler for endpoint #35 (`enrollments-v4`) — confirmed alias, see §4 below.**
**Success (200):** `{"enrollments": {"standalone": [...], "bootcamps": [{"bootcamp_name","bootcamp_courses":[...]}]}}`. Excludes `PACKAGE_ENROLLMENT`/`PACKAGE_BATCH_ENROLLMENT` types entirely (`whereNotIn`). Each enrollment entry includes `course_completion_details` (percentage + written/subjective exercise fractions + an HTML "more info" tip string built by private `moreTips()`), and a conditional `refund_info` populated only if the enrollment carries the `{"en":"Refund Eligible"}` tag (else `null`). Deactive enrollments get an extra `deactivation_details` (and `student_deactivation_details` if the student itself is inactive).

### 22. `GET /api/v1/students/assignments-v2`
**Handler:** `getStudentAssignmentsV2` → `{"assignments": [...]}` — same shape/fields as V1's assignments-for-AI-support but excludes package/package-batch enrollments and adds `submitted_date` (from the latest `latest=ACTIVE` `Result` row) and `assignment_created_at`.

### 23. `GET /api/v1/students/results-v2`
**Handler:** `getStudentResultsV2` → `{"results": [...]}`. Only `Result::latest == ACTIVE` rows; each row includes dynamically-numbered `score_1`, `score_2`, ... keys (one per non-null `resultExerciseScores` entry) merged into the row alongside `assignment_link`, `feedback`, `evaluator` (name string), `evaluated_date`.

### 24. `GET /api/v1/students/certificates-v2`
**Handler:** `getStudentCertificatesV2` → `{"certificates": [...]}` — only `is_certified == CERTIFIED` with non-null `certificate_file`, excluding package/package-batch types; each entry has a human-readable `exercises` string like `"12 Exercises (Total written 3/5 , Total subjective: 2/7)"` built via `sprintf`, computed by calling into `CourseCompletionMasterController::getWrittenDoneByStudent()`/`getSubjectiDoneByStudent()` (cross-module call, not a local query).

### 25. `GET /api/v1/students/hardcopy-v2`
**Handler:** `getStudentHardCopyDeliveryV2` → `{"hardcopy": [{"Book Name","SKU","Status" ("Sent"/"Deliverable"/"Not Deliverable"), "Sent On" (Y-m-d), "Address"}, ...]}` from `BookDeliveryLog`. Note the response object keys are **capitalized with spaces** (`"Book Name"`, not `book_name`) — inconsistent with every other endpoint's snake_case keys.

### 26. `GET /api/v1/students/meetings-v2`
**Handler:** `getStudentMeetingsV2` → `{"meetings": <raw Book-a-Call API JSON>}`. Same synchronous `Http::get(env('BOOK_A_CALL_API')...)` call and same "success"-labeled-failure-body quirk as V1 endpoint #9.

### 27. `GET /api/v1/students/enrollment-form-data-v2`
**Handler:** `getStudentEnrollmentFormDataV2` → `{"enrollment_form_data": [{"question","answer"}, ...]}` from `EnrollmentQuestionAnswer`; multi-select answers are comma-joined into a single string, and an `"Other"` sentinel answer is replaced with the free-text `is_other` value if present.

---

## 3. Course Calendar (Tier 1)

Prefix `v1/course-calender/*`. Handlers in `CourseCalenderAPITrait`. All hand-rolled `response()->json()`, no validation on the "all" endpoints (they take no input). **Throttle differs for one endpoint** — noted below.

### 28. `GET /api/v1/course-calender/course-category-details/all` (throttle 10/min)
**Handler:** `getAllCourseCategoryDetails()` → `{"category_details": [{"id","category_name","status" ("Active"/"Inactive"),"created_at","updated_at"}, ...]}` — all `CourseCategory` rows, unfiltered.

### 29. `GET /api/v1/course-calender/course-anchor-users-details/all` (throttle 10/min)
**Handler:** `getAllCourseAnchorUsersDetails()` → `{"anchor_user_details": [...]}` — `App\Models\User::whereHas('roles', name = 'Course Anchors')`, includes `meeting_id`, `meeting_status`, `meeting_link_status`, `has_event`, `status` ("Active" if `USER_APPROVED`), `meeting_url` (from `calendly_link`).

### 30. `GET /api/v1/course-calender/evaluator-users-details/all` (throttle 10/min)
**Handler:** `getAllEvaluatorUsersDetails()` — identical shape to #29 but role name `'evaluator'`, key `evaluator_user_details`.

### 31. `GET /api/v1/course-calender/evaluator-admin-users-details/all` (throttle 10/min)
**Handler:** `getAllEvaluatorAdminUsersDetails()` — identical shape, `whereIn('name', ['Evaluator-Admin', 'evaluator admin'])` (two role-name spellings), key `evaluator_admin_user_details`.

### 32. `GET /api/v1/course-calender/student-count-in-course-and-batch` (throttle 10/min)
**Handler:** `getStudentCountInCourseAndBatch(Request $request)`
**Params:** `course_id` (required), `batch_id` (required, **but is actually a `batch_date` string, not a numeric batch id** — resolved via `CourseBatch::where('batch_date', $request->batch_id)`).
**Success (200):** `{"student_count": <int>}` — count of `ACTIVE` enrollments for that course+batch.
**Errors:** 422 `{"message":"Course ID and Batch ID are required"}` if either missing (note: no `status` key, unlike most other endpoints in this module); 404 `{"message":"Batch not found"}` if `batch_id` string doesn't resolve to a `CourseBatch`.

### 33. `GET /api/v1/course-calender/get-user-by-roles` (throttle 10/min)
**Handler:** `getUserByRoles(Request $request)`
**Params:** `roles` (required) — accepts either a comma-separated string, a JSON-encoded array string (`?roles=[1,2,3]`), or a native query array; all normalized to an array of role IDs via `explode(',', implode(',', $roles))`.
**Success (200):** `{"user_details": [{"id","user_name","email","phone","role" (first role name only), "meeting_id","status"}, ...]}` — only `USER_APPROVED` users.
**Errors:** 422 `{"message":"Roles are required"}` if empty after normalization.

### 43. `GET /api/v1/course-calender/course-details/all` (Tier 1, **throttle 20/min** — different group from the rest of this section)
**Handler:** `getAllCourseDetails()`
**Success (200):** `{"course_details": [{"id","course_name","category_id","category_name","course_duration_days","evaluators":[{"id","evaluator_name"}], "instructors":[...], "mentors":[...], "created_at","updated_at"}, ...]}` — only `Course::STATUS_ACTIVE`, with `category`, `evaluators.user`, `instructors.user`, `mentors.user` eager-loaded; entries with a null `user` relation are filtered out of the respective sub-arrays.

### 35. `GET /api/v1/students/enrollments-v4` — confirmed alias of #21
**Handler:** `getStudentEnrollmentsV2(Request $request)` — the route binds to the **exact same method** as endpoint #21 (`GET /api/v1/students/enrollments-v2`), not a copy or a versioned variant. Same params, same success/error shapes, same side-effect profile as #21 in every respect — see #21 for the full contract. Confirmed by reading `Modules/AgenticSupportSystem/Routes/api.php`, where both routes list `'getStudentEnrollmentsV2'` as the controller method.

---

## 4. Other Team Automation (Tier 1, throttle 10/min)

Prefix `v1/`. Handler in `OtherTeamAutomationTrait` — a single bulk-export endpoint built for a different consuming team, deliberately not reusing any of the other formatters in this module.

### 34. `GET /api/v1/students/enrollments-v3`
**Handler:** `getStudentEnrollmentsV3(Request $request)`
**Params:** `page` (default 1, floored at 1), `limit` (default 200, clamped 1–500), `since` (optional, `Carbon`-parsed timestamp — filters `updated_at > since`).
**Success (200):** `{"status":"ok","total","page","limit","has_more","data":[...]}` — cursor-free offset pagination, ordered `id desc`. Each row (private `formatEnrollmentRowV3`): `enrollment_id` (the enrollment **code**, not numeric id — field name is misleading), `customer_phone`, `customer_country_code`, `customer_email`, `course_id`/`course_name`, `batch_id`/`batch_date` (uppercased `M-d-Y`), `enrollment_date`/`updated_at` (ISO-8601), `course_completion_pct` (int), `certificate_issued` (bool). Bootcamp rows add `bootcamp_id`/`bootcamp_name`; package/package-batch rows add `package_id`/`package_name`.
**Notes / bug:** `customer_country_code` is set to `$enrollment->student->country_id ?? '+91'` — this returns the student's numeric **`country_id` foreign key**, not a phone/dialing code (e.g. `12` instead of `+91`) whenever the student has a `country_id` set; the `'+91'` fallback only fires when `country_id` is null. A parity test should assert this exact (likely-unintended) behavior rather than a "correct" phone code.
**No auth/validation quirks beyond Tier 1** — no explicit error branch for missing/invalid `since` (an unparseable string throws inside `Carbon::parse`, surfacing as an uncaught 500).

---

## 5. Support Hub — Reads & Deactivate (Tier 1, throttle 10/min except noted)

Prefix `v1/support-hub/*` and `v1/course-calender`-adjacent. Handlers in `SupportHubTrait` (deactivate is in `AgenticSupportSystemTraitV2` but routed/grouped under `support-hub/*`). Several of these have unusually thorough docblocks in the source — summarized/quoted below rather than re-derived.

### 36. `GET /api/v1/support-hub/students/enrollments`
**Handler:** `getStudentEnrollmentsOverview(Request $request)`
**Params:** `email` (query, required).
**Success (200):** `{"status":"success","enrollments":[{"id","code","name","course_id","batch","batch_id","bootcamp_id","bootcamp_name","type" (label string),"enrollment_status"}, ...]}` — excludes package/package-batch types; built via `leftJoin` to `courses`/`course_batches` (soft-delete aware) rather than Eloquent relations, intentionally omitting `batch_assigned_by`/`tags` (reserved for the single-enrollment detail endpoint, #37) to keep the list query cheap.
**Errors:** 400 `"Email is required"`; 404 `"Student not found"`.

### 37. `GET /api/v1/support-hub/enrollments/details`
**Handler:** `getEnrollmentDetails(Request $request)`
**Params:** `enrollment_id` (query, required).
**Success (200):** `{"status":"success","enrollment":{"standalone":[<one entry, if Normal>], "bootcamps":[{"bootcamp_name","bootcamp_courses":[<one entry>]}] (if Bootcamp)}}` — excludes package/package-batch types entirely (query filters them out, so a package enrollment id here 404s as "not found", not as an empty/typed result). Single-enrollment payload (private `formatSingleEnrollmentForSupportHub`) mirrors the list-endpoint field derivation (refund eligibility, deactivation details) but for exactly one row.
**Errors:** 400 `{"status":"error","message":"Enrollment id is required"}`; 404 `{"status":"error","message":"Enrollment not found"}` (fires both for a truly-missing id and for a package/package-batch enrollment id, since those types are excluded by the query).

### 38. `GET /api/v1/support-hub/students/enrollment-list`
**Handler:** `getStudentEnrollmentListForSupportHub(Request $request)`
**Params:** `from_date`/`to_date` (optional, `Y-m-d`, inclusive range on `enrollments.created_at`; either alone is an open-ended bound), `course_id`/`batch_id` (optional FK filters, combinable), `page`/`limit` (limit default 15, capped 500).
**Success (200):** `{"status":"success","total","page","limit","has_more","next_page_url","prev_page_url","students":[{"student_id","student_name","email","contact_number","status" ("Active"/"Deactive"), "course_enrolled":{"standalone_course": <name>|null, "bootcamp": {"bootcamp_name","course_names":[...]}|null, "package": <name>|null}, "enrollment_date" (Y-m-d)}, ...]}`. Per the source docblock: this is a **student/enrollment report, not a plain enrollment list** — bootcamp enrollments (one row per course under one signup) collapse into a single list entry with a `course_names` array so one bootcamp doesn't consume multiple page slots; pagination is computed over **groups** (one custom SQL `group_key` expression, `COUNT()` + windowed `GROUP BY`) rather than raw rows, so page boundaries land on group edges, not individual enrollment rows.
**Errors:** 400 `{"status":"error","message":"from_date and to_date must be valid dates in Y-m-d format"}`; 400 `{"status":"error","message":"from_date must not be after to_date"}`.
**Notes:** Every matching row for the date range is fetched to build the SQL group-key aggregate before pagination is applied to it — an unfiltered/very-wide date range means a large one-time query, per the source comment.

### 39. `GET /api/v1/support-hub/students/by-course-batch`
**Handler:** `getStudentsByCourseAndBatchForSupportHub(Request $request)`
**Params:** all optional and combinable: `course_id`, `batch_id` (numeric FK, not batch_date), `enrollment_type` (one of `Normal`/`Bootcamp`/`Package`/`Package Batch`, else 400), `enrollment_status` (`Active`/`Deactive`, else 400), `page`/`limit` (default 15, cap 500).
**Success (200):** `{"status":"success","total","page","limit","has_more","next_page_url","prev_page_url","enrollments":[{"student_id","student_name","email","contact_number","student_status","enrollment_code","course_name","batch" (raw `batch_date`, **not** run through the batch-date normalizer used elsewhere),"enrollment_type" (label),"enrollment_status"}, ...]}` — response key is `enrollments` (a student can repeat if they have multiple matching enrollments), ordered by `students.full_name`.
**Errors:** 400 `{"status":"error","message":"enrollment_type must be one of: Normal, Bootcamp, Package, Package Batch"}`; 400 `{"status":"error","message":"enrollment_status must be one of: Active, Deactive"}`.

### 40. `GET /api/v1/support-hub/students/assignments-by-email`
**Handler:** `getAssignmentsDetailsForSupportHub(Request $request)`
**Params:** `email` (query, required).
**Success (200):** `{"assignments": [...]}` — same field set as V2 assignments (#22), via a Support-Hub-local copy of the formatter (`getAssignmentsForSupportHubV2`) that excludes package/package-batch enrollments.
**Errors:** 400 `"Email is required"`; 404 `"Student not found"`.

### 41. `GET /api/v1/support-hub/get-upcoming-batches-for-specific-course`
**Handler:** `getUpcomingBatchesForSpecificCourse(Request $request)`
**Params:** `course_name` (query, required, exact match against `courses.course_name`).
**Success (200):** `{"status":"success","total","batches":[{"id","name","start_date"}, ...]}` — batches returned by the external Course Calendar API for that course whose `batch_start_date` falls between "today" and `2040-12-31`, cross-referenced against local `CourseBatch` rows by `batch_date` (external batches with no local match are silently dropped via `->filter()`).
**Errors:** 422 `{"status":"error","message":"course name is required"}`; 404 `{"status":"error","message":"Course not found"}`; 502 `{"status":"error","message":"Failed to fetch batch details"}` if the external Course Calendar API call fails.
**External call:** `Http::withOptions(['verify'=>false])->withToken(config('services.course_calendar.portal_token'))->get(config('services.course_calendar.url') . '/batch-details', ...)` — TLS verification explicitly disabled for this call.

### 42. `POST /api/v1/support-hub/students/deactivate` — **write endpoint on Tier 1** (not Tier 2, despite mutating data)
**Handler:** `deactivateStudentsAgenticAPI(Request $request)` (in `AgenticSupportSystemTraitV2`)
**Params/validation:** `Validator::make(...)`: `email` required|email, `comment` required|string.
**Behavior:** Deletes all the student's Sanctum tokens (forced logout), sets `Student.status → PENDING`, sets **every** enrollment of that student to `Enrollment::PENDING` (not scoped to any particular enrollment), logs an `Activity` + a `DeactivatingComment` row per student id via private `addActivityLogsAndComments()` (`log_name = 'student_activation_and_deactivation'`), then synchronously calls `deactivateStudentInEdmingleAgentic()` for each of the student's `lms_id`s (in a loop — currently always 0 or 1 iteration since a student has a single `lms_id`).
**Success (200):** via `apiResponse([$data, $data2], 'Deactivated Successfully', statusCode: 200)` → `{"data": [<student-update row count>, <enrollment-update row count>], "message": "Deactivated Successfully", "status": "success"}` — **not** `apiResponse`'s usual single-value `data`; `data` here is a 2-element array of raw `update()` affected-row counts, not any student/enrollment representation.
**Errors:** 422 (from the `Validator`, standard shape per `_COMMON_CONVENTIONS.md`); 404 `{"status":"error","message":"Student not found"}`.
**Side effects:** `DeactivateStudentEdmingleBatches::dispatch(...)` queued job (`onQueue('default_medium')`) to remove the student from Edmingle-mapped batches; queued `Mail::to($email)->queue(new StatusDeactivated(...))` per affected student, with `enrollment_types`/`enrollment_names` context built from that student's enrollments; synchronous `Http::post()` to the Edmingle "remove student" endpoint (`config('app.edmingle_api_endpoint') . 'remove/organization/student/{lmsId}'`) per LMS id, with a Sentry warning capture (if bound) on Edmingle's specific "stale/invalid LMS id" error code `15003`.
**Notes:** The synchronous per-student Edmingle HTTP call inside a request handler (not queued) means this endpoint's latency and success/failure both depend on Edmingle availability, even though the primary DB-level deactivation already committed by that point — a partial-failure (DB deactivated, Edmingle not) still returns 200.

---

## 6. Enrollment Creation, Update & Registration (Tier 2, throttle 5/min)

Prefix `v1/`. Handlers in `AgenticSupportSystemTraitV2` unless noted. All require the **Tier 2** listing token.

### 44. `POST /api/v1/students/create-enrollment-v2`
**Handler:** `createEnrollmentV2(Request $request)` — `set_time_limit(0)` at entry (unbounded execution time).
**Validation:** `$request->validate([...])`: `email` required|email; `enrollment_type` required|string (must resolve to `course`/`bootcamp`/`bootcamp_additional`, else 400 `"Unsupported enrollment_type"`); `country_id` required|`exists:countries,id`; `phone` required|string|max:255 + a `Propaganistas\LaravelPhone` mobile-format rule scoped to the country resolved from `country_id`.
**Params (beyond validated):** `name` (optional, used for new-student creation), `course_id`/`course_ids` (array or scalar, required — 400 `"The course_id field is required."` if empty after filtering), `bootcamp_id`/`bootcamp_name` (for `bootcamp`/`bootcamp_additional` types), `batch_id` (optional), `ls_order_id` (optional — if a matching order id already has an enrollment, that enrollment is **updated** in place via `updateStudentCourseEnrollment()` instead of creating a new one), `shift_assignments` (`'true'` string to trigger `BatchsAssignmentsJob`).
**Behavior by `enrollment_type`:**
- `course`: auto-creates the `Student` (generated password, `status=ACTIVE`, `AGENTIC_USER_ID` as `created_by`) if none exists for that email, plus an `Activity` "Student Created" log and an `originalRegistrationDetails` snapshot row. Then, per `course_id`, checks for an exact course+batch duplicate (422 if found) and creates the enrollment via `createCourseEnrollmentAgentic()`; every course enrollment created this way always gets the "Refund Eligible" tag attached (`attachRefundEligibleTagAgentic`).
- `bootcamp`: same student auto-creation; resolves the bootcamp by id or `bootcamp_name`; if `course_id`(s) not supplied, fetches the bootcamp's full course list from the external LawSikho enrollment-form API (`config('services.lawsikho.url') . '/api/v1/enrollmentForm/getOfferBundle?id={bootcampId}'`) and enrolls in all of them; supplied course ids are validated against that external course list (400 if any doesn't belong to the bootcamp). Duplicate-bootcamp check: 422 `"Student is already enrolled in this bootcamp."` if the student already has *any* enrollment for that `bootcamp_id`.
- `bootcamp_additional`: student must already exist (400 if not) and must already be enrolled in the target bootcamp (400 if not); adds one or more additional courses to that existing bootcamp enrollment, tagging each with the `Additional` tag.
**Success (201):** `{"data":{"enrollment": <EnrollmentResource::make($enrollment->fresh())>}, "message":"Enrollment created successfully"|"Bootcamp additional course enrollment created successfully", "status":"success"}` — **this is the only read/write group in the module that wraps its success payload in `EnrollmentResource`** rather than a raw model/array.
**Errors:** 400 for missing course_id/bootcamp fields; 422 `"Course ID $id already exists for this student in this batch."` / `"Student is already enrolled in these courses."` / `"Student is already enrolled in this bootcamp."`; 400 if the external bootcamp-courses fetch fails and no `course_id` was supplied as a fallback.
**Side effects:** `Activity::create()` for student creation and for each enrollment creation; `SendStudentDataToExternalAPI::dispatch($student)` (queued, wrapped in try/catch so a dispatch failure doesn't fail the request); for `batch_status` values (an undocumented extra input consumed deep inside `createCourseEnrollmentAgentic`) `1`/`2`/`3`, triggers Edmingle batch assignment/creation and, when the batch's student count crosses 100–103, a queued `SendMailForStudentsCountInBatch` to `env('SUPPORT_MAIL')` addresses.

### 45. `POST /api/v1/students/assign-batch-v2`
**Handler:** `assignBatchV2(Request $request)` — **a commented-out, near-identical earlier version of this method (117 lines) sits directly above the live one in the source** (`AgenticSupportSystemTraitV2.php` ~L1786–1901) — dead code, not reachable, but present if grepping the file.
**Params:** hand-checked, no `$request->validate()`: `email` (required, 400 `"email is required"` — plain hand-rolled error, not `apiResponse`, matching the already-specced entry), `batch_id` (required, 400 `"batch_id is required"`), then either `enrollment_id` OR both `course_id`+`bootcamp_id` (400 if neither combination given) to resolve the target enrollment, `comment` (optional), `shift_batch` (string `'true'` to trigger shift-assignment job instead of a plain activity log), `refund_eligible` (boolean-ish).
**Behavior:** Branches on whether the resolved enrollment has a `package_id` (creates a new `PACKAGE_BATCH_ENROLLMENT` row, leaving the original package enrollment's `batch_assigning_eligibility` set to `NOT_ELIGIBLE`) vs. a regular/bootcamp enrollment (updates the same enrollment row in place with the new `batch_id`+generated `enrollment_code`). Duplicate-batch checks differ slightly per branch (package: any existing row for that course+batch+student; non-package: excludes `PENDING`-status rows). Refund-eligible tag attachment enforces the bootcamp's `refund_eligible_course` limit, erroring 422 if exceeded.
**Success (200):** `{"data": {"enrollment": <EnrollmentResource>, ["edmingle_failures": [...]]}, "message": "Batch assigned successfully"[.  Note: ...], "status":"success"}`.
**Errors:** 404 `"Student not found"`; 404 `"Batch not found or inactive"`; 404 `"Enrollment not found"`; 422 `"Package is not eligible for batch assignment"`; 422 duplicate-enrollment messages (two slightly different wordings for package vs. non-package); 422 refund-eligible-tag-limit message; on any uncaught exception inside the transaction, 422 with the raw exception message (`$e->getMessage()`) as `message` — **exception messages are leaked directly to the API caller** here.
**Side effects:** Edmingle student-assignment call (if a mapping exists) collected into `edmingle_failures` rather than failing the whole request; `countBatchStudents()` check → queued `SendMailForStudentsCountInBatch` at 100–103 students; queued `Mail::to($enrollment->student->email)->queue(new BatchAdded(...))` always sent on success; revenue-system bulk update via `bulkUpdateDateForRevenue()`.

### 46. `POST /api/v1/students/update-v2`
**Handler:** `updateStudentV2(Request $request)`
**Params:** hand-checked, no `$request->validate()`: `email` (required, 400 `"email is required"`), `lms_user_id` (required, 400 `"lms_user_id is required"`), `comment` (optional, used as the Activity description, default `"Student updated via Agentic API"`).
**Behavior:** Updates the `Student` row's `lms_id` column (**input field name `lms_user_id` maps to DB column `lms_id`** — confirms the already-specced note in `API_SPECIFICATIONS.md`).
**Success (200):** `{"data":{"student":{"id","email","lms_user_id"}}, "message":"Student updated successfully", "status":"success"}`.
**Errors:** 400 for missing fields (as above); 404 `{"status":"error","message":"Student not found"}`.
**Side effects:** `Activity::create()` — `log_name: 'Student Updated'`, `event: 'AP-LMS Integration'`, `causer_id: env('AGENTIC_USER_ID', 1)` — a fixed system actor id, not the real caller (no per-caller identity exists in this static-token auth scheme).

### 54. `POST /api/v1/students/create-bootcamp-additional-enrollment-by-course-name`
**Handler:** `createBootcampAdditionalEnrollmentByCourseName(Request $request)` — `set_time_limit(0)`.
**Validation:** `student_id` required|integer|`exists:students,id`; `bootcamp_name` required|string; `course_name` required_without `course_names` (nullable string); `course_names` required_without `course_name` (nullable array) — exactly the same additional-enrollment logic as endpoint #44's `bootcamp_additional` branch, but resolves by **`student_id`** (not email) and by **course name(s)** (not id(s)), matching bootcamp by exact `name` or `"{name} - {title}"` concatenation.
**Success (201):** `{"data":{"enrollment": <EnrollmentResource>}, "message":"Bootcamp additional course enrollment created successfully", "status":"success"}`.
**Errors:** thrown as `\RuntimeException($message, $httpCode)` inside private helpers and caught in the handler, re-emitted as `{"status":"error","message": ...}` at that code: 400 course/bootcamp-name missing, 404 course/bootcamp/enrollment-not-found variants, 422 duplicate-course-in-bootcamp.
**Side effects:** same `SendStudentDataToExternalAPI::dispatch($student)` pattern as #44.

### 55. `POST /api/v1/students/get-student-registration-details`
**Handler:** `getStudentRegistrationDetails(Request $request)` — despite the `get-` prefix and being a data-read, this is a **POST** route.
**Validation:** `id` required|`exists:students,id`; `bootcamp_name` required_if `course_name` is `null`; `course_name` required_if `bootcamp_name` is `null` (i.e., exactly one of the two is effectively expected, though Laravel's `required_if` here compares against the literal string `"null"`, not PHP `null` — verify this rule actually fires as intended; not confirmed against a live request).
**Behavior:** For `bootcamp_name`, resolves the bootcamp then looks up the enrollment for **hardcoded `course_id = 135`** (comment: "courese Id of 'Bootcamp 10 Writing Course'") within that bootcamp — an environment-specific magic number, not derived from any config. For `course_name`, looks up the plain course enrollment.
**Success (200):** `{"data": {registration_status, enrollment_created_date, student_logged_in ("Yes"/"No"), registered_student_id, registered_email_id, registered_phone_number (country phone_code + phone), registered_name, address, city, state, country, pin_code}, "message":"Student registration details fetched successfully", "status":"success"}`.
**Notes / bug:** The `registration_status` is computed as `"Registered"` vs `"Not Registered"` based on whether `StudentOriginalRegistrationDetails.updated_by`/`created_by` is `"self"`/empty — **but the `if`/`else` branches building `$response` for the two cases are byte-for-byte identical** (both build the exact same array with `registration_status` differing only by which branch set the string). Confirmed from source: the two branches produce the same fields with the same values except the `registration_status` string itself — i.e., every other field is unaffected by which branch fires, so this isn't a functional bug for the caller, just dead/duplicated code.
**Errors:** 404 `"Student not found"`, `"Bootcamp not found"`, `"Course not found"`, `"Enrollment not found"` — all with `"data": []` in the body.

---

## 7. Enrollment Status Management (Tier 2, throttle 5/min except #53)

### 47. `POST /api/v1/students/update-enrollment-status-v2`
**Handler:** `updateEnrollmentStatusV2(Request $request)` (in `SupportHubTrait`) — explicit source docblock: "Duplicate of `EnrollmentController::update()` adapted for static-token (no logged-in user) access", self-contained (its own `*Agentic`-suffixed Edmingle helpers).
**Validation:** `email` required|email; `enrollment_id` required|integer|`exists:enrollments,id`; `status` required, `Rule::in([Enrollment::PENDING, Enrollment::ACTIVE])`; `comment` required|max:200; `deactivation_reason` sometimes|string|max:100; `other_reason` required_if `deactivation_reason=others`|nullable|string|max:500; `refund_eligibility_retained`/`refund_eligibility_transferred` sometimes|boolean; `add_missed_assignments` sometimes|boolean.
**Business rules:** 422 `"Enrollment cannot be activated when the student is deactivated."` if activating while the student itself is inactive (matches the already-specced entry); 422 duplicate-active-enrollment-in-same-batch guard on activation; 422 `"Deactivation reason is required when deactivating an enrollment."`; 422 `"Please provide the other reason text when selecting \"Others\" as the deactivation reason."`; when deactivating for `course_pause` on a refund-eligible enrollment, exactly one of `refund_eligibility_retained`/`refund_eligibility_transferred` must be true (422 if both or neither).
**Success (200):** `{"data":{"enrollment": <EnrollmentResource::make($enrollment->fresh())>}, "message":"Enrollment updated successfully", "status":"success"}`.
**Errors:** 404 `"Student not found"` / `"Enrollment not found"`; 400 `{"status":"error","message":"Student is not added or removed at Edmingle"}` if the Edmingle sync call itself reports an error.
**Side effects:** `activity()->on($enrollment)->by($actionBy)...->log(...)` (Spatie helper form, not raw `Activity::create`) with event `'Enrollment Activated'`/`'Enrollment Deactivated'`; on deactivation, a synchronous `Http::post(config('app.ONBOARDING_API_BASE_URL') . '/student/batch/assign', ['order_id'=>null-batch...])` call with **no response handling** ("Handle the response and errors..." — literal TODO comment in source, response outcome is never checked); queued `Mail::to($enrollment->student->email)->queue(new EnrollmentUpdated(...))`; Edmingle add/remove-student-from-batch call (via the trait's own `assignStudentToEdmingleBatchAgentic`/`removeStudentToEdmingleBatchAgentic`); optional queued `HandleMissedAssignments` job if `add_missed_assignments` and reactivating; queued `SyncEnrollmentWithCourseCalendarJob` (event name `enrollment_active`/`enrollment_deactive`) if the enrollment has a `batch_id`.

### 48. `POST /api/v1/students/resume-enrollment-v2`
**Handler:** `resumeEnrollmentV2(Request $request)` (in `SupportHubTrait`) — "Duplicate of `EnrollmentTrait::resume()`", fully self-contained via its own `*Agentic` helper copies.
**Validation:** `email` required|email; `enrollment_id` required|integer|`exists:enrollments,id`. A **second, conditional** validation block fires only if the request also includes `batch_id` or `batch_title`: `batch_id` required|`exists:course_batches,id`|integer, `comment` required|string, `refund_eligible`/`refund_eligibility_foregone` nullable|boolean.
**Business rule:** 422 `{"status":"error","message":"Enrollment is not paused."}` unless the enrollment's status is `PAUSED` or `RESUME_REQUESTED`.
**Two response shapes for the same endpoint depending on input, confirmed from source:**
- **No `batch_id`/`batch_title` given** (plain resume): reactivates the same enrollment row in place (`status → ACTIVE`), creates an `EnrollmentPauseLogNew` row, re-syncs Edmingle if a batch is already assigned, optionally dispatches `ResumeEnrollmentHandleMissedAssignments`. **Success (200): `{"data": [], "message": "Enrollment resumed successfully.", "status": "success"}`** — `data` is always an empty array here.
- **`batch_id`/`batch_title` given** (resume-with-migration): creates a **new** enrollment row on the target batch (optionally creating the batch itself first if `status == 3`, via `createNewBatchAgentic`), deactivates the old one (`status → PENDING`, `deactivation_status → BATCH_MIGRATION_DEACTIVATION`), replicates the full batch-migration machinery (refund-eligibility carry-over, `EnrollmentPauseLogNew` with `paused_reason: 'Resumed with Batch Migration'`, `'Batch Migrated'` tag, Edmingle remove-then-assign-or-create). **Success (200): `{"data": <raw Enrollment model, NOT wrapped in EnrollmentResource>, "message": "Enrollment resumed and migrated to new batch successfully", "status": "success"}`.**
**Notes / inconsistency:** The two success shapes for this one endpoint diverge sharply — `data: []` vs. `data: <raw model>` — and neither uses `EnrollmentResource` (unlike #44/#45/#47's `EnrollmentResource`-wrapped responses). A parity test must branch on whether batch-migration params were supplied, not just assert one fixed response shape for this route.
**Errors:** 404 `"Student not found"`/`"Enrollment not found"`; 422 "Enrollment is not paused."; 422 duplicate-batch-enrollment message; in the migration branch, any exception is caught and returned as 422 with the raw `$e->getMessage()` (same leak-the-exception pattern as #45).
**Side effects:** queued `SyncEnrollmentWithCourseCalendarJob` in both branches; synchronous Edmingle add/remove/create-batch calls in the migration branch.

### 53. `GET /api/v1/support-hub/enrollments/pause-requested` (Tier 2, throttle 5/min)
**Handler:** `getPauseRequestedEnrollmentsForSupportHub(Request $request)`
**Params:** `from_date`/`to_date` (optional `Y-m-d`, filters on `refund_eligible_pause_request_time`), `page`/`limit` (default 15, cap 500).
**Success (200):** `{"status":"success","total","page","limit","has_more","next_page_url","prev_page_url","pause_requested_enrollments":[{"enrollment_id","enrollment_code","student_id","student_name","email","course_id","course_name","batch_id","batch" (normalized), "bootcamp": {"bootcamp_id","bootcamp_name"}|null, "pause_requested_at"}, ...]}`, ordered newest-request-first.
**Notes (per source docblock):** Filters strictly on `enrollments.status == PAUSE_REQUESTED` as "the authoritative is-this-still-pending signal" — explicitly **not** `enrollment_pause_log_new`, because "rejection only sets a `rejected` flag on the existing log row rather than changing its status, and approval doesn't touch the log table at all." Important for a parity test targeting this endpoint: don't infer pending-ness from the log table.
**Errors:** same from_date/to_date validation errors as #38.

---

## 8. Listing (Tier 2, throttle 5/min)

Prefix `v1/listing/*`. Handlers in `AgenticSupportSystemTraitV2`. No validation on any of the four — all params are optional search filters, all hand-rolled `response()->json()`.

### 49. `GET /api/v1/listing/batches-v2`
**Handler:** `getBatchesListingV2(Request $request)` — `search` (optional, `LIKE` on `batch_date`). Returns **all** batches regardless of status (the `->where('status', ACTIVE)` line is present but commented out in source) → `{"batches":[{"id","batch_name"}, ...]}`.

### 50. `GET /api/v1/listing/courses-v2`
**Handler:** `getCoursesListingV2(Request $request)` — `search` (optional, `LIKE` on `course_name`). Filters `Course::STATUS_ACTIVE` only (unlike #49's batches, which has no such filter) → `{"courses":[{"id","course_name"}, ...]}`.

### 51. `GET /api/v1/listing/bootcamps-v2`
**Handler:** `getBootcampsListingV2(Request $request)` — `search` (optional, matched against `name`, `title`, or the concatenated `"{name} - {title}"`). No status filter → `{"bootcamps":[{"id","bootcamp_name" (concatenated if both name/title present, else whichever exists)}, ...]}`.

### 52. `GET /api/v1/listing/countries-v2`
**Handler:** `getCountriesListingV2(Request $request)` — `search` (optional, matched against `name`/`common_name`/`short`/`phone_code`/`id`, all via `LIKE '%...%'` including the numeric `id`). Ordered by `name` → `{"countries":[{"id","name","common_name","short","phone_code"}, ...]}`.

---

## 9. Batch/Bootcamp Migration (Tier 2, throttle 5/min)

Prefix `v1/`. Handlers in `BatchBootcampMigrationTrait`. All three migration endpoints (#56/#57/#59) follow the same pattern: validate → resolve student/enrollment/batch → pre-fetch Edmingle mappings before opening a DB transaction → create a **new** enrollment row + deactivate the old one inside the transaction → post-commit queued jobs for Edmingle/revenue sync. All wrap their top-level logic in `try/catch`, using the global `apiResponse()` helper for every response (unlike most of the rest of this module).

### 56. `POST /api/v1/students/migrate-batch-v2`
**Handler:** `migrateBatchV2(Request $request)`
**Validation:** `email` required|email; `enrollment_code` required|string; `new_batch_name` required|string (this is a **`batch_date` string**, resolved via `CourseBatch::where('batch_date', ...)` — the batch must already exist, unlike v3 below); `comment` required|string; `shift_batch`/`shift_assignment`/`refund_eligible` nullable|boolean.
**Success:** `apiResponse('', 'Batch migrated successfully')` → `{"data":"", "message":"Batch migrated successfully", "status":"success"}`.
**Errors:** `apiResponse('', <message>, 'error', <code>)`: 404 `"Student not found"`; 404 `"Active enrollment not found for code: {code}"` (excludes `PENDING`-status enrollments — a paused/deactivated enrollment code 404s here); 404 `"Batch not found: {new_batch_name}"`; 422 `"Student is already enrolled in this batch for this course"`; 422 refund-eligible-tag-limit message; 400 `"Batch already exists in Database"` on a MySQL duplicate-key error (code 1062); 500 `"An unexpected database error occurred"` on any other `QueryException`; 422 with the raw exception message for any other `\Exception`.
**Side effects:** creates the new enrollment, deactivates the old (`status → PENDING`, `deactivation_status → BATCH_MIGRATION_DEACTIVATION`), attaches `'Batch Migrated'` tag, `DeactivatingComment` on the old enrollment, `Activity`/refund-eligibility handling identical in spirit to #45; **all HTTP/Edmingle work is deferred to a single post-commit queued job** `AgenticBatchMigrationSyncJob::dispatch(...)->onQueue('default_medium')` (revenue update + Edmingle remove + Edmingle assign, all inside the job — not synchronous in the request); two `SyncEnrollmentWithCourseCalendarJob` dispatches (`'batch_migrate'` for the new enrollment, `'batch_migrate_old'` for the old); optional `BatchsAssignmentsJob`/assignment-shift dispatch if `shift_batch`/`shift_assignment` are `1`; queued `SendMailForStudentsCountInBatch` at the 100–103 threshold.

### 57. `POST /api/v1/students/migrate-batch-v3`
**Handler:** `migrateBatchV3(Request $request)` — `set_time_limit(0)`; heavily `Log::info`-instrumented (`[V3:stepN]` tags) for observability.
**Validation:** `email` required|email; `enrollment_code` required|string; `new_batch_name` required|string; `comment` required|string; `status` required|integer|`in:1,2` (**required, unlike v2** — controls Edmingle behavior, see below); `shift_batch`/`shift_assignment`/`refund_eligible` nullable|boolean; `submission_last_date`/`start_date`/`date_of_compilation` nullable|date; `tutor_id`/`tutor_name`/`edmingle_batch_name` nullable|string.
**Key difference from v2:** `new_batch_name` does **not** need to already exist — `CourseBatch::firstOrCreate(['batch_date' => $newBatchName], [...])` creates it on the fly if missing, seeded from `start_date`/`date_of_compilation`. `tutor_id` is auto-resolved from `tutor_name` via an `EdmingleBatch` lookup if not directly supplied.
**`status` param semantics (Edmingle side-effect selector):** `status=1` with an existing Edmingle-batch mapping → assign student to that existing Edmingle batch; `status=1` with no mapping, or `status=2` unconditionally → create a new Edmingle batch (via `createEdmingleBatch()`) then map it.
**Success:** `apiResponse('', 'Batch migrated successfully')` — same shape as v2.
**Errors:** same student/enrollment/duplicate-batch 404/422 pattern as v2 (message wording for the duplicate case differs slightly: `"This Student is already enrolled with same batch for this course which enrollment is active, Please try with another batch"`); mid-transaction Edmingle-create failure returns 409 `{"status":"error","message":"Batch is not added at edmingle, Please try again"}` directly (not queued/deferred — this is the one migration endpoint where an Edmingle failure can produce a non-2xx **during** the request, though this specific 409 path is only reached for the "create batch" step, not the "assign to existing batch" step, which instead accumulates into `edmingle_failures`).
**Side effects:** same new/old-enrollment pattern as v2, but **all Edmingle calls in this version are synchronous, in-request** (`removeStudentToEdmingleBatch`, `assignStudentToEdmingleBatch`, `createEdmingleBatch`) rather than deferred to a queued job — failures are collected into an `$edmingleFailures` array and, if non-empty, trigger a queued `BatchMigrationSummaryJob` to `techteam@lawsikho.in` rather than failing the whole request (except the 409 case above); `updateDateForRevenue()` called synchronously post-commit; two `SyncEnrollmentWithCourseCalendarJob` dispatches, same as v2.

### 58. `POST /api/v1/batch/check-edmingle-mapping`
**Handler:** `checkEdmingleBatchMapping(Request $request)` — a pure read (despite being POST and grouped with the migration writes; it's the only side-effect-free endpoint in this section).
**Validation:** `course_name` required|string; `batch_name` required|string.
**Success (200):** `apiResponse(['edmingle_batch_exists' => bool, 'edmingle_batch_id' => <id>|null], 'Edmingle batch mapping found'|'Edmingle batch mapping not found')`.
**Errors:** `apiResponse('', 'Course not found: {name}', 'error', 404)`; `apiResponse('', 'Batch not found: {name}', 'error', 404)`; 422 with raw exception message on any other failure.

### 59. `POST /api/v1/students/migrate-bootcamp-v2`
**Handler:** `migrateBootcampV2(Request $request)`
**Validation:** `student_email` required|email; `source_bootcamp_name` required|string; `target_bootcamp_name` required|string (both names matched against `name` or `"{name} - {title}"`).
**Behavior:** Deactivates **all** of the student's active enrollments under the source bootcamp and, if the student has no existing enrollments in the target bootcamp, auto-enrolls them into every course of the target bootcamp (fetched from the same external LawSikho `getOfferBundle` API used by #44's bootcamp branch) before deactivating the source-bootcamp rows; attaches a `'Bootcamp Migrated'` tag to every target-bootcamp enrollment (existing or newly created).
**Success:** `apiResponse('', 'Bootcamp migrated successfully')`.
**Errors:** 404 `"Student not found"`; 404 `"Source bootcamp not found: {name}"` / `"Target bootcamp not found: {name}"`; 404 `"No active enrollments found in source bootcamp"`; 422 `"Could not fetch courses for target bootcamp: {name}"` (external API failure) / `"No courses found in target bootcamp: {name}"` / `"Failed to create enrollments in target bootcamp"`; 422 with raw exception message otherwise.
**Notes:** Unlike #56/#57, this endpoint does **not** touch Edmingle at all (no batch-level concept for a bootcamp-to-bootcamp move) — no Edmingle side effects, no `SyncEnrollmentWithCourseCalendarJob` dispatch.

---

## 10. Student Search by Name (Tier 1, throttle 5/min)

### 60. `GET /api/v1/students/details-by-name`
**Handler:** `getStudentsDetailsFromName(Request $request)`
**Validation:** `$request->validate(['name' => 'required|string'])`.
**Success (200):** `{"status": true, "message": "Students fetched successfully", "data": [{"id","full_name","email","phone","country_code" (from countryRelation.phone_code, may be null), "address","city","state","country","pincode"}, ...]}` — `LIKE '%name%'` match against `full_name`, `Student::ACTIVE` only.
**Notes:** `status` is a **boolean `true`**, not the string `"success"` used almost everywhere else in this module — a caller branching on `status === "success"` would misread this endpoint's success case. No 404 for zero matches — an empty `data: []` array is still a 200.

---

## 11. Sanctum Token Validation (Tier 1, no throttle limit)

### 61. `POST /api/v1/external/sanctum/validate-user`
**Handler:** `sanctumTokenValidation(Request $request)` (in `AgenticSupportSystemTraitV2`)
**Auth:** Tier 1 static token — but this **route group has no `throttle:N,1` middleware at all** (`Route::middleware(['json.response', 'agentic.static.token'])`, no throttle entry), unlike every other group in this module.
**Validation:** `$request->validate(['token' => 'required|string'])`.
**Behavior:** Looks up `token` as a **Laravel Sanctum personal access token** (`PersonalAccessToken::findToken($request->token)`) — i.e., this validates a *different* kind of bearer token (a real per-user Sanctum token issued elsewhere in the app, e.g. to an admin/student session) against this static-token-gated endpoint, letting an external agentic caller confirm a Sanctum token's validity/identity without itself holding admin credentials.
**Success (200):** `{"status":"success","message":"User verified successfully","data":{"user_id","username" (name ?? full_name),"email","role" (first role name only)}}`.
**Errors:** 401 `{"status":"error","message":"Invalid or expired token"}` if the token doesn't resolve to a `PersonalAccessToken` or its `tokenable` relation is null.

---

## Cross-cutting notes for parity testing

- **Route-count mismatch:** the module has 61 routes, not "~41" — confirm any parity harness enumerates all 61, not a partial list.
- **Confirmed alias:** `GET /api/v1/students/enrollments-v4` (#35) routes to the exact same `getStudentEnrollmentsV2` method as `GET /api/v1/students/enrollments-v2` (#21) — byte-identical behavior, not just similar.
- **`AGENTIC_SUPPORT_SYSTEM_LISTING_TOKEN` has a non-empty hardcoded fallback** (`Kp7rX2Yg4b9M8cTQW0sJz5dN1vLhA6kF3eUqDtyV`) if the env var is unset, unlike the Tier 1 token which 500s when unset — a parity/security test should check whether this fallback is still live in the target environment.
- **Response envelope is not consistent even within this one module:** raw hand-rolled `response()->json()` (majority), the global `apiResponse()` helper (all of §9's migration endpoints + the deactivate endpoint in §5), `EnrollmentResource`-wrapped payloads (only #44/#45/#47, and the migration branch of #48 explicitly does **not** wrap), and one endpoint (#60) using `status: true` (boolean) instead of the string `"success"` used everywhere else.
- **Exception messages leaked to callers:** `assignBatchV2` (#45), `resumeEnrollmentV2`'s migration branch (#48), and all four migration endpoints (§9) return the raw PHP exception message as the API `message` field on unhandled failure — useful for debugging but not a stable, sanitized contract; a parity test should not assert exact wording on these paths without also checking the underlying trigger condition.
- **Synchronous vs. queued external calls vary per endpoint, not just per "is this a write":** `migrateBatchV2` defers all Edmingle/revenue work to one post-commit job; `migrateBatchV3` and `assignBatchV2` make the same kind of Edmingle calls synchronously, in-request, and surface failures via an `edmingle_failures` array in the success response rather than deferring — a parity harness measuring latency or asserting "no external call happens during this request" needs to check per-endpoint, not assume module-wide consistency.

## Confidence / verification caveats

- Internal helper machinery shared across the migration/refund-eligibility/Edmingle-sync code paths (particularly the ~2500 remaining lines of private helpers in `SupportHubTrait` after the public endpoints, and the private helpers at the tail of `BatchBootcampMigrationTrait`) was read structurally (method signatures, call sites, docblocks) but not transcribed line-by-line into this document — the endpoint-level contracts above (validation, response shape, error codes, named side effects) are traced from actual source, but extremely deep edge cases inside those private helpers (e.g. every branch of `attachRefundEligibleTagForResume`/`updateRefundEligibleTagActivityLogForResume`) are not individually enumerated. Verify directly against source if a specific refund-eligibility edge case needs bit-for-bit parity.
- The exact rendered body of a bare `abort(401/500, $message)` from the two auth middlewares was not confirmed by a live request in this pass (inferred from `_COMMON_CONVENTIONS.md`'s documented `Handler::render()` behavior for manually-thrown HTTP exceptions) — verify directly if a test asserts the exact JSON shape of an auth failure.
- `getStudentRegistrationDetails`'s `required_if:bootcamp_name,null` / `required_if:course_name,null` validation rules compare against the literal string `"null"` per Laravel's `required_if` semantics when the referenced field is absent vs. explicitly the JSON value `null` — the practical effect (whether omitting both fields, or passing one as literal null, triggers the rule) was not tested live; verify directly if this endpoint's validation-failure behavior matters for a test.
