# CoursePlanType Module API Documentation

The `CoursePlanType` module is a small, generic reference-data CRUD surface for named "plan types" (a simple `id`/`name` lookup table with soft deletes and creator/updater tracking). Grep across `Modules/` and `app/` for any read/write of `CoursePlanType` outside this module's own files turns up nothing beyond DI registration and a one-off `CoursePlanTypeSeeder` call — **no other module or admin flow consumes this entity**, matching `API_SPECIFICATIONS.md`'s existing note that this has "no confirmed consumer anywhere."

**Module-wide auth:** the single route group in `Modules/CoursePlanType/Routes/api.php` is `auth:sanctum` + `json.response`, mounted under `/api/v1/...` (standard `prefix('api')->middleware('api')` wrapping). No route deviates from this.

See [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for the app-wide response envelope styles, standard error shapes, and pagination conventions referenced below instead of being repeated per endpoint.

`CoursePlanTypeController` (`Modules/CoursePlanType/Http/Controllers/CoursePlanTypeController.php`) extends `App\Http\Controllers\Controller` and implements all four routed actions directly — no trait indirection in this module.

```php
Route::apiResource('course-plan-types', 'CoursePlanTypeController');
```
Full, unscoped `apiResource` — 5 actions registered (`index`, `store`, `update`, `destroy`, plus `show` which is **not implemented** on the controller at all). Calling `GET /api/v1/course-plan-types/{id}` hits an undefined method — the same "fatal 500 via undefined method" failure mode documented for NPS's broken `apiResource` actions, not a clean 404. Confirmed by reading the full controller: only `index`, `store`, `update`, `destroy` exist.

---

## `GET /api/v1/course-plan-types` (route name `course-plan-types.index`, controller `index`)

- **Success response:** `CoursePlanTypeResource::collection($this->coursePlanTypeRepo->all())`.
- **⚠️ Structural surprise — this is real Laravel pagination, not this app's usual cursor scheme.** `coursePlanTypeRepo->all()` resolves to the generic `BaseRepository::all(array $columns = ['*'], array $relations = [], int $count = 15)`, which the controller calls with **zero arguments** — so it always returns a `LengthAwarePaginator` with a hardcoded page size of 15, and the controller **never reads any `rows`/`page`/`cursor` query parameter at all** (confirmed: no `request()` access anywhere in `index()`). Wrapping a paginator in `Resource::collection()->...` without an explicit `->additional([...])` call means Laravel's **default paginated-resource envelope** is used: `{"data": [...], "links": {"first","last","prev","next"}, "meta": {"current_page","from","last_page","links","path","per_page","to","total"}}`. This is a genuinely different shape from both pagination families documented in the common conventions (neither the resource-collection `{"data","meta":{"total"}}` style nor the cursor-based `{"data","meta":{"total","range"}}` style) — a parity test must expect Laravel's native paginator JSON here, and must not expect page-size control via any request parameter.
- `CoursePlanTypeResource`: raw-merged model attributes minus `created_at`/`updated_at`/`created_by`/`updated_by`, plus `creator` (`{id, first_name, last_name}`, via the `creator` BelongsTo relation on `created_by`) and `updater` (same shape, **null-safe** `$this->updater?->only(...)` — unlike `creator` which has no null-guard and would throw if a row somehow had no `created_by`; in practice `created_by` is always set by `store()`, so this is latent rather than currently reachable).

## `POST /api/v1/course-plan-types` (route name `course-plan-types.store`, controller `store`)

- **Request body** (`StoreCoursePlanTypeRequest`, `authorize()` always `true`): `name` — required, string, max:255, `unique:course_plan_types,name`.
- **Behavior:** `created_by` is injected server-side (`auth()->user()->id`, added onto the request bag before persisting) — not client-suppliable, and not part of the FormRequest's validated fields.
- **Success response:** `$this->apiResponse(['course_plan_type' => CoursePlanTypeResource::make(...)], 'Course plan type created successfully', statusCode: 201)` → `{"data": {"course_plan_type": {...}}, "message": "Course plan type created successfully", "status": "success"}`. Note this uses the **instance** `$this->apiResponse()` (available since this controller extends the app's base `Controller`), unlike `index()` which returns a bare resource collection with no envelope helper at all.

## `PUT/PATCH /api/v1/course-plan-types/{id}` (route name `course-plan-types.update`, controller `update`)

- **Request body** (`UpdateCoursePlanTypeRequest`):
  - `course_plan_type_id` — **required**, `exists:course_plan_types,id` — a body field the client must supply *in addition to* the `{id}` route path parameter.
  - `name` — required, string, max:255, unique on `course_plan_types.name` **ignoring** the row identified by `course_plan_type_id` (via `Rule::unique(...)->ignore($this->input('course_plan_type_id'))`).
- **⚠️ Notable quirk:** the controller's actual lookup/update/response all key off the **route path** `{id}`, never off the body's `course_plan_type_id` — the two are never cross-checked for equality. If a caller sends a `course_plan_type_id` in the body that differs from the path `{id}`, the uniqueness check's `ignore()` clause excludes the **wrong row** from the check (the one named in the body, not the one actually being updated) — this can produce either a false-positive "name taken" validation failure (if the real target row's own current name collides with nothing, but ignore() excludes a different row) or, more concerningly, silently let a duplicate name through the ignore() on the wrong id while the real row (path `{id}`) is the one actually renamed. Worth a dedicated test sending mismatched `course_plan_type_id` vs. path `{id}`.
- **Error response:** `$this->apiResponse([], 'Course plan type Not Found', 'error', 404)` if `{id}` (path param) doesn't resolve via `findById`.
- **Success response:** `$this->apiResponse(['course_plan_type' => CoursePlanTypeResource::make(...)], 'Course plan type updated successfully')`, HTTP 200.
- **Behavior:** `updated_by` injected server-side the same way `created_by` is on store.

## `DELETE /api/v1/course-plan-types/{id}` (route name `course-plan-types.destroy`, controller `destroy`)

- **Error response:** same `$this->apiResponse([], 'Course plan type Not Found', 'error', 404)` shape.
- **Behavior:** soft delete (`CoursePlanType` entity uses `SoftDeletes`; `BaseRepository::delete()` calls plain Eloquent `->delete()`).
- **Success response:** `$this->apiResponse([], 'Course plan type deleted successfully')`.
- **Side effects:** `activity()->on($coursePlanT)->by($actionBy)->withProperties(['course_criteria_id' => $coursePlanT->id])->event('Course plan type Deleted')->log('Course Plan Type')` — **note the `withProperties` key is the literal `course_criteria_id`, not `course_plan_type_id`** — a copy-paste artifact from the sibling `CourseCriteria` module's near-identical destroy method, preserved exactly as it appears in source; the activity log for this module's deletions carries a misleadingly-named property key.

---

## Summary

**Routes documented:** 5 actions registered via unscoped `apiResource('course-plan-types', ...)`; **4 reachable** (`index`, `store`, `update`, `destroy`) and **1 broken** (`show` — undefined method, fatal 500 on call, not a clean 404).

**Notable findings for parity testing:**
- `index()` returns Laravel's native `LengthAwarePaginator` JSON envelope (`links`+`meta.current_page`/`per_page`/etc.) — a third, distinct pagination shape not covered by either family in the common conventions doc, and page size is hardcoded to 15 with no client-side override possible.
- `show` is unimplemented despite being registered by the unscoped `apiResource` call — fatal-error-on-call, same failure class as NPS's broken routes.
- `update`'s required `course_plan_type_id` body field is never reconciled against the path `{id}` it actually operates on — a real divergence risk for the uniqueness check.
- `destroy`'s activity log writes a `course_criteria_id` property key (copy-paste leftover), not `course_plan_type_id`.
- No confirmed consumer of this entity anywhere else in the codebase (verified via repo-wide grep) — low business risk, but CRUD-correctness and the above quirks are still worth covering for parity since AP-V3 must reproduce them exactly if the migration doesn't intentionally fix them.

**Confidence:** High — every behavior traced directly from `CoursePlanTypeController.php`, `StoreCoursePlanTypeRequest.php`, `UpdateCoursePlanTypeRequest.php`, `CoursePlanTypeResource.php`, the `CoursePlanType` entity, `CoursePlanTypeRepository.php` (confirmed no override of `BaseRepository::all()`/`update()`/`delete()`), and a repo-wide grep for other consumers.
