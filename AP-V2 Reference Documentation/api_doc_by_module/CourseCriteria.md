# CourseCriteria Module API Documentation

The `CourseCriteria` module owns per-course (and per-bootcamp-course) pass/fail marking criteria: minimum exercise counts, marks needed to pass, and writing-assignment thresholds used later by `CourseCompletionMaster`'s marksheet calculation. It exposes two nearly-identical controllers over the same underlying entity — one for standard courses, one for bootcamp courses with a narrower field set.

**Module-wide auth:** every route in `Modules/CourseCriteria/Routes/api.php` is `auth:sanctum` + `json.response`, mounted under `/api/v1/...` (standard `prefix('api')->middleware('api')` wrapping from `RouteServiceProvider`). No route in this file deviates from this.

See [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for the app-wide response envelope styles, standard error shapes, and pagination conventions referenced below instead of being repeated per endpoint.

## ⚠️ Only `store`/`update`/`destroy` are wired — `index`/`show` are not real endpoints here

```php
Route::apiResource('course-criteria', 'CourseCriteriaController')->only(['store', 'update', 'destroy']);
Route::apiResource('bootcamp-course-criteria', 'BootcampCourseCriteriaController')->only(['store', 'update', 'destroy']);
```
Both `apiResource` calls are explicitly scoped with `->only([...])` — `index`/`show`/`create`/`edit` were never registered at all (not even as dead stubs), so `GET /api/v1/course-criteria` and `GET /api/v1/course-criteria/{id}` return the standard 404 route-not-found shape, not a controller response. Neither controller class defines `index()`/`show()` methods either, consistent with this.

Both controllers (`CourseCriteriaController`, `BootcampCourseCriteriaController`) pull their real create/update logic from the same shared `CourseCriteriaTrait` (`Modules/CourseCriteria/Http/Traits/CourseCriteriaTrait.php`) via `use CourseCriteriaTrait;` — `createCourseCriteria($request)` and `updateCourseCriteria($request, $id)`. `CourseCriteriaController` extends `App\Http\Controllers\Controller` but never calls `$this->apiResponse()`; `BootcampCourseCriteriaController` extends the bare `Illuminate\Routing\Controller` (no `apiResponse()` instance method available on it at all). **Both controllers instead use the global `apiResponse()` helper function exclusively** — a consistent style within this module, just not the instance-method variant.

---

## Standard course criteria

### `POST /api/v1/course-criteria` (route name `course-criteria.store`, controller `CourseCriteriaController::store`)
- **Request body** (`Store` FormRequest, `authorize()` always `true`):
  - `course_id` — required, `exists:courses,id`, **`unique:course_criterias,course_id`** (one criteria row per course)
  - `minimum_exercises` — `required_unless:course_id,!=,1|integer|min:0` — **the exact literal rule string in source**. Laravel's `required_unless:field,value1,value2,...` treats every comma-separated token after the field name as an independent "skip-required" value; here the tokens are `!=` (a literal string, never equal to a real numeric `course_id`) and `1`. The practical effect: **the field is NOT required only when `course_id == 1`; for every other course it IS required.** This is the inverse of what the rule name suggests ("required unless not 1") and is almost certainly a hardcoded-id bug (likely meant to special-case bootcamp courses via some sentinel), not intentional business logic — confirmed directly from `Store.php:31`, not inferred. **A parity test must submit with `course_id=1` (not required) vs. any other id (required) to reproduce this exactly.**
  - `each_exercises_marks` — identical `required_unless:course_id,!=,1|integer|min:0` rule, same bug/behavior.
  - `min_attempt_exercises_percent` / `no_writing_assignments` / `writing_assignments_marks` — each `nullable|integer|min:0`.
  - `lms_mcq` — `nullable|boolean`.
  - `pass_marks_needed_percent` / `pass_marks_needed` / `total_marks` — each `required|integer|min:0`.
- **Success response:** global `apiResponse(['course_criteria' => CourseCriteriaResourse::make(...)], 'Course Criteria created successfully', statusCode: 201)` → `{"data": {"course_criteria": {...}}, "message": "Course Criteria created successfully", "status": "success"}`.
- `CourseCriteriaResourse` (note the misspelled class name "Resourse" — literal in source, preserve exactly): raw-merged model attributes minus `created_at`/`updated_at` (i.e. `id`, `course_id`, `minimum_exercises`, `each_exercises_marks`, `min_attempt_exercises_percent`, `no_writing_assignments`, `writing_assignments_marks`, `lms_mcq`, `pass_marks_needed_percent`, `pass_marks_needed`, `total_marks`, and `deleted_at` since the underlying model uses `SoftDeletes` and only `created_at`/`updated_at` are excluded).
- **Side effects:** an `Activity::create()` log row (`log_name: 'Course Criteria Added'`) built from a hand-concatenated description string listing every submitted field (falling back to the literal string `'null'`, not actual `null`, for any missing field) — bypasses the app's usual `activity()` helper.

### `PUT/PATCH /api/v1/course-criteria/{id}` (route name `course-criteria.update`, controller `CourseCriteriaController::update`)
- **Request body** (`Update` FormRequest): all nine criteria fields (`minimum_exercises` ... `total_marks`) optional (`nullable`), no `course_id` field accepted/validated on update.
- **Error response:** `apiResponse([], 'Course Criteria Not Found', 'error', 404)` if `{id}` doesn't resolve via `courseCriteriaRepo->findById($id)` — a plain repository lookup, not Laravel route-model binding, so a non-numeric or non-existent id gets this clean 404 shape rather than a `ModelNotFoundException`.
- **Success response:** `apiResponse(['course_criteria' => CourseCriteriaResourse::make(...)], 'Course Criteria updated successfully')` → same shape as store, HTTP 200 (no explicit `statusCode` passed).
- **Side effects:** same hand-built `Activity::create()` pattern as store (`log_name: 'Course Criteria Updated'`), also fetching `$course_id` from the *pre-update* row for the activity's `subject_id` (via a second, redundant `findById` call before `updateCourseCriteria` runs).

### `DELETE /api/v1/course-criteria/{id}` (route name `course-criteria.destroy`, controller `CourseCriteriaController::destroy`)
- **Error response:** same `apiResponse([], 'Course Criteria Not Found', 'error', 404)` shape as update.
- **Behavior:** a **soft delete** — `CourseCriteria` entity uses the `SoftDeletes` trait and `BaseRepository::delete()` calls plain Eloquent `->delete()`, so the row is retained with `deleted_at` set, not hard-removed.
- **Success response:** `apiResponse([], 'Course Criteria deleted successfully')` — `data` is an empty array, HTTP 200.
- **Side effects:** `Activity::create()` (`log_name: 'Course Criteria deleted'`), description interpolates `auth()->user()->first_name`/`last_name` directly (no null-guard — would throw if somehow unauthenticated, but `auth:sanctum` guarantees a user here).

---

## Bootcamp course criteria (narrower field set)

### `POST /api/v1/bootcamp-course-criteria` (route name `bootcamp-course-criteria.store`, controller `BootcampCourseCriteriaController::store`)
- **Request body** (`StoreBootcampCourseCriteriaRequest`): `course_id` — required, `exists:courses,id`, `unique:course_criterias,course_id` (same unique constraint, same table, as the standard course path — a bootcamp course and a standard course criteria row cannot coexist for the same `course_id`, and neither can two bootcamp criteria for the same course). Only 5 fields total: `no_writing_assignments`, `writing_assignments_marks`, `pass_marks_needed_percent`, `pass_marks_needed`, `total_marks` — each `required|integer|min:0`. **Confirmed: `minimum_exercises`, `each_exercises_marks`, `min_attempt_exercises_percent`, and `lms_mcq` are entirely absent from this FormRequest** — the bootcamp path has no way to set these four fields at creation time (they stay `null`/unset on the row).
- **Success response:** `apiResponse(['course_criteria' => CourseCriteriaResourse::make(...)], 'Bootcamp Course Criteria created successfully', statusCode: 201)` — same `CourseCriteriaResourse` shape as the standard path (all columns present in the response regardless of which fields this endpoint actually lets you set).
- **Side effects:** none — unlike the standard-course controller, this action does **not** write an activity log.
- Uses the same `createCourseCriteria()` trait method as the standard controller, which does `$request->only([...all 10 fields...])` — since the unset fields are simply absent from `$request->only()`, they're omitted from the `create()` call entirely (left to column defaults/`null`), not explicitly nulled.

### `PUT/PATCH /api/v1/bootcamp-course-criteria/{id}` (route name `bootcamp-course-criteria.update`, controller `BootcampCourseCriteriaController::update`)
- **Request body** (`UpdateBootcampCourseCriteriaRequest`): the same 5 fields as store, all `nullable|integer|min:0` instead of `required`.
- **Error response:** `apiResponse([], 'Bootcamp Course Criteria Not Found', 'error', 404)`.
- **Success response:** `apiResponse(['course_criteria' => CourseCriteriaResourse::make(...)], 'Bootcamp Course Criteria updated successfully')`.
- **Side effects:** none (no activity log on this update path, unlike the standard controller's update).

### `DELETE /api/v1/bootcamp-course-criteria/{id}` (route name `bootcamp-course-criteria.destroy`, controller `BootcampCourseCriteriaController::destroy`)
- **Error response:** same 404 shape as its update.
- **Behavior:** same soft-delete via the shared repository.
- **Success response:** `apiResponse([], 'Bootcamp Course Criteria deleted successfully')`.
- **Side effects:** **does** log activity here (unlike its own update, but using the modern `activity()->on(...)->by(...)->withProperties([...])->event(...)->log(...)` helper style — `event: 'Bootcamp Course Criteria Deleted'`, properties `{course_criteria_id}` — a different logging mechanism from the standard controller's hand-rolled `Activity::create()` calls, despite both being in the same module).

---

## Summary

**Routes documented:** 6 `Route::` entries (2 `apiResource(...)->only([...])` calls × 3 actions each) — all 6 reachable, no dead/broken routes found (the `->only()` scoping means `index`/`show` were deliberately never registered, not silently broken).

**Notable findings for parity testing:**
- **Confirmed bug:** `required_unless:course_id,!=,1` on `minimum_exercises`/`each_exercises_marks` in the standard `Store` request makes these fields required for every course **except** `course_id == 1` — a hardcoded-id special case, not a general "unless bootcamp" rule as the intent likely was. Verified directly against `Store.php` source.
- The bootcamp-course-criteria path shares the exact same `course_criterias` table and the exact same `unique:course_criterias,course_id` constraint as the standard path — a bootcamp criteria row and a standard criteria row for the same `course_id` are mutually exclusive at the DB-constraint level, not just conceptually.
- Activity logging is inconsistent within the module: standard controller logs on store+update+destroy (hand-rolled `Activity::create()`); bootcamp controller logs only on destroy (modern `activity()` helper) — not a uniform pattern across the two nearly-identical controllers.
- `CourseCriteriaResourse` (misspelled class name, preserved verbatim) returns the same full shape regardless of which controller/endpoint created the row — a bootcamp-criteria row's response will show `null`/absent values for the 4 fields that path can never set.

**Confidence:** High — every rule and behavior traced directly from `Store.php`, `Update.php`, `StoreBootcampCourseCriteriaRequest.php`, `UpdateBootcampCourseCriteriaRequest.php`, both controllers, `CourseCriteriaTrait.php`, `CourseCriteriaResourse.php`, the `CourseCriteria` entity, and `BaseRepository::delete()`/`update()`. The `required_unless` bug and the bootcamp field-omission behavior were independently re-verified against the exact source lines, not taken from `API_SPECIFICATIONS.md`'s paraphrase alone.
