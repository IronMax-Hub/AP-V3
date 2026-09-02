# Role Module API Documentation

The `Role` module is the **admin/staff-facing** CRUD, search, bulk status-change, evaluator-transfer, and CSV-export surface for `spatie/laravel-permission`-backed `Role` records (`Modules/Role/Entities/Role`), plus a per-role activity log. Closely paired with the `Permission` module (roles are assigned sets of permissions; see `Permission.md`).

**Module-wide auth:** every route is `auth:sanctum` + `json.response`, prefixed `/api/v1/...`. No unauthenticated routes in this module.

See [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for the app-wide response envelope styles, standard error shapes, and pagination conventions. `RolesController` (`Modules/Role/Http/Controllers/RolesController.php`) implements every routed method directly — no traits pulled in besides `ActivationAndDeactivationProcess` (shared with `Student`/`User` bulk-status-change helpers, used by `changeStatus`) and `ActivityLog` (used by `activity`). This module mixes `$this->apiResponse()` and the global `apiResponse()` helper across different methods — noted per endpoint.

## Structural note: same page-number-as-cursor pagination style as `Student`'s activity log

`GET /v1/roles/{role_id}/activity` uses `ActivityLog::logOfRole()`, which — like `Student`'s `logOfStudent()` documented in `Student.md` — paginates via Laravel's built-in `Activity::query()->paginate($rows, $columns, 'cursor')`, where the `cursor` query parameter is actually a **plain page number**, not the opaque base64-JSON token used by `index()` below. Response shape: `{"data":[...ActivityResource...], "meta":{"next_page_url","prev_page_url","range":{"from","to","total"}}}`. Do not confuse this with `index()`'s own `cursor` scheme (different format, same param name).

---

### `GET /v1/search/roles` (route name `roles.search`, `search`)
- **Query params:** `search` (optional, matched against `id`/`name`), `except` (optional role id to exclude from results).
- **⚠️ Filtering bug in `RoleRepository::searchRoles()`:** the underlying query is `where('status','=',1)->where('id','LIKE',...)->orWhere('name','LIKE',...)` all chained inside one grouping closure — because of `orWhere`'s precedence within that closure, the effective condition is **`(status=1 AND id LIKE %search%) OR (name LIKE %search%)`**, not `status=1 AND (id LIKE ... OR name LIKE ...)` as the surrounding code's intent (a `status=1` filter presumably meant to scope to active roles only) suggests. **A role matched by name search is returned regardless of its `status`**, while an id-match is correctly scoped to `status=1`. Worth a dedicated test: create an inactive role, confirm it surfaces via name search but not id search.
- Also: no `status=1` filtering happens at all if the `search` query param is absent — the `when(!is_null(request('search')), ...)` wrapper means an empty request returns **all** roles regardless of status, capped at `limit(10)`.
- **Success response:** `$this->apiResponse($data)` (global default message "Success") — `$data` is a plain `Collection` of `{id, name}` (via `->get(['id','name'])`), optionally `->reject()`-filtered to exclude the `except` id and re-indexed (`->values()->all()`) — **not** a Resource-collection, so no `meta`/`total` key at all in either branch, and `apiResponse()`'s `data` key holds a raw array/collection directly (not `{data: {...}}` double-nested — it *is* the array).

### `POST /v1/roles/transfer-to-other` (route name `roles.transfer-to-other`, `transferToOther`)
- **Request body** (`TransferToNewRoleRequest`): `current_id` required `exists:roles,id`; `new_id` required `exists:roles,id`. **No check that `current_id !== new_id`** — transferring a role to itself passes validation.
- **Behavior:** only proceeds if the `current_id` role has at least one user assigned (`->users()->count() > 0`); if so, calls `ModelHasRoleRepository::updateTheRolesToNew($current_id, $new_id)` to reassign all of that role's user-pivot rows to `new_id`.
- **Success response:** `$this->apiResponse([], 'Users updated with new role')` if the transfer ran; `$this->apiResponse([], 'Nothing to update')` (still 200) if `current_id` had zero users — **both are 2xx "success"-shaped responses regardless of whether any row was actually touched**, per the common-conventions cross-cutting QA caution.
- **Notes:** does not itself delete/deactivate the `current_id` role — this is purely the pivot-reassignment step referenced as a prerequisite by `destroy()`'s "Roles is assigned to users" 422 below.

### `POST /v1/roles/status/change` (route name `roles.status.change`, `changeStatus`)
- **Request params:** no FormRequest — inline `Validator::make($request->all(), [...])->validate()`: `roles_ids` required array, each `exists:roles,id`; `comment` required string; `status` required, `in:activate,deactivate`.
- **Behavior:** bulk `Role::whereIn('id', $roles_ids)->update(['status' => Role::ACTIVE|Role::DEACTIVE])`, then `ActivationAndDeactivationProcess::addActivityLogsAndComments($roles_ids, $request, 'role_activation_and_deactivation', Role::class, 'role deactivated'|'role activated', 0|1)` — the same shared helper used by `Student`/`User` bulk activate/deactivate, writing one activity-log-plus-comment row per affected role.
- **Success response:** global `apiResponse([], 'roles deactivated successfully', statusCode: 200)` or `apiResponse([], 'roles activated successfully', statusCode: 200)`.
- **⚠️ Does NOT cascade to the users holding the role** — this only flips the `Role.status` column and logs the action; it does not deactivate/reactivate any `User` rows despite the "Deactivate Users"/"Activate Users" inline code comments suggesting that was the intent. Matches the existing finding in `documentation/API_SPECIFICATIONS.md` — confirmed still accurate from source. Verify with the team whether cascading deactivation was ever implemented elsewhere before assuming this is dead intent vs. a genuine gap.

### `POST /v1/roles/export` (route name `roles.export`, `export`)
- **Request params:** inline `Validator::make($request->all(), ['data' => ['nullable','array']])->validate()` — `data` is an optional filter array, but **its actual shape/fields are not used anywhere in this method** (only presence/array-type validated, then passed through wholesale to the job) — check `RolesCSVDownloadStart`/`RolesExport` if the exact filter semantics matter for a test.
- **Success response:** global `apiResponse('', 'Roles Csv file exporting started')` — **`data` is an empty string, not `[]`**, matching the pattern seen in `Student`'s CSV-export endpoints.
- **Side effects:** dispatches `RolesCSVDownloadStart::dispatch($request->user(), $request->all(), $data['data'] ?? [])` onto the `default_medium` queue — async; completion is observable only via whatever `RolesCSVCompletedMail`/`RolesCSVCompletedNotification` this job triggers, not this response.

---

## Admin CRUD (`Route::apiResource('roles', 'RolesController')`)

### `GET /v1/roles` (`index`)
- **Query params:** `rows` (default 15), `cursor` (opaque base64-JSON token, see common conventions — tampered value triggers `abort(500, 'Cursor value tempered')`), `search` (matches `id`/`name`, scoped correctly this time — `searchQuery()`'s own `search` clause has no analogous status-leak bug, unlike `searchRoles()` above), `status` (optional exact-match filter).
- **Success response:** `RoleCollectionResource::customCollection($rolesCursorPaginator, $topLevelPermissions)->additional(['meta' => {total, active_role, deactive_role, range}])`. `RoleCollectionResource`: raw-merged role columns excluding `created_at`/`updated_at`/`deleted_at`/`created_by`/`updated_by`/`pivot`/`guard_name`, plus `users_count` (count of assigned users) and `permissions` (via `PermissionsForRoleResource::customCollection` — see `Permission.md` for that resource's own shape, notably its `checked`/`child` fields).
- **Notes:** `active_role`/`deactive_role` in `meta` reuse `searchQuery()` (i.e. respect the current `search`/`status` filters), unlike some other modules' analogous counts which report unfiltered totals — verify this is the intended semantic (a search/status-filtered role list's "active/deactive" counts here describe the filtered set, not the whole table).

### `POST /v1/roles` (`store`)
- **Request body** (`Store`): `name` required string `unique:roles,name`; `status` required, `in:0,1`; `permissions` required array (of permission **names**, not ids — confirmed by `$role->syncPermissions($request->only('permissions'))`, and by the display-name lookup below using `whereIn('name', $request->permissions)`).
- **Behavior:** `guard_name` is forced server-side to `'sanctum'` (`$request->request->add(['guard_name' => 'sanctum', ...])`) — not client-settable; `created_by`/`updated_by` similarly forced to `auth()->user()->id`. Wrapped in `DB::transaction()`: creates the `Role` row (excluding `permissions` from the mass-assigned fields) then `syncPermissions()`.
- **Success response:** `$this->apiResponse(['role' => RoleResource::customMake($role->fresh(), $topLevelPermissionsWithChildren)], 'Roles created successfully', statusCode: 201)`. `RoleResource`: same field-exclusion pattern as the collection resource, plus `users_count`, `creator`/`updater` (each `{id, first_name, last_name}` or null), and `permissions` (`PermissionsForRoleResource::customCollection`, nested `child`/`checked` structure — see `Permission.md`).
- **Side effects:** activity log (`event: 'Role Added'`), message body interpolates permission **display names** (comma-joined) directly into raw HTML (`<br>` literal tag) — the log's `description` field contains unescaped HTML, not plain text.

### `PUT`/`PATCH /v1/roles/{id}` (`update`)
- Raw `$id` param (not route-model-bound) — hand-rolled `$this->apiResponse([], 'Role Not Found', 'error', 404)` if `$id` doesn't resolve via the repository, not a `ModelNotFoundException`.
- **Request body** (`Update`): `role_id` required integer `exists:roles,id` (**must be sent in the body in addition to the URL `{id}`** — the two are never cross-checked against each other, so a client could send a URL id different from the body's `role_id`; the repository lookup/update uses the **URL** `$id`, while the `Rule::unique('roles')->ignore($this->input('role_id'))` uniqueness check ignores the **body's** `role_id` — a mismatch between the two would validate the name's uniqueness against the wrong row's exclusion); `name` required string, unique excluding `role_id`; `permissions` required array. **`status` is not accepted here at all** — no way to flip a single role's active/inactive flag via this endpoint (only the bulk `status/change` route above can).
- **Behavior:** computes before/after permission diffs (`array_diff`) purely for the activity-log description text — the actual permission write is a full `syncPermissions()` replace, not an incremental add/remove.
- **Success response:** `$this->apiResponse(['role' => RoleResource::customMake($role->fresh(), ...)], 'Role updated successfully')`.
- **Side effects:** activity log (`event: 'Role Updated'`), description built as `"The Role has been Updated"` plus optional `<br> Added Permissions: ...` / `<br> Removed Permissions: ...` lines (same raw-HTML-in-log-text pattern as `store`) — omitted entirely if no permissions changed.

### `DELETE /v1/roles/{id}` (`destroy`)
- Same hand-rolled 404 pattern as `update` (raw `$id`).
- **Error response:** `$this->apiResponse([], 'Roles is assigned to users', 'error', statusCode: 422)` if `$role->users()->count() > 0` — a role must be reassigned (via `transfer-to-other` above) before it can be deleted.
- **Success response:** `$this->apiResponse([], 'Role deleted successfully')`.
- **Side effects:** activity log (`event: 'Role Deleted'`, description literally `'Role Deleted'`) written **before** `$this->roleRepository->delete($id)` runs — confirm with the repository whether this is a soft or hard delete before asserting recovery/audit-trail behavior.

### `GET /v1/roles/{id}` (`show`)
- Raw `$id` param, same hand-rolled 404 pattern (`'Role Not Found'`, 422... actually 404) as `update`/`destroy`.
- **Success response:** `$this->apiResponse(['role' => RoleResource::customMake($role, $topLevelPermissionsWithChildren)])` (default "Success" message) — `$role->load(['permissions'])` eager-loaded first; note `show` does **not** include `users_count` differently from `store`/`update`'s version of the same resource — actually it does, since it's the same `RoleResource` class, so this is consistent.

### `POST /v1/roles` / dead `apiResource` stub actions
`Route::apiResource('roles', 'RolesController')` also registers `create`/`edit` (`GET /roles/create`, `GET /roles/{id}/edit`) — **`RolesController` defines no `create()`/`edit()` methods at all**, so these two auto-registered routes will throw a `BadMethodCallException` (missing method) if ever hit; effectively dead/broken routes with no corresponding controller implementation, distinct from the "returns a Blade view" dead-stub pattern seen in other modules (here there's no method whatsoever, not even an empty one).

---

## Other routes

### `GET /v1/search/specific-roles` (route name `roles.specific.search`, `searchRolesWithArray`)
- **Query params:** `search` — used via `whereIn('name', request('search'))`, meaning **`search` must be sent as an array of exact role names** (e.g. `search[]=Admin&search[]=Editor`), not a substring/LIKE match — a single string value here would make `whereIn` compare against each individual character of the string if PHP coerces it to an array unexpectedly, or fail outright depending on how the query parameter is parsed; treat this endpoint as array-only input, unlike `roles.search`'s free-text `search`.
- **Success response:** global `apiResponse($this->roleRepository->searchRolesWithArray())` — raw `Collection` of `{id, name}`, not resource-wrapped, no `meta`.

### `GET /v1/roles/{role_id}/activity` (route name `roles.activity`, `activity`)
- **Error response:** `apiResponse([], 'Role Not Found', 'error', 404)` if the id doesn't resolve.
- **Success response:** see the pagination structural note above — `logOfRole()`'s page-number-as-`cursor` shape, `ActivityResource` items scoped to `['id','description','causer_id','event','created_at']` columns only (a narrower column set than `Student`'s equivalent `activity` endpoint, which additionally surfaces `causedBy`/`actionedAt`/`actionName` computed fields — confirm `ActivityResource`'s own field-presence logic if the exact response shape matters, since fewer source columns are selected here).

---

## Summary

**Routes documented:** all 8 explicit routes plus the 5 `apiResource('roles', ...)` actions (`index`, `store`, `show`, `update`, `destroy` — `create`/`edit` are dead/broken, not real endpoints) in `Modules/Role/Routes/api.php` — 13 route registrations total, 11 live/functional, 2 broken.

**Notable bugs/discrepancies found:**
- `roles.search`'s underlying `RoleRepository::searchRoles()` has an operator-precedence bug: the intended `status=1 AND (id LIKE ? OR name LIKE ?)` is actually `(status=1 AND id LIKE ?) OR (name LIKE ?)` — a name-based match bypasses the active-status filter entirely, while an id-based match does not.
- The `apiResource('roles', ...)` registration auto-creates `create`/`edit` routes with **no corresponding controller methods at all** — hitting either throws a framework-level "method does not exist" error, not a graceful 404/dead-stub view.
- `changeStatus` does not cascade to the users holding the affected roles despite code comments suggesting that was the intent — confirmed still accurate against `documentation/API_SPECIFICATIONS.md`'s existing note.
- `update`'s `role_id` (body) and `{id}` (URL) are never cross-validated against each other — the uniqueness-ignore check and the actual update target different sources of the "same" id.
- `store`/`update` both interpolate permission display names as raw, unescaped HTML (`<br>` tags) directly into the activity-log `description` text.
- `transferToOther` allows `current_id === new_id` (no distinctness check) and returns a 200 "success" response even on its no-op branch (`current_id` has zero users).
- This module freely mixes `$this->apiResponse()` and the global `apiResponse()` function across sibling methods in the same controller (e.g. `search`/`export`/`changeStatus`/`searchRolesWithArray` use the global function; `store`/`update`/`show`/`destroy` use the instance method) — same shape either way per common conventions, but confirms no consistent per-module convention exists here either.

**Confidence:** High — every endpoint read directly from `RolesController.php` (full file), `Store.php`/`Update.php`/`TransferToNewRoleRequest.php`, `RoleResource.php`/`RoleCollectionResource.php`, `PermissionsForRoleResource.php`, and the relevant `RoleRepository` query-builder methods (`searchRoles`, `searchQuery`, `searchRolesWithArray`, `activeRole`/`deactiveRole`). The shared `ActivationAndDeactivationProcess`/`ActivityLog` trait methods were cross-referenced against their use in `Student.md`/confirmed directly (`logOfRole`) rather than assumed identical.
