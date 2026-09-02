# LawSikho Module — API Documentation

The `LawSikho` module is the **integration gateway** between this app (the Assignment Portal, "AP") and the external LawSikho revenue/marketing site. It exposes endpoints that let that external system create/update students, push address and LMS data, activate/revoke access, upload student files, submit the post-purchase "enrollment form," ingest bootcamp/course metadata, and query enrollment status — almost all of it **unauthenticated** by design (the caller is a trusted internal system, not an end user). See [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for the app-wide envelope/error/pagination conventions referenced below — this file only calls out where a specific endpoint deviates from those.

Exact route count: **33 route registrations** in `Modules/LawSikho/Routes/api.php` (15 `GET`, 17 `POST`, 1 `PATCH`), all inside one `Route::middleware(['json.response', 'log.third.party'])->prefix('v1')` group (i.e. every path below is actually `/api/v1/...`).

## Module-wide notes (read once)

- **Auth default: none.** Every route in this file carries only `json.response` (forces JSON responses) and `log.third.party` middleware, **not** any auth guard — with the sole exception of two routes explicitly noted below that add `CheckLawSikhoApiToken` middleware. Per-endpoint "Auth" lines below only exist for those two; every other endpoint should be read as "no authentication."
- **`log.third.party` (`App\Http\Middleware\LogThirdPartyRequestResponse`) logs every single call**, success or failure, into the `third_party_logs` table (`Modules\LawSikho\Entities\ThirdPartyLog`): full request URL, method, headers (JSON-encoded), body (JSON-encoded), plus the eventual response status code and full response body. This runs on literally all 33 routes — a parity test can use this table as an independent record of exactly what was sent/returned, including for endpoints whose own response has no envelope.
- **Token check (only 2 routes):** `POST /v1/active-access` and `POST /v1/revoke-access` carry `Modules\LawSikho\Http\Middleware\CheckLawSikhoApiToken`. It compares header `X-Auth-Token` against `config('lawsikho.api_token')` (env `REVENUE_API_TOKEN`) using **strict `===`, not `hash_equals()`** — not timing-safe, a genuine (if likely low-severity) side-channel weakness worth preserving in a security-focused test. Missing/mismatched token → `401 {"status":"error","error":"Unauthorized","message":"Token does not match"}`.
- **Response shapes are inconsistent by design.** This module mixes: the global `apiResponse()` helper, hand-rolled arrays returned directly from a controller method (Laravel auto-JSON-encodes a returned array as a 200 response), `response([...], $code)` (note: **not** `response()->json(...)` — same effective result for an array payload, but worth knowing which call site it is), and completely bare/unwrapped scalars. Each endpoint below states exactly which.
- **Class-location note:** `LawSikhoController` (`Modules/LawSikho/Http/Controllers/LawSikhoController.php`) is a thin shell — almost all of its behavior is pulled in via five traits: `StudentTrait`, `CourseTrait`, `EnrollmentTrait`, `FileTrait`, `CourseBatchTrait` (all under `Modules/LawSikho/Http/Traits/`). The two `/lms` routes (`getStudentLmsId`, `updateStudentLmsId`) are the only logic that lives directly on the controller itself.
- **Cross-module delegation:** four routes in this file point at controllers that live in *other* modules — `add-course` → `Modules\Course\Http\Controllers\CourseController::store`, `single-course-enrollment`/`bootcamp-course-enrollment`/`bootcamp-course-enrollment-from-revenue`/`package-enrollment-lawsikho` → `Modules\Enrollment\Http\Controllers\EnrollmentController`, `/lawsikho/students-listing` → `Modules\Student\Http\Controllers\StudentController::activeStudents`. Documented here since this route file is what wires them in, with their real location noted.

---

## Student creation & lookup

### `POST /v1/add-student` — create or update-on-conflict a student
**Auth:** none (module default).
**Request:** `StoreStudentRequest` validates only a subset of fields — `email` (required, email); `password` (nullable, `confirmed`, `Password::defaults()`); `status` (required, int, one of `Student::PENDING=0|ACTIVE=1|DISABLED=2`); `kanboard_id`/`forum_id`/`lms_id` (nullable int); `forum_pass`/`forum_access_token`/`forum_token_time` (nullable string); `tags` (nullable array of `{key:int, value:string max:255}`, both required together if `tags` present). **Several other fields are read directly off the request in the controller with no FormRequest validation at all**: `full_name`, `phone`, `countryCode`, `address`, `city`, `state`, `zipcode`, `country`, `linkedin_profile`, `cv_link`, `user_ip`/`user_browser`/`user_os`/`user_device`.
- If `auth()->user()` resolves (rare on an unauthenticated route, but possible if a session cookie happens to be present), `created_by` is set to that user's id; otherwise `null`.
- **Existing-email branch:** if a `Student` with that `email` already exists, and `address` is present in the request, the student's `state`/`city`/`address`/`pin_code`(from `zipcode`)/`country`/`phone`/`country_id`/`lms_id` are updated (each falling back to the existing value if not sent). Country is resolved by `Country::where('phone_code', $request->countryCode)->first()`, falling back to India (`phone_code = 91`) if no match. Response: `apiResponse(['student' => $email], 'Student Exist', statusCode: 201)` — **HTTP 201, not 200, even though this is an update, not a creation.**
- **New-student branch, manual null-check (not FormRequest):** if `full_name`, `phone`, or `status` is `null`, returns `apiResponse(['message' => "Full Name, Phone, Status Can't be null"], 'Field Required', statusCode: 422)` — note the response body's outer `message` is `"Field Required"` while the actual detail string is nested one level down as `data.message`, **not** the standard per-field Laravel validation shape.
- Otherwise creates the student inside `DB::transaction`: `reg_code` initially `' '` (single space), then updated to `'STU' . now()->format('Ymd') . '/' . $student->id`; `password` = `Hash::make($request->password)` if sent, else auto-generated 8-char random string via `Str::random(8)` which is **emailed to the student** (`Mail::to($email)->queue(new StudentPasswordGeneration(...))`) and then hashed; `country_id` resolved the same way as above; `is_terms_and_condition_checked`/`is_message_send_aggreed` forced to `Student::ACTIVE`; also writes a `student->originalRegistrationDetails()->create([...])` audit row with a snapshot JSON (`created_by: 'Self'`). If `tags` present, each tag is either created (`key == 0`) or attached by id (`key != 0`) via `$student->tags()->attach($newTag->id, [])` — **`attach`, not `sync`, so repeated calls accumulate duplicate pivot rows**, unlike the near-identical `attachTags` in the Enrollment module which uses `sync`.
- **Side effect:** after the transaction commits, dispatches `SendStudentDataToExternalAPI::dispatch($student)` (queued job) which POSTs the new student to an external job-portal registration endpoint (`config('app.external_job_portal_api_url') . '/v1/auth/email-registration-without-verification'`) and, on a `200` response with a `user_id`, writes a `student_other_details` row linking the student to that third-party id. Dispatch failure is caught and logged, **does not fail the request**.
- **Success:** `apiResponse(['student' => StudentResource::make($student->fresh())], 'Student created successfully', statusCode: 201)`. `StudentResource` returns all raw Student columns except `created_at`/`updated_at`/`created_by`/`updated_by`, plus nested `tags`, `creator`, `updater` (each `only('id','first_name','last_name')` or null).

### `GET /v1/check-student` — quick existence probe by email
**Auth:** none. **Params:** `email` (query, no validation — a raw `Student::where('email', $request->email)->first()`; missing `email` param just looks up `null`, matching nothing).
**Response (hand-rolled array, not `apiResponse`):** found → `{"res":"Y","data":{"p_image":<image col or null>,"id_image":<id_image col or null>,"cv":<cv_title col or null>},"message":"User Found"}`; not found → `{"res":"N","message":"User Not Found"}` (no `data` key at all in the not-found case). Both cases are HTTP 200.

### `GET /v1/get-student-address`
**Auth:** none. **Params:** `email` (query, no validation).
**Response:** found → `{"status":"success","error":null,"data":{"address","city","country","zip_code","state"}}`, HTTP 200. Not found → `response([...], 422)` with `{"status":"error","error":null,"data":"No Record Found"}` — **`data` is a bare string here, not an object**, unlike the success shape's object.

### `POST /v1/update-student-address`
**Auth:** none. **Request** (`UpdateStudentAddressRequest`): `address`/`city`/`country`/`zip_code` required, `max:255`; `batch_id` nullable int `exists:course_batches,id`; `ap_course_id` nullable int `exists:courses,id`. `countryCode`/`phone` are read from the request but **not validated** (their FormRequest rules are commented out in source).
- Country resolved from `countryCode` the same fallback-to-91 pattern as `add_student`.
- If no `Student` matches `email` → `response([...], 422)` `{"status":"error","error":null,"data":"No Record Found"}`.
- If found, updates `address`/`city`/`country`/`pin_code`(from `zip_code`)/`state`/`phone`/`country_id` unconditionally (no "keep old value" fallback here, unlike `add_student`).
- **Optional batch-assignment branch** — only runs if `batch_id`, `ap_course_id`, **and** `ls_order_id` are *all* present in the request (note: `ls_order_id` isn't in the FormRequest's rules at all, so it's read unvalidated):
  - If an `Enrollment` already exists for this student+course+batch → `response([...], 422)` `{"status":"error","error":null,"data":"This Course, & Batch is already associated with this student"}`.
  - Else looks up an existing enrollment by `course_id` + `ls_order_id` + `student_id` where `bootcamp_id` and `package_id` are both null. If found, sets its `batch_id`, `batch_assigned_by` (`auth()->user()->id ?? 1`), recomputes `enrollment_expire_at` from the course's `duration_days`, and regenerates `enrollment_code` as `"LS/{course_id}/{batch_id}/{enrollment_id}"`. If **not** found → `response([...], 422)` `{"status":"error","error":null,"data":"This LS Order ID not exist at all, or not associated with this student, & course"}`.
- **Success response shape does not match the app-wide envelope:** `{"status":"success","error":null,"data":"Address Updated"}` — `status` key ordered before `data`, **no `message` key at all**, and it's returned as a plain PHP array (not `response()->json`), so Laravel serializes it with the default 200 status.

---

## LMS fields

### `GET /v1/check-lms`
**Auth:** none. **Params:** `email` (query, unvalidated).
**Response — always HTTP 200 regardless of outcome**, distinguishable only by body: student not found → `{"status":"error","message":"User Not Found"}`; found but `lms_id` is null → `{"status":"error","message":"LMS ID NOT FOUND!"}`; found with an `lms_id` → `{"status":"success","lms_id":<int>,"message":"LMS ID FOUND!"}`. No `data` key in any branch.

### `POST /v1/update-lms`
**Auth:** none. **Request** (`UpdateLMSIDRequest`): `email` — wait, note `email` itself is **not** in this FormRequest's rules (only `lms_id` required int is validated); `email` is read unvalidated off the request to find the student.
- Not found → `response([...], 422)` `{"status":"error","error":null,"message":"No Record Found"}` (no `data` key).
- Found → sets `lms_id`, saves, then **always** returns `{"status":"success","error":null,"message":"LMS ID Updated"}` since the `if ($student)` check after `$student->save()` is checking the already-truthy `$student` variable, not the save's return value — the `else` branch (`"LMS ID Not Updated"`) is dead code, unreachable in practice.

### `GET /v1/lms` — `getStudentLmsId` (lives directly on the controller, not a trait)
**Auth:** none. **Request:** `$request->validate(['email' => 'required|email'])` — inline validation, standard 422 on failure (see `_COMMON_CONVENTIONS.md`).
**Response: completely unwrapped raw value**, no JSON envelope of any kind — `response()->json($student?->lms_id ?? null)`. Body is the bare integer, or the literal JSON `null` if the student doesn't exist or has no `lms_id`. **A parity test must not expect any `data`/`status` wrapper here.**

### `PATCH /v1/lms` — `updateStudentLmsId` (lives directly on the controller)
**Auth:** none. **Request:** inline `$request->validate(['email'=>'required|email', 'lms_id'=>'required|integer'])`.
- Runs `Student::where('email', ...)->update(['lms_id' => ...])` (an update-query, not a model save) and separately re-fetches `$student` beforehand to log the "old" value. If the update affected exactly 1 row and a matching student was found pre-update, writes an `Activity::create()` row directly (log_name `Student Updated`, event `Student LMS ID Updated`, `causer_id: auth()->id()` — this one, unlike most of the module, attributes to the *actual* caller if authenticated, not a hardcoded id).
- **Response: bare unwrapped integer** — `response()->json($affected === 1 ? 1 : 0)`. `1` means exactly one row was updated; `0` covers both "no student with that email" and "update affected 0 rows" — **indistinguishable from the response body alone.**

### `GET /v1/check-enrollment`
**Auth:** none. **Request** — inline `$request->validate([...])`: `course_id` nullable **`exists:course_batches,id`** ⚠️ — despite the field's name, it is validated against the `course_batches` table, not `courses`. A syntactically valid `courses.id` that doesn't happen to also exist as a `course_batches.id` fails validation with a generic 422 before the lookup logic even runs. Preserve this exactly — almost certainly an unintentional copy-paste from the `batch_id` rule, but it's the live behavior. `batch_id` nullable `exists:course_batches,id`; `ls_order_id` nullable `exists:enrollments,ls_order_id`; `email_id` nullable `exists:students,email`.
- Branch 1 — `course_id` **and** `batch_id` **and** a resolved student: looks up an `Enrollment` matching `course_id`+`batch_id`+`student_id`. Found → `response([...], 200)` `{"status":"success","error":null,"message":"Found enrollment associated with these course, batch, & email","data":1}`. Not found → `response([...], 422)` `{"status":"error","error":null,"message":"No enrollment is associated with these course, batch, email","data":0}` — note `data` is the integer `1`/`0`, not a boolean.
- Branch 2 — no `course_id`, no `batch_id`, but `ls_order_id` present: looks up by `ls_order_id` alone. Same `data:1`/`data:0` pattern, messages naming "this ls order id" instead.
- Fallback (neither branch's precondition met, e.g. a student wasn't resolvable, or an inconsistent combination of params) → `response([...], 422)` `{"status":"error","error":null,"message":"You have to pass essential values","data":"You have to pass essential values"}` — `data` here is a duplicate of `message`, not `0`/`1`.

---

## Access activation & revocation (token-gated)

Both routes below carry `CheckLawSikhoApiToken` — see the module-wide note above for the 401 shape and the `===`-not-`hash_equals` caveat.

### `POST /v1/active-access`
**Auth:** `X-Auth-Token` header must equal `config('lawsikho.api_token')`.
**Request:** inline `validate()`: `ls_order_id` required, `exists:enrollments,ls_order_id`; `email` nullable `exists:students,email`; `name` nullable.
- Looks up the `Enrollment` by `ls_order_id` → not found → `response([...], 422)` `{"status":"error","error":null,"message":"No Record Found Against This LS Order ID"}`.
- Found: sets the associated `Student.status = ACTIVE`; sets `status = ACTIVE` on every `Enrollment` for that student+`ls_order_id` **where `is_batch_migrated = BATCH_NOT_MIGRATED`** (batch-migrated enrollments are silently skipped from activation).
- **Activity log quirk — confirmed:** both the student-level and each enrollment-level `activity()` log entry are attributed via `->by(User::find(1))` — **hardcoded to user id 1 regardless of who/what actually called this endpoint** (there's no real caller identity available anyway, since the route has no user-auth guard, only the shared token). Events: `Activate From Revenue System` on both.
- **Success:** `response([...], 200)` `{"status":"success","error":null,"message":"Enrollment & Student Activated"}`.

### `POST /v1/revoke-access`
**Auth:** same token gate. **Request:** identical inline rules to `active-access`.
- Not found by `ls_order_id` → same 422 `"No Record Found Against This LS Order ID"` shape as above.
- Found: counts *other* enrollments for the same student that either have a different `ls_order_id` or a null one.
  - **If other enrollments exist:** only the matched `ls_order_id`'s enrollments are set to `PENDING` (the student record itself is left untouched/still active) — logged as event `"Revoked From Revenue System"` if `ls_order_id`+`email`+`name` are all non-null in the request, else `"Revoked From Lawsikho"`. Response `200` `{"status":"success","error":null,"message":"Enrollment Deactivated since student is old"}`.
  - **If no other enrollments exist:** the student itself is set to `PENDING`, and **if `lms_id` is set**, triggers a live outbound call to Edmingle (`deactivateStudentInEdmingle()` — POSTs to `config('app.edmingle_api_endpoint') . 'remove/organization/student/' . $lms_id` with `apikey`/`ORGID` headers) to archive/deactivate the student on the LMS side — **not mockable at this app's own boundary**, needs an Edmingle stub/sandbox for a real parity test. That call's own success/failure is only logged (`Log::info`/`Log::error`), never surfaced in this endpoint's HTTP response — a failed Edmingle deactivation still returns this endpoint's normal 200 success body. The matched enrollments are also set `PENDING`. Response `200` `{"status":"success","error":null,"message":"Student & Enrollment Deactivated"}`.
  - **Same `User::find(1)` hardcoded activity-log causer** as `active-access`, on both branches.

---

## File storage

All three routes below: **no auth**, no `AsymmetricAuthPresent` middleware — pure S3 upload endpoints keyed off a FormRequest whose *only* job is a file-type/size check.

### `POST /v1/store-photo`
**Request** (`StorePhotoRequest`): `photo` required, `mimes:jpg,jpeg,png`, `max:10240` (10MB).
**Response:** the controller code checks `$_FILES['photo']['name'] != ''` (raw PHP superglobal, bypassing the validated `Request` object) before building `$data`; if that condition is false the method falls through to `return $data;` with **`$data` never assigned** — an undefined-variable condition (PHP 8 emits a warning, not a fatal error, and the response body ends up `null`), **not a clean 4xx**, contradicting what the FormRequest's "required" rule would suggest. When the file is present as expected, returns a **raw unwrapped array** (no envelope) of `client_name`, `file_ext`, `file_name` (random-prefixed, e.g. `12345_1700000000.jpg`), `file_path` (S3 URL), `file_size`, `file_type`, `full_path` (same S3 URL, computed twice — the first assignment via `asset('storage/...')` is immediately overwritten), `orig_name`, `raw_name`. **Does not attach the file to any `Student` record** — this endpoint only stores to S3 and returns metadata; the actual student-column update happens separately, in `store-enrollment-form`/`-v2`.

### `POST /v1/store-id-proof`
Same pattern as `store-photo`: `StoreIDRequest` (`id` required, `mimes:jpg,jpeg,png`, `max:10240`), stores under `uploads/students/id/`, same raw-array response shape (`client_name`,`file_ext`,`file_name`,`file_path`,`file_size`,`file_type`,`full_path`,`orig_name`,`raw_name`), same undefined-variable fallthrough if `$_FILES['id']['name']` is empty.

### `POST /v1/store-cv`
`StoreCVRequest`: `cv` **not required** (no `required` rule — only `mimes:doc,docx,pdf`, `max:10240`), so an entirely file-less request is valid input. Controller wraps the body in `if ($request->file('cv'))` before the `$_FILES['cv']['name']` check, so a request with no file at all cleanly returns `$data = null` (`return $data;` → JSON `null`), rather than an undefined-variable warning — better-behaved than the other two in that one respect. Same S3 path pattern (`uploads/students/cv/`) and same raw-array metadata shape on success.

---

## Enrollment form submission (v1 vs v2)

### `POST /v1/store-enrollment-form` (v1)
**Auth:** none. **Request:** plain `Request`, **zero validation** of any field.
- Looks up `Student` by `email`; not found → `response([...], 422)` `{"status":"error","error":null,"data":"No Record Found"}`.
- Found: sets `date_of_birth` (parsed via `strtotime($request->birthday)`, or `null`), `father_name`, `gender` (mapped `0→"male"`, `1→"female"`, anything else→`"others"`), `enrollment_form_filled_at` (`now()` in `Asia/Kolkata`, forced via a **process-wide** `date_default_timezone_set()` call — a side effect on the whole PHP process, not scoped to this request), `id_image`/`image` from `hidUserImageIdProof`/`hidUserImage` **treated as already-uploaded URL strings** — this v1 endpoint does nothing with actual file uploads; if the frontend sends real files here they are effectively ignored/dead code.
- If `know_abt_lawsikho` array present, inserts one `KnowAboutLawsikhoStudentAnswer` row per entry (`is_other` populated only for answer ids `12`/`39`).
- Parses `response` (an object of `resp_<question_number>` keys, optionally `resp_oth_<question_number>` for "Other" answers) and bulk-inserts into `EnrollmentQuestionAnswer` via `insert()` (no model events fire). **No schema validation on `response`'s keys at all** — malformed keys are silently skipped (the `resp_` prefix strip via regex just no-ops if absent), not rejected.
- **Success:** hand-rolled array (not `apiResponse`) `{"status":"success","error":null,"data":"Data Submitted"}`, HTTP 200.

### `POST /v1/store-enrollment-form-v2`
Same overall logic as v1, with two real differences:
1. **Validates the two image fields:** inline `$request->validate(['hidUserImage'=>'nullable|mimes:jpg,jpeg,png|max:10240', 'hidUserImageIdProof'=>'nullable|mimes:jpg,jpeg,png|max:10240'])` — everything else remains unvalidated.
2. **Accepts them as actual file uploads**, not URL strings: if present, uploads to S3 (`uploads/students/photo/` / `uploads/students/id/`) and persists the resulting S3 URL to `student.image`/`student.id_image`. v2 additionally sets `student.linked_in_link` from `linkedin_profile` (v1's equivalent line is commented out in source).
Same student-not-found 422 shape, same `know_abt_lawsikho`/`response` bulk-insert logic, same `{"status":"success","error":null,"data":"Data Submitted"}` success shape.

---

## Course, course-batch & category reference data (cross-module + module-native)

### `POST /v1/add-course` — **cross-module delegation**
Routed to `Modules\Course\Http\Controllers\CourseController::store` (the `Course` module, not `LawSikho`) — a `Store` FormRequest with the full course-creation field set (see `API_SPECIFICATIONS.md` §3 for the detailed field table: `course_name`, `status`, `duration_days`, `course_category_id`, evaluator/coach ids, `evaluators`/`mentors` arrays with no `distinct` rule, AI fields, instruction/feedback file-or-URL fields). Dispatches `SyncCourseWithCalendar::dispatch($course)`. Success: `apiResponse(['course' => CourseResource::make(...)], 'Course created successfully', statusCode: 201)`.

### `POST /v1/course_update`
`UpdateCourseRequest`: `course_id` required `exists:courses,id`; everything else optional/nullable including `default_evaluator_id`/`default_written_evaluator_id` (no `nullable` on those two — but also not `required`, so simply omitted silently skips update of those fields, distinct from the `Course` module's own admin update route where they're described as required — **this LawSikho variant is more permissive**), `evaluators.*`/`mentors.*` each `exists:users,id`, `remove_evaluators`/`remove_mentors` (`nullable|in:1`).
- Runs the update inside `DB::transaction`, only touching the whitelisted columns (`status`, `course_name`, `course_category_id`, `duration_days`, `default_evaluator_id`, `default_written_evaluator_id`, `student_coach_id`, `student_writing_coach_id`, `freelance_id`, `placement_id`, `updated_by`). **Note: `evaluators`/`mentors`/`remove_evaluators`/`remove_mentors` are validated but never actually applied to any pivot table in this method** — they're accepted and silently dropped, unlike the `Course` module's own update endpoint.
- **Activity log attributed to `User::find(3)`** — hardcoded, with a comment "For Lawsikho we are using the user id value to 3" (i.e. an intentional, documented convention, distinct from `active-access`/`revoke-access`'s `User::find(1)`).
- Success: `apiResponse(['course' => CourseResource::make($course->fresh())], 'Course updated successfully')`.

### `GET /v1/course_batches` and `GET /v1/course_batch`
Both point at the same `course_batches()` method (`CourseBatchTrait`). Filters `CourseBatch` rows to `status = STATUS_ACTIVE`, additionally to `id = request('batch_id')` if that query param is present. **Response is a hand-built plain array** (not a Resource, not `apiResponse`) of `{"id":..., "batch_name": <batch_date column>}` objects — an empty array `[]` if nothing matches, HTTP 200 either way.

### `GET /v1/course-category`
Returns `CourseCategory::all('id', 'category_name', 'status')` directly from the controller — Laravel auto-serializes an Eloquent collection to a bare JSON array, **no envelope, no `data` wrapper**.

### `GET /v1/written-assignment-course`
`response()->json(['data' => BootcampWrittenCourseResource::collection(Course::where('status', STATUS_ACTIVE)->where('course_type', BOOTCAMP_COURSE)->get()), 'error' => null, 'status' => 1])` — note `status` is the **integer `1`**, not the string `"success"` used elsewhere in this same module. Each resource item: `{"course_id":..., "course_name":...}`.

### `GET /v1/student-enrollment-check`
Maps to `check_if_student_filled_enrollment_form`. Student not found → `{"status":2,"data":"No Student Found","error":null}` (note: `status` integer `2`, a third distinct "not found" convention within this one module). Found with ≥1 `EnrollmentQuestionAnswer` row → `{"status":1,"data":"Filled Enrollment Form","error":null}`; none → `{"status":0,"data":"Not Filled Enrollment Form","error":null}`. All HTTP 200 (returned as a plain array, no explicit status code ever set).

---

## Enrollment creation (cross-module: routes to `Enrollment`)

These four routes live in this file but delegate to `Modules\Enrollment\Http\Controllers\EnrollmentController` (some methods pulled in from that module's own `EnrollmentTrait`). All four ultimately funnel through the same shared engine, `createCourseEnrollment()` (side effects: computes `passing_criteria`/`dashboard_journey_steps`, sets `course_expiry_date`/`enrollment_expire_at` from the course's `duration_days`, generates `enrollment_code`, writes an `Activity::create()` row unconditionally, optionally dispatches `BatchsAssignmentsJob` if `shift_assignments=='true'`, optionally creates/links an Edmingle batch and fires a live Edmingle API call if `batch_status` is `2`/`3`, and emails `SUPPORT_MAIL` if the target batch's student count lands in the `100–103` range) — these are genuine external/queued side effects to account for in any parity test that exercises these routes with a `batch_id`.

### `POST /v1/single-course-enrollment` and `POST /v1/bootcamp-course-enrollment`
Both route names differ but **both point at the identical controller method**, `EnrollmentController::store_from_lawsikho` (`StoreEnrollmentRequestForLS` — `course_id` required `exists:courses,id` [validated per-element if an array], `countryCode` required (no `exists` check, just presence), `email`/`phone`/`name`/`status` required, `batch_id` nullable `exists:course_batches,id`, phone validated via `propaganistas/laravel-phone` using the ISO derived from `countryCode`). There is **no route-level distinction between "single course" and "bootcamp" traffic** — the controller branches purely on whether `course_id` is sent as a scalar or an array in the request body, not on which URL was hit.
- If a `Student` with that `email` exists: for a scalar `course_id`, looks up any existing `Enrollment` by `ls_order_id` (if sent) — if found, re-associates it to this student and reactivates it (`updateStudentSingleCourseEnrollmentFromLawsikho`); else creates a fresh enrollment (`createCourseEnrollment`). For an array `course_id` (bootcamp/multi-course), the equivalent `ls_order_id` lookup uses `updateStudentCourseEnrollmentFromLawsikho`, otherwise loops the array and creates one enrollment per course id — plus a further optional `writtenassignment_id` add-on course if present.
- If no `Student` exists: creates one first (`country_id` **is** resolved from `countryCode`, Student status forced `ACTIVE`, password auto-generated and mailed via `$this->studentController->generatePassword(...)`), then runs the identical create/re-associate branching as above.
- **Success:** `$this->apiResponse(['enrollment' => EnrollmentResource::make($enrollment->fresh())], 'Enrollment created successfully', statusCode: 201)`.
- ⚠️ This method has no explicit "duplicate enrollment" guard — an old check for "same course+batch already enrolled" is present in source but fully commented out (`// $check = Enrollment::where(...)`), so calling this repeatedly with the same course/batch for the same student will create additional `Enrollment` rows rather than being rejected.

### `POST /v1/bootcamp-course-enrollment-from-revenue`
Routes to `EnrollmentController::store_from_revenue` (`StoreEnrollmentRequest` — note: **this one requires `country_id` directly** with `exists:countries,id`, unlike the LS variant's `countryCode`-only rule). Logic mirrors `store_from_lawsikho` closely (same array-vs-scalar `course_id` branching, same `ls_order_id` re-association path), with two confirmed differences:
- ⚠️ **When creating a brand-new student, `country_id` is never set** in either the array- or scalar-`course_id` new-student branch (both omit `'country_id' => $country->id` from the `create([...])` call, even though a `$country` lookup happens earlier in the method and *is* used elsewhere) — students created through this specific route end up with a null `country_id` regardless of what `country_id` was submitted, unlike every sibling enrollment-creation path in this module.
- Tag attachment is commented out in one of the array-`course_id` sub-branches (`// $this->attachTags($newRequest, $student);`) — tags silently don't get attached on that specific path even if `tags` was sent.
Success shape identical: `apiResponse(['enrollment' => EnrollmentResource::make(...)], 'Enrollment created successfully', statusCode: 201)`.

### `POST /v1/package-enrollment-lawsikho`
Routes to `EnrollmentController::store_package_enrollment_from_lawsikho` (lives in `Modules/Enrollment/Http/Traits/EnrollmentTrait.php`), `StorePackageEnrollmentRequest`: `package_id` required `exists:packages,id`; `student_id` required `exists:students,id` (this is the one enrollment-creation route in the module that takes an existing `student_id` directly rather than an email/name payload — the student must already exist). `created_by` defaults to `auth()->user()->id ?? 1`.
- Looks up every course mapped to `package_id` and calls `createPackageEnrollment()` once per course.
- ⚠️ **Always returns success regardless of whether any courses were actually enrolled** — `return $this->apiResponse([], 'Package Enrollments created successfully', statusCode: 201)` runs unconditionally, even when the package has zero mapped courses (the `if (count($packageCourses) > 0)` branch only gates an internal `$enrollment` lookup that's otherwise unused — no email is actually sent, that code path is fully commented out). A caller sending a `package_id` with no mapped courses gets an indistinguishable "success" with an empty `data:{}`. This is exactly the "2xx + success body ≠ proof of effect" caution flagged in `_COMMON_CONVENTIONS.md` — verify via a follow-up read of the student's enrollments, don't trust this response alone.

---

## Bootcamp ingestion

### `POST /v1/bootcamp_from_lawsikho`
**Auth:** none. **Request** (`BootcampRequest`): `id` required int; `name` required string (1–500 chars); `title` nullable string max:500; `refund_eligible_course` nullable int.
- `$refund_eligible_course` defaults to `1` if not sent, then is force-overridden to `2` if `request->title ?? request->name` contains the substring `"Independent Director"` (case-sensitive `str_contains`).
- Looks up `Bootcamp::find($request->id)` — **the caller supplies the primary key directly; it is not auto-increment from this endpoint's perspective.**
  - **If found** (update branch): if `$bootcamp->id < 932` (hardcoded threshold, "the first bootcamp id after bootcamp title change released" per an inline comment), updates only `name` (from `request->name`) and `refund_eligible_course`. If `id >= 932`, updates `name` (from `title ?? name`) **and** `title` (set to `request->name` **only if `title` was present in the request** — i.e. `title` gets overwritten with the *name* value, an inversion that's easy to misread; if `title` wasn't sent, `title` is explicitly nulled out). Both branches return `apiResponse(['bootcamp' => BootcampResource::make($bootcamp->fresh())], 'Bootcamp updated Successfully')` — default 200.
  - **If not found** (create branch, per `API_SPECIFICATIONS.md` §7 correction — this confirms `Bootcamp::create()` genuinely is reachable, contrary to an earlier "orphaned model" finding for the `Bootcamp` module proper): `Bootcamp::query()->create(['id' => $request->id, 'name' => $request->title ?? $request->name, 'title' => isset($request->title) ? $request->name : null, 'refund_eligible_course' => ...])` — **same id-is-caller-supplied, same title/name inversion logic** as the `id >= 932` update branch, applied unconditionally (no `id < 932` distinction on create). Returns `apiResponse([...], 'Bootcamp Added Successfully')` — **HTTP 200 by default, not 201**, even though this is the create path.
- `BootcampResource` (LawSikho's own, not the `Enrollment` or `Bootcamp` module's identically-named resource): `{"id","name","title","refund_eligible_course"}`.

---

## Enrollment code, enrollment-status lookups, student summaries

### `GET /v1/generate-enrollment-code`
**Request** (`EnrollmentCodeRequest`): `course_id`, `batch_id`, `ls_order_id` all required `int`.
**Response is a raw string**, not JSON-wrapped at all — literally `return 'LS/' . $course_id . '/' . $batch_id . '/' . $ls_order_id;` (e.g. `"LS/12/34/56"`). No existence checks against any table — any three integers produce a well-formed-looking code even if none of them correspond to a real course/batch/order.

### `GET /v1/check-lawsikho-student` → `showEnrollmentNames`
**Params:** `email` (query, unvalidated, read via the `request()` helper rather than an injected `Request $request`).
- Not found → `response([...], 422)` `{"status":"error","error":null,"message":"Student not found with this email"}`.
- Found: builds a merged flat list of names — active simple-course enrollments' `course.course_name` (only `status == ACTIVE`, `package_id`/`bootcamp_id` both null), distinct bootcamp `bootcamp_display_name` values (via the `bootcamp` relation, no status filter), and distinct package `name` values (`package_id` set, `bootcamp_id`/`batch_id` null, no status filter) — `array_merge($enrollments, $bootcamps, $packages)`, so the three categories are **flattened into one undifferentiated array of strings**, not separated. Success: `response()->json(['status'=>'success','message'=>'Successful','data'=>$allEnrollments], 200)`.

### `GET /v1/all-enrollments` → `getAllEnrollmentNames`
Same student-lookup/not-found shape as above. On success, returns the **same three categories kept separate** this time (unlike the sibling endpoint): `{"status":"success","message":"Successful","data":{"courses":[{"course_name","image_path"}...],"bootcamps":[{"bootcamp_name","image_path":null}...],"packages":[{"package_name","image_path"}...]}}` — note bootcamp entries always have `image_path: null` hardcoded (no bootcamp image column is actually read), unlike courses/packages which pull a real `image_path` column.

### `GET /lawsikho/students-listing` — **cross-module delegation**
Routes to `Modules\Student\Http\Controllers\StudentController::activeStudents` (`Student` module's own `StudentTrait`). Returns `ActiveStudentResourse::collection(...)->additional(['meta' => ['total' => ...]])` — the standard Resource-collection pagination shape from `_COMMON_CONVENTIONS.md` (`{"data":[...],"meta":{"total":N}}`), with no filtering by any query param evident at this call site — it's the module's generic "active students" listing reused verbatim under a LawSikho-facing URL.

### `GET /lawsikho/student-details/{id}` → `studentDetails`
**Params:** `{id}` path segment, no validation/model-binding (`Student::where('id', $id)->get()` — a `get()`, not `first()`, so it returns a collection even for a single id; a non-existent id yields an empty collection, not a 404). Response: `response()->json(['data' => StudentResourceIdWise::collection($data), 'status' => 'success'], 200)` — always 200, empty `data: []` array for an unmatched id. `StudentResourceIdWise` is a narrow projection: `{"id","full_name","email","phone"}` only (no tags/creator/updater, unlike the full `StudentResource`).
**Note:** the route file references this controller as `LawsikhoController::class` (lowercase "s" in "sikho") rather than the `LawSikhoController` alias imported at the top of the file — PHP resolves class names case-insensitively so this is **not a functional bug** (it correctly resolves to the same class), but it's a cosmetic inconsistency worth knowing about if grepping the codebase for the class name.

---

*Companion documents: [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md), [`../API_SPECIFICATIONS.md`](../API_SPECIFICATIONS.md) §6 (original pass, cross-referenced throughout above) and §7 (corrections re: `Bootcamp::create()` and `AtsGateWay`, both confirmed and folded in above where relevant to this module).*
