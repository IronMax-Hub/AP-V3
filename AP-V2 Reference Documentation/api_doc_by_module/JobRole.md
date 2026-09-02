# JobRole Module API Documentation

The `JobRole` module owns the `job_roles` reference table (id, title, `created_by`/`updated_by` FKs to `users`) used for dropdowns/typeahead elsewhere in the app.

**Module-wide auth:** both routes in `Modules/JobRole/Routes/api.php` are `auth:sanctum` + `json.response`, mounted under `/api/v1/...`. No deviation.

See [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for the app-wide response envelope styles, standard error shapes, and pagination conventions referenced below instead of being repeated per endpoint.

`JobRoleController` (`Modules/JobRole/Http/Controllers/JobRoleController.php`) is a complete, self-contained controller with **only two routed methods, `search()` and `searchJobRolesWithArray()`**. Unlike `Country`/`State`, **there is no `apiResource('job-roles', ...)` registration at all** — no `index`, no `store`/`show`/`update`/`destroy` routes exist for this module, functional or otherwise. `JobRole` is a pure read-only, search-only reference module by design, not a broken-CRUD module. Confirmed no `Http/Requests` directory exists in this module — every input is read raw via `request()`, no FormRequest validation anywhere.

---

## `GET /v1/search/job-roles` (`search`, route name `job-roles.search`)
- **Request params (all optional, no FormRequest — read via `request()` inside the repository):**
  - `search` — free text; applied as `WHERE id LIKE %search% OR title LIKE %search%`.
  - `offset` — optional int, default `0`.
  - `limit` — optional int, default `10`.
- **⚠️ `id LIKE '%search%'` quirk:** the `search` term is matched against the numeric `id` column via string `LIKE`, not exact/numeric equality. MySQL implicitly casts `id` to a string for this comparison, so `search=1` matches ids `1`, `10`, `11`, `21`, `31`, ...`91`, `100`+, etc. — any id containing "1" as a substring, not just id `1`. **A parity test must reproduce this substring-match behavior exactly**, not assume `search` performs an id-equality lookup.
- **Success response:** `SearchJobRoleResource::collection(...)->additional(['meta' => ['total' => ...]])` → `{"data": [...], "meta": {"total": N}}`. Each item trimmed via `Arr::only(..., ['id', 'title'])` — no `created_by`/`updated_by`/timestamps.
- **`meta.total`:** `searchJobRoleCount()` — identical `id LIKE OR title LIKE` filter, independent `COUNT(*)`.

## `GET /v1/search/specific-job-roles` (`searchJobRolesWithArray`, route name `job-role.specific.search`)
- **Request params:** `search` — **no FormRequest, no presence/type validation at all** beyond `is_null()`. Repository code does `$builder->whereIn('title', request('search'))` when `search` is present.
- **⚠️ Confirmed crash on a scalar `search` value:** `whereIn()`'s second argument must be an array (or `Arrayable`). If the caller sends `search` as a plain query-string scalar (e.g. `?search=Engineer`, which Laravel resolves to the string `"Engineer"`, not an array), Laravel's query grammar iterates the values with `array_values($values)` when compiling bindings — passing a non-array here throws a PHP `TypeError`, surfacing as an uncaught **500**, not a validation error. **The endpoint requires PHP array syntax in the query string** (`?search[]=Engineer&search[]=Designer` or an equivalent JSON/form-array body) to avoid this; a plain `search=X` string parameter will crash it. This must be reproduced exactly in AP-V3 for parity (i.e. AP-V3 should also 500 on a scalar `search`, not silently coerce it to an array).
- **Success response (array `search` provided or omitted):** global `apiResponse($this->jobRoleRepo->searchJobRolesWithArray())` → `{"data": [...], "message": "Success", "status": "success"}`. **Not a Resource collection** — raw model attributes for the default columns `['id', 'title']` only (`get($columns)` is called with the same 2-column default as `search()`'s repository method, just returned as plain model instances rather than through a Resource). No `meta`/`total` key at all on this endpoint, unlike `search()`.
- **Notes:** if `search` is omitted entirely, the `whereIn` clause is skipped (the `when(!is_null(...))` guard is false) and the endpoint returns **all** job roles (`id`, `title` columns only) — effectively a no-filter "list all" fallback via what looks like a filtered-search endpoint.

---

## Summary

**Routes documented:** 2 `Route::` declarations, both plain `Route::get`, both reachable. No `apiResource`, no dead stubs, no missing-method landmine in this module — the smallest/cleanest of the six modules in this wave in terms of route-registration correctness.

**Notable findings for parity testing:**
- **Confirmed bug:** `search`'s `id LIKE '%term%'` performs a substring match against the numeric id, not an exact-id lookup — reproducible false-positive matches for any query overlapping another id's digits.
- **Confirmed bug:** `searchJobRolesWithArray` throws an uncaught `TypeError` (500) if `search` is sent as a scalar instead of an array — no validation guards against this. This is the JobRole-module instance of a pattern also present in `Topic::searchTopicsWithArray()` (see `Topic.md`) — both repository methods pass `request('search')` straight into `whereIn()` with zero type-checking.
- `search()` and `searchJobRolesWithArray()` return meaningfully different shapes for overlapping data: the former is a `meta.total`-bearing Resource collection filtered/trimmed to `id`+`title`; the latter is a bare `apiResponse()` array with no `meta`, also `id`+`title` only but via raw model serialization (so any model accessors/casts on `JobRole`, if added later, would surface here but not in `search()`, and vice versa for anything `SearchJobRoleResource` might add).
- No write endpoints exist for `JobRole` at all (no `store`/`update`/`destroy`, functional or stub) — this is a genuinely read-only module by design, unlike `Country`/`State` where CRUD was apparently intended (via `apiResource`) but never implemented.

**Confidence:** High — every behavior traced directly from the complete `JobRoleController.php`, `JobRoleRepository.php`, `JobRoleResource.php`, `SearchJobRoleResource.php`, and the `job_roles` migration. The `whereIn()` scalar-crash behavior was independently verified against Laravel's query grammar binding-compilation logic, not merely inferred from the absence of a type hint.
