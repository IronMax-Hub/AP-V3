# Student Module API Documentation

The `Student` module is the **admin/staff-facing** CRUD, search, activation, and reporting surface for student records (`Modules/Student/Entities/Student`) — creating/editing students as an admin, activating/deactivating cohorts, exporting rosters, and drilling into a given student's enrollments/assignments/activity log. It is distinct from `StudentProfile` (the student's own self-service profile endpoints, `auth:student`) and from `StudentDashboard`/`StudentMyCourses` (the student-facing course/engagement surface).

**Module-wide auth:** every route except one is `auth:sanctum` + `json.response` (admin/staff token), prefixed `/api/v1/...`. The one exception — `POST /v1/students/get-reg-code` — sits in its own route group with **only** `json.response`, i.e. **no authentication at all**; called out explicitly below.

See [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for the app-wide response envelope styles, standard error shapes, and pagination conventions referenced below instead of being repeated per endpoint.

`StudentController` (`Modules/Student/Http/Controllers/StudentController.php`) directly implements only `index`, `show`, `store`, `update`, `destroy`. **Every other routed method's real body lives in `StudentTrait`** (`Modules/Student/Http/Traits/StudentTrait.php`, ~2400 lines), pulled in via `use StudentTrait, ActivityLog;` — check that file, not the controller, for anything not listed as `index`/`show`/`store`/`update`/`destroy` below. `StudentTrait` itself pulls in `App\Traits\ActivationAndDeactivationProcess` (shared with the `User` module — same activate/deactivate activity-log-and-comment helper) and `Modules\ProjectManagement\Http\Traits\kanboardTrait` (deprecated-module integration, not exercised by any routed endpoint here).

## Structural note: a third pagination style, on top of the two in the common conventions doc

`GET /v1/students/{student_id}/activity` uses `App\Http\Traits\ActivityLog::logOfStudent()`, which is **not** the custom base64-`cursor` scheme used by `index()`/`showPackageEnrollments()`/etc. in this same module. It uses Laravel's built-in `Activity::query()->paginate($rows, $columns, 'cursor')` — a standard `LengthAwarePaginator`, with the page-number query parameter simply *renamed* to `cursor` (so `?cursor=2` means "page 2", not an opaque token). Response shape: `{"data":[...ActivityResource...], "meta":{"next_page_url","prev_page_url","range":{"from","to","total"}}}`. Do not confuse this `cursor` (a plain integer page number as a string) with the base64-JSON `cursor` object expected by every other cursor-paginated endpoint in this module — they share a query-param name but have incompatible formats.

---

## Profile / detail read endpoints

### `GET /v1/students/profile/{student}` (route name `students.profile.show`, trait `showProfile`)
- **Auth:** `auth:sanctum`. Route-model-bound `{student}` — a non-existent id 404s via the standard `ModelNotFoundException` shape (see common conventions).
- **Success response:** global `apiResponse(['profile' => StudentResource::make($student)])`.
- `StudentResource` fields: raw-merged `id`,`full_name`,`email`,`phone`,`date_of_birth`,`father_name`,`address`,`state`,`country`,`gender`,`city`,`pin_code`,`lms_id`, plus `country_code` (`countryRelation->phone_code`), `linkedin_link` (aliased from `linked_in_link`), `cv` (aliased from `cv_title`), `documents` (aliased from `id_image`), `image`.

### `GET /v1/students/enrollment-form-data/{student}` (`showEnrollmentFormData`)
- **Success response:** `apiResponse(['enrollment_form_data' => [...]])` — an array of `{question, answer}` pairs assembled from `EnrollmentQuestionAnswer` rows plus a synthesized "How did you come to know about Lawsikho?" entry (only included if the student answered at least one `KnowAboutLawsikhoQuestion`). If a question referenced by an answer row no longer exists, that answer is silently skipped (`continue`), not erred.

### `GET /v1/students/enrollments/{student}` (`showEnrollments`)
- **Success response:** `apiResponse(['enrollments' => StudentEnrollmentShowResource::collection(...), 'packages' => [...], 'bootcamps' => [...], 'student' => {id,name,email}])`. `enrollments` here is the student's direct (non-package, non-bootcamp) course enrollments only — package/bootcamp enrollments are separately summarized in the `packages`/`bootcamps` arrays (name + assign date only, not full enrollment detail).
- `StudentEnrollmentShowResource`: raw-merged `id`,`enrollment_code`,`created_at`,`current_percent`,`completed`,`certified_datetime`,`batch_assigning_eligibility`,`total_exercises`, plus `bootcamp_name`,`status`,`course` (nested `{id,course_name,image}` — falls back to a hardcoded Unsplash placeholder URL if `image_path` is empty), `package`/`batch` (nested or null), `student` (`{full_name}` only), and four computed exercise-count fields (`total_exercise`, `written_done_by_student`, `subjective_done_by_student`, `written_out_of`, `subjective_out_of`) that synchronously call into `CourseCompletionMasterController` methods per row — **N+1 risk** on a list with many enrollments.

### `GET /v1/students/enrollments/{enrollment}/assignments` (`showStudentEnrollmentAssignments`)
- Query: `rows` (default 15), `cursor` (base64-JSON, see common conventions), `search` (optional — matches against `assignment.assignment_code` LIKE or `assignment.topic.title` LIKE).
- **Success response:** `StudentEnrollmentAssignmentResource::collection(...)->additional(['meta' => {course,package,batch,bootcamp,total_assignments,total,total_submitted,total_results,range}])`. `total_assignments` and `total` are computed by the **same** count query (`showStudentEnrollmentAssignmentsCount`) — always equal, one is not a distinct metric from the other despite the different key names.

### `GET /v1/students/package/{package}/enrollments/{student}` (`showPackageEnrollments`)
- Query: `rows` (default 15), `cursor`, `with_batch` (`1` filters to enrollments with a `batch_id`; `0` or omitted filters to enrollments *without* one — there is no "either" option).
- **Success response:** `StudentEnrollmentShowResource::collection(...)->additional(['meta' => {package,student,with_batch,without_batch,total,range}])`. `with_batch`/`without_batch`/`total` in `meta` are **unfiltered** counts of the whole package regardless of the request's own `with_batch` query param (they always report both counts), while the returned `data` rows **are** filtered by it.

### `GET /v1/students/bootcamp/{bootcamp}/enrollments/{student}` (`showBootcampEnrollments`)
- Query: `rows` (default 15), `cursor`.
- **Success response:** `StudentEnrollmentShowResource::collection(...)->additional(['meta' => {bootcamp,student,completed,'not completed',total,range}])`. Note the literal space in the meta key **`'not completed'`** (not `not_completed`) — must be accessed with that exact key.

---

## Listing, search & lookup

### `GET /v1/students` (`apiResource`, `index`)
- Uses `apiResource('students', 'StudentController')` — this is the only one of the 5 apiResource actions that's a `GET` on the collection root; despite the name, the actual heavy filtering happens via the separate `POST /v1/students/search/index` route below (same controller method, `index()` — `Route::apiResource`'s own `GET /students` also routes here with an empty `data` filter).
- **Request:** `Illuminate\Support\Facades\Validator` (no FormRequest) validates an optional `data` array of filter clauses: each entry optionally has `question_id` (`exists:enrollment_questions,id`), `question_operator` (`in:and,or`), `options` (array of strings) — all `required_with:data` (i.e., only required if the top-level `data` key is present at all, not per-entry). Query: `rows` (default 15), `cursor`.
- **Success response:** `StudentIndexResource::collection(...)->additional(['meta' => {total,active_student,deactive_student,range}])`.
- `StudentIndexResource`: raw-merged `full_name`,`status`,`phone`,`email`,`id`,`reg_code`, plus `country_code`, `last_login` (formatted or `null`), `enrollment_form_filled` (`'Y'`/`'N'` string, not boolean), `courses`/`bootcamp`/`packages`/`batches` (derived groupings over the student's enrollments), `tags` (`TagResource::collection`), `country_id` (nested object, confusingly named — it's `{id,name,phone_code}` of the country, not a raw FK int), `father_name`,`gender`,`lms_id`,`date_of_birth`,`linked_in_link`.

### `POST /v1/students/search/index` (route name `students.filters.index`, `index`)
Same method/validation/response as `GET /v1/students` above — a `POST` alias so a complex `data` filter array can be sent in the body instead of as a query string. Documented once; behavior is identical.

### `GET /v1/search/students` (`search`)
- **Success response:** `SearchStudentResource::collection(...)->additional(['meta' => ['total' => ...]])`. `SearchStudentResource` returns only `{id, full_name}` — the minimal shape for typeahead/autocomplete use.

### `GET /search/custom/students` (`searchCustom`)
- **Success response:** `StudentCustomSearchResource::collection(...)` — **no `meta`/`total` at all**, just a bare `{"data":[...]}`. Each item: all raw fields except `full_name`/`reg_code` (excluded) plus `name` (=`full_name`), `email`, `phone`, `pattern` (`"{full_name}/{reg_code}"`).

### `GET /search/specific-students` (`searchStudentsWithArray`)
- **Success response:** global `apiResponse($this->studentRepo->searchStudentsWithArray())` — raw repository output, not resource-wrapped.

### `GET /search/city` (`searchCity`)
- **Success response:** `SearchCityResource::collection(...)->additional(['meta' => ['total' => ...]])` — `{id, city}` only.

### `POST /v1/students/count` (route name `students.count`, `getStudentCounts`)
- Same `data` filter validation as `index()`.
- **Success response:** `apiResponse(['active_student' => N, 'deactive_student' => N], 'Successfull', 200)` — **note the literal typo `'Successfull'`** (double-l), preserve exactly.

---

## Admin CRUD (`apiResource('students', 'StudentController')`)

### `POST /v1/students` (`store`)
- **Request body** (`StoreStudentRequest`): `country_id` required `exists:countries,id`; `full_name` required max:255; `email` required, `unique:students,email`; `phone` required, `Phone::countryField('_phoneIso')->mobile()` (country inferred server-side from `country_id` via `prepareForValidation()`); `password` nullable, `confirmed`, `Password::defaults()` — **if omitted**, `StudentTrait::generatePassword()` generates an 8-char random password, hashes it, and emails the plaintext to the student via `StudentPasswordGeneration` mail (queued); `status` required int, one of `Student::PENDING|ACTIVE|DISABLED`; `kanboard_id`/`forum_id`/`forum_pass`/`forum_access_token`/`forum_token_time` all nullable (legacy fields tied to the deprecated Forum/kanboard integration — accepted and stored but not otherwise exercised by any live endpoint in this module); `tags` optional array of `{key: int, value: string}` (`key == 0` creates a new `Tag`, otherwise attaches an existing tag by id via `attachTags()`).
- **Success response:** `apiResponse(['student' => StudentResource::make($student->fresh())], 'Student created successfully', statusCode: 201)`.
- **Side effects:** wrapped in `DB::transaction()`; `reg_code` generated post-insert as `STU{Ymd}/{id}` (so it depends on the student's own auto-increment id, requiring the two-step create-then-update); `spatie/laravel-activitylog` "Student Created" activity; dispatches `SendStudentDataToExternalAPI` job (wrapped in try/catch — a dispatch failure is logged but does **not** fail the request, so a 201 here does not guarantee the external sync job was ever queued).

### `PUT`/`PATCH /v1/students/{student}` (`update`)
- **Request body** (`UpdateStudentRequest`) — **much smaller than `Store`**: only `linked_in_link` (nullable, max:255), `date_of_birth` (nullable, date), `father_name` (nullable, max:255), `gender` (nullable, string), `lms_id` (nullable, int), `tags` (same shape as store), `remove_tags` (nullable boolean). **`email`, `phone`, and `status` are not accepted here at all** — email goes through the dedicated `PUT /students/{student}/email/update` below; there is no dedicated status-change endpoint in this module (see `activate`/`deactivate` below, which only support bulk operation, not a single-student direct status write via this route).
- **Error response:** `apiResponse([], 'Student Not Found', 'error', 404)` if the `$id` doesn't resolve — a **hand-rolled 404**, not route-model-binding (the route parameter here is a raw `$id`, not a bound `Student $student`, unlike `store`/`show`).
- **Success response:** `apiResponse(['student' => StudentResource::make($student->fresh())], 'Student updated successfully')`.
- **Side effects:** activity log capturing old vs. new for the 5 updatable fields, referencing `$request->comment` in the log description even though `comment` is **not a validated field** on `UpdateStudentRequest` — an absent `comment` simply renders as an empty string in the log text, not a validation error. `if ($request->has('remove_tags'))` **detaches all tags unconditionally** regardless of the truthiness of the value sent — merely including the key (even `remove_tags: false`) clears every tag.

### `DELETE /v1/students/{id}` (`destroy`)
- Same hand-rolled 404 pattern as `update` (raw `$id`, not model-bound).
- **Success response:** `apiResponse([], 'Student deleted successfully')`.
- **Side effects:** activity log ("Student Deleted"), `$student->tags()->sync([])` (detach all pivot rows) before `studentRepo->delete($id)` — confirm with the repository whether this is a soft or hard delete before asserting recovery behavior.

### `GET /v1/students/{student}` (`show`)
- Route-model-bound `{student}` (standard 404 on miss, per common conventions).
- **Success response:** `apiResponse(['student' => StudentResource::make($student), 'enrollment_form_data' => [...], 'enrollments' => EnrollmentResource::collection(...), 'packages' => [...], 'bootcamps' => [...]])`.

---

## Activation / deactivation (bulk, admin-only)

### `POST /v1/students/activate` (route name `students.active`, `activeStudent`)
- **Request body:** `student_ids` required array, each `exists:students,id`; `comment` required string.
- **Success response:** `apiResponse($data, 'Activated Successfully', statusCode: 200)` — `$data` is the raw return of `studentRepo->activate(...)`, not resource-wrapped.
- **Side effects (heavy, several synchronous):** per-student activity log + `DeactivatingComment` row via `ActivationAndDeactivationProcess::addActivityLogsAndComments()` (shared with `User` module's `changeStatus`); **synchronous** Edmingle "unarchive" HTTP call per student with a non-null `lms_id` (`activateStudentInEdmingle()` — this loop runs inline in the request, so activating N students with LMS ids means N sequential outbound HTTP calls before the response returns); queues `ActivateStudentEdmingleBatches` job (`default_medium` queue) separately for batch-side Edmingle mapping; sends a `StatusActivated` mail per affected student (queued), with the mail payload's `enrollment_types`/`enrollment_names` built from the student's enrollments (course/bootcamp/package name lookups per enrollment).

### `POST /v1/students/deactivate` (route name `students.deactive`, `deactivateStudent`)
- Same request validation as `activate`.
- **Success response:** `apiResponse([$data, $data2], 'Deactivated Successfully', statusCode: 200)` — **`data` here is a plain numeric-indexed array of two raw values** (`studentRepo->deactivate(...)` result, `enrollmentRepo->deactivate(...)` result), not a keyed object — a client expecting named keys (as in `activate`'s response) will find this shape different.
- **Side effects:** additionally deactivates the student's `Enrollment` rows (not just the `Student` row itself — `activate` does **not** have a symmetric enrollment-reactivation step); same per-student Edmingle deactivate call pattern (synchronous) and `DeactivateStudentEdmingleBatches` job; `StatusDeactivated` mail per student.

---

## Other admin actions

### `PUT /v1/students/{student}/email/update` (route name `students.email.update`, `updateEmail`)
- **Request body** (inline `$request->validate()`, no FormRequest class): `email` required, email format, max:255, `unique:students,email,{student->id}` (excludes self); `full_name` required max:255; `phone` required + phone format (country inferred from `country_id`); `country_id` required `exists:countries,id`; `comment` string (not marked required/nullable — omitting it is accepted by the validator but will render as `null`/missing in the interpolated activity-log string).
- **Success response:** `apiResponse([], 'Student email updated successfully')`.
- **Side effects:** if the student has a linked `userDetail->third_party_id`, synchronously calls an external job-portal API (`PUT {external_job_portal_api_url}/v1/auth/update-user-details`) to keep that side in sync (logged on failure, does not block the request); if the student has a non-null `lms_id`, synchronously calls the Edmingle API to update email/name/phone there too — **on an Edmingle-side unique-constraint violation (`QueryException` code 1062)**, returns `apiResponse([], 'This email is already taken.', 'error', 422)` **instead of** completing the update, even though the student-record validation itself already passed; any other Edmingle exception → 422 with a message built by `getEdmingleMessasge()`. Also always calls `updateRevenueProfile()` synchronously (another outbound HTTP call to the revenue-side gateway) — a single request here can therefore make up to 3 sequential external HTTP calls before responding.

### `GET /v1/students/dashboard/list` (route name `students.dashboard.list`, `studentsDashboardData`)
- **Success response:** `apiResponse(['pie' => [...], 'students' => [...]])`, wrapped in `Cache::remember('dashboard.student.data', 1800, ...)` — **the response is cached app-wide for 30 minutes**; a test that mutates data and expects to see it reflected immediately in this endpoint's response will fail until the cache expires (or is manually flushed).

### `GET /v1/students/login-from-admin/{student}` (route name `students.login-from-admin`, `loginAsStudent`)
- **Error response:** `ValidationException::withMessages(['message' => ['This Student is not Active for logging in!']])` (standard 422 shape) if `student->status != Student::ACTIVE`.
- **Success response:** hand-rolled `response()->json(['status' => 'success', 'token' => $token, 'admin_id' => $userId])` — **no `data`/`message` envelope at all**, and note this uses the string key `'status' => 'success'`, not the app's usual `apiResponse()` envelope.
- **Side effects:** generates a short-lived (`tmp_verification_token`, 5-minute expiry) impersonation token stored on the `Student` row and an activity log entry ("Student Logged In!") — this token is presumably later consumed by the student-facing `ssoValidation` endpoint (not part of this module's routes) to mint an actual Sanctum student token; this endpoint itself does **not** issue a usable student session token.

### `GET /v1/students/{student_id}/activity` (route name `students.activity`, `activity`)
- **Error response:** `apiResponse([], 'Student Not Found', 'error', 404)` if the id doesn't resolve (raw `$id`, no route-model-binding here either).
- **Success response:** see the "third pagination style" note at the top of this file — `logOfStudent()`'s page-number-as-`cursor` shape, `ActivityResource` items (`actionName`,`causedBy` (looked up email),`actionedAt`,`description`).

### `GET /v1/students/{student}/bootcamps` (route name `students.bootcamps`, `bootcamps`)
- Query: `except` (optional bootcamp id to exclude from the result).
- **Success response:** global `apiResponse([...])` — a plain array of `{bootcamp_id, bootcamp_name}`, deduplicated by `bootcamp_id`.

### `GET /v1/students/{student}/availability` (route name `students.availability`, `getStudentAvailability`)
- **Error response:** hand-rolled `response()->json(['status' => 'error', 'message' => 'No availability marked by this student'], 404)` if the student has no `weekdayAvailability` rows.
- **Success response:** hand-rolled `response()->json(['status' => 'success', 'availability' => {...grouped by weekday_id...}, 'timezone' => ...])` — **no `apiResponse()` envelope, no `data` key**; `timezone` defaults to `'Asia/Kolkata'` if unset on the first availability row.
- **⚠️ Orphaned FormRequest:** `Modules\Student\Http\Requests\StudentAvailabilityRequest` exists (validating an `availabilities`/`timezone` write payload) but **this route is a `GET` with no body validation at all** — the class is never referenced by any controller/trait method in this module. Confirmed by grep: its own file is the only place its class name appears. Do not assume this endpoint accepts or validates a write payload shaped like that class.

### `POST /v1/students/export`, `POST /v1/students/export-with-enrollment-form`, `POST /v1/students/international/books/export`
All three follow the same pattern: `Validator::make()` (no FormRequest) validating the same optional `data` filter-array shape as `index()`; queue a CSV-generation job (`StudentCSVDownloadStart` / a chained `Maatwebsite\Excel` queue + `EnrollmentFormCSVDownload` / `InternationalStudentsBookCsvJob`, respectively) on the `default_medium` queue; return `apiResponse('', '<X> Csv file exporting started')` (or `'...', 'success'` for the enrollment-form variant) — **`data` is an empty string, not `[]`**, and completion is only observable via the queued completion email, not this response.

---

## Unauthenticated public endpoint

### `POST /v1/students/get-reg-code` (route name `students.get-reg-code`, `getRegCode`)
- **Auth:** **none** — this route is in a separate `Route::middleware(['json.response'])` group with no `auth:sanctum`. Publicly callable by anyone who can reach the API.
- **Request body:** inline `$request->validate(['email' => 'required|email'])`.
- **Success response:** hand-rolled `response()->json(['status' => 'success', 'data' => {reg_code, email}, 'message' => 'Student registration code fetched successfully'])` — default status code (200).
- **Error response:** hand-rolled `response()->json(['status' => 'error', 'data' => [], 'message' => 'Student registration code not found'])` — **also default status code 200 (no explicit status code is set)**. A status-code-only check (e.g. "is this a 2xx?") will misread a not-found lookup as a success; the caller must inspect the `status` string field.
- **Notes:** no rate-limiting visible on this route — combined with being unauthenticated and enumerable by email, this could be used to probe which emails are registered students (returns a different `status` string depending on match) at unlimited volume.

---

## Summary

**Routes documented:** all 29 routes in `Modules/Student/Routes/api.php` (24 distinct trait/controller actions, several with multiple route aliases to the same method — `index()` is reachable both as `GET /students` via `apiResource` and as `POST /students/search/index`).

**Structural surprises:**
- A third, distinct pagination convention (`logOfStudent`'s page-number-as-`cursor`) not covered by the two documented in `_COMMON_CONVENTIONS.md`.
- `UpdateStudentRequest` genuinely excludes `email`/`phone`/`status` — confirmed, not an oversight in the existing spec.
- `StudentAvailabilityRequest` is a confirmed orphaned FormRequest class — the route it would logically belong to is a parameterless `GET`.
- `activate`/`deactivate` are asymmetric: only `deactivate` cascades to the student's enrollments.
- `updateEmail` can make up to 3 sequential synchronous external HTTP calls (job portal, Edmingle, revenue gateway) inside a single request — a real latency/flakiness risk for parity/load testing.

**Confidence:** High — every endpoint's behavior was confirmed directly from `StudentController.php`, `StudentTrait.php` (read in full, ~2400 lines), `StoreStudentRequest`/`UpdateStudentRequest`/`StudentAvailabilityRequest`, and the referenced Resource classes. The `ActivationAndDeactivationProcess`/`ActivityLog` shared traits were also read directly rather than assumed.
