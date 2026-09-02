# AssignmentTag Module — API Documentation

The `AssignmentTag` module owns the `tags` table (via `Spatie\Tags\Tag`, extended as `Modules\AssignmentTag\Entities\Tag`) — a single shared tag store used, per its own `type` column, for assignment tags, user tags, and student tags (`Tag::ASSIGNMENT_TAG`/`USER_TAG`/`STUDENT_TAG`; a fourth constant `ENROLLMENT_TAG` exists on the model but is not one of the values this module's own `StoreAndUpdateRequest` accepts — see note below). Despite the module name, it is not assignment-specific at the data layer; `Assignment.php:store()`/`update()` in the `Assignment` module reads/writes rows here via this same repository. See [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for app-wide envelope/error/pagination conventions.

**Module-wide auth:** every route in `Modules/AssignmentTag/Routes/api.php` is `auth:sanctum` + `json.response`, prefix `v1`. No per-route deviation.

**Class layout:** single controller, `TagController` (`Modules/AssignmentTag/Http/Controllers/TagController.php`), no trait — all method bodies are directly on the controller.

---

## `GET /v1/search/tags` — `search()` (route name `tags.search`)
- Registered **before** the `apiResource` block in the route file, so this literal path takes precedence over the `{tag}` wildcard from the resource routes.
- Query: `type` (optional, one of `Tag::STUDENT_TAG`/`USER_TAG`/`ASSIGNMENT_TAG` — a value outside these three is silently ignored, no filter applied, so an unrecognized `type` returns tags of *any* type rather than erroring); `search` (optional, `LIKE '%...%'` against both `id` and `name`).
- **Success response:** hand-rolled plain PHP array (not even wrapped in `apiResponse()` or `response()->json()` — Laravel auto-serializes the returned array to JSON): `{"data": [...]}` — **no `message`/`status` key at all**, a shape distinct from every other convention documented in `_COMMON_CONVENTIONS.md`. Each item from `TagSearchResource`: all raw columns except `name` is re-added at the end (a functional no-op reordering — the field ends up identical to the untouched original, just moved to the last key position in the JSON object).
- Result set is hard-`limit(10)` — no `rows`/pagination param honored; a caller cannot request more than 10 matches from this endpoint no matter what.

## `GET /v1/tags` — `index()` (`apiResource`)
- **No query params honored** — `TagRepository::all()` (inherited `BaseRepository::all()`) returns the entire `tags` table with **no filtering, no `rows`/cursor pagination, no `type` scoping** — every tag of every type, unpaginated, on every call. This is a deviation from every other listing endpoint in this codebase's conventions (see `_COMMON_CONVENTIONS.md`'s pagination families) — worth a dedicated growth/perf note if the `tags` table is large.
- **Success response:** `TagResource::collection(...)` — bare resource collection, no `->additional(['meta' => ...])` at all, so the response is a plain `{"data": [...]}` with no `meta` key whatsoever (not even a `total`).
- `TagResource` fields: all raw columns except `created_at`/`updated_at`/`deleted_at`/`pivot`/`created_by`/`updated_by`, plus `creator` (`{id,first_name,last_name}`) and `updater` (same shape or `null`).

## `POST /v1/tags` — `store()` (`apiResource`)
- **Request body** (`StoreAndUpdateRequest`, `authorize()` always `true`): `type` required, one of `Tag::ASSIGNMENT_TAG`/`USER_TAG`/`STUDENT_TAG` (not `ENROLLMENT_TAG` — see module note); `name` required string max:255; `status` required boolean.
- **Success response:** `$this->apiResponse(['tag' => TagResource::make($assignmentTag)], 'Tag is created successfully', statusCode: 201)`.
- **Side effects:** `created_by` forced server-side from `auth()->user()->id` before persistence — a client-supplied `created_by` in the body is silently overwritten, not rejected.
- **Notes:** no uniqueness check on `name` (even scoped by `type`) — duplicate tag names for the same type are allowed.

## `PUT/PATCH /v1/tags/{id}` — `update()` (`apiResource`)
- Path param `id` — **plain int parameter, not route-model-bound** (`function update(StoreAndUpdateRequest $request, $id)`), so an id for a non-`Tag` row or a soft-deleted tag doesn't 404 automatically via binding — the controller does its own existence check.
- **Request body:** same `StoreAndUpdateRequest` rules as `store()`.
- **Success response:** `$this->apiResponse(['tag' => TagResource::make($tag->fresh())], 'Tag updated successfully')` (200).
- **Error response:** `$this->apiResponse([], 'Tag Not Found', 'error', 404)` if `$id` doesn't resolve via `TagRepository::findById()` — a **hand-rolled 404 in this exact shape**, not the standard `ModelNotFoundException` 404 documented in `_COMMON_CONVENTIONS.md` (message differs: `"Tag Not Found"` here vs. `"Resource Not Found"` for the app-wide convention).
- **Side effects:** `updated_by` forced server-side from `auth()->user()->id`, same override-not-reject pattern as `store()`.

## `GET /v1/tags/{tag}` and `DELETE /v1/tags/{tag}` — `apiResource`'s `show`/`destroy` — **confirmed broken, no method exists**
`Route::apiResource('tags', 'TagController')` wires up all 5 CRUD routes, but `TagController` implements only `index`/`store`/`update` (plus the module-specific `search()`, not part of the resource). No `show()` or `destroy()` method exists anywhere in the class — grepped the full file, confirmed absent. Calling either route triggers a PHP fatal `Error: Call to undefined method`, surfacing as an uncaught-exception **500**, not a clean 404/405 — same failure pattern documented for `NPS`'s partially-wired `apiResource('nps', ...)` in `NPS.md`. A parity suite must confirm whether AP-V3 is expected to reproduce this 500-on-fatal-error behavior or fix it — confirm with the team rather than assuming either direction.

---

## Summary of endpoints documented

**5 raw routes registered** (`search` + the 5-route `apiResource`, so 6 total route entries, 5 distinct actions since `search` is separate from the resource block):
- **3 working:** `search`, `index`, `store`, `update` (4 distinct working actions).
- **2 confirmed broken:** `show`, `destroy` (fatal 500, undefined method).

**Notable findings for parity testing:**
- `index()` has zero pagination/filtering — full unpaginated table dump, unlike every other listing endpoint's cursor/meta conventions.
- `search()` returns a bespoke `{"data": [...]}` shape with no `message`/`status` key — distinct from all 4 documented envelope styles in `_COMMON_CONVENTIONS.md`.
- `update()`'s 404 body (`"Tag Not Found"`) differs in message text from the app-wide standard 404 shape (`"Resource Not Found"`) — both are HTTP 404 but with different JSON bodies; a parity test keyed only on status code will pass while missing the message-text divergence.
- `show`/`destroy` are fatal-error dead routes, not clean 404s.
- This module is a shared cross-domain tag store, not assignment-exclusive — `Assignment.php`'s `store()`/`update()` (see `Assignment.md`) creates/attaches `Tag::ASSIGNMENT_TAG` rows through this same repository as a side effect of assignment-template writes, so tag data created here is directly visible to, and created by, that other module.

**Confidence:** High — every route traced to its controller method (or confirmed absent) by reading the full controller, both FormRequest classes, both Resource classes, the repository, and the entity's constants.
