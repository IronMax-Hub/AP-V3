# CourseCategory Module API Documentation

The `CourseCategory` module owns the admin-facing CRUD, search, CSV export, activity log, and per-category course-performance rollups for `course_categories` — the taxonomy courses are grouped under. It also transparently manages a category's pass-mark criteria row (a `CourseCategoryCriteria` entity) as an embedded side effect of its own `store`/`update` actions — see the dedicated ⚠️ note below, since the separate `CourseCategoryCriteria` module ([`./CourseCategoryCriteria.md`](./CourseCategoryCriteria.md)) manages the exact same underlying table via its own independent endpoints.

**Module-wide auth:** every route in `Modules/CourseCategory/Routes/api.php` is `auth:sanctum` + `json.response`, mounted under `/api/v1/...` (standard `prefix('api')->middleware('api')` wrapping from `RouteServiceProvider`, confirmed). No route in this file deviates.

See [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for the app-wide response envelope styles, standard error shapes, and pagination conventions referenced below instead of being repeated per endpoint.

All controller logic lives on `CourseCategoryController` (`Modules/CourseCategory/Http/Controllers/CourseCategoryController.php`), which additionally pulls in `CourseCategoryTrait` (`Http/Traits/CourseCategoryTrait.php`, cursor-range math + the course-performance query builder), `ActivationAndDeactivationProcess` (app-level trait, used by `changeStatus`), and `ActivityLog` (app-level trait, supplies `logOfCourseCategory()` used by the `activity` endpoint). Every response uses `$this->apiResponse()` (instance method) except three endpoints that call the **global** `apiResponse()` function instead (`searchCourseCategoriesWithArray`, `coursesPerformanceTotal`, `changeStatus`, `export`) — same shape either way, but named per the "check every endpoint" rule in the common conventions.

## ⚠️ `apiResource('course-categories', ...)` is partially broken, same landmine pattern as NPS/CourseFaq

```php
Route::apiResource('course-categories', 'CourseCategoryController'); // wires index, store, show, update, destroy (+ create/edit for web)
```
`CourseCategoryController` implements `index`, `store`, `update`, `destroy` — **`show` does not exist anywhere in the class** (confirmed by reading the full controller). `GET /api/v1/course-categories/{course_category}` will hit a PHP `Error: Call to undefined method`, surfacing as an uncaught-exception **500**, not a clean 404. (`create`/`edit` are web-only apiResource actions and irrelevant to the API surface.)

## ⚠️ `store`/`update` silently manage a second table's rows (`CourseCategoryCriteria`)

- `store()`: if the request body contains **any** of `minimum_exercises`/`each_exercises_marks`/`pass_marks_needed_percent`/`pass_marks_needed`/`total_marks` (checked via `hasAny`), it also creates a `CourseCategoryCriteria` row via `CourseCategoryCriteriaRepository::create()`, passing through everything **except** the category's own 4 fields (`category_name`,`status`,`parent_id`,`created_by`) — i.e. any extra keys in the payload (including junk ones) get forwarded into the criteria `create()` call.
- `update()`: driven by an `add_or_not` boolean field — `1` creates-or-updates the category's `criteria` relation, `0` deletes it if present, anything else (including omission — see Request params below) does neither.
- **This is the same data the dedicated `CourseCategoryCriteria` module's own `POST /v1/course-category-criteria` / `PUT /v1/course-category-criteria/{id}` endpoints manage** (see [`./CourseCategoryCriteria.md`](./CourseCategoryCriteria.md)). Both paths write to the same `course_category_criterias` table row for a given category — a client that creates a category with inline criteria fields here, then also calls the dedicated endpoint, is operating on the same row twice via two different validation rule sets. Confirm with the team which is the intended source of truth before treating either as canonical for parity testing.

---

## `GET /course-categories/export` (no route name, controller `export`)
- **Request params:** `data` — optional array, `Validator::make()` inline (not a FormRequest).
- **Success response:** global `apiResponse('', 'Course Category Csv file exporting started')` → `{"data": "", "message": "...", "status": "success"}` (`data` is an empty **string**).
- **Side effects:** queues `CourseCategoryCSVDownloadStart` (`default_medium` queue) — writes a CSV (`Category Name`,`Total Courses`,`Criteria`, ...) to local `storage/tmp/` then presumably S3 (not fully traced), and emails the requesting user via `CourseCategoryCSVCompletedMail` once done. Fire-and-forget — response returns before export completes.

## `GET /search/course-categories` (route name `course-categories.search`, controller `search`)
- **Query params:** `search` (optional, `LIKE` on both `id` and `category_name`), `offset` (default 0), `limit` (default 10) — note this endpoint uses raw offset/limit, **not** the `rows`/`cursor` scheme used by `index()` below.
- **Success response:** `SearchCategoryResource::collection(...)` → `{"data":[{"id","category_name"}, ...], "meta":{"total": N}}` — resource-collection shape. `total` here is the **filtered** count (same `search` condition reapplied), not the grand total.

## `POST /course-categories/status/change` (route name literally `roles.status.change` — copy-pasted from the Role module, not renamed)
- **Request body:** raw `Request`, validated inline via `Validator::make()` (not a FormRequest): `category_ids` required array, each `exists:course_categories,id`; `comment` required string; `status` required, `in:activate,deactivate`.
- **Success response:** global `apiResponse([], 'categories deactivated successfully')` or `'categories activated successfully'`, both HTTP 200.
- **Side effects:** bulk `UPDATE ... SET status = ...` on all matching ids; `ActivationAndDeactivationProcess::addActivityLogsAndComments()` writes an activity log entry with the `comment` per the app's generic activation/deactivation logging path.
- **Error responses:** standard 422 (via the inline `Validator`) if `category_ids`/`comment`/`status` fail their rules.

## `GET /search/specific-course-categories` (route name `course-categories.specific.search`, controller `searchCourseCategoriesWithArray`)
- **Query params:** `search` — optional array of ids, `whereIn('id', ...)`.
- **Success response:** global `apiResponse($this->courseCategoryRepo->searchCourseCategoriesWithArray())` → `{"data": [{"id","category_name"}, ...], "message": "Success", "status": "success"}` — **not** a resource-collection shape (no `meta`), despite the sibling `search` endpoint above using one for near-identical data.

## `POST /course-categories/transfer-to-other` (route name `course-categories.transfer-to-other`, controller `transferToOther`)
- **Request body** (`TransferToNewCategoryRequest`): `current_id` required `exists:course_categories,id`; `new_id` required `exists:course_categories,id` — **no check that `current_id !== new_id`**, and no check that `new_id` actually differs in any meaningful way; a self-transfer (`current_id == new_id`) passes validation and runs a no-op bulk update.
- **Behavior:** if `current_id` has zero associated courses, no-op (`courses()->count() > 0` gate) — response is still 200 success either way.
- **Success response:** `$this->apiResponse([], 'Courses updated with new course category id')` if courses were moved, else `$this->apiResponse([], 'Nothing to update')` — **both 200, both success-shaped**; the only way to tell "did anything change" apart is the exact `message` string, not `status`/HTTP code. A parity test must not treat this as a boolean-success signal without reading `message`.
- **Side effects:** `CourseRepository::updateTheCourseCategoriesToNew()` bulk-reassigns `course_category_id` on all of `current_id`'s courses to `new_id`. `current_id`'s own row (and its criteria) is untouched — this only reassigns courses, it does not merge/delete the old category.

## `GET /course-categories-for-package-creation` (route name `course-categories.list-for-package-creation`, controller `listForPackageCreation`)
- **Success response:** `CourseCategoriesForPackageCreationResource::collection($this->courseCategoryRepo->categoriesWithCourses())` — resource-collection shape, `{"data":[...]}` (**no `meta`** — this endpoint returns the full unpaginated set of categories that have at least one course). Each item: category columns except `created_at`/`updated_at`/`deleted_at`/`status`/`parent_id`/`created_by`/`updated_by`, plus `courses` (nested `CourseForCategoryPackageCreationResource::collection`, defined in the `Course` module) and a hardcoded `checked: false` on every row.

## `GET /course-categories/{courseCategory}/courses/performance` (route name `course-categories.courses.performance`, controller `coursesPerformance`)
- **Path param:** `courseCategory` — route-model-bound `CourseCategory`; a non-existent id 404s via the standard `ModelNotFoundException` shape (see common conventions).
- **Query params:** `rows` (optional int, default **10** — not the module's usual default of 15), `search` (optional, `LIKE` on `course_name`), `cursor` (opaque base64 token, same scheme as elsewhere but computed by a **category-scoped** range function, `calculateCoursePerformanceRangeForCursor()` — distinct from `index()`'s `calculateRangeForCursor()`, both live in the same trait).
- **Success response:** `CategoriesCoursesResource::collection(...)->additional(['meta' => ['total', 'range']])`. Each item merges `id`/`course_name` with a large set of computed assignment-submission metrics per course (`number_of_students`, `submitted_assignments_percentage`, several "students where submitted assignments is 40%-or-above / is-zero" counts and percentages, one variant of which excludes package-based/no-batch enrollments) — all derived client-side from an eager-loaded `enrollments` collection with per-enrollment assignment counts, not database aggregates.
- **Notes:** heavy N+1-shaped in-PHP `Collection::filter()`/`count()` looping per course per row — a large category could be slow; worth a performance-oriented parity check, not just a shape check.

## `GET /course-categories/{courseCategory}/courses/performance/total` (route name `course-categories.courses.performance.total`, controller `coursesPerformanceTotal`)
- **Success response:** global `apiResponse([...])` — hand-rolled array of the **same** metric family as `CategoriesCoursesResource` above, but pre-aggregated across **all** courses in the category (ignores `rows`/`cursor`, applies the same `search` filter if present) via `$courses->sum(...)` over the eager-loaded counts. Uses the app-wide `calculateThePercentage()` helper (0 if denominator ≤ 0).
- **Notes:** re-runs `searchAndFilterQueryForCoursePerformance()` **twice** in this one action (once for the `$courses->sum(...)` calls, once implicitly nowhere else — actually only once, assigned to `$courses` and reused) — no separate note needed beyond: this is a full, unpaginated scan of the category's courses (with all their enrollments eager-loaded) on every call.

## `apiResource('course-categories', 'CourseCategoryController')` — 4 of 5 wired actions functional

### `GET /course-categories` (`index`)
- **Query params:** `rows` (optional int, default 15), plus whatever `status`/`search` filters `CourseCategoryRepository::searchQuery()` supports (`status` exact match, `search` `LIKE` on `category_name`), `cursor` (opaque base64 token, standard scheme).
- **Success response:** `CourseCategoryResponse::collection(...)->additional(['meta' => [...]])` → `{"data":[...], "meta":{"total","total_course_category","total_active_course_category","total_deactive_course_category","range"}}` — **`total` and `total_course_category` are always identical values** (both call the same repository method) sitting side by side in the same `meta` object, a genuine redundancy, not two different counts.
- `CourseCategoryResponse` fields: `status`,`id`,`category_name`,`parent_id` (raw-merged), plus `criteria` (nested `CourseCategoryCriteriaResourse`, `null` if the category has no criteria row) and `total_courses` (live count).

### `POST /course-categories` (`store`)
- **Request body** (`Store`): `parent_id` optional int; `category_name` required string max:255, unique in `course_categories` (ignoring `category_id` if present in the payload — a leftover `ignore()` clause that only matters for an update-via-store style call, not a normal create); `status` required boolean. Conditionally, if any pass-mark field is present: `minimum_exercises`/`each_exercises_marks`/`pass_marks_needed_percent`/`pass_marks_needed`/`total_marks` each `required_with` the other four (int, min:0); `min_attempt_exercises_percent`/`no_writing_assignments`/`writing_assignments_marks` optional int min:0; `lms_mcq` optional boolean. **Note a cosmetic-only source quirk**: several `required_with:` rule strings in `Store::rules()` contain embedded literal newlines/indentation inside the comma-separated field list (e.g. `'required_with:each_exercises_marks,\n    pass_marks_needed_percent,\n    ...'`) — Laravel's rule parser tolerates this (whitespace around list items is trimmed), so it does not change validation behavior, but is worth knowing if you're diffing rule strings verbatim against a migrated implementation.
- **Success response:** `$this->apiResponse(['course_category' => CourseCategoryResponse::make(...)], 'Course Category created successfully', statusCode: 201)`.
- **Side effects:** creates the `CourseCategory` row (`created_by` forced server-side to the authenticated user), and conditionally the linked `CourseCategoryCriteria` row — see the ⚠️ note above.

### `PUT/PATCH /course-categories/{course_category}` (`update`)
- **Request body** (`UpdateRequest`): `parent_id` optional int; `course_category_id` **required**, `exists:course_categories,id` (send both the path id and this body field — the body field, not the route param, is what's actually validated/used for the uniqueness-ignore check); `category_name` optional, unique (ignoring `course_category_id`); `add_or_not` **required** boolean (controls the criteria create/update/delete branch — see note above); if `add_or_not == 1`: `minimum_exercises`/`each_exercises_marks`/`pass_marks_needed_percent`/`pass_marks_needed`/`total_marks` become `required_if:add_or_not,1`; always-optional `min_attempt_exercises_percent`/`no_writing_assignments`/`writing_assignments_marks` (int min:0), `lms_mcq` (int min:0 here — **not `boolean` like `Store`'s equivalent rule**, an inconsistency between the two FormRequests for the same underlying column).
- **Success response:** `$this->apiResponse(['course_category' => CourseCategoryResponse::make($courseCategory->fresh())], 'Course Category and Criteria updated successfully')` — message always mentions "and Criteria" even on calls where `add_or_not` didn't touch criteria at all.
- **Error responses:** `$this->apiResponse([], 'Course Category Not Found', 'error', 404)` if the id (route param, looked up via repository — not the `course_category_id` body field) doesn't resolve.

### `DELETE /course-categories/{course_category}` (`destroy`)
- **Error responses:** `$this->apiResponse([], 'Course Category Not Found', 'error', 404)` if missing; `$this->apiResponse([], 'Course Category is associated with courses', 'error', statusCode: 422)` if `courses()->count() > 0` — the category's `CourseCategoryCriteria` row, if any, is **not** explicitly cleaned up in this action (not confirmed whether a DB-level cascade exists — verify against the migration if a hard parity requirement).
- **Success response:** `$this->apiResponse([], 'Course Category deleted successfully')`.
- **Side effects:** an `activity()` helper-based log entry (`event: 'Course Category Deleted'`, log name `'Course Category'`) — a **different** logging mechanism from `CourseFaq`'s destroy (direct `Activity::create()`) and from this same module's own `changeStatus` (`ActivationAndDeactivationProcess::addActivityLogsAndComments()`) — three different activity-logging call styles exist across this app's course-adjacent modules.

### `GET /course-categories/{course_category}` — ⚠️ confirmed broken, undocumented as a real endpoint
No `show()` method exists. See the landmine note above.

---

## `GET /course-categories/{category_id}/activity` (route name `course-categories.activity`, trait `activity`)
- **Path param:** `category_id`.
- **Query params:** `rows` (optional int, default 15) — standard Laravel `paginate()` (not cursor-based despite the app's other cursor conventions), using pagination type `'cursor'` as the **page-name** parameter to `paginate()` (i.e. Laravel's own cursor pagination, a third distinct pagination mechanism from the two documented in common conventions).
- **Success response:** `ActivityResource::collection($paginator)->additional(['meta' => ['next_page_url','prev_page_url','range' => ['from','to','total']]])` — filters `activity_logs` where `subject_type = 'Modules\CourseCategory\Entities\CourseCategory'` and `subject_id = category_id`, columns limited to `id,description,causer_id,event,created_at`.
- **Error responses:** global `apiResponse([], 'Course Category Not Found', 'error', 404)` if the id doesn't resolve via the repository.
- **Notes:** this is a **third pagination style** in this one module alone (Laravel `paginate('cursor')` with `next_page_url`/`prev_page_url`, vs. the base64-JSON-cursor `range` scheme used by `index`/`coursesPerformance` in the same controller) — do not assume `activity`'s pagination behaves like this module's other cursor-paginated endpoints.

---

## Not routed / not part of this module's live API

- `CourseCategoryTreeResource` (`Http/Resources/CourseCategoryTreeResource.php`) exists and is fully implemented but **is not referenced anywhere in `CourseCategoryController` or this module's `Routes/api.php`** — confirmed by reading the full controller; grep any other module before assuming it's dead entirely, but no route in this file returns it.

## Summary

**Routes:** 9 `Route::` declarations (8 explicit + 1 `apiResource` contributing 5 verb/action pairs, one of which — `show` — is broken) → **12 distinct reachable endpoints**, 1 confirmed-broken (`show`).

**Structural surprises:**
- `store`/`update` on this controller silently create/update/delete rows in a *different* module's table (`CourseCategoryCriteria`) — overlapping, not delegating to, that module's own dedicated endpoints.
- `apiResource`'s `show` action is missing entirely — fatal 500 on `GET /course-categories/{id}`, same failure class documented in `NPS.md`.
- Route name `roles.status.change` on `POST /course-categories/status/change` is a copy-paste leftover from the `Role` module — cosmetic, but a route-name-based test lookup must use the actual (misleading) name.
- Three different pagination mechanisms coexist inside this one module: base64-JSON cursor (`index`, `coursesPerformance`), raw offset/limit (`search`), and Laravel's native cursor `paginate()` (`activity`).
- Three different activity-logging call styles are used across sibling actions in the broader Course-adjacent modules (`activity()` helper here in `destroy`, `Activity::create()` directly in `CourseFaq::destroy`, `ActivationAndDeactivationProcess` trait in `changeStatus`).
- `lms_mcq`'s validation type differs between `Store` (`boolean`) and `UpdateRequest` (`integer|min:0`) for the same underlying column.

**Confidence:** High — every endpoint traced directly from the full `CourseCategoryController.php`, `CourseCategoryTrait.php`, both FormRequests, all 5 routed Resource classes, `CourseCategoryRepository.php`, and the relevant `ActivityLog`/`ActivationAndDeactivationProcess` app-level trait methods. The `store`/`CourseCategoryCriteria` field-forwarding behavior and the missing `show()` method were independently confirmed by reading the full controller body and grepping for the method name.
