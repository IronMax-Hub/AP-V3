# Course Module API Documentation

The `Course` module owns the `courses` entity CRUD, its evaluator/mentor/instructor pivot mappings, AI-evaluation configuration, mock-question management, and the parallel "bootcamp course" surface (same `courses` table, `course_type = BOOTCAMP_COURSE`). It also exposes course-scoped performance/reporting endpoints and CSV exports.

**Module-wide auth:** every route in `Modules/Course/Routes/api.php` is declared inside a single `Route::middleware(['auth:sanctum', 'json.response'])->prefix('v1')->group(...)` — i.e. `auth:sanctum` + `json.response`, all under `/api/v1/...`. No route in this file deviates from this.

See [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for the app-wide response envelope styles, standard error shapes, and pagination conventions referenced below instead of being repeated per endpoint.

Two controllers implement this module's routes: `CourseController` (`Modules/Course/Http/Controllers/CourseController.php`) and `BootcampCourseController` (`Modules/Course/Http/Controllers/BootcampCourseController.php`). Both `use CourseTrait;` (`Modules/Course/Http/Traits/CourseTrait.php`) — most of the actual endpoint logic lives in the trait, not the controllers; `CourseController` additionally `use ActivityLog;` (`app/Http/Traits/ActivityLog.php`) for its `activity()` endpoint. Each endpoint below names whether its body is on the controller directly or pulled in via a trait.

## ⚠️ `apiResource('course', 'CourseController')` is partially broken — `show`, `create`, `edit` do not exist

```php
Route::apiResource('course', 'CourseController'); // registers index, create, store, show, edit, update, destroy
```

`index`, `store`, `update`, `destroy` are all implemented (on the controller directly). **`show`, `create`, and `edit` are not defined anywhere in `CourseController`, `CourseTrait`, or `ActivityLog`** — confirmed by reading both files in full. Calling `GET /api/v1/course/{course}` (show), `GET /api/v1/course/create`, or `GET /api/v1/course/{course}/edit` hits a PHP `Error: Call to undefined method`, surfacing as an uncaught-exception **500**, not a clean 404/405 — the same failure mode documented for NPS's broken `apiResource` actions (see `NPS.md`). A parity test must confirm whether the migrated backend is expected to reproduce this 500 or fix it — confirm with the team.

---

## Course reporting / performance endpoints

### `GET /course/{course}/batches/performance` (route name `course.batches.performance`, trait `batchesPerformance`)
- Path param `{course}` — route-model-bound `Course`; standard 404-model-not-found shape if missing.
- Query: `rows` (optional int, default 15), `search` (optional, `LIKE` on the batch's `batch_date`), `cursor` (base64 cursor token, this module's own scheme — see below).
- **Success response:** `CourseBatchesResource::collection(...)->additional(['meta' => ['total' => N, 'range' => {...}]])` — resource-collection + custom cursor pagination (`calculateRangeForCursorForBatchesPerformance`, a fourth local reimplementation of the base64-cursor scheme, scoped to this course's batch set). Only batches the course has enrollments against are included (`$course->enrollments()->pluck('batch_id')->unique()`).
- `CourseBatchesResource` fields: `id`, `batch_date`, `number_of_students` (`enrollments_count`), `submitted_assignments_percentage` (via global `calculateThePercentage()` helper), `number_of_students_submitted_assignments`, `students_submitted_assignments_percentage`, `number_of_students_where_submitted_assignments_is_40_or_above`, `percentage_of_where_students_submitted_assignments_is_40_or_above`, `number_of_students_submitted_assignments_is_zero`, `percentage_of_where_students_submitted_assignments_is_zero` — all computed client-side from eager-loaded per-enrollment counts, not raw columns.
- **Notes:** the resource class also defines two public/private helper methods (`calculateTheNumberOfStudentsWith40PercentOrMoreSubmission`, `calculateTheNumberOfStudentsWithZeroSubmission`) that are **never called from `toArray()`** — dead code inside the resource, the actual 40%-threshold/zero-submission figures above are computed inline via `->filter()->count()` instead.

### `GET /course/{course}/batches/performance/total` (route name `course.batches.performance.total`, trait `batchesPerformanceTotal`)
- Same batch scoping as above, but **unpaginated** — runs the full query and aggregates with `->sum()`.
- **Success response:** `apiResponse([...])` (global helper) → `{"data": {...}, "message": "Success", "status": "success"}` with keys `total_number_of_students`, `submitted_assignments_percentage`, `total_number_of_students_who_submitted_the_assignments`, `total_number_of_students_who_submitted_the_assignments_percentage`, `total_number_of_students_where_submitted_assignments_is_40_or_above`, `total_percentage_of_students_where_submitted_assignments_is_40_or_above`, `total_number_of_students_submitted_assignments_is_zero`, `total_percentage_of_students_submitted_assignments_is_zero`.
- **Notes:** two of these fields are computed by resolving a **different module's controller out of the container mid-request** — `app(\Modules\CourseCategory\Http\Controllers\CourseCategoryController::class)->calculateTotalStudentsWhoSubmittedAssignmentsPercentageIs40OrAbove($batches)` / `...IsZero($batches)` — a `Course`-domain computation is delegated to a `CourseCategory` controller instance rather than living in this module; not a route delegation (no HTTP route involved) but a direct cross-module method call worth knowing about if `CourseCategoryController`'s constructor dependencies ever change.

### `GET /course/{course}/ai-config` (route name `course.ai-config`, controller `getAIConfig`)
- **Success response:** `apiResponse([...], 'AI configuration retrieved successfully')` → `is_ai_enabled` (cast bool), `ai_model` (`{id, name, version, gemini_model_id}` or `null`), `assignment_instruction_link`, `assignment_sample_feedback_link`.
- **Side effects:** writes an activity-log entry (`event: 'Course AI Config Viewed'`) on every call — a **read** endpoint that logs an activity row per hit, unlike most GETs in this module.

### `GET /course/for/assignment-library` (route name `course.index-for-assignment-library`, trait `courseIndexForAssignmentLibrary`)
- Query: `rows` (optional, default 15), `search` (optional, `LIKE` on `course_name`).
- **Success response:** `courseIndexForAssignmentLibraryResource::collection(...)->additional(['meta' => ['total' => N, 'range' => {...}]])` — this module's fifth independent local reimplementation of the base64-cursor range calculation (`calculateRangeForCursorForCourseIndexForAssignmentLibrary`).
- `courseIndexForAssignmentLibraryResource` fields: `id`, `course_name`, `duration_days`, `status`, `assignments_count` (`count($this->assignments)` — loads the full relation into memory to count it, not a DB-level `withCount`).

### `GET /course/{course}/mentors` (route name `course.mentors.index`, trait `courseMentors`)
- **Success response:** `apiResponse(['mentors' => CourseMentorsMappingResource::collection($course->mentors)])`. `CourseMentorsMappingResource`: raw pivot row (`id`, timestamps excluded) plus `mentor: {id, first_name, last_name}` (from `user` relation).

### `GET /search/courses` (route name `course.search`, trait `search`)
- Query: `search` (optional, substring match on `id` OR `course_name`), `except` (optional int, excludes that course id from results).
- **Success response:** `SearchCourseResource::collection(...)->additional(['meta' => ['total' => N]])` — resource-collection shape, `{id, course_name}` only.
- **⚠️ Cache quirk:** the underlying data source is `Cache::rememberForever('all_courses', fn() => Course::all())`, filtered/searched **in PHP after retrieval**, not via a DB `WHERE`. The cache is correctly invalidated on every `Course` `saved`/`deleted` model event (`Modules/Course/Entities/Course.php::boot()` calls `Cache::forget('all_courses')` then eagerly re-primes it) — so results are not observably stale, but a parity test simulating a raw DB insert (bypassing Eloquent, e.g. a direct SQL seed) would not be reflected here until the next save/delete event touches the cache.

### `GET /search/specific-courses` (route name `course.specific.search`, trait `searchCoursesWithArray`)
- Query: `search` — **array of course ids** (`whereIn('id', request('search'))`), **not a substring search string** despite the near-identical name to `/search/courses` above, whose own `search` param IS a substring filter. Do not conflate the two `search` params' semantics.
- **Success response:** global `apiResponse($this->courseRepo->searchCoursesWithArray())` → `{"data": [{id, course_name}, ...], "message": "Success", "status": "success"}` — a raw Eloquent collection, not resource-wrapped, and (unlike the sibling above) **not cached** — hits the DB directly every call.

### `GET /{course}/faqs` (route name `course.faqs`, trait `courseFaqs`)
- **⚠️ Path shape:** full path is `/api/v1/{course}/faqs` — the `{course}` wildcard sits directly under the `v1` prefix, not nested under `/course/...` like every sibling route in this file. `{course}` here is a raw id looked up manually (`$this->courseRepo->findById($id)`), not route-model-bound — a non-existent id returns a clean `apiResponse([], 'Course Not Found', 'error', 404)` (hand-rolled, not the framework's `ModelNotFoundException` shape) rather than the standard "Resource Not Found" text.
- Query: `rows` (read but see bug below).
- **Success response:** `CourseFaqResource::collection(...)->additional(['meta' => ['total' => 2, 'range' => {...}]])`.
- **⚠️ Two confirmed bugs, preserve exactly:**
  1. `$course->faqs()->latest('id')->cursorPaginate(1)` — the page size is **hardcoded to `1`**, completely ignoring the `$rows` value read from the request two lines above. Every call to this endpoint returns at most **one** FAQ per page regardless of what `rows` the caller sends.
  2. `'total' => 2` in the `meta` block is a **literal hardcoded integer `2`**, not `$course->faqs()->count()` — the actual total FAQ count for the course is computed correctly inside `calculateRangeForCourseFaqCursor()`'s own `range.total`, but the top-level `meta.total` is always exactly `2` no matter how many FAQs the course actually has. A parity test must assert `meta.total === 2` unconditionally (bug-for-bug) and use `meta.range.total` for the real count.
- See `CourseFaq.md` for `CourseFaqResource`'s own field shape.

### `POST /course/transfer-to-other` (route name `course.transfer-to-other`, trait `transferToOther`)
- **Request body** (`TransferEnrollmentToNewCourseRequest`): `current_id` required `exists:courses,id`; `new_id` required `exists:courses,id`. No `authorize()` gate — returns `true` unconditionally. **No check that `new_id !== current_id`, and no check that `new_id` isn't itself an already-deleted/mismatched course type** — both are validated only for existence.
- **Success response:** `apiResponse([], 'Enrollments updated with new course id')` if `current_id` has ≥1 enrollment (delegates the actual re-pointing to `EnrollmentRepository::updateTheCourseIdToNewId`), else `apiResponse([], 'Nothing to update')` — **both are 200 success shapes; the "nothing to update" case is not an error**, just a no-op confirmation.

### `POST /course/bulk-ai-config` (route name `course.bulk-ai-config`, controller `bulkAIConfig`)
- **Request:** no FormRequest — inline `$request->validate([...])` on the controller. `course_ids` required array each `exists:courses,id`; `ai_model_id` optional `exists:ai_models,id`; `is_ai_enabled` optional bool; `assignment_instruction_link`/`assignment_sample_feedback_link` optional string; `assignment_instruction_file`/`assignment_sample_feedback_file` — file (`pdf,doc,docx`, max 10240KB) if uploaded as a file, else optional string (branches on `hasFile()`, same pattern as `Store`/`Update`). Also accepts `ai_model` as an alias for `ai_model_id` (merged in before validation if `ai_model_id` absent).
- **Behavior:** wrapped in `DB::transaction()`. If a file is present, it's uploaded **only against the first course in `course_ids`** (`Course::find($courseIds[0])`) via Spatie MediaLibrary, and the resulting single S3 URL is then applied to **every** course in `course_ids` — i.e. all courses in the bulk batch end up pointing at the same one physical file. Then bulk-updates `courses` rows, propagates `ai_model_id`/`is_ai_enabled` to any `Assignment` template rows under those courses that currently have `is_ai_enabled = 0`, and further propagates to `StudentAssignment` rows (excluding `STATUS_SUBMITTED`/`STATUS_EVALUATED`) with `is_ai_enabled = 0`. Writes one activity-log entry per affected course (`event: 'Bulk AI Config Updated'`).
- **Success response:** `apiResponse([], 'Bulk AI configuration updated successfully for courses and assignments')` — empty `data`, no indication of how many rows were actually touched.

---

## `apiResource('course', 'CourseController')`

### `GET /course` (`index`, controller)
- Query: `rows` (optional, default 15), `search` (substring on `id`/`course_name`/`category.category_name`), `status` (exact match), `course_category` (array, `whereIn`), plus standard `cursor`.
- **Success response:** `CourseResource::collection(...)->additional(['meta' => ['total_course', 'total_active', 'total_deactive', 'range']])` — note the extra `total_course`/`total_active`/`total_deactive` meta keys beyond the usual `total`/`range` pair seen elsewhere in this app; `total_active`/`total_deactive` are computed by two **separate** full re-queries against `status = STATUS_ACTIVE` / `STATUS_PENDING` (not derived from `total_course` minus something), each re-applying the same `search`/`course_category` filters as the main listing.
- `CourseResource` fields: nearly all raw `courses` columns (`Arr::except` drops FK ids, `updated_at`, `deleted_at`, relation-name collisions), plus `created_at` reformatted `Y-m-d h:i:s`; `no_of_assignments` (`assignments_count`), `enrollments_count`; `evaluators` (`CourseEvaluatorsMappingResource::collection`, each `{..pivot fields.., evaluator:{id,first_name,last_name}}`); `instructors` (hand-built array excluding soft-deleted mapping rows, `{id, first_name, last_name, email}` sourced from `user`, **not** a Resource class — `InstructorMappingResource` exists in this module but is never referenced anywhere, confirmed dead/orphaned code); `mentors` (`CourseMentorsMappingResource::collection`); `category` (`{id, category_name}` or null); `default_evaluator`/`default_written_evaluator`/`freelancer`/`placement`/`student_writing_coach`/`student_coach` (each `{id, first_name, last_name}` or null); `ai_model` (`{id, name, version, description, is_default, gemini_model_id}` or null); `is_ai_enabled` (cast bool); `assignment_instruction_link`/`assignment_sample_feedback_link`; `criteria` (`CourseCriteriaResourse::make($this->criteria)` — see `CourseCriteria.md`); `question` (array of active (`status==1`) `mockQuestions` question strings only — a private helper method on the Resource itself, not a separate class).
- **Notes:** `created_by`/`updated_by` nested-object serialization is commented out in source (`// 'created_by' => $this->creator?->only(...)`) — the raw FK columns are excluded from output entirely, so **neither the id nor a nested creator/updater object appears in the response**, despite `creator`/`updater` relations being eager-loaded in `index()`'s query.

### `POST /course` (`store`, controller)
- **Request body** (`Store`): `course_name` required, `max:255`, unique; `status` required, one of `Course::STATUS_ACTIVE`/`STATUS_PENDING`; `duration_days` required integer; `course_category_id` optional `exists:course_categories,id`; `default_evaluator_id`/`default_written_evaluator_id`/`student_coach_id`/`student_writing_coach_id`/`freelance_id`/`placement_id` optional `exists:users,id`; `evaluators`/`mentors` optional array\<int\> each `exists:users,id` (**no `distinct` rule — duplicate ids pass validation** and will be inserted as duplicate pivot rows); `ai_model_id` optional `exists:ai_models,id`; `is_ai_enabled` optional bool; `assignment_instruction_link`/`assignment_sample_feedback_link` optional string; `assignment_instruction_file`/`assignment_sample_feedback_file` — file (`pdf,doc,docx`, max 10240KB) or string URL, branching on `hasFile()`.
- **Success response:** `apiResponse(['course' => CourseResource::make(...)], 'Course created successfully', statusCode: 201)`.
- **Side effects:** `SyncCourseWithCalendar::dispatch($course)` — queued job, synchronous `Http::post()` to `config('services.course_calendar.url').'/external/courses'` (**External call**) with `X-Portal-From` token header; failure is only logged (`Log::error`), never surfaced back to the caller. An activity-log call for "Course Created" exists in source but is **entirely commented out** — creating a course does **not** produce an activity-log row, despite `update`/`destroy` on this same controller doing so.

### `PUT/PATCH /course/{course}` (`update`, controller)
- **Request body** (`Update`): `course_id` required `exists:courses,id` (send in body in addition to the path param); `course_name` optional, unique-ignoring-self; `status` optional bool; `duration_days` optional int; `course_category_id` optional exists; **`default_evaluator_id`/`default_written_evaluator_id` become `required`** here (opposite of `Store`, where they're optional) — omitting either on an update 422s even if the course already has one set; `student_coach_id`/etc. optional exists; `evaluators`/`mentors` optional arrays (same no-`distinct` gap); `remove_evaluators`/`remove_mentors` optional `in:1` (clears the respective pivot set); AI fields same shape as `Store`.
- **Behavior:** `set_time_limit(0)` at the top of the method (unbounded execution time) then `updateCourse()` (trait) + `addOrUpdateQuestions()` (trait, replaces the course's `MockQuestion` set: all currently-active questions for the course get `status=0`, then the submitted `questions` array — if any — is bulk-inserted as new active rows; if no `questions` key is present at all, existing questions are still deactivated and nothing is re-inserted, effectively wiping mock questions on any update call that omits the field).
- If any AI-related field changed (`ai_model_id`/`assignment_instruction_link`/`assignment_sample_feedback_link`/`is_ai_enabled`), propagates the new AI config to `Assignment` templates with `is_ai_enabled=0` under this course, and to `StudentAssignment` rows (excluding `STATUS_EVALUATED`) with `is_ai_enabled=0`; if specifically `ai_model_id` or either file link changed, also dispatches `PropagateAIConfigToStudentAssignments::dispatch($course->id)` — a queued job that additionally flips `is_ai_enabled` to `1` on qualifying non-evaluated student assignments (see job docstring for the exact "already has a complete standalone config" exclusion logic).
- **Success response:** `apiResponse(['course' => CourseResource::make($course)], 'Course updated successfully')`.
- **Side effects:** activity-log entry (`event: 'Course Updated'`) — this one is **not** commented out, unlike `store`'s.
- **Notes:** `evaluators`/`mentors`/`instructors` pivot replacement (`update`) is a full delete-then-reinsert whenever the corresponding array key is present and its `remove_*` sibling is absent — not a merge/diff; sending a partial `evaluators` array on update drops any evaluators not included in it.

### `DELETE /course/{course}` (`destroy`, controller)
- Path param not route-model-bound here — the method signature is `destroy($id)`, manually looked up via `$this->courseRepo->findById($id)` (called **twice** — once for the existence check, again to build the activity-log subject — two separate queries for the same row).
- **Error response:** `apiResponse([], 'Course Not Found', 'error', 404)` if not found (hand-rolled, not the framework `ModelNotFoundException` shape, since there's no route-model binding to trigger that).
- **Success response:** `apiResponse([], 'Course deleted successfully')` — default 200, despite being a destroy action.
- **Side effects:** activity-log entry (`event: 'Course Deleted'`); `DeleteCourseSync::dispatch($course->course_name, $course->id)` — queued job, synchronous **External call** `Http::post()` to `{course_calendar.url}/external/courses/delete`; failures only logged, not surfaced.

---

## `GET /courses/except_bootcamp` (no route name, trait `courses_except_bootcamp`)
- Query: `bootcamp_id` required (any non-empty value — validated as `required` only, no `exists` rule despite the name); `student_id` required `exists:students,id`; `search` optional substring on `course_name`; `offset`/`limit` optional (default `0`/`10`).
- **Success response:** hand-rolled `response()->json(['data' => $query, 'meta' => ['total' => $query->count()]], 200)` — **`meta.total` is the count of the current (already offset/limited) page's result set, not the total matching rows before pagination** — a client cannot use this `total` to compute how many pages exist; it will just echo back `min(limit, actual_matches)`.
- **Notes:** the underlying logic finds course ids the given student already has enrollments in **for the given `bootcamp_id`**, then returns courses NOT in that set — used for "which courses can this student still add under this bootcamp" UI flows.

---

## Bootcamp-course endpoints (`BootcampCourseController`)

All of these operate on the same `courses` table as above, scoped via `course_type = Course::BOOTCAMP_COURSE`. `BootcampCourseController extends \Illuminate\Routing\Controller` (the bare framework controller, not `App\Http\Controllers\Controller`) but still calls the **global** `apiResponse()` helper function throughout (available regardless of base class, unlike the `$this->apiResponse()` instance method) — so response shapes are consistent with `CourseController`'s despite the different parent class.

### `POST /bootcamp-course` (route name `bootcamp-course.store`, controller `store`)
- **Request body:** same `Store` FormRequest as the plain-course `store` endpoint above — reused as-is. `course_type` is force-set to `Course::BOOTCAMP_COURSE` server-side via `$request->request->add(...)` before delegating to the shared `createCourse()` trait method — not itself a validated/client-supplied field.
- **Success response:** `apiResponse(['course' => CourseResource::make(...)], 'Bootcamp Course created successfully', statusCode: 201)`.
- **Notes:** unlike the plain-course `store`, this path does **not** dispatch `SyncCourseWithCalendar` — bootcamp courses created here are not synced to the external course-calendar service.

### `PUT /bootcamp-course/{course}` (route name `bootcamp-course.update`, controller `update`)
- **Request body:** same `Update` FormRequest as plain-course update (including the same `default_evaluator_id`/`default_written_evaluator_id`-required-on-update quirk).
- **Success response:** `apiResponse(['course' => CourseResource::make($course->fresh())], 'Bootcamp Course updated successfully')`.
- **Notes:** calls the same shared `updateCourse()` trait method as the plain-course `update` — so the same AI-propagation and mock-question-wipe behaviors documented above apply here too, but this action does **not** write an activity-log entry (the `activity()->log(...)` call is only present in `CourseController::update`, not here).

### `POST /bootcamp-course/status/change` (route name `bootcamp-course.change.status`, controller `changeStatus`)
- **Request:** no FormRequest — inline `Validator::make()`. `courses_ids` required array each `exists:courses,id`; `comment` required string; `status` required `in:activate,deactivate`.
- **Success response:** `apiResponse([], 'courses deactivated successfully')` or `'courses activated successfully'`, both `statusCode: 200`.
- **Side effects:** bulk `UPDATE courses SET status = ...` for all given ids; `addActivityLogsAndComments()` (from `App\Traits\ActivationAndDeactivationProcess`) — logs one activity+comment per course id with a fixed subject type string `'bootcamp_course_activation_and_deactivation'`.

### `GET /bootcamp-course/{course}/logs` (route name `bootcamp-course.logs`, controller `activityLogs`)
- **Success response:** `ActivityLogResource::collection($paginator)->additional(['meta' => ['next_page_url', 'prev_page_url', 'range' => {from,to,total}]])` — uses Laravel's built-in cursor `paginate()` with `next_page_url`/`prev_page_url` string URLs, a **different pagination style** from every other cursor-paginated endpoint in this module (which all hand-roll the base64-JSON-cursor scheme and never expose raw next/prev URLs). Filters `Activity::forSubject($course)` — i.e. all activity log rows for this specific course id, any event type.

### `GET /bootcamp-course` (route name `bootcamp-course.index`, controller `index`)
- Query: `rows` (default 15), plus the same `search`/`status`/`course_category` filters as `searchQueryBootcamp()` supports.
- **Success response:** `CourseResource::collection(...)->additional(['meta' => ['total', 'total_assignment', 'range']])` — **`total_assignment` is set to the exact same value as `total`** (`$this->courseRepo->total_course_bootcamp()` called twice, once per key) — not actually an assignment count despite the key name; likely a copy-paste artifact.

### `GET /bootcamp-course/export` (route name `bootcamp-course.export`, controller `exportBootcampCourse`)
- **Request:** inline `Validator::make()`, `data` optional array.
- **Success response:** `apiResponse('', 'Bootcamp course Csv file exporting started')` — `data` is an empty **string**, not `[]`.
- **Side effects:** `BootcampCSVDownloadStart::dispatch(...)->onQueue('default_medium')` — queued job builds a CSV (`Course`, `Added Date`, `Number of assignments`, `Status` columns) and uploads to S3 under `exports/tmp/bootcamp-course`, then mails the requesting user via `BootcampMailDownloadStart`. Fire-and-forget — response returns before the export completes.

---

## Misc / dashboard / export endpoints

### `GET /courses/student-assignments/dashboard/list` (route name `course.student-assignments.dashboard.list`, trait `courseStudentAssignmentsDashboardData`)
- **Success response:** `apiResponse([...])` with `pie` (Google-Charts-style array-of-arrays: `[['Section','Number'], ['Pending', N], ['Submitted', N]]`) and `courses` (top courses by pending assignment count, default limit 6, overridable via `rows`).
- **⚠️ Cached for 30 minutes, ignoring request params:** `Cache::remember('dashboard.course_assignment.data', 60*30, fn() => ...)` — the cache key is a **fixed string with no request-parameter component**, so a call with `?rows=20` immediately after a call with no `rows` (or a different value) will silently return the **first** call's cached result for up to 30 minutes, not data respecting the new `rows` value. A parity test varying `rows` on repeated calls within the cache window will observe stale/ignored values.

### `GET /courses/export` (no route name, controller `export`)
- **Request:** inline `Validator::make()`, `data` optional array.
- **Success response:** `apiResponse('', 'Courses Csv file exporting started')` (`data` is an empty string).
- **Side effects:** `SendCourseCSVEmail::dispatch(...)->onQueue('default_medium')` — CSV columns `Id`, `Course_name`, `Course category`, (and more, truncated in source read) uploaded to S3 under `exports/tmp/courses`, then `CourseCSVCompletedMail` to the requester. Fire-and-forget.

### `GET /courses/assignment-library/export` (no route name, controller `exportAssignmentLibrary`)
- Same pattern as above: `AssignmentLibraryCSVDownload::dispatch(...)->onQueue('default_medium')` → CSV (`Course_name`, ...) to S3 under `exports/tmp/Assignment-library`, then `AssignmentLibraryCSVCompleteMail`.
- **Success response:** `apiResponse('', 'Assignment-library Csv file exporting started')`.

### `GET /courses/{course_id}/activity` (route name `courses.activity`, trait `activity`)
- **Error response:** `apiResponse([], 'Course Not Found', 'error', 404)` if `courseRepo->findById($id)` misses (manual check, not route-model-bound).
- **Success response:** delegates to `ActivityLog::logOfCourse($id, [...])` (`app/Http/Traits/ActivityLog.php`) — cursor-`paginate()` (Laravel built-in, `next_page_url`/`prev_page_url` style, same as `bootcamp-course/{course}/logs` above) over `Activity` rows where `subject_type = 'Modules\Course\Entities\Course'` and `subject_id = $id`, returned via `ActivityResource::collection(...)->additional(['meta' => ['next_page_url','prev_page_url','range']])`. Any event type for this course is included (not scoped to a particular event name).

---

## Orphaned/unused code in this module (confirmed by grep, not fabricated)

- **`InstructorMappingResource`** (`Modules/Course/Http/Resources/InstructorMappingResource.php`) — defined, never referenced anywhere else in the codebase. `CourseResource`'s own `instructors` key is built with an inline closure instead.
- **`CourseForCategoryPackageCreationResource`** and **`CourseForCategoryTreeResource`** — not used by any route in this module's own `api.php`, but they ARE live: nested and invoked from `Modules\CourseCategory\Http\Resources\CourseCategoriesForPackageCreationResource` / `CourseCategoryTreeResource` respectively, reachable only via `CourseCategory`'s own routes. See `CourseCategory.md` for the endpoints that actually surface them.
- Two private helper methods on `CourseBatchesResource` (`calculateTheNumberOfStudentsWith40PercentOrMoreSubmission`, `calculateTheNumberOfStudentsWithZeroSubmission`) are defined but never called from `toArray()` — dead code within a live Resource class.
- The "Course Created" activity-log call in `CourseController::store()` is fully commented out — course creation produces no activity-log row, unlike update/delete on the same entity.

---

## Summary

**22 `Route::` declarations** in `Modules/Course/Routes/api.php`, expanding to **~24 distinct HTTP endpoints** once `apiResource('course', ...)`'s 7 implicit routes (`index`, `create`, `store`, `show`, `edit`, `update`, `destroy`) are counted individually — of which **3 (`show`, `create`, `edit`) are confirmed broken** (undefined method → fatal 500), matching the failure pattern already documented for `NPS`'s `apiResource`.

**Notable findings:**
- `apiResource('course', ...)`'s `show`/`create`/`edit` actions are missing entirely — not stubs, genuinely undefined methods.
- `courseFaqs` (`GET /{course}/faqs`) has two independent hardcoded-literal bugs: page size pinned to `1` regardless of the `rows` param, and `meta.total` pinned to the literal integer `2` regardless of the course's actual FAQ count.
- `courseStudentAssignmentsDashboardData` caches its response under a request-parameter-independent key for 30 minutes — varying `rows` won't be reflected until the cache expires.
- `bootcamp-course.index`'s `meta.total_assignment` is a duplicate of `meta.total`, not an actual assignment count.
- `/search/courses` and `/search/specific-courses` both accept a `search` query param with **incompatible semantics** (substring string vs. array of ids) despite the similar endpoint names.
- `store()`'s activity-log call is commented out; `update()`'s and `destroy()`'s are not — inconsistent logging coverage for otherwise-parallel CRUD actions on the same entity.
- This module contains **5 separate, near-identical hand-rolled reimplementations** of the same base64-JSON cursor-pagination range calculation (`calculateRangeForCursor`, `...ForBatchesPerformance`, `...ForCourseIndexForAssignmentLibrary`, `...ForCourseFaqCursor`, plus `BootcampCourseController`'s own copy) — all functionally identical, none refactored into one shared helper.
- Cross-module fact: `CourseForCategoryPackageCreationResource`/`CourseForCategoryTreeResource` physically live in this module but are only reachable via `CourseCategory`'s routes.

**Confidence:** High — every endpoint traced directly from `CourseController.php`, `BootcampCourseController.php`, and the full `CourseTrait.php` (all read in their entirety), plus every Request/Resource class the routes actually invoke and the relevant `CourseRepository` query-building methods. The `show`/`create`/`edit` gap, the `courseFaqs` hardcoded-`1`/hardcoded-`2` bugs, and the orphaned-resource findings were independently confirmed via grep across the whole repository, not inferred from naming.
