# CourseCategoryCriteria Module API Documentation

The `CourseCategoryCriteria` module owns a minimal, 2-route CRUD surface (create + update only, no index/show/delete) for the `course_category_criterias` table — the pass-mark rules (`minimum_exercises`, `pass_marks_needed`, etc.) applied to all courses under a given `CourseCategory`. **This is one of two live write-paths for the same table** — see the ⚠️ overlap note in [`./CourseCategory.md`](./CourseCategory.md): `CourseCategoryController::store()`/`update()` can also create/update/delete the identical row inline as a side effect of managing the parent category, using a different (looser) set of validation rules than this module's own dedicated endpoints.

**Module-wide auth:** both routes in `Modules/CourseCategoryCriteria/Routes/api.php` are `auth:sanctum` + `json.response`, mounted under `/api/v1/...`. No deviation.

See [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for the app-wide response envelope styles, standard error shapes, and pagination conventions.

All logic lives directly on `CourseCategoryCriteriaController` (`Modules/CourseCategoryCriteria/Http/Controllers/CourseCategoryCriteriaController.php`) — no trait is used, both routed methods (`store`, `update`) are defined inline on the controller itself. Both use `$this->apiResponse()` (instance method).

---

## `POST /course-category-criteria` (route name `course-category-criteria.store`, controller `store`)
- **Request body** (`Store`): `category_id` — required, `exists:course_categories,id`, **`unique:course_category_criterias,category_id`** (enforces exactly one criteria row per category via this endpoint — a second `store` call for the same `category_id` 422s); `minimum_exercises` — required, integer, min:0; `each_exercises_marks` — required, integer, min:0; `min_attempt_exercises_percent` — optional (nullable), integer, min:0; `no_writing_assignments` — optional, integer, min:0; `writing_assignments_marks` — optional, integer, min:0; `lms_mcq` — optional, boolean; `pass_marks_needed_percent` — required, integer, min:0; `pass_marks_needed` — required, integer, min:0; `total_marks` — required, integer, min:0. **Unlike `CourseCategory::store()`'s equivalent inline fields (all `required_with` each other, so omitting all of them is valid), this dedicated endpoint makes 5 of the 9 fields unconditionally `required`.**
- **Success response:** `$this->apiResponse(['course_category_criteria' => CourseCategoryCriteriaResourse::make($courseCriteria)], 'Course Category Criteria created successfully', statusCode: 201)`.
- `CourseCategoryCriteriaResourse` (note the class's own name is misspelled **"Resourse"**, not "Resource" — this is the real class/file name, preserve exactly when referencing it in test code): raw columns except `created_at`/`updated_at` — i.e. `id`, `category_id`, `minimum_exercises`, `each_exercises_marks`, `min_attempt_exercises_percent`, `no_writing_assignments`, `writing_assignments_marks`, `lms_mcq`, `pass_marks_needed_percent`, `pass_marks_needed`, `total_marks`.
- **Error responses:** standard 422 (see common conventions) on any rule violation, most notably the `unique:category_id` constraint if a criteria row already exists for that category (including one created via `CourseCategory::store()`'s inline path — the uniqueness constraint is shared at the DB/table level, so a category that already got criteria via the *other* module's endpoint will 422 here too).
- **Side effects:** none beyond the row insert (no activity log, no queued job).

## `PUT /course-category-criteria/{course_category_criteria}` (route name `course-category-criteria.update`, controller `update`)
- **Path param:** `course_category_criteria` — a `course_category_criterias.id` (**not** a `category_id** — do not confuse the two ids when constructing a test URL), looked up manually via `courseCategoryCriteriaRepo->findById($id)` (no Laravel route-model binding, so a non-existent id gets this module's own hand-rolled 404, not the standard `ModelNotFoundException` shape).
- **Request body** (`Update`): `category_id` is **not accepted/validatable here at all** — you cannot repoint an existing criteria row to a different category via this endpoint. All 9 criteria fields (`minimum_exercises` through `total_marks`) are optional (nullable, integer min:0; `lms_mcq` nullable boolean) — **every field is optional on update, including the ones that were unconditionally required on create**, so a call with an empty body is valid and simply leaves the row unchanged (repository `update()` is called with an empty array).
- **Success response:** `$this->apiResponse(['course_category_criteria' => CourseCategoryCriteriaResourse::make($this->courseCategoryCriteriaRepo->findById($id))], 'Course Category Criteria updated successfully')`.
- **Error responses:** `$this->apiResponse([], 'Course Category Criteria Not Found', 'error', 404)` if the id doesn't resolve.
- **Side effects:** none beyond the row update.

---

## Summary

**Routes:** 2 `Route::` declarations, both reachable, both fully documented above. No `index`/`show`/`destroy` action exists anywhere in this module — reads and deletes of a criteria row happen only indirectly, through the parent `CourseCategory`'s own resource (`CourseCategoryResponse.criteria`, nested) and through `CourseCategoryController::update()`'s `add_or_not=0` delete branch, respectively.

**Structural surprises:**
- The resource class is named `CourseCategoryCriteriaResourse` (misspelled) in the actual codebase — not a documentation typo.
- This module's `Store` rules are strictly *stricter* (5 unconditionally-required fields) than the inline criteria-creation path inside `CourseCategoryController::store()` (all `required_with`-only) for the exact same table — a client integrating against one path cannot assume the other accepts/rejects the same payloads.
- `Update` accepts no `category_id` field at all, so this endpoint can only ever mutate an existing row's numeric criteria values, never reassign it to a different category.
- A DB-level `unique(category_id)` constraint is the real enforcement of "one criteria row per category" — it's shared with (and can be violated from either side by) `CourseCategoryController`'s inline path, so a duplicate-creation attempt via *this* module can 422 because of a row that was actually created via the *other* module's endpoint.

**Confidence:** High — both routed methods, both FormRequests, and the Resource class were read in full. The overlap with `CourseCategoryController`'s inline criteria handling was independently verified by reading that controller's `store()`/`update()` bodies directly (see [`./CourseCategory.md`](./CourseCategory.md)).
