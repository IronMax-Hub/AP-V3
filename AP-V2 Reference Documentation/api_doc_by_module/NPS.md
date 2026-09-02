# NPS Module API Documentation

The `NPS` module owns the admin/system-side Net Promoter Score survey: submitting a rating+reasons record for an enrollment, and a large surface of read-only listing/reporting/export endpoints used by the admin dashboard (NPS graphs, per-course/per-bootcamp/per-package NPS rollups, reason-option lookups). It does **not** cover the student-facing NPS submission endpoints — those live in `StudentDashboard` (`POST /api/v1/add-nps`, a different payload shape) and are documented in `StudentDashboard.md`.

**Module-wide auth:** every route in `Modules/NPS/Routes/api.php` is `auth:sanctum` + `json.response` (admin/staff token), mounted under `/api/v1/...` (legacy) and `/api/v2/...` (current). No route in this module uses `auth:student`, even `store` (`POST /v2/nps`), which is the endpoint that actually records a student's NPS response — see the note under that endpoint. No per-endpoint deviation from `auth:sanctum` exists in this file.

See [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for the app-wide response envelope styles, standard error shapes, and pagination conventions referenced below instead of being repeated per endpoint.

All controller logic is implemented via `NPSController` (`Modules/NPS/Http/Controllers/NPSController.php`), which is almost entirely a thin wrapper — nearly every method's real body lives in `NPSTrait` (`Modules/NPS/Http/Traits/NPSTrait.php`), pulled in with `use NPSTrait;`. Only `index()`, `index1()`, and `store()` are defined directly on the controller; every other routed method below is a trait method.

## ⚠️ Structural landmine: `apiResource('nps', ...)` in the v2 group is partially broken

```php
Route::apiResource('nps', 'NPSController'); // inside the /api/v2 group
```

`apiResource` wires up 5 routes: `index`, `store`, `show`, `update`, `destroy`. `NPSController` (including via `NPSTrait`) only implements `index` and `store`. **`show`, `update`, and `destroy` do not exist anywhere in the class or its trait** — this is not the "empty stub" pattern described in the common structural traps, it's a genuinely missing method. Calling any of the following will hit a PHP `Error: Call to undefined method` at dispatch time, which surfaces as an uncaught-exception **500**, not a clean 404/405 JSON error:
- `GET /api/v2/nps/{nps}`
- `PUT` / `PATCH /api/v2/nps/{nps}`
- `DELETE /api/v2/nps/{nps}`

A parity test suite must confirm the migrated backend reproduces this exact 500-on-fatal-error behavior (or, more likely, the migration is expected to *fix* this — confirm with the team which is intended before asserting either way).

---

## Survey submission

### `POST /api/v2/nps` (route name `nps.store`, controller `store`)
- **Auth:** `auth:sanctum` — **not** `auth:student`, despite this endpoint creating what is semantically a student's own survey response. `student_id` is taken directly from the request body, not from the authenticated identity — **an authenticated staff/admin token can submit an NPS response on behalf of any `student_id` it names.** Worth a dedicated authorization-boundary test.
- **Request body** (`StoreNPSRequest`, no `authorize()` gate — always returns `true`):
  - `rating` — required, string, max:255
  - `answer` — required, string, max:255
  - `enrollment_id` — required, `exists:enrollments,id`
  - `student_id` — required, `exists:students,id`
  - `course_id` — required, `exists:courses,id`
  - `batch_id` — required, `exists:course_batches,id`
  - `reasons` — required, array; `reasons.*` — `exists:nps_form_reason,id`
  - `survey_type` — required, one of `NPSForm::SURVEY_TYPE_1` / `SURVEY_TYPE_2` (`1`/`2`)
- **Success response:** `$this->apiResponse($npsData, 'NPS Submitted successfully', statusCode: 201)` → `{"data": <created NPSForm row>, "message": "NPS Submitted successfully", "status": "success"}`. `rating` bucketing determines which columns get populated: `rating > 8` → written to `suggestions` (not `experience`) with `reason: 'N'`; `rating` 7–8 → `experience` with `reason: 'N'`; `rating <= 6` → `experience` with `reason: 'Y'`. Each id in `reasons[]` creates a separate `NPSFormReasonMaping` row.
- **⚠️ Duplicate-check bug (confirmed by reading the repository method):** `NPSController::store()` calls `checkIfDuplicate($request->student_id, $request->surveyType, $request->courseId, $request->batchId)`. The validated/actual request fields are `survey_type`, `course_id`, `batch_id` (snake_case) — **`surveyType`, `courseId`, `batchId` (camelCase) are never defined anywhere on the request**, so all three resolve to `null` via the FormRequest's magic property access. The repository's `checkIfDuplicate()` then runs `where('student_id', $id)->where('course_id', null)->where('batch_id', null)->where('survey_type', null)->count()`. Since `course_id`/`batch_id`/`survey_type` are always non-null on real rows (validated as `required` on insert), this condition can only ever match a row that itself has `course_id`/`batch_id`/`survey_type` literally `null` in the database — i.e., **for all practically-existing data, the duplicate check always returns 0 and never blocks a resubmission**, regardless of how many times the same student/enrollment/survey combination is submitted. Only `student_id` is passed correctly; the other three are the broken part. Preserve this exactly — do not "fix" it when documenting/asserting behavior.
- **If the (effectively always-false) duplicate check *does* fire:** `$this->apiResponse(['status' => 1, 'message' => ''], 'NPS Already submitted', statusCode: 201)` — **HTTP 201, not 409**, on what is semantically a rejected duplicate.
- **Side effects:** wrapped in `DB::transaction()`. No queued jobs, no mail.
- **Notes:** This is a genuinely different payload shape from `StudentDashboard`'s own `POST /api/v1/add-nps` (`enrollId`/`courseId`/`batchId`/`surveyType`/`reason[]`, raw `json_decode`, no FormRequest) — the two are not interchangeable and a client must not assume either accepts the other's field names. See `StudentDashboard.md` for that endpoint's full detail.

---

## Listing & dashboard endpoints

### `GET /api/v1/nps` (route name `nps.index1`, controller `index1`) — legacy listing
- Query: `rows` (optional int, default 15, page size).
- **Success response:** `NPSFormResource1::collection(...)` (V1 `NPSForm` entity, `NPSFormReasonMapping` relation) `->additional(['meta' => ['total' => ..., 'range' => ...]])` — resource-collection shape, `{"data":[...],"meta":{"total":N,"range":{"from":N,"to":N,"total":N}}}`. `range` computed by `NPSTrait::calculateRangeForCursor1()` using the app's custom base64-JSON `cursor` query param scheme (see common conventions); malformed cursor → `abort(500, 'Cursor value tempered')`.
- `NPSFormResource1` fields: `id`, `suggestions`, `experience`, `rating`, `created_at` (merged raw), plus `survey_type` (string `"one month"` if the raw value is literally `'one_month'`, otherwise passed through unchanged — so this only normalizes one specific historical value), `student` (`id`,`full_name`,`email`,`country_code`,`phone`), `enrollment` (`id`,`enrollment_code`), `course` (`id`,`course_name`), `batch` (`id`,`batch_date`), `reasons` (`NPSFormReasonMapingResource::collection`, each `{id, question}` from the mapped reason), `submitted_date` (`Y-m-d H:i:s`), `bootcamp` (`{bootcamp_id, bootcamp_name}` or `null` — re-queries `Enrollment` by id to find a bootcamp mapping).

### `GET /api/v2/nps` (route name from `apiResource`, controller `index`) — current listing
- Query: `rows` (optional int, default 15).
- **Success response:** `NPSFormResource::collection(...)` (V2 `NPSForm` entity with richer eager loads) `->additional(['meta' => [...]])` → `{"data":[...],"meta":{"total":N,"range":{...},"nps":N,"totalStudents":N,"totalNpsSubmitted":N}}`. `nps`/`totalStudents`/`totalNpsSubmitted` in `meta` are computed **only from the current page's data** (`NPSTrait::npsData($data)` operates on the paginated collection, not the full table) — these are *page-level* aggregates, not overall totals, despite sitting in `meta` next to `total`. A parity test must not assume these three change only when the underlying dataset changes; they change with pagination/filtering too.
- `NPSFormResource` fields: `id`, `rating`, `experience`, `suggestions`, `created_at` (ISO string), `survey_duration` (string `"{survey_type} days"` — literal concatenation, so e.g. `survey_type` value `30` becomes `"30 days"`), `student` (`id`,`full_name`,`email`,`country_code`,`phone`), `submitted_date` (`Y-m-d H:i:s`), `courses`/`bootcamp`/`packages` (arrays derived by scanning the student's *entire* enrollment set, not just the one tied to this NPS row), plus dynamically-keyed `reason`, `reason2`, `reason3`, ... — one key per distinct `reason_parent_id` group found in `NPSFormReasonsMappingV2`, each `{"question": ..., "options": [...]}`. **The number and names of these `reasonN` keys vary per row** depending on how many reason groups that student answered — not a fixed schema.

### `GET /api/v1/nps/dashboard` (route name `nps.dashboard`, controller `graph_index`) and `GET /api/v1/graph-index` (v1, `graph_index1`) / `GET /api/v2/graph-index` (v2, `graph_index`)
Both v1 and v2 `graph-index` routes map to trait methods that compute NPS graph/summary data from `NPSFormRepository::graphSearch()`/`graphSearch1()`. **Note the v1/v2 method-name swap**: v1's `graph-index` route calls `graph_index1()` while v1's `nps/dashboard` route and v2's `graph-index` route both call `graph_index()` — same underlying method serves two different paths across versions.
- **Success response** (`graph_index()`): `$this->apiResponse([...])` with keys `allData` (Google-Charts-style array-of-arrays: header row + one row per rating 0–10 with count/annotation/color), `countDetractor`, `dectractorPercentage` (note the literal misspelling `dectractor`, not `detractor` — preserve exactly), `countPassive`, `passivePercentage`, `countPro`, `promoterPercentage`, `nps` (`floor(promoter% − detractor%)`), `responseCode: 1`, `totalEnrolledStudents`, `totalStudents`, `totalNpsSubmitted`.
- **`graph_index1()`** (legacy, v1 `/graph-index` only) returns a **different, non-overlapping key set**: `allData`, `countDetractor`/`countPassive`/`countPro` each as a combined string `"N(XX.XX%)"` (not split into separate count/percentage keys), `nps`, `responseCode`, `totalEligible`, `totalSubmitted` (also a combined string). Do not assume the two are interchangeable shapes.
- Both compute `promoter`/`passive`/`detractor` buckets from `rating` thresholds (`<7` detractor, `7–8` passive, `>8` promoter) by iterating **all** rows returned by the (unbounded, unpaginated) `graphSearch()`/`graphSearch1()` query — potentially a full-table scan client-side, not filtered by the `rows`/`cursor` params used elsewhere.

### `GET /api/v1/nps-charts/{value}` and (commented out) `GET /api/v2/nps-options/{value}` (route name `nps.reports`, controller `npsReports`)
- Path param `value`: `0` filters reasons under `NPSFormReason::LikeQuestionId`; anything else filters under `DisLikeQuestionId`.
- Query: `nps` (optional, `asc`/`desc`, default `desc` for anything else including omission).
- **Success response:** hand-rolled `response()->json(['data' => [...], 'message' => 'Success', 'status' => 'success'])`. `data` is an array of `[question_text, count]` pairs (positional, not keyed) — **the v2 route for this action is commented out in the route file** (`// Route::get('/nps-options/{value}', ...)`), so this endpoint is only reachable via the v1 path `GET /api/v1/nps-charts/{value}`.

### `GET /api/v1/nps/bootcamps` (`npsBootcampData`), `GET /api/v1/nps/library` (`npsPackageData`), `GET /api/v1/nps/courses` (`npsCoureseData`) — no v2 equivalents exist for any of these three
- Query: `rows` (optional, default 15).
- **Success response:** resource-collection shape (`BootcampNPSResource` / `LibraryNPSResource` / `NPSCourseResource`) `->additional(['meta' => ['nps', 'totalStudents', 'totalNpsSubmitted', 'range']])`. `range` here uses `rangeForPagination()` (the global helper, `app/Helpers/functions.php`) — a **third, distinct pagination-range calculation** from the base64-cursor one used elsewhere in this same module (`calculateRangeForCursor`/`calculateRangeForCursor1`), because these three use standard Eloquent `LengthAwarePaginator`s internally (via the respective repositories), not custom cursor logic. `nps` per-row = `floor((promoters − detractors) / total_responses × 100)`, `0` if no responses; `meta.nps`/`meta.totalStudents`/`meta.totalNpsSubmitted` are aggregate totals across the whole filtered set (from `calculateTotals()`), unlike v2 `/nps`'s page-only aggregates noted above.
- `BootcampNPSResource`: `main_id` (the underlying rollup-table row id), `id` (`bootcamp_id`), `name` (`"{name} - {title}"` if title set, else `bootcamp_name`), `nps`, `total_students`, `total_responses`.
- `LibraryNPSResource` / `NPSCourseResource`: `id` (`package_id`/`course_id`), `name`, `nps`, `total_students`, `total_responses`.

### `GET /api/v1/nps/method-calls` (`npsMethodCalls`) and `GET /api/v2/...` equivalent
Route is registered (`nps.method-calls`) but **no `npsMethodCalls` method exists anywhere in `NPSController` or `NPSTrait`** — calling this route produces the same "fatal 500 via undefined method" failure mode as the broken `apiResource` actions above. Confirmed absent by reading the full controller and trait; not fabricated.

---

## Reason / option lookup endpoints (present in both v1 and v2 groups, identical implementation)

### `GET /nps/reasons` (route name `nps.reasons`, controller `getNPSFormReason`)
- **Success response:** `ListingNPSFormReasonResource::collection(...)->additional(['meta' => ['total' => ...]])` → `{"data":[{"id","question","created_at","updated_at"}, ...], "meta":{"total":N}}`. Unfiltered, unpaginated — returns the entire `NPSFormReason` listing every call.

### `GET /search/specific-nps-reason` (route name `course.specific.nps-search`, controller `searchNPSReasonsWithArray`)
- **Success response:** global `apiResponse($this->NPSFormReasonRepository->searchNPSReasonsWithArray())` → `{"data": <raw array>, "message": "Success", "status": "success"}`.

### `GET /nps-filter-options` (route name `nps.options`, controller `searchNPSReasons`)
- Query: `search` (optional, `LIKE '%...%'` on `question`), `exclude_questions` (optional array, `whereNotIn`).
- **Success response:** hand-rolled `response()->json(['status' => 'success', 'data' => $options])` — `data` here is a raw array (not resource-wrapped), each item `{id, question}`. Only rows with a non-null, non-zero `parent_id`, grouped by `question`.

### `GET /nps-filter-search` (route name `search.options`, controller `searchOptions`)
- Query: `question` (optional array — `whereIn`).
- **Success response:** hand-rolled `response()->json(['status' => 'success', 'data' => $data])`, same `{id, question}` shape, grouped by `question` (no `parent_id` filter, unlike `searchNPSReasons` above).

### `GET /search/nps-type-filter` (route name `nps.type.filter`, controller `npsTypeFilter`)
- **Success response:** hand-rolled `response()->json(['status' => 'success', 'data' => $npsTypes])` — `$npsTypes` is a raw Eloquent collection of `{survey_type}` rows (grouped/distinct) from the V2 table, **not** wrapped through a Resource.

### `GET /search/specific-nps-type-filter` (route name `search.nps.type.filter`, controller `searchnpsTypeFilter`)
- Query: `search` (optional array of survey-type values).
- **Success response:** hand-rolled `response()->json(['status' => 'success', 'data' => $data])` where `data` is manually rebuilt as `[{'survey_type': $day}, ...]` for each item in `search` — if `search` is omitted, `data` is `[]`.

### `GET /nps/survey-data/{id}` (route name `nps.survey-data`, controller `getSurveyData`)
- Path param `id` — an **enrollment id** (looked up via `EnrollmentRepository::findById`), not an NPS row id.
- Determines whether the given enrollment is currently "due" for a 1-month or completion NPS survey, based on: assignment `created_at` vs. `-30 days`, `mcq_completed`/`completed` flags, and whether an NPS row already exists for that survey type (via `NPSFormRepository::getNPSData`).
- **Success response, "due" cases:** `$this->apiResponse(['status' => 1, 'survey_status' => <1|2>, 'name', 'email', 'course_name', 'batch_name', 'course_id', 'batch_id', 'enrollment_Id', 'resones' => <NPSFormReason listing>, 'message' => ''])`. **The key is literally `resones`, not `reasons` — a typo in the actual source code, must be reproduced verbatim.** Also note `enrollment_Id` (capital `I`), not `enrollment_id`.
- **Success response, "not due":** `$this->apiResponse(['status' => 1, 'message' => 'survey Not needed '])` — note the trailing space in `'survey Not needed '` is literal, present in source.
- **Notes:** `$assignment_created_at->created_at` is dereferenced on the result of `StudentAssignment::where('enrollment_id', ...)->first()` with **no null-check** — if the enrollment has zero `StudentAssignment` rows, this is a null-object-property access that will throw and surface as an uncaught-exception 500, not a clean 404. Worth a boundary test with an enrollment that has no assignments.

---

## Export

### `GET /api/v1/nps/exports` and `GET /api/v2/nps/exports` (route name `nps.exports`, controller `export`)
- **Success response:** global `apiResponse('', 'NPS Csv file exporting started')` → `{"data": "", "message": "NPS Csv file exporting started", "status": "success"}` (`data` is an empty **string**, not `[]` or `null`).
- **Side effects:** queues a `NPSExport` Excel export (`Maatwebsite\Excel`) to S3 at `exports/tmp/nps/{filename}`, chained with a `NPSCSVDownload` job that emails the requesting user (`Modules/NPS/Emails/NPSCSVStartedMail.php` / `NPSCSVCompletedMail.php`) once the export completes. **Fire-and-forget** — the response returns before the export runs; a parity test must poll or wait for the follow-up email/S3 object rather than asserting completion from this response.

---

## Summary of endpoints documented

28 routes exist in `Modules/NPS/Routes/api.php` (14 distinct actions × 2 API versions, since v1 and v2 groups largely mirror each other, plus the 5-route `apiResource('nps', ...)` only in v2). Of these:
- **13 distinct behaviors** fully documented above (`store`, `index`/`index1`, `graph_index`/`graph_index1`, `npsReports`, `npsBootcampData`, `npsPackageData`, `npsCoureseData`, `getNPSFormReason`, `searchNPSReasonsWithArray`, `searchNPSReasons`, `searchOptions`, `npsTypeFilter`, `searchnpsTypeFilter`, `getSurveyData`, `export`).
- **4 routes confirmed broken** (fatal-error-on-call, not documented with a fabricated shape): `apiResource`'s `show`/`update`/`destroy` (v2 only) and `npsMethodCalls` (both v1 and v2).
- **1 route** (`GET /api/v2/nps-options/{value}`) confirmed **commented out** in the route file — not live despite the underlying controller method existing.

**Confidence:** High for all documented shapes — every one was confirmed by reading the actual controller/trait/resource/request source, not inferred. The duplicate-check bug and the `resones`/`dectractorPercentage` typos were independently re-verified against the repository method and resource source rather than taken solely from the existing spec.
