# StudentDashboardManagement

Admin-facing configuration surface for the student "dashboard journey" checklist — defines which onboarding/progress steps (and sub-steps) show on a student's dashboard per course/bootcamp/package/category, and exposes read-side lookups (courses, categories, bootcamps, packages, activity logs) used to build the admin UI for managing those steps. This is the **configuration** side; the **student-facing consumption/interaction** side (viewing/marking/rating steps) lives in `StudentDashboard` (`StudentDashboardController`/`StudentDashboardTrait`), which depends on this module's trait — see that file's cross-module note.

**Module-wide auth:** all 13 routes are under `Route::middleware(['auth:sanctum', 'json.response'])->prefix('v1')` — **`auth:sanctum`, not `auth:student`**, confirming this is an admin/staff surface, not a student one. See [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for the `auth:sanctum` 401 shape and shared conventions.

The controller (`StudentDashboardManagementController`) composes `StudentDashboardManagementTrait` (all the real logic) and the app-wide `App\Http\Traits\ActivityLog` trait (used by `stepActivityLog`, see below). Only `index()` and `saveJourneySteps()` are defined directly on the controller class; every other named action (`getJourneySteps`, `getCategoriesWithAll`, `export`, `getJourneyDetails`, `stepActivityLog`, `getCourses`, `all_bootcamps_with_serch`, `deleteDraftedSteps`, `getParentSteps`) is either a trait method the controller calls into, or (for `getCategoriesWithAll`) a thin controller wrapper around a trait method (`getCategories()`).

---

## ⚠️ Systemic bug, confirmed by reading `app/Helpers/functions.php`: most "error status code" arguments in this module are silently swallowed

The global helper's real signature is:

```php
function apiResponse($data, string $message = 'Success', string $status = 'success', int $statusCode = 200): JsonResponse
```

The **third** positional parameter is `$status` (a string that becomes the `"status"` field in the JSON body), and the **fourth** is `$statusCode` (the actual HTTP response code). Throughout this trait, calls that clearly *intend* to set an HTTP status code instead pass it as the **third** argument, e.g. `apiResponse([], 'Something went wrong', 500)` or `apiResponse(false, 'Drafted Steps not found', 404)`. Because the parameter is typed `string` and PHP does weak-mode coercion (no `declare(strict_types=1)` in this file), the integer is silently coerced to its string form and stored in the **`status`** field — **the fourth parameter (`$statusCode`) is never touched and stays at its default, `200`.**

**Concrete, verified consequence: every one of this module's intended non-200 responses is actually returned as HTTP 200.** A parity test asserting `assertStatus(500)` or `assertStatus(404)` against any of the call sites below will fail — the real wire-level status is `200` in all of them, with the intended code visible only as a string inside the JSON body's `status` field. This is called out per-endpoint below; treat it as the single most important behavioral quirk in this module.

---

## `apiResource('studentdashboardmanagements', StudentDashboardManagementController)`

Registers `index`/`create`/`store`/`show`/`edit`/`update`/`destroy` under `/v1/studentdashboardmanagements`.

### `GET /v1/studentdashboardmanagements` — **live**
- **Controller method:** `index(Request $request)` (defined directly on the controller).
- **Request params (query):** `rows` (int, page size, default 15); `cursor` (opaque base64 token — see common conventions' cursor-pagination family; a tampered cursor triggers `abort(500, 'Cursor value tempered')`, a genuine 500 this time since `abort()` bypasses `apiResponse()` entirely).
- **Success:** `StudentDashboardResource::collection($data)->additional(['meta' => ['total' => <int>, 'range' => {'from','to','total'}]])` — the cursor-paginated family shape from common conventions. Eager-loads `students` (id/full_name/email/phone/reg_code), `enrollment`, `subject`.
- **Side effects:** read-only.

### `GET /v1/studentdashboardmanagements/create`, `GET /v1/studentdashboardmanagements/{id}` (show), `GET /v1/studentdashboardmanagements/{id}/edit` — **dead scaffolding**
Return raw Blade `view()` calls (`studentdashboardmanagement::create`/`show`/`edit`) — non-functional for a JSON API client; calling these against an `Accept: application/json` client will not produce a usable JSON body. Not real endpoints.

### `POST /v1/studentdashboardmanagements` (store), `PUT/PATCH /v1/studentdashboardmanagements/{id}` (update), `DELETE /v1/studentdashboardmanagements/{id}` (destroy) — **dead stubs**
All three method bodies are empty (`{ // }`) — they accept the request, do nothing, and implicitly return `null` (HTTP 200, empty/`null` JSON body). Not fabricated behavior to test against; flagged as non-functional per the task's dead-scaffolding convention.

---

## Journey-step configuration endpoints

### `GET /v1/dashboard-management/get-journey-steps`
Fetch the configured step tree for a given subject (course/bootcamp/package/category/"all").
- **Trait method:** `getJourneySteps(Request $request)`.
- **Request params (query, read via `$request->all()`, no FormRequest):** filters passed straight into `StudentDashboardJourneyStep::filterForType($filters)` — expected keys include `type` (1=All, 2=Course, 3=Bootcamp, 4=Package, per `stepType()`) and `is_draft`; exact filter-scope semantics live in the `filterForType` Eloquent scope on `StudentDashboardJourneyStep`, not re-derived here.
- **No steps found:** `apiResponse(['isDraftData' => 'Yes'|'No'], 'No steps found', 200)` → HTTP 200, body `{"data": {...}, "message": "No steps found", "status": "200"}` (⚠️ the `200` here is the coerced-to-string status-field bug described above; harmless in this specific case since the intended code was also 200, but the **field value is the string `"200"`, not the string `"success"`** — a client checking `status === "success"` will get a false negative even though this is a genuinely successful, non-error response).
- **Steps found:** `apiResponse({'type', 'is_draft', 'steps': <recursively formatted tree>, 'isDraftData'}, 'Steps fetched successfully', 200)` — same `status: "200"` field quirk. Each step object: `{id, title, description, subSteps, isVisible, sequenceId, image, old_id, idDeletable ('Yes'/'No'), reference_id, is_editable, is_for_old, is_for_new, is_hide_for_old, is_hide_for_new}`, root steps additionally carry `stepId` (= `sequence_id`).
- **Exception path:** `apiResponse([], 'Something went wrong', 500)` → **HTTP 200** (not 500 — see the systemic bug above), body `{"data": [], "message": "Something went wrong", "status": "500"}`.

### `POST /v1/dashboard-management/save-journey-steps`
Create/update/publish (or draft) journey steps and sub-steps.
- **FormRequest:** `StoreJourneyStepRequest` (the only validated endpoint in this module) — confirmed rules, read directly from the class:
  - `type`: `'required|'` — a **trailing-pipe no-op**; Laravel splits rules on `|` and discards empty segments, so this rule is functionally just `required` with **no actual type constraint** despite the field's name suggesting one. Any non-empty value (string, int, garbage) passes.
  - `is_draft`: `required|integer`
  - `steps`: `required|array`; `steps.*.title`: `required|string`; `steps.*.stepId`: `required|integer`
  - `steps.*.subSteps`: `nullable|array`; `steps.*.subSteps.*.title`: `required|string`; `steps.*.subSteps.*.isVisible`: `required|boolean`; `steps.*.subSteps.*.imageFile`: `nullable|image|mimes:png,jpg,jpeg,gif|max:2048` (KB)
  - A test asserting a 422 for an "invalid type" value will fail — only presence is checked, matching the prior survey.
- **Controller method:** `saveJourneySteps(StoreJourneyStepRequest $request)` → delegates entirely to trait `createJourneySteps($request->all())`.
- **Behavior summary** (full branch-by-branch logic lives in `StudentDashboardManagementTrait::createJourneySteps()`/`saveDraftSteps()`, ~350 lines — summarized rather than transcribed line-by-line):
  - `courseId`/`courseCategoryId`/`bootcampId`/`packageId` in the payload determine `type` (2/5/unset-defaults-from-input) and `subjectId`.
  - If `is_draft == 0` (publishing) **and** matching published steps already exist for this subject, dispatches the queued job `UpdateStepsForOldStudents::dispatch($data)->onQueue('default_high')` — an async side effect (propagates the new step config onto already-enrolled/older students' `Enrollment.dashboard_journey_steps` JSON column, based on the job name; not independently re-verified here since it's out of this trait's file).
  - `is_draft == 1` → routes to `saveDraftSteps()`, which creates/updates rows with `is_published = NOT_PUBLISHED`.
  - `is_draft == 0` → `createJourneySteps()`'s main branch: for each step, either updates an existing `StudentDashboardJourneyStep` (matched by `id`, with extra `old_id`-driven promote-draft-to-published logic that deletes the draft row after copying its data onto the original) or creates a new one (`is_published = IS_PUBLISHED`); each sub-step follows the analogous existing/new logic. Sub-step `imageFile` (if present) is stored to S3 under `uploads/result/feedback/{fileName}` and its public URL saved as `image`.
- **Success:** `apiResponse($createdSubSteps, 'Steps created successfully', 200)` → HTTP 200, `status: "200"` (string, same field quirk as above — again cosmetically harmless since 200 was intended). ⚠️ **`$createdSubSteps` is only ever appended-to inside the "create new sub-step" branch** — updates to existing steps/sub-steps are never pushed into it, so on a request that's 100% updates (no brand-new steps/sub-steps), the response `data` array will be **empty even though the update genuinely succeeded** — don't treat an empty `data` array from this endpoint as proof nothing happened.
- **Exception path:** `apiResponse([], $e->getMessage(), 500)` → **HTTP 200** (systemic bug), body `{"data": [], "message": "<actual exception message>", "status": "500"}` — note the *message* field is genuinely useful here (real exception text) even though the wire-level status code is misleading.

### `GET /v1/dashboard-management/get-journey-details`
Per-student progress view against a subject's journey steps (this is the admin-facing "see one student's checklist state" lookup — contrast with `StudentDashboard`'s student-facing `student-joureny-steps`, which is the same shape of computation scoped to the caller's own enrollment).
- **Trait method:** `getJourneyDetails(Request $request)`.
- **Request params (query):** `studentId` (required), `subjectType` (required, `in:course,bootcamp,package`), `subjectId` (required), `enrollmentId` (optional — if present, looks up steps by enrollment id directly instead of by student+subject).
- **No steps configured:** `response()->json(['status' => 'success', 'data' => []])` — this one uses hand-rolled `response()->json()`, not `apiResponse()`, so no status-code bug here.
- **Success:** `response()->json(['status' => 'success', 'data': <formatted step tree>, 'student': {'id','full_name'}, 'totalSteps': <int, count of root/parent steps>, 'current': <parent step sequence id or 'All Completed'>, 'subStepName': <current substep title or 'All Completed'>, 'percentage': <int>])`.
- **Side effects:** read-only.

### `GET /v1/dashboard-management/{stepId}/activity`
Activity-log history for a single student-step mapping.
- **Trait method:** `stepActivityLog($id)`.
- **No mapping found for `$id`:** `apiResponse([], 'No action taken on this step by student', 200)` → HTTP 200, `status: "200"` field (harmless, matches intended code).
- **Found:** delegates to `App\Http\Traits\ActivityLog::logOfJourneyStep($id, [...])` — a cursor-style paginated `Activity` (Spatie Activitylog) listing filtered to `subject_type = StudentDashboardJourneyStepsMapping::class`. **Correction to a prior survey pass:** that pass flagged `StudentActivityResource` as "imported but never instantiated" in the controller — true of the controller's own file, but `StudentActivityResource::collection(...)` **is** actually invoked, inside `ActivityLog::logOfJourneyStep()` (a different file, `app/Http/Traits/ActivityLog.php`, imported there). This endpoint's real response shape is: `StudentActivityResource::collection($paginator)->additional(['meta' => {'next_page_url', 'prev_page_url', 'range': {'from','to','total'}}])`, each item `{actionName (the activity's `event`), actionedAt (formatted `Y-m-d G:i:s`), description}`. `rows` query param controls page size (default 15).
- `JourneyStpesResource`, separately, **is** confirmed genuinely dead (imported in the controller, zero instantiations anywhere in the codebase via grep) — that half of the prior survey's claim holds.

### `POST /v1/dashboard-management/delete-drafted`
- **Trait method:** `deleteDraftedSteps(Request $request)`. No FormRequest.
- **Request params (body):** `id` — expected to be an **array** of step ids (`$data['id']`), read via `$request->all()`.
- **Any null present in `id`:** `apiResponse(false, 'Drafted Steps not found', 404)` → **HTTP 200** (systemic bug), body `{"data": false, "message": "Drafted Steps not found", "status": "404"}`.
- **Success:** for each id, if the step exists and `is_published == NOT_PUBLISHED` (i.e., it's actually a draft), deletes it; if it's a top-level step (`parent_id == null`), also deletes its children — ⚠️ **the child-lookup is buggy**: `StudentDashboardJourneyStep::where('parent_id', $data['id'])` compares `parent_id` against the **entire `id` array** rather than the single current `$id` being iterated (should almost certainly be `where('parent_id', $id)`, or `whereIn('parent_id', $data['id'])`). Laravel's query builder will coerce an array passed to a plain `where(..., $array)` equality clause in a way that is unlikely to match real integer `parent_id` values — in practice, **child drafted sub-steps are likely never deleted by this branch**, leaving orphaned draft sub-step rows behind. Worth a dedicated regression test: create a drafted parent+child, delete the parent via this endpoint, then check whether the child row still exists.
- **Success response:** `apiResponse(true, 'Drafted Steps deleted successfully', 200)` → HTTP 200, `status: "200"` field (harmless here).

### `GET /v1/dashboard-management/get-parent-steps`
Resolve the effective step list for a subject, inheriting from category/global parent steps where the subject has no steps of its own, and merging where it has some.
- **Trait method:** `getParentSteps(Request $request)`.
- **Request params (query):** `id` (subject id), `type` (subject type constant), plus whatever else is in `$request->all()` (used again for `isDraftedCheck`).
- **No self-steps and no parent-steps found:** `apiResponse([], 'No steps found', 200)`.
- **No self-steps, parent-steps exist:** returns the parent tree as inherited (`is_editable` forced to `'No'`), `apiResponse($data, 'Steps fetched successfully', 200)`.
- **Both self- and parent-steps exist:** merges them — self-steps that reference a parent step (`reference_id`) inherit the parent's field values (except `id`/`parent_id`/`reference_id`/timestamps) and are marked `is_editable: 'No'`; parent steps not yet referenced by any self-step are added in as new inherited steps. Returns the merged/sorted tree, `apiResponse($data, 'Steps fetched successfully', 200)`.
- ⚠️ **Exception path returns a bare string, not JSON at all:** `catch (\Exception $e) { ... return $e->getMessage(); }` — no `apiResponse()`, no `response()->json()`. The raw exception message string is returned directly as the action's return value; Laravel will serialize this as a JSON string literal (e.g. `"Some error"`) with HTTP 200, not as an object/envelope of any kind — a parity test expecting `{"status": ..., "message": ...}` on this failure path will not find it.
- All success branches use `apiResponse(..., 200)`, so the `status: "200"` field-string quirk applies uniformly (cosmetically harmless since 200 is genuinely intended throughout this endpoint).

---

## Reference/lookup endpoints

### `GET /v1/dashboard-management/course-categories`
- **Controller method:** `getCategoriesWithAll()` (thin wrapper, defined directly on the controller) → trait `getCategories()`.
- **Success:** `apiResponse($data, 'success', 200)` → HTTP 200, `status: "200"` field (harmless — 200 intended). `$data` = `CourseCategory::query()->select('id','category_name')->whereStatus(CourseCategory::ACTIVE)->get()` — a flat array of `{id, category_name}`.
- **Note:** despite the method name and commented-out dead code in the controller suggesting an "All Categories" pseudo-entry (`id: 100`) was once prepended, that code is fully commented out — **no synthetic "All" entry is actually added**; the response is exactly the active-categories list, nothing more. Don't assume an `id: 100` sentinel exists in the live response.

### `GET /v1/category-courses`
- **Trait method:** `getCourses(Request $request)`.
- **Request params (query):** `search` (optional, `LIKE` filter on `course_name`); `categoryId` (optional — `100` is treated as a sentinel meaning "all categories", i.e. the filter is skipped when `categoryId == 100`, consistent with the "All Categories" convention referenced above even though that entry isn't synthesized by `course-categories` itself; the `100` value must originate from the frontend's own hardcoded convention).
- **Success:** `apiResponse($data, 'success', 200)` — `$data` is a mapped array of `{id, name}` for `Course::STATUS_ACTIVE` courses. `status: "200"` field quirk, cosmetically harmless.
- **Exception path:** `apiResponse(false, $e->getMessage())` — only 2 args passed, so this uses the **default** `$status = 'success'` and default `$statusCode = 200` — ⚠️ **an actual exception here returns `{"data": false, "message": "<exception text>", "status": "success"}`** — `status` says `"success"` on a genuine error path, the worst version of the "don't trust status" caution in this module, since here it's not even a coerced-int artifact, it's a literal, unconditional `"success"` default that was never overridden.

### `GET /v1/get-bootcamps`
- **Trait method:** `all_bootcamps_with_serch()` (method name typo — `serch` — preserved verbatim; this is the literal PHP method name, not a documentation error).
- **Request params (query):** `search` (optional, matches bootcamp `id` or `name` via `LIKE`).
- **Success:** `SearchBootcampResource::collection(...)->additional(['meta' => ['total' => <count>]])` — the resource-collection pagination family from common conventions (`{"data": [...], "meta": {"total": N}}`, no `message`/`status` key at all — genuinely different envelope from every other endpoint in this file, since it bypasses `apiResponse()` entirely).

### `GET /v1/get-packages` — ⚠️ cross-module delegation
- **Declared in this module's route file**, but points at `PackageController::search()` in the **`Package` module** (`Modules\Package\Http\Controllers\PackageController`), not `StudentDashboardManagementController`. Documented here because that's where the route is registered, per the cross-module-delegation convention.
- **Real behavior (traced from `PackageController::search()`):** `SearchPackageResource::collection($this->packageRepo->searchPackages())->additional(['meta' => ['total' => count($this->packageRepo->searchPackages())]])` — note `searchPackages()` is called **twice** (once for the collection, once just to `count()` it) — not a correctness bug, just a redundant duplicate query. No request params are read by this action at all (no `search`/`categoryId`-style filtering, unlike `get-bootcamps`/`category-courses` above) — it always returns the full package list. Same `{"data": [...], "meta": {"total": N}}` envelope family as `get-bootcamps`.

---

## Async export

### `GET /v1/studentdashboardmanagements/export/csv`
- **Trait method:** `export(Request $request)`.
- **Behavior:** dispatches `StudentDashboardManagementCsvDownloadStart::dispatch(auth()->user(), $request->all())` and returns immediately — **fire-and-forget**, no synchronous file in the response.
- **Success:** `apiResponse('', 'Student Dashboard Management Csv file exporting started')` → `{"data": "", "message": "Student Dashboard Management Csv file exporting started", "status": "success"}`, HTTP 200 (default args used correctly here, no status-code bug — this is a 3-arg-max call where the 3rd arg was never supplied, so defaults apply cleanly).
- **Side effects:** whatever the queued job does (presumably emails/notifies the requesting admin with a download link once complete) — out of scope of this trait file; poll/wait rather than expecting a synchronous file, per the async-export convention used elsewhere in this app (e.g. Roles/Package CSV exports).

---

## Summary

- **Endpoint count:** 13 routes as scoped — 1 `apiResource` line (7 sub-routes: 1 live `index`, 3 dead Blade-view actions, 3 dead empty-body stubs) + 12 explicit named routes, all confirmed live and functioning (modulo the systemic status-code bug and the two flagged real logic bugs below). This matches the task's pre-survey of "13 routes."
- **Structural surprises / corrections to the prior survey:**
  1. **New finding, high-value:** the `apiResponse($data, $message, $intendedCode)` 3-argument call pattern used throughout this trait **never actually sets the HTTP status code** — it's silently written into the `status` JSON field as a stringified number instead, so every intended 404/500 in this file is wire-level **HTTP 200**. This affects `getJourneySteps` (500 path), `createJourneySteps` (500 path), `deleteDraftedSteps` (404 path), and cosmetically (but harmlessly, since 200 was already intended) most success paths too.
  2. **Correction:** `StudentActivityResource` is **not** dead code — it's genuinely instantiated inside `App\Http\Traits\ActivityLog::logOfJourneyStep()`, which backs `stepActivityLog`. Only `JourneyStpesResource` is confirmed truly dead/unused. The prior survey conflated the two.
  3. **New finding:** `deleteDraftedSteps`'s child-step deletion (`where('parent_id', $data['id'])` against a whole array instead of the single current id) is very likely a real bug that leaves orphaned drafted sub-steps behind — flagged for a dedicated regression test.
  4. **New finding:** `getCourses`'s exception path returns `status: "success"` on a genuine failure (unconditional default, not just the coercion artifact above) — the single worst instance of "don't trust the status field" in this module.
  5. **New finding:** `getParentSteps`'s exception path returns a bare exception-message string, not any JSON envelope at all.
  6. `saveJourneySteps`'s response `data` array under-reports what actually happened (only newly-created sub-steps are collected; updates are invisible in the response body even though they persist).
- **Confidence:** High — every endpoint traced directly from the controller, the full ~1525-line `StudentDashboardManagementTrait`, the `StoreJourneyStepRequest` FormRequest, the `ActivityLog` trait's `logOfJourneyStep`, and `PackageController::search()` for the cross-module route. The apiResponse status/statusCode finding was independently verified by reading `app/Helpers/functions.php`'s literal function signature, not inferred.
