# Enrollment Module — API Documentation

The `Enrollment` module owns the `enrollments` table — the core record linking a `Student` to a `Course`/`Bootcamp`/`Package`/`CourseBatch` — plus its admin-facing CRUD, certification, batch assignment/migration, CSV import/export, refund-eligibility tagging, and the (two, parallel, and only partly compatible) pause/resume subsystems. See [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for app-wide envelope/error/pagination conventions — this file only calls out deviations.

Exact route count: **56 raw `Route::` registrations** in `Modules/Enrollment/Routes/api.php` (one of which, `Route::apiResource('enrollments', ...)`, expands to 5 concrete routes — `index`/`store`/`show`/`update`/`destroy` — bringing the total live endpoints to **60**, two of which are dead-on-arrival — see below). Two route pairs (`pause-resume/history` and `batch-tracker`) are registered **twice**, verbatim, under both the "admin" and a second block in the same file — harmless duplication for the working one, compounding the problem for the broken one.

## Module-wide notes (read once)

- **Auth, admin block:** `auth:sanctum` + `json.response`, prefix `v1` — covers everything except the student-side block and one unguarded debug route (both called out explicitly below).
- **Auth, student block:** `auth:student` + `json.response`, prefix `student/v1` — six routes at the bottom of the route file, all under `/student-my-courses/...`.
- **Class layout:** `EnrollmentController` (`Modules/Enrollment/Http/Controllers/EnrollmentController.php`, ~2,340 lines) is a real controller (not a thin shell), but the large majority of its route-bound methods are pulled in via `use EnrollmentTrait;` (`Modules/Enrollment/Http/Traits/EnrollmentTrait.php`, ~7,900 lines — the true bulk of this module's logic). `EnrollmentCSVReportController` uses a second, much smaller `EnrollmentCSVReportTrait`. Every method below is noted as living in the controller or a named trait.
- **Response helpers:** this module uses the global `apiResponse()` helper and `$this->apiResponse()` (identical, `Controller`-instance form) **interchangeably, often within the same method** — both share the signature `($data, $message = 'Success', $status = 'success', $statusCode = 200)`.
- ⚠️ **Systemic bug — misordered `apiResponse()` arguments.** Several call sites pass only 3 arguments intending `($data, $message, $statusCode)`, but the third positional parameter is actually `$status` (a **string**), not `$statusCode` — the real `$statusCode` silently falls back to its default, **200**. PHP coerces the int into the string param rather than erroring, so these calls silently return HTTP 200 with a stringified status code as the `status` field (e.g. `{"status":"422", ...}` at HTTP 200) instead of the intended error status. Confirmed at (line numbers in `EnrollmentTrait.php` / `EnrollmentController.php` at time of writing):
  - `EnrollmentController::update()` — `$this->apiResponse([], 'Only one refund eligibility option can be selected', 422)` and `$this->apiResponse([], 'One refund eligibility option must be selected', 422)` (both intended 422, both actually return 200).
  - `EnrollmentController::update()`'s Edmingle-failure branch — `$this->apiResponse(['error' => 'Student is not added or removed at Edmingle'], 400)` — only **2** args passed here, so `400` lands in `$message` (coerced to the string `"400"`) and `$status`/`$statusCode` both stay at their defaults (`"success"`/200) — the response for a genuine Edmingle failure comes back looking like a routine success envelope with `message: "400"`.
  - `migrateBatch()`'s `QueryException` (MySQL error 1062, duplicate key) branch — `$this->apiResponse([], 'Batch is already exist in Database', 400)`.
  - `multipleMigrateBatch()`'s identical duplicate-key branch — same 3-arg call, same bug.
  - `saveCsvExportTemplate()` — both its validation-failure branch (`$this->apiResponse([], $validator->errors()->first(), 422)`) and its success branch (`$this->apiResponse($template->only(...), 'Template saved successfully', 201)`) use the 3-arg form — the "created" response for a new template is actually HTTP 200, not 201.
  This is a recurring authorship habit, not an isolated typo — treat any 3-argument `apiResponse(...)` call anywhere else in this module as suspect and verify its real HTTP status empirically rather than trusting the intended-looking third argument.
- ⚠️ **Two broken routes — undefined controller methods.** Neither of these can ever succeed:
  - **`DELETE /v1/enrollments/{enrollment}`** — the `destroy` action implied by `Route::apiResource('enrollments', 'EnrollmentController')`. No `destroy()` method exists anywhere in `EnrollmentController` or `EnrollmentTrait`, and there is no `__call` fallback on the base `Controller`. Hitting this route throws `Error: Call to undefined method Modules\Enrollment\Http\Controllers\EnrollmentController::destroy()` — an uncaught fatal PHP `Error`, surfaced as a 500 by Laravel's handler (not the standard `apiResponse` shape).
  - **`GET /v1/enrollments/batch-tracker`** (registered twice, at both `->name('enrollments.batch-tracker')` occurrences in the route file) — routed to `EnrollmentController::batchTracker`, which **does not exist anywhere in the codebase**. Same failure mode as above: an uncaught `Error`, not a clean 404.
  Also note `create`/`edit` (the two `apiResource` actions Laravel does *not* auto-register for an `apiResource`) were never expected here, so their absence is normal, not a bug.
- ⚠️ **Recurring crash pattern — unguarded `batch_title` → `CourseBatch` lookup.** At least five methods (`store()`, `resume()`, `addBatch()`, `migrateBatch()`, `multipleMigrateBatch()`) open with this exact shape:
  ```php
  if ($request['batch_status'] == 3) {
      $newBatch = $this->createNewBatch($request); // creates a new CourseBatch row
      $request->request->add(['batch_id' => $newBatch->id]);
  } else {
      $batchId = CourseBatch::where('batch_date', $request['batch_title'])->first();
      $request->request->add(['batch_id' => $batchId->id]);   // <-- unguarded
  }
  ```
  If `batch_status` isn't `3` (or isn't sent at all) **and** `batch_title` doesn't exactly match an existing `course_batches.batch_date` string, `CourseBatch::where(...)->first()` returns `null`, and `$batchId->id` throws `Error: Attempt to read property "id" on null` — an uncaught fatal 500, not a validation error. This is significant because **`batch_title`/`batch_status` are not part of `StoreEnrollmentRequest`'s validation rules at all** — a caller who supplies every field that FormRequest actually requires, and nothing else, will 500 on `POST /v1/enrollments` unless they also happen to pass a `batch_title` that resolves. (`addBatch()` alone logs an error before the crash instead of crashing silently; the other four give no warning.)
- **Activity logging is a mix of the `activity()` helper (Spatie Activitylog, `->by($causer)`) and direct `Activity::create([...])`** — the latter bypasses the package's usual causer-resolution convenience and requires the method to set `causer_id`/`causer_type` by hand; several call sites pass `causer_type: null` alongside a real `causer_id` (a schema inconsistency, not a functional bug, but worth knowing if a parity test asserts on `causer_type`).
- **Two separate, non-interoperable pause-log stores exist.** `EnrollmentPauseLogNew` (a real Eloquent model, table `enrollment_pause_log_new`) backs the student self-service pause/resume routes, the admin single `pause`/`resume` routes, and the pause/resume history listing/export. `EnrollmentPauseLog` (referenced via `use Modules\Enrollment\Entities\EnrollmentPauseLog;` in `EnrollmentTrait.php`, and separately in the unrelated `StudentMyCourses` module) **does not exist as a class anywhere in the codebase** — see the dedicated ⚠️ under "Admin bulk pause/resume" below; this is the module's single most severe confirmed defect.

---

## Core CRUD (`Route::apiResource('enrollments', 'EnrollmentController')`)

### `GET /v1/enrollments` — `index()` (controller)
Cursor-paginated listing (see `_COMMON_CONVENTIONS.md`'s "cursor-paginated `index()`" family) — query param `rows` (default 15, cast to int). Eager-loads a wide, hand-tuned set of relations with column whitelists for performance (`pauseLogs`, `course`, `referencePackage`, `package`, `batch`, `student`, `creator`, `batchAssigner`, `tags`, `comments` — capped to the 5 latest active ones — `studentAssignments` with nested `results`, `edmingleBatch`). Response: `EnrollmentResource::collection(...)->additional(['meta' => ['total','active','deactive','paused','resume_requested','pause_requested', 'range' => calculateRangeForCursor($rows)]])` — richer `meta` than the generic convention (adds per-status counts on top of `total`/`range`).

### `GET /v1/enrollments/{enrollment}` — `show()` (controller)
No relation eager-loading beyond what `EnrollmentResource` triggers lazily. `$this->apiResponse(['enrollment' => EnrollmentResource::make($enrollment)])`. Route-model-binding miss → the standard 404 `ModelNotFoundException` shape from `_COMMON_CONVENTIONS.md`.

### `POST /v1/enrollments` — `store()` (controller) — the direct/manual admin creation path
**Request** (`StoreEnrollmentRequest`): `course_id` required `exists:courses,id`; `reference_package` nullable `exists:packages,id`; `status` required, one of `Enrollment::PENDING(0)`/`ACTIVE(1)`; `country_id` required `exists:countries,id`; `email` required; `phone` required + `propaganistas/laravel-phone` mobile rule (ISO derived from `country_id` in `prepareForValidation()`); `name` required max:255; `batch_id` nullable `exists:course_batches,id`; `bootcamp_name` nullable max:255; `refund_eligible` nullable bool; `tags` nullable array of `{key,value}`. **Not validated by the FormRequest at all, but read directly off the request and load-bearing:** `batch_title`, `batch_status`, `ls_order_id`, `shift_assignments`, `default_course_id`/`default_batch_id`, `start_date`, `date_of_compilation`.
⚠️ See the module-wide crash note above — **this endpoint 500s** unless `batch_title` resolves to an existing `course_batches.batch_date` (or `batch_status == 3`, which creates a fresh batch from `batch_title`/`start_date`/`date_of_compilation` first). This runs unconditionally, before any of the FormRequest's own validation-driven fields are used for enrollment creation.
- Duplicate check: same `course_id`+`batch_id`+`student_id` already existing → `apiResponse('', 'This Student Is Already Enrolled with same batch for this course with active enrollment, Please try with another batch', 'error', 422)`.
- `course_id` may be sent as an **array** (despite the FormRequest's singular `exists:courses,id` rule, which Laravel's `exists` validates per-element for an array value) — each id becomes its own enrollment via the shared `createCourseEnrollment()` engine (see below); a scalar `course_id` takes the single-enrollment path, which additionally supports an `ls_order_id`-based re-association (`updateStudentCourseEnrollment()`) if a matching enrollment already exists for that order id.
- **Shared engine — `createCourseEnrollment($request, $student)`** (used by `store()`, `store_from_lawsikho`, `store_from_revenue`, `storeBootcampEnrollment`, `storeBootcampAdditionalEnrollment`, `addBatch()`'s package branch, etc.): computes `passing_criteria`/`dashboard_journey_steps`, sets `course_expiry_date`/`enrollment_expire_at` from the course's `duration_days`, generates `enrollment_code`, writes an `Activity::create()` row unconditionally, optionally dispatches `BatchsAssignmentsJob` (`default_high` queue) if `shift_assignments=='true'`, optionally links/creates an Edmingle batch and fires a **live outbound Edmingle API call** when `batch_status` is `2` (existing batch) or `3` (new batch), and emails `SUPPORT_MAIL` (`SendMailForStudentsCountInBatch`) if the target batch's student count lands in `100–103`.
- Also dispatches `SendStudentDataToExternalAPI::dispatch($student)` (queued, the same external job-portal registration call documented in `LawSikho.md`) on every successful path.
- **Success:** `$this->apiResponse(['enrollment' => EnrollmentResource::make($enrollment->fresh())], ...)` — for the array-`course_id` branch, no explicit success return exists inside the loop (relies on `$enrollment` from the last iteration); for the scalar branch, wrapped in `try { DB::transaction(...) } ` with **no catch block** — an exception inside the transaction propagates uncaught past `store()` entirely.

### `PUT/PATCH /v1/enrollments/{enrollment}` — `update()` (controller)
**Request** (`UpdateEnrollmentRequest`): `status` required (`PENDING`/`ACTIVE`); `comment` required max:200; `deactivation_reason` sometimes, one of `batch_cancel`/`others`; `other_reason` required if `deactivation_reason=='others'`; `refund_eligible`/`refund_eligibility_retained`/`refund_eligibility_transferred` sometimes bool.
- Guards, in order: reject activating an enrollment whose student is deactivated (`ValidationException`, message *"Enrollment cannot be activated when the student is deactivated."*); reject activating into a batch the student is already actively enrolled in for the same course (`ValidationException`); if deactivating a refund-eligible enrollment for `deactivation_reason=='course_pause'`, exactly one of `refund_eligibility_retained`/`refund_eligibility_transferred` must be set (⚠️ both these branches are among the misordered-`apiResponse` bugs above — always HTTP 200 despite intending 422); deactivating without a `deactivation_reason` → *"Deactivation reason is required when deactivating an enrollment."* (this one correctly passes `'error', 422`); `deactivation_reason=='others'` without `other_reason` text → similarly correct 422.
- Persists `status`/`updated_by`/resolved `deactivation_reason` via the repository, and `comment` via a direct model save.
- Refund-eligibility side effects on deactivation with `course_pause`: "retained" logs an activity only; "transferred" detaches the `{"en":"Refund Eligible"}` tag and logs; deactivating for any *other* reason while refund-eligible unconditionally detaches the tag and logs "removed".
- On `PENDING` (deactivation), makes a **live, unguarded `Http::post()`** to `config('app.ONBOARDING_API_BASE_URL') . '/student/batch/assign'` with `order_id`/`student_email`/`brand_id` — response is discarded (comment says "Handle the response and errors..." — it doesn't).
- Queues `EnrollmentUpdated` mail to the student on every call (both activation and deactivation).
- If a batch+Edmingle mapping exists, either assigns (activating) or removes (deactivating) the student on the Edmingle side; ⚠️ if that call reports an error, the buggy 2-arg `apiResponse(['error'=>...], 400)` fires (see above — actually returns 200).
- Conditionally dispatches `HandleMissedAssignments` (if `add_missed_assignments` truthy on activation) and `SyncEnrollmentWithCourseCalendarJob` (`enrollment_active`/`enrollment_deactive`) on the `default_medium` queue.
- **Success:** `$this->apiResponse(['enrollment' => EnrollmentResource::make($enrollment->fresh())], 'Enrollment updated successfully')`.

### `DELETE /v1/enrollments/{enrollment}` — **broken, see module-wide note above.**

`EnrollmentResource` fields (all four working CRUD endpoints): raw columns `status`,`enrollment_code`,`bootcamp_id`,`course_expiry_date`,`batch_assigning_eligibility`,`enrollment_expire_at`,`total_exercises`,`is_certified`,`enrollment_code_created_at`,`id`,`course_calendar_map`, plus computed `bootcamp_name`, `created_at` (reformatted), nested `course`/`batch_assigner`/`creator`/`package`/`reference_package`/`batch`/`student` (each a narrow projection), `is_written` (hardcoded category-id-8 check), `type` (derived label: Package With Batch/Package/Bootcamp/Standard), exercise-completion counts, `comments` (sorted desc, mapped), `tags` (only if eager-loaded), `edmingle_batch_name`, `refund_eligibility_exists` (cast to int), **`pausable_status`** (resolved by instantiating `app(EnrollmentController::class)->isEnrollmentPausable($this->resource)` from inside the Resource — an unusual pattern that re-invokes controller logic per row), `original_enrollment_id`/`original_enrollment_date` (self-fallback if unset), `paused_at`, `pause_reason`, `is_course_paused` (derived from the latest `pauseLogs` entry's status), `refund_eligible_pause_request_status`/`_time`.

---

## Certification

### `POST /v1/enrollments/certify` — `certify()` (trait)
Inline `Validator`: `enrollment_ids` required array, each `exists:enrollments,id`. Calls `enrollmentRepo->updateCertifiedStatus($ids, auth()->user()->id)`. `$this->apiResponse([], 'Enrollments certified successfully')`.

### `POST /v1/enrollments/un-certify` — `unCertify()` (trait)
Same shape, `updateEnrollmentToUnCertifiedStatus($ids)`. `'Enrollments un certified successfully'`.

### `PUT /v1/enrollments/certificate/status/update` — `updateCertifiedStatus()` (trait)
Inline `Validator`: `enrollment_id` required `exists:enrollments,id`; `status` required, one of `Enrollment::CERTIFIED`/`NOT_CERTIFIED`.
⚠️ **Confirmed bug — assignment instead of comparison.** The update array is:
```php
$this->enrollmentRepo->update($data['enrollment_id'], [
    'is_certified' => $data['status'],
    'certified_by' => ($data['status'] = Enrollment::NOT_CERTIFIED ? null : auth()->user()->id),
    'certified_datetime' => ($data['status'] = Enrollment::NOT_CERTIFIED ? null : now())
]);
```
The author wrote `=` where `==` was intended. Because PHP's ternary binds tighter than `=`, this parses as `$data['status'] = (Enrollment::NOT_CERTIFIED ? null : auth()->user()->id)` — i.e. it evaluates the **constant** `Enrollment::NOT_CERTIFIED` (which is `0`, always falsy on its own, never compared to the submitted value) as the ternary condition, always takes the "else" branch, and *overwrites* `$data['status']` as a side effect. Net effect: `is_certified` correctly reflects the submitted status (its array element is evaluated first, before the clobbering), but **`certified_by` is always set to the acting admin's id and `certified_datetime` is always set to `now()` — even when the request is un-certifying an enrollment (`status = NOT_CERTIFIED`)**. A parity test toggling an enrollment to not-certified should expect `certified_by`/`certified_datetime` to be nulled out, but this endpoint never nulls them.
**Success:** `$this->apiResponse([], 'Enrollment status updated successfully')` regardless.

### `PUT /v1/enrollments/{enrollment}/update/mcq` — `updateMcq()` (trait)
`Validator::make(...)->validate()`: `mcq_score` required numeric min:1 max:100 (`$this->maxLength` = `'max:100'`); `mcq_completed` required, one of `Enrollment::MCQ_COMPLETED(1)`/`MCQ_NOT_COMPLETED(0)`. Direct `$enrollment->update($data)`. `apiResponse([], 'Enrollment mcq score updated successfully')`.

---

## CSV import & export

### `POST /v1/enrollments/import` — `importFile()` (trait)
**Request** (`EnrollmentCsvImportRequest`): `file` required, broad CSV/plain-text mimetype allowlist; `instruction_files.*`/`feedback_files.*` nullable file (pdf/doc/docx/zip) — **these two fields are validated but never referenced anywhere in the method body**, dead validation.
- Parses the CSV header via League CSV (`Reader::createFromString`) and validates it's **exactly** the set `Course,Full Name,Email,Phone,Batch,Reference Package` (order-insensitive, via `header.*` => `in:...`).
- Per-column validation: `email.*` required email; `full_name.*` required max:255; `phone.*` required (no format check, unlike every other phone field in this codebase); `course.*` required `exists:courses,id`; `batch.*` required `exists:course_batches,id`; `reference_package.*` nullable `exists:packages,id`. ⚠️ Despite the header labels reading "Course"/"Batch", the actual cell values must already be **numeric ids**, not names — a CSV built with human-readable batch/course names will fail validation with a generic "field.N does not exist" message, not a clear "expected an id" message.
- Uploads the raw file to S3 (`imports/enrollments/`), then dispatches `EnrollmentCsvImport::dispatch(...)` on the `default_high` queue — **fire-and-forget**, actual row-by-row enrollment creation happens asynchronously; the response gives no indication of success/failure per row.
- **Success:** `$this->apiResponse('', 'Enrollments creation started by csv file')`.

### `GET /v1/enrollments/export/csv` — `export()` (trait)
No params consumed beyond the raw request forwarded to the job. Dispatches `EnrollmentCsvDownload::dispatch($user, $request->all())` on `default_medium`. `apiResponse('', 'Enrollment Csv file exporting started')`.

### `GET /v1/enrollments/books/export/csv` — `exportBooksList()` (trait)
`type=international` query param branches to `InternationalEnrollmentBookCSVDownload`, else `RegularEnrollmentBookCSVDownload` — both dispatched, both fire-and-forget with an immediate "exporting started" response.

### `EnrollmentCSVReportController` (separate controller, same module) — `enrollment-csv-report` (GET/POST) and `enrollment-csv-report-export/{enrollment_csv_report}`
- `store()` on this controller is an **empty-body dead stub** (`# code...`) — not wired to any route (the actual POST route targets `enrollment_csv_store`, a different method, in `EnrollmentCSVReportTrait`). Flagged per the "dead `apiResource` stub" trap, though technically this isn't an `apiResource`-generated route — it's simply unused scaffolding left in the controller.
- `GET enrollment-csv-report` → `enrollment_csv_report()`: cursor-paginated list of past CSV-report rows (`rows` query param), `EnrollmentCSVReportResource::collection(...)->additional(['meta'=>[...]])` with several hardcoded-zero `meta` fields (`total_completed`, `total_mcq_confirmation`, `total_certified`, `total_incompleted` — dead/unimplemented stats). `EnrollmentCSVReportResource`: `id`, `created_at` (reformatted), `download_link` (raw stored path, **not actually a usable URL** — see below), `file_name` (basename extracted from the path), `user` (only `id`,`full_name`).
- `POST enrollment-csv-report` → `enrollment_csv_store()` (`EnrollmentCsvImportRequest`): runs `Modules\Enrollment\Imports\EnrollmentImport::import()` synchronously (not queued, unlike `importFile()` above), then stores the uploaded file to the **`public` disk** (not S3, unlike every other file-upload endpoint in this module) under `uploads/enrollment_csv_report/`, and writes an `EnrollmentCSVReport` row with `file_name` set to a full `asset()` URL. On a Maatwebsite Excel `ValidationException`, `return $e->failures();` — returns the raw validation-failures array **with no envelope and no explicit status code (defaults to 200)**, a completely different error shape from the rest of the app. Success: `$this->apiResponse('', 'Enrollments created by import file')`.
- `GET enrollment-csv-report-export/{enrollment_csv_report}` → `enrollment_csv_report_export()`: `return $enrollment_csv_report->getFirstMedia('enrollment_csv_report');` — reads from the Spatie Media Library collection `enrollment_csv_report`. ⚠️ **The import path above never actually attaches media to that collection** (the `addMediaFromRequest(...)->toMediaCollection('enrollment_csv_report')` call is commented out in `enrollment_csv_store()`) — so this export endpoint will return `null` (serialized as the JSON literal `null`, HTTP 200) for every report created through the live import flow, never a real file.

---

## Package / bootcamp / additional enrollment creation

### `POST /v1/enrollments/package` — `storePackageEnrollment()` (trait)
`StorePackageEnrollmentRequest`: `package_id` required `exists:packages,id`; `student_id` required `exists:students,id`. **Fire-and-forget**: dispatches `StorePackageEnrollmentJob` (`default_medium`) and immediately returns `$this->apiResponse([], 'Enrollment created successfully...', statusCode: 201)` — the 201 says nothing about whether the job actually created anything (per the cross-cutting caution in `_COMMON_CONVENTIONS.md`).

### `POST /v1/enrollments/bootcamp` — `storeBootcampEnrollment()` (trait)
`StoreBootcampEnrollmentRequest`: `bootcamp_id` required `exists:bootcamps,id`; `student_name`/`student_email`/`student_phone`/`country_id` required.
- **External call:** makes a live `Http::get()` to `config('services.lawsikho.url') . '/api/v1/enrollmentForm/getOfferBundle?id={bootcamp_id}'` to fetch the list of courses (and "written courses") belonging to the bootcamp — this is a genuine, non-mockable-in-this-app external dependency; a parity test needs a stub/sandbox for the LawSikho revenue site itself for this endpoint to be testable at all.
- If the student already exists: rejects with a 422 if the external call returned zero courses (`{bootcamp_name} has no course associated. Please contact tech team.` — message built from `$this->noCourseInBootcamp`), or if the student is **already** enrolled in this bootcamp (422, `"{bootcamp_name} bootcamp already associated with this student"`). Otherwise creates one enrollment per returned course (and one per "written course") via `createEnrollmentsForBootcamp()` → `createCourseEnrollment()`.
- If the student doesn't exist: creates one (auto-generated password, mailed), then runs the same course-enrollment loop.
- **Success:** `$this->apiResponse([], $this->enrollmentCreated, statusCode: 201)` regardless of how many courses ended up enrolled.

### `POST /v1/enrollments/bootcamp/additional` — `storeBootcampAdditionalEnrollment()` (trait)
Inline `Validator`: `bootcamp_id`/`course_id`/`student_id` all required + `exists`. Requires the student to already have *some* enrollment in that bootcamp (422 `"Student is not enrolled in the bootcamp"` otherwise). Creates one additional course enrollment via `createCourseEnrollment()`, tags it `Additional` (`sync`, not `attach` — replaces any prior tags on that specific new enrollment row, though since it's a brand-new row this is moot in practice). `$this->apiResponse([], 'Enrollment created successfully', statusCode: 201)`.

### `POST /v1/enrollments/bulk-additional` — `storeBulkAdditionalEnrollment()` (trait)
Inline `Validator`: `file` required, `mimes:csv,txt`; `course_ids` required array (each `exists:courses,id`); `comment` nullable max:1000. Uploads to S3 (`imports/enrollments/`), creates a `BulkEnrollmentReport` row (`status: STATUS_PROCESSING`, counts all zeroed initially), dispatches `BulkAdditionalEnrollmentJob` (unqueued call shown as bare `::dispatch(...)`, no explicit `onQueue`) to process the CSV asynchronously (bootcamp is resolved per-row from the CSV, not from a request field). **Success:** `$this->apiResponse(['report_id' => ..., 'message' => 'Bulk enrollment processing started'], 'Processing initiated', statusCode: 200)` — immediate, tells the caller nothing about eventual per-row outcomes; the `BulkEnrollmentReport` row must be polled separately (no documented polling endpoint found in this route file).

---

## Search & reference lookups

- **`GET /v1/search/enrollments`** — `search()`: `SearchEnrollmentResource::collection(...)->additional(['meta'=>['total'=>...]])`, the standard Resource-collection shape. `SearchEnrollmentResource` is minimal: `{id, enrollment_code}` only.
- **`GET /v1/search/specific-enrollments`** — `searchEnrollmentsWithArray()`: `apiResponse($this->enrollmentRepo->searchEnrollmentsWithArray())` — a raw repository-returned array wrapped once, not a Resource collection; shape is whatever the repository method returns (not independently verified against a Resource contract).
- **`GET /v1/search/bootcamp`** — `search_bootcamp()` (controller): merges results from **two different sources** — the `bootcamps` table (id/name/title, `LIKE`-searched) **and** distinct `bootcamp_id`/`bootcamp_name` pairs pulled directly off old `enrollments` rows that predate normalized bootcamp records — deduplicated by id and by display name, bootcamps-table entries taking priority on conflict. `response()->json(['data'=>..., 'meta'=>['total'=>...]])`.
- **`GET /v1/search/specific-bootcamp`** — `searchBootcampWithArray()`: thin `apiResponse($this->enrollmentRepo->searchBootcampWithArray())` wrapper.
- **`GET /v1/enrollments/total`** — `total()`: `apiResponse(['total'=>..., 'active'=>..., 'deactive'=>...])` — three repository aggregate counts, no filters.
- **`GET /v1/enrollments/dashboard/list`** — `enrollmentsDashboardData()`: cached 30 minutes (`Cache::remember('dashboard.student_assignments.data', 1800, ...)`) — **the cache key is global, not scoped by any request parameter**, so all callers share one cached snapshot regardless of who's asking. Returns 7/30/90-day enrollment and student counts plus a Google-Charts-shaped `bar` array (literal `'{role: "annotation"}'` strings embedded as array values — a very specific, easy-to-break shape if a parity test tries to generically diff this array).
- **`GET compare-batch`** — `compareBatch()`: `batch_title` required, `course_id` required `exists:courses,id`. Looks up the batch by `batch_date` (no crash guard here — wrapped in an `if ($batch)` check, unlike the sibling methods with the same lookup pattern). Returns `{"status":1,"data":{start_date,date_of_compilation}}` if an Edmingle batch mapping also exists for that course, `{"status":2,"data":{...}}` if the batch exists but has no Edmingle mapping, `{"status":3}` (no `data` key at all) if no batch matches — **all three branches return HTTP 200**, differentiated only by the `status` integer.
- **`GET edmingle-tutors`** — `getTutors()`: live outbound `Http::get()` to Edmingle's `organization/tutors` endpoint (optionally filtered by a `search` query param), SSL verification explicitly disabled (`'verify' => false`). Returns `{"data": [...tutors]}` on success with tutors present, `{"error": "No tutors found"}` if the Edmingle payload's `tutors` key is empty/missing (still HTTP 200), `{"error": "API request failed"}` at Edmingle's own status code if the HTTP call itself failed, or `{"error": <exception message>}` at 500 on a thrown exception.

---

## Batch assignment

### `POST /v1/enrollments/add/batch` — `addBatch()` (trait)
`StoreBatchRequest`: `enrollment_ids` required array, each `exists:enrollments,id`; `batch_title` required; `status` required; `refund_eligible` nullable bool.
- Manually opens `DB::beginTransaction()` (not the `DB::transaction()` closure form) — ⚠️ the entire method body that follows was originally wrapped in a `try {...} catch (QueryException...) catch (\Exception...)` block that is now **entirely commented out** in source, leaving `DB::beginTransaction()` active with **no corresponding rollback path** on any exception (including the same `batch_title`-lookup crash pattern noted at the top of this file, which this method hits too, though it does at least log an error first here). An uncaught exception mid-method leaves the transaction to be implicitly rolled back only by the DB connection closing at request end, not by explicit application logic.
- Per enrollment id: package enrollments spawn a **new** `Enrollment` row of `type: PACKAGE_BATCH_ENROLLMENT` (the original package enrollment is marked `batch_assigning_eligibility: NOT_ELIGIBLE` rather than deleted); regular/bootcamp enrollments have their **existing** row updated in place with the new `batch_id`. Both paths reject (422, single-enrollment call) or flag-and-continue (multi-enrollment call) if the student already has an active enrollment for that exact course+batch.
- Refund-eligibility tag handling, Edmingle batch creation/assignment (`status` 1/2/3 branches mirroring `createCourseEnrollment()`), a bulk revenue-API update call, optional old-assignment-shifting (`shift_batch=='true'`), and — for multi-enrollment calls — a `BatchAssignmentSummaryJob` admin-summary email (CSV via job) plus individual `BatchAdded` emails per successfully-assigned student. Single-enrollment calls instead send one `BatchAdded` email inline.
- **Success:** `$this->apiResponse($responseData, $responseMessage)` where `$responseData` may include an `edmingle_failures` array (Edmingle-side failures don't fail the whole request — the batch assignment itself is still committed) and `$responseMessage` is built up conditionally ("Batch id added to enrollments successfully" / a partial-failure variant / an Edmingle-failure-count suffix).

---

## Bulk activation / deactivation

### `POST /v1/enrollments/make/active` — `activate()` (trait)
Inline `Validator`: `ids` required array (each `exists:enrollments,id`); `comment` required max:100. Per enrollment: rejects (adds to a `failed` list, does not abort the whole batch) if the student is deactivated, or if the student already has another active enrollment for the same course+batch; otherwise flips `status` to `ACTIVE` and writes an `Activity::create()` row. On any successes, dispatches `EnrollmentActivatedJob` (per-student emails) and `StudentAddJob` (Edmingle sync + admin summary email to `techteam@lawsikho.in` plus the acting admin) both on `default_high`; on zero successes but some failures, dispatches `EnrollmentStatusChangeSummaryJob` instead. **Success:** `$this->apiResponse(['successful_count'=>N, 'failed_count'=>N], $message)` — no per-enrollment detail returned in the response body itself (unlike the newer bulk pause/resume endpoints below), though the dispatched jobs receive the full detail arrays.

### `POST /v1/enrollments/make/deactive` — `deactivate()` (trait)
Same validation shape. Unconditionally deactivates every listed enrollment (`status: PENDING`) and updates its `comment` — **no eligibility checks at all** (unlike `activate()`, there's no "already deactivated" or "student state" guard). Dispatches `EnrollmentDeactivationJob` and `StudentRemoveJob` (both `default_high`) when at least one succeeded. `$this->apiResponse(['successful_count'=>N], $message)`.

---

## Activity log

### `GET /v1/enrollments/{enrollment_id}/activity` — `activity()` (trait)
`{enrollment_id}` is a plain int, **not** route-model-bound (checked manually via `enrollmentRepo->findById()`) — a non-existent id returns a clean `apiResponse([], 'Enrollment Not Found', 'error', 404)` rather than the generic `ModelNotFoundException` shape. On success, delegates to the shared `logOfEnrollment()` helper (`app/Http/Traits/ActivityLog.php`) — cursor-paginated (`rows` query param, `Activity::paginate($rows, $columns, 'cursor')`) `ActivityResource::collection`, `meta` carries `next_page_url`/`prev_page_url`/`range`.

---

## Migration (batch / course / bootcamp)

All three "migrate" endpoints follow the same core pattern: **create a brand-new `Enrollment` row for the destination, deactivate the source row** (`status: PENDING`, a distinct `deactivation_status` enum value per migration type), rather than mutating the original in place — this preserves enrollment history but means a parity test must track the *new* enrollment id returned implicitly via side effects (none of the three return the new enrollment's id directly in their response body — see each below).

### `POST /v1/enrollments/migrate_batch/{enrollment}` — `migrateBatch()` (trait)
Hits the same unguarded `batch_title`/`batch_status` crash pattern described at the top of this file (this is the method the pattern likely originates from, given the docblock-free copy/paste across the other four). Validates `batch_id` (post-resolution) `required|exists:course_batches,id|integer`, `comment` required, `refund_eligible` nullable bool. Rejects (422) if the student already has an active enrollment in the target course+batch. Creates the new enrollment via `enrollmentRepo->create()` (a hand-rolled duplicate of much of `createCourseEnrollment()`'s field set, not a call to that shared method), calls the revenue-update webhook, generates a new `enrollment_code`, attaches a "Batch Migrated" tag (looked up by exact JSON-encoded name `{"en":"Batch Migrated"}`, created if missing), leaves a `DeactivatingComment` on the old enrollment noting the destination, logs a dedicated `batchMigrationLog()` activity entry keyed off the *second-latest* enrollment for that course+student (a fragile way to find "the previous one"), optionally shifts old assignments/creates new ones, and removes the student from the old Edmingle batch (extensively logged on every failure branch, but none of those failures block success). **Success:** `apiResponse('', 'Batch migrated successfully')`. Catches `QueryException` (1062 → the buggy 3-arg `apiResponse` noted above; anything else → 500) and generic `\Exception` (→ 422 with the raw exception message as the user-facing `message`, which may leak internal detail).

### `POST /v1/enrollments/migrate_course/{enrollment}` — `migrateCourse()` (trait)
No `batch_title` crash risk (works directly off validated `course_id`/`batch_id`). `course_id` required `exists:courses,id`; `batch_id` nullable `exists:course_batches,id` (course-only migration, no batch, is explicitly supported — several fields conditionally null out if `batch_id` isn't sent); `comment` required; `refund_eligible` nullable bool. Same create-new/deactivate-old/tag/comment/Edmingle-removal pattern as `migrateBatch()`, scoped to a course change instead.

### `POST /v1/enrollments/migrate_bootcamp/{enrollment}` — `migrateBootcamp()` (trait)
`bootcamp_id` required int. Unlike the other two, this does **not** create any new enrollment rows — it assumes the student **already has** existing (non-`PENDING`) enrollment(s) tagged to the destination `bootcamp_id`, and just re-tags those as "Bootcamp Migrated" while deactivating the student's enrollments under the *old* `bootcamp_id` (`deactivation_status: BOOTCAMP_MIGRATION_DEACTIVATION`). ⚠️ **Crash risk:** `$bootcampEnrollments->first()->bootcamp_name` is called unguarded — if the student has **no** existing enrollment for the target bootcamp (the more likely real-world case for a genuine migration), `first()` returns `null` and this throws. `apiResponse('', 'Bootcamp migrated successfully')` on the happy path only.

### `POST /v1/multiple_migrate_batch` — `multipleMigrateBatch()` (trait)
Same `batch_title`/`batch_status` crash-prone resolution up top, **not wrapped in any exception handling** for that specific line (only a `try` around the whole rest of the method that catches `QueryException` alone — a bare `\Exception`, including the batch-lookup `Error`... note `Error` is not caught by `catch (QueryException $e)` either, so it's genuinely uncaught here too). Validates `batch_id` `required|exists:course_batches,id|integer`. **Fire-and-forget**: dispatches `MultipleEnrollmentBatchMigration` (not queued via `->onQueue()`, so it runs on the app's default queue) and calls `DB::commit()` — ⚠️ **note there is no preceding `DB::beginTransaction()` anywhere in this method**, so this `DB::commit()` call has nothing to commit (Laravel's `DB::commit()` is a no-op when the transaction-nesting counter is already zero — harmless but dead code). Returns `apiResponse('', 'Batch migrated successfully')` **before the actual per-enrollment migration has happened** (it's all inside the dispatched job) — a stronger instance of the "2xx doesn't mean it worked" caution than most, since literally none of the migration logic has executed yet when this response is sent. If the `QueryException` catch's `errorInfo[1] !== 1062` branch is hit, the method falls through with **no `return` statement at all** — PHP implicitly returns `null`, which Laravel cannot serialize as an HTTP response and will itself error on.

---

## Refund eligibility

### `GET check-refund-eligible/{enrollment}` — `checkRefundEligibleInBootcampAndPackage()` (trait)
Query param `slug` (optional, maps to an internal event-slug for `batch_migrate`/`course_migrate` context — otherwise ignored). If the enrollment already carries a `"Refund Eligibility Foregone"` tag, short-circuits with `apiResponse(0, "Cannot add refund eligibility. This enrollment has been marked as \"Refund Eligibility Foregone\"...", 'success', 200)` — note the **`data` payload is the bare integer `0`**, not an object, and the envelope's `status` is `"success"` even though this is effectively a rejection — a real instance of the "2xx success-shaped body on a semantic no-op" caution. Otherwise checks bootcamp/package-level capacity for the refund-eligible tag (delegates to `hasRefundEligibleCourseInBootcamp`/`hasRefundEligibleCourseInPackage`) and returns `data: 1` (eligible) or `data: 0` (not eligible, with an explanatory `message`) — same bare-integer `data` shape either way.

### `PATCH enrollments/{enrollment}/refund-eligible/{tag}` — `editRefundEligibleTag()` (trait)
`{tag}` path segment is actually named `$removeTag` in the method signature and is a **string** `"true"`/`"false"` — ⚠️ **counter-intuitively named**: `$removeTag == "true"` means **add** the tag (checked against the "foregone" tag first, rejecting with 422 if present), and `$removeTag == "false"` means **remove** it. Requires `batch_id` to already be set on the enrollment (422 `"Please assign batch first"` otherwise). For a standalone enrollment (no `bootcamp_id`/`package_id`), directly attaches/detaches the `{"en":"Refund Eligible"}` tag and logs. For a bootcamp or package enrollment, delegates to `bootcampEnrolmentEdit()`/`packageRefundEligibilityEdit()`, which enforce a **per-bootcamp/package capacity limit** (`Bootcamp::refund_eligible_course`, default 1) counted across the student's other active-batch enrollments in the same bootcamp/package. The whole method is wrapped in a `try/catch (\Exception $e) { Log::error(...); }` with **no `return` in the catch** — any exception (including from the capacity-limit branches, which `throw new \Exception(...)` directly rather than returning an error response) results in an implicit `null` return, another Laravel-response-serialization failure case.

### `PATCH enrollments/{enrollment}/refund-eligibility-foregone` — `updateRefundEligibilityForegone()` (trait)
`refund_eligibility_foregone` required bool; `comment` nullable string. Adding the "foregone" tag on a **bootcamp** or **package** enrollment cascades to every other active (non-`PENDING`) enrollment the same student has in that same bootcamp/package — attaching the foregone tag to all of them and detaching "Refund Eligible" from all of them; removing it is scoped the same way. A standalone enrollment only affects itself. Wrapped in a real `DB::beginTransaction()`/`DB::commit()`/`catch(\Exception){DB::rollBack(); return apiResponse([], $e->getMessage(), 'error', 500);}` — unlike most of this module's error handling, this one is complete and correctly shaped (genuinely returns 500 with the caught message, and does roll back). **Success:** `apiResponse(['has_foregone_tag' => bool], $message)`.

---

## Admin bulk pause / resume (`make/pause`, `make/resume`) — ⚠️ confirmed broken

Both were added per an in-source comment block ("Added by: Copilot, Date: 25th February 2026") as a bulk alternative to the older single-enrollment `pause`/`resume` endpoints below. **Both reference a model class, `Modules\Enrollment\Entities\EnrollmentPauseLog`, that does not exist anywhere in the codebase** (confirmed: no such file under `Modules/Enrollment/Entities/`, no matching migration — only `EnrollmentPauseLogNew` exists, a different class backing every other pause/resume endpoint in this module).

### `POST /v1/enrollments/make/pause` — `pauseEnrollment()` (trait)
Inline `Validator`: `ids` required array (each `exists:enrollments,id`); `reason` nullable max:500; `notification_emails` nullable array of emails. Per enrollment, rejects (adds to a `failed` list) if already `PAUSED` or not currently `ACTIVE`; otherwise, inside `DB::transaction()`, updates the enrollment to `PAUSED` and then calls `EnrollmentPauseLog::create([...])`.
⚠️ **This `EnrollmentPauseLog::create()` call throws an uncaught fatal `Error: Class "Modules\Enrollment\Entities\EnrollmentPauseLog" not found`.** Because `\Error` and `\Exception` are siblings under `\Throwable` (not parent/child), `DB::transaction()`'s own internal `catch (Throwable $e)` rolls the transaction back and re-throws — but there is **no surrounding `try/catch` in `pauseEnrollment()` at all** to intercept that re-thrown `\Error`. The very first eligible enrollment in the `ids` array will crash the entire request with an uncaught 500 (the enrollment-status update is rolled back, so no partial state persists, but the caller gets a raw Laravel exception page/JSON, not the graceful `successful`/`failed` per-enrollment response this endpoint was designed to return). **This endpoint cannot succeed for any enrollment that passes eligibility.**

### `POST /v1/enrollments/make/resume` — `resumeEnrollment()` (trait)
Inline `Validator`: `ids` required array; `comment`/`new_batch_id`/`shift_assignments`/`shift_batch`/`refund_eligible`/`refund_eligibility_foregone`/`status`/`notification_emails` all optional. Two modes:
- **Mode 1 (same batch, no `new_batch_id`)** — reactivates the enrollment (`status: ACTIVE`), then calls `EnrollmentPauseLog::create(...)` inside a bare `DB::transaction()` with **no try/catch anywhere around it** (not even the `catch (\Exception)` that Mode 2 has). Hits the identical missing-class crash — **every call to this endpoint without `new_batch_id` fatally errors on the very first paused enrollment it processes**, killing the request outright before any response-building code runs.
- **Mode 2 (`new_batch_id` present)** — replicates `migrateBatch()`'s entire flow (new enrollment in the target batch, revenue update, refund-eligibility tag handling, Edmingle batch assign/create, `EnrollmentPauseLog::create()` again, activity logs) inside a `try { DB::transaction(...) } catch (\Exception $e) { ...; $failedResumes[] = [...]; }`. The `EnrollmentPauseLog::create()` call here hits the same missing-class `\Error` — and because the catch is typed `\Exception`, **it still does not catch it**; the error propagates out of `resumeEnrollment()` entirely, uncaught, exactly as in Mode 1. **Neither mode of this endpoint can complete successfully as currently deployed.**

Both methods, had the class existed, would have dispatched `EnrollmentPauseResumeSummaryJob` (only if `notification_emails` was supplied) and returned `$this->apiResponse(['successful_count','failed_count','successful','failed'], $message)` — this is the *intended* shape, useful to know for what AP-V3 should probably reproduce even though the current app cannot exercise it end-to-end.

---

## Admin single pause / resume, and pause-log/status

These use the working `EnrollmentPauseLogNew` model and are functionally sound (unlike the bulk pair above).

- **`POST enrollments/pause/{enrollment}`** — `pause()`: rejects via `isEnrollmentPausable()` (see below) with 403 if not pausable, or 422 if already `PAUSED`. Sets `status: PAUSED`, `pause_status`, `paused_at`, `pause_reason` (from `comment`, default `"Admin initiated pause"`), stamps `original_enrollment_id`/`original_enrollment_date` if not already set (first-time-paused bookkeeping). Creates an `EnrollmentPauseLogNew` row (`request_source: 'support'`). If the student has an Edmingle-mapped batch, removes them from it (failures logged, non-fatal). `apiResponse([], 'Enrollment paused successfully.')`.
- **`POST enrollments/resume/{enrollment}`** — `resume()`: requires current status `PAUSED` or `RESUME_REQUESTED` (422 otherwise). If `batch_id`/`batch_title` supplied, performs a full migration-as-resume (identical `batch_title` crash-pattern risk, identical duplicate-enrollment check, identical refund-eligibility/Edmingle/tag machinery as `migrateBatch()`) — otherwise just flips the existing enrollment back to `ACTIVE` in place. Uses `EnrollmentPauseLogNew` correctly (no crash here).
- **`GET enrollments/pause-status/{enrollment}`** — `pauseStatus()`: `apiResponse($this->isEnrollmentPausable($enrollment))`. `isEnrollmentPausable()`: not pausable if no batch assigned, already `PAUSED`, or tagged `{"en":"Refund Eligible"}` — returns `{pausable: bool, reason?, code?}`.
- **`POST enrollments/reject-pause/{enrollment}`** — `rejectPauseRequest()` (controller, delegates to `rejectPauseRequestedEnrollment()` in the trait): only acts if status is `PAUSE_REQUESTED` — reactivates to `ACTIVE`, marks the latest matching `EnrollmentPauseLogNew` row `rejected: 1`. Returns a **hand-rolled `response()->json([...])`** (not `apiResponse`) — `{"status":"success","message":"..."}` on success, `{"status":"error","message":"Enrollment status is not pause requested."}` at HTTP 400 otherwise (a genuinely correctly-coded 4-arg-equivalent call, since this bypasses `apiResponse()` entirely).
- **`GET enrollments/pause-log/{enrollment}`** — `pauseLog()` (controller, delegates to `enrollmentPauseLog()`): `response()->json(['status'=>'success', ...formattedLogData])` — a flattened, non-`apiResponse` shape with `data` (formatted, human-readable per-entry titles like `"Paused (2)"` counting occurrences of that status), plus `refund_eligible_pause_request_status`/`_time`.

---

## Pause/resume history listing, CSV export, and export templates

### `GET /v1/enrollments/pause-resume/history` — `pauseResumeHistory()` (trait)
⚠️ **Uses standard Laravel page-number pagination** (`per_page`/implicit `page` query params, `->paginate($perPage)`) — a **third pagination style**, distinct from both families documented in `_COMMON_CONVENTIONS.md` (it's neither the `{data,meta:{total}}` Resource-collection shape nor the `rows`/`cursor` convention). Query is built off the **latest `EnrollmentPauseLogNew` row per enrollment** (`MAX(id) GROUP BY enrollment_id`), so history reflects each enrollment's *current* pause/resume state, not a full timeline (the full per-enrollment timeline is nested separately via `PauseResumeHistoryResource`'s `status_history`). Supports filters: `status` (with a synthetic `..._rejected` variant that filters on `rejected=1`), `enrollment_id`, `paused_from`/`paused_to`, `resumed_from`/`resumed_to`, `course_name` (LIKE), `course_id`/`batch_id`/`student_id` (arrays via `whereIn`), free-text `search` (enrollment code / student name / email), `from_date`/`to_date`, `sort_by` (whitelisted to `created_at`/`paused_at`/`resumed_at`/`status`) / `sort_order`. **Success:** a flattened custom shape (not the standard `{data,meta}`) — `data`, `current_page`, `per_page`, `total`, five separate `total_*_count` stat fields, `last_page`, `from`, `to`, `previous_page_url`, `next_page_url`, all as top-level siblings inside `apiResponse()`'s `data` key.

### `GET /v1/enrollments/pause-resume/history/export` — `pauseResumeHistoryCSVExport()` (trait)
Accepts the same filter set as the listing above, plus an optional `fields` array (whitelisted against `self::$PAUSE_RESUME_EXPORT_FIELDS`, falling back to all 14 known fields if omitted/empty). Fire-and-forget: dispatches `PauseResumeHistoryCSVExportJob`, returns `$this->apiResponse([], 'CSV export started. You will be notified once the file is ready for download.')` immediately.

### `GET/POST/DELETE enrollments/pause-resume/export-templates` — saved-filter-field templates
- `listCsvExportTemplates()`: lists `CsvExportTemplate` rows scoped to `export_type='pause_resume_history'` (**not scoped to the current user** — any authenticated admin sees every admin's saved templates), plus the full `available_fields` catalog.
- `saveCsvExportTemplate()`: `name` required max:100; `fields` required array (each must be one of the known field keys). ⚠️ Both its validation-failure and success responses use the buggy 3-arg `apiResponse()` form noted at the top of this file — the validation-failure branch returns HTTP 200 (not 422) and the success branch returns HTTP 200 (not 201).
- `deleteCsvExportTemplate($template)`: **is** scoped to the current user (`where('user_id', auth()->id())`) and to `export_type='pause_resume_history'` — `firstOrFail()` throws the standard `ModelNotFoundException` 404 shape if the template doesn't belong to the caller or doesn't exist. `apiResponse([], 'Template deleted successfully')`.

`PauseResumeHistoryResource` (backs the listing above): a dense, hand-built shape per log row — `id`, `enrollment_id`, `enrollment_code`, `status`, `display_status` (human label, with special-cased "Pause Request Approved/Rejected" wording), nested `student`/`course`/`batch` (each with `'N/A'` string fallbacks rather than `null`), `enrollment_type` label, a `match`-computed `enrollment_status` label, `pause_status`, `paused_at`/`paused_reason`, `resumed_at` (falls back to `created_at` if the log's own status is `resumed` but `resumed_at` itself is unset), `resumed_by`/`performed_by` (resolved from either `pausedByStudent` or `resumedByAdmin` relations), `resumed_requested_date`, `accepted`/`rejected` (cast to bool from `==1`), a conditionally-spread `resume_type` key (only present when `status==='resumed'`), and `status_history` — every *other* log entry for the same enrollment, grouped/formatted per-status, sorted newest-first, with an internal `_sort_at` sort key stripped before output.

---

## Debug / unguarded routes

### `GET /api/debug-enrollments` — inline closure, **no middleware, no auth, registered outside any group**
```php
Route::get('/api/debug-enrollments', function (Request $request) {
    $ids = explode(',', $request->ids);
    return Enrollment::whereIn('id', $ids)->get();
});
```
Note the path is literally `/api/debug-enrollments` (this route file is already mounted under `/api` by the framework, so the *effective* URL has a doubled `/api/api/debug-enrollments` — needs empirical confirmation of the exact resolved path before writing a parity test against it, but the route registration itself has no version prefix, no `json.response`, and no auth guard of any kind). Returns a **raw Eloquent collection** serialized directly (full model attributes, no Resource wrapping, no envelope) — `ids` query param is comma-split with no validation; an empty/missing `ids` param resolves to `explode(',', null)` → `['']`→ `whereIn('id', [''])` → an empty result set, not an error.

---

## Student-side pause / resume (`auth:student`, prefix `student/v1`)

All six routes below operate through `CoursePauseService`/`CourseResumeService` (`Modules/Enrollment/Services/`) and the working `EnrollmentPauseLogNew` model — this half of the pause/resume system is functionally sound.

### `GET /student-my-courses/pause-status/{enrollment}` — `pauseEligibility()`
Looks up the enrollment scoped to `auth('student')->user()->id` — a mismatch (enrollment exists but belongs to a different student) returns 404 `{"status":"error","message":"Enrollment not found or does not belong to you."}` rather than the generic model-not-found shape (this is intentional obfuscation of ownership, not route-model-binding). `CoursePauseService::checkEligibility()`: not eligible if no batch assigned, if `isRefundEligible()` (the same `{"en":"Refund Eligible"}` tag check used throughout this module), or if already `PAUSED`/`RESUME_REQUESTED`/`PAUSE_REQUESTED`. Response: `{eligible, reason, days_remaining, pause_status, refund_eligible}` (a second, independent `isRefundEligible`-equivalent tag check computed inline here, not reused from the service).

### `POST /student-my-courses/pause/{enrollment}` — `pauseSingleEnrollmentStudent()`
`reason` nullable max:250. Same ownership/eligibility checks as above (422 with `reason` code if ineligible). `CoursePauseService::pauseEnrollment()`: sets `PAUSED`/`pause_status`/`paused_at`/`paused_reason`, creates an `EnrollmentPauseLogNew` row (`request_source: 'student'`), removes the student from their Edmingle batch if mapped (non-fatal on failure), logs activity attributed to `auth('student')->user()` (the actual student — a correct, non-hardcoded causer, unlike several admin-side LawSikho/Enrollment endpoints). `{"status":"success","message":"Enrollment paused successfully.","enrollment": EnrollmentResource}`.

### `POST /student-my-courses/pause-bundle` — `pauseBundleEnrollmentStudent()`
`enrollment_ids` required array of int; `reason` nullable max:250. `CoursePauseService::pauseMultipleEnrollments()`: only considers enrollments that are both owned by the caller and currently `ACTIVE`; per-enrollment eligibility is re-checked (refund-eligible ones are collected separately as `refund_eligible_ids` rather than paused). Response includes `should_open_support_ticket` (true if any refund-eligible ids were skipped) and a matching `support_ticket_message` hint — a UI-facing nudge baked into the API response itself.

### `POST /student-my-courses/resume/{enrollment}` — `resumeRequestStudent()`
`ticket_id` nullable max:250. Requires `pause_status === PAUSE_STATUS_PAUSED` (422 `"Only paused enrollments can be resumed."` otherwise). `CourseResumeService::raiseResumeRequest()`: sets `status: RESUME_REQUESTED`/`pause_status: PAUSE_STATUS_RESUME_REQUESTED`, logs a new `EnrollmentPauseLogNew` row and an activity entry — **this only records a request; it does not reactivate the enrollment** (an admin must act via the single-enrollment `resume()` endpoint or the broken bulk one above to actually complete it).

### `POST /student-my-courses/refund-eligible-pause/{enrollment}` — `refundEligiblePauseRequestStudent()`
`ticket_id` **required** max:250 (the one pause/resume-family endpoint that mandates a ticket id). Requires `isRefundEligible()` to be true (422 otherwise — this is the *only* path by which a refund-eligible enrollment can be paused/requested at all, since ordinary pause explicitly excludes refund-eligible enrollments). Sets `refund_eligible_pause_request_status`/`_time`, `status: PAUSE_REQUESTED`, `pause_status: PAUSE_STATUS_PAUSE_REQUESTED`, logs both an `EnrollmentPauseLogNew` row and an activity entry attributed to the student. `{"status":"success","message":"...","enrollment": EnrollmentResource}`.

### `GET student-my-courses/pause-log/{enrollment}` — `studentPauseLog()`
Identical implementation to the admin `pauseLog()` above (`enrollmentPauseLog()` shared helper) — **note the route does not scope this to the requesting student's own enrollments** (no `where('student_id', ...)` guard, unlike every other student-side endpoint here) — a student who knows/guesses another student's enrollment id can read that enrollment's full pause/resume log via this route, since it's only gated by `auth:student` (any authenticated student), not ownership. Worth flagging as an authorization gap for a security-focused parity pass.

---

*Companion documents: [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md), [`../API_SPECIFICATIONS.md`](../API_SPECIFICATIONS.md) §2 (original, lighter-detail pass on `POST /v1/enrollments` — expanded substantially above, including corrections regarding the undocumented `batch_title`/`batch_status` fields it did not originally cover).*
