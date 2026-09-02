# CourseFaq Module API Documentation

The `CourseFaq` module owns simple CRUD + listing + course-scoped search for `course_faqs` — question/answer pairs attached to a `Course`.

**Module-wide auth:** both routes in `Modules/CourseFaq/Routes/api.php` are `auth:sanctum` + `json.response`, mounted under `/api/v1/...`. No deviation.

See [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for the app-wide response envelope styles, standard error shapes, and pagination conventions.

`CourseFaqController` (`Modules/CourseFaq/Http/Controllers/CourseFaqController.php`) pulls in `CourseFaqTrait` (`Http/Traits/CourseFaqTrait.php`) purely for its two cursor-range calculator methods (`calculateRangeForCursor`, `calculateRangeForCourseFaqsCursor`) — every routed action itself is defined directly on the controller. All responses use `$this->apiResponse()` (instance method) except `destroy`'s activity-log write, which bypasses the app's `activity()` helper entirely in favor of a direct `Activity::create()` call (see note below).

## ⚠️ `apiResource('course-faqs', ...)` is partially broken — same landmine as `CourseCategory`/`NPS`

```php
Route::apiResource('course-faqs', 'CourseFaqController'); // wires index, store, show, update, destroy
```
`CourseFaqController` implements `index`, `store`, `update`, `destroy` — **`show` does not exist anywhere in the class** (confirmed by reading the full controller source). `GET /api/v1/course-faqs/{course_faq}` will hit a PHP `Error: Call to undefined method`, surfacing as an uncaught-exception **500**, not a clean 404/405 JSON error.

---

## `GET /search/faqs/with-specific-course` (route name `course-faqs.with-specific-course.search`, controller `searchSpecificCourseFaqs`)
- **Request params:** `course_id` — **no FormRequest, raw `request('course_id')` access**, only an `is_null()` presence check (not `exists:courses,id` — an id for a non-existent course silently returns an empty, "successful" paginated result rather than a validation error); `rows` (optional int, default 15).
- **Success response (course_id present):** `CourseFaqResource::collection($this->courseFaqRepo->searchSpecificCourseFaqs($course_id, ['*'], $rows))->additional(['meta' => ['total', 'range']])` — resource-collection shape with a **third, course-scoped** cursor-range calculator (`calculateRangeForCourseFaqsCursor()`, distinct from `index()`'s `calculateRangeForCursor()` even though both live in the same trait and use the identical base64-JSON cursor token format).
- **Error response (course_id missing):** `$this->apiResponse([], 'Please provide course id in the parameters', 'error', 404)` — **HTTP 404 used for what is semantically a validation failure** (a missing required query param), not the standard 422 shape the rest of the app uses for validation errors.

## `apiResource('course-faqs', 'CourseFaqController')` — 4 of 5 wired actions functional

### `GET /course-faqs` (`index`)
- **Query params:** `rows` (optional int, default 15), `cursor` (opaque base64 token, standard scheme — malformed cursor → `abort(500, 'Cursor value tempered')`).
- **Success response:** `CourseFaqResource::collection(...)->additional(['meta' => ['total', 'range']])`. `CourseFaqResource` fields: `id`, `question`, `answer`, `status` (raw-merged, `course_id`/`created_by`/`updated_by`/timestamps all excluded from the response).

### `POST /course-faqs` (`store`)
- **Request body** (`Store`): `course_id` required, `exists:courses,id`; `question` required string; `answer` required string; `status` required boolean.
- **Success response:** `$this->apiResponse(['course_faq' => CourseFaqResource::make(...)], 'Course Faq is created successfully', statusCode: 201)`.
- **Side effects:** `created_by` forced server-side to the authenticated user id. No activity log on create (only on delete — see below).

### `PUT/PATCH /course-faqs/{course_faq}` (`update`)
- **Request body** (`UpdateRequest`): `question`/`answer`/`status` all optional (nullable) — **`course_id` cannot be changed via this endpoint at all** (not present in the update rule set, and the controller's `->only([...])` call for the update also excludes it even if sent).
- **Success response:** `$this->apiResponse(['course_faq' => CourseFaqResource::make($courseFaq->fresh())], 'Course Faq updated successfully')`.
- **Error responses:** `$this->apiResponse([], 'Course Faq Not Found', 'error', 404)` if the id doesn't resolve via the repository (manual lookup, not route-model binding).
- **Side effects:** `updated_by` forced server-side to the authenticated user id.

### `DELETE /course-faqs/{course_faq}` (`destroy`)
- **Error responses:** `$this->apiResponse([], 'Course Faq Not Found', 'error', 404)` if missing.
- **Success response:** `$this->apiResponse([], 'Course Faq deleted successfully')`.
- **Side effects:** direct `Spatie\Activitylog\Models\Activity::create([...])` call (log_name `'Course Faq deleted'`, description string-interpolates the acting user's first/last name, `causer_type => User::class`) — this bypasses the app's usual `activity()`-helper-based logging pattern seen in most other modules (e.g. `CourseCategory::destroy()`), and also bypasses whatever automatic causer/subject resolution the helper normally provides; a hard-delete of the row itself follows (`$this->courseFaqRepo->delete($id)` — no soft-delete column exists on `course_faqs` per its migration, confirm before assuming recoverability).

### `GET /course-faqs/{course_faq}` — ⚠️ confirmed broken, undocumented as a real endpoint
No `show()` method exists. See the landmine note above.

---

## Summary

**Routes:** 2 `Route::` declarations (1 explicit + 1 `apiResource` contributing 5 verb/action pairs, one of which — `show` — is broken) → **5 distinct reachable endpoints**, 1 confirmed-broken (`show`).

**Structural surprises:**
- `apiResource`'s `show` action is missing entirely — fatal 500 on `GET /course-faqs/{id}`, matching the pattern already documented for `NPS` and `CourseCategory`.
- `searchSpecificCourseFaqs`'s missing-`course_id` branch returns HTTP 404 for what is semantically a validation error, not the app's standard 422 shape — and its present-but-invalid-`course_id` branch (a real course_id doesn't exist) silently returns an empty success page rather than any error at all, since there's no `exists:courses,id` check.
- `destroy` logs via a direct `Activity::create()` call rather than the `activity()` helper most sibling modules use — a genuinely different code path, not just a different message.
- Three distinct base64-cursor range calculators exist across just this module + its cross-references (`calculateRangeForCursor`, `calculateRangeForCourseFaqsCursor`) — both use the identical token format/failure mode (`abort(500, 'Cursor value tempered')`), just scoped to different underlying queries.

**Confidence:** High — every endpoint traced directly from the full `CourseFaqController.php`, `CourseFaqTrait.php`, both FormRequests, and `CourseFaqResource.php`. The missing `show()` method and the `destroy` activity-log divergence were independently confirmed by reading the full controller body, not inferred from the route list.
