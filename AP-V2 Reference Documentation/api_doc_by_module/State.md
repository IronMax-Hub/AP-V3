# State Module API Documentation

The `State` module owns the static `states` reference table (id, name, `country_id` FK to `countries`) used for dropdowns/typeahead elsewhere in the app (e.g. `Enrollment`, `StudentProfile`).

**Module-wide auth:** both routes in `Modules/State/Routes/api.php` are `auth:sanctum` + `json.response`, mounted under `/api/v1/...`. No deviation.

See [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for the app-wide response envelope styles, standard error shapes, and pagination conventions referenced below instead of being repeated per endpoint.

`StateController` (`Modules/State/Http/Controllers/StateController.php`) is a complete, self-contained controller — no traits pulled in. **It implements only `index()` and `search()`**, both via `$this->apiResponse()` / a Resource collection.

## ⚠️ `apiResource('states', 'StateController')` — only 2 of 5 wired actions exist (same landmine as `Country`)

```php
Route::get('/search/states', [StateController::class, 'search'])->name('states.search');
Route::apiResource('states', 'StateController');
```
`Route::apiResource(...)` registers `index`, `store`, `show`, `update`, `destroy`. **`StateController` defines only `index()`** (confirmed by reading the complete controller source, 44 lines). `store`, `show`, `update`, `destroy` have no method on the class at all — `POST /api/v1/states`, `GET /api/v1/states/{state}`, `PUT/PATCH /api/v1/states/{state}`, `DELETE /api/v1/states/{state}` all trigger an uncaught `Error: Call to undefined method` — a **500**, not a clean JSON error. Identical structural bug to `Country`'s `apiResource('countries', ...)`. No `StoreRequest`/`UpdateRequest` exists anywhere in the module, confirming this isn't just undocumented but genuinely absent.

## ⚠️ No `country_id` coupling/validation anywhere in this module — `State` cannot be filtered, scoped, or validated by country at all

The task brief for this wave specifically calls out checking State↔Country coupling. Traced through `StateController`, `StateRepository`, and `StateResource` in full:
- **`search()` accepts no `country_id` parameter whatsoever.** `StateRepository::searchStates()` only ever applies a single filter — `WHERE name LIKE %search%` — there is no `country_id` `where` clause, no query param read for it, and no way to ask "give me states for country X" through this endpoint. A caller cannot get a country-scoped state list from this API at all; they'd have to fetch all/filtered-by-name states and filter `country_id` client-side themselves (the field is present in the response, see below, just never used server-side for filtering).
- **No FormRequest exists in this module at all** (confirmed: no `Http/Requests` directory), so there is no validation path (`exists:countries,id` or otherwise) that would ever check a submitted `country_id` against the `countries` table — moot in practice since, per the point above, no live endpoint accepts a `country_id` input parameter to validate in the first place. The only place `country_id` is enforced is the DB-level `foreignId('country_id')->constrained('countries','id')->cascadeOnDelete()` in the migration — but since `store`/`update` are both non-functional stubs (see above), that FK constraint is currently unreachable from the API surface.
- **Confirmed: no dual-write hazard between `Country` and `State`** in the sense the brief warns about, simply because neither module's write endpoints (`store`/`update`/`destroy`) are functional at all right now — there is no code path in either module today that writes to both tables, or that could leave them inconsistent, since neither can be written to via this API.

---

## `GET /api/v1/states` (`index`, route name `states.index`)
- **Request params:** none.
- **Success response:** `$this->apiResponse($this->stateRepo->getAllState())` → `{"data": [...], "message": "Success", "status": "success"}`. `getAllState()` is a plain `State::all()` — every row/column, unfiltered, **not wrapped in `StateResource`** (same pattern as `Country::index`).

## `GET /v1/search/states` (`search`, route name `states.search`)
- **Request params (all optional, no FormRequest — read via `request()` inside the repository):**
  - `search` — free text; applied as `WHERE name LIKE %search%` only (no `country_id` filter — see coupling note above).
  - `offset` — optional int, default `0`.
  - `limit` — optional int, default `10`. Same `offset`/`limit` pagination style as `Country`'s `search`, not `rows`/`cursor`.
- **Success response:** `StateResource::collection(...)->additional(['meta' => ['total' => ...]])` → `{"data": [...], "meta": {"total": N}}`. Each item trimmed via `Arr::only(..., ['id', 'name', 'country_id'])` — `country_id` **is** present in the output (just never usable as an input filter).
- **`meta.total`:** `searchStatesCount()` — same `name LIKE` filter, independent `COUNT(*)` query (no off-by-one hazard here, unlike `Country`'s hardcoded-India case, since `State` has no equivalent synthetic-row injection).

---

## Summary

**Routes documented:** 2 `Route::` declarations (1 explicit `search` + 1 `apiResource` contributing 5 action bindings) → **7 total route registrations, only 2 reachable as real endpoints** (`index`, `search`); `store`/`show`/`update`/`destroy` 500 with "Call to undefined method" when hit.

**Notable findings for parity testing:**
- **Confirmed bug (same pattern as `Country`):** `store`/`show`/`update`/`destroy` are registered by `apiResource` but have no controller implementation — `State` is effectively **read-only** in practice.
- **Confirmed:** `search` has no `country_id` filter param at all — a country-scoped state lookup is not possible through this API today, despite `country_id` being a column on the table and present in the response shape.
- No dual-write hazard exists between `Country` and `State` currently, only because neither module's write endpoints work — this should be re-verified in AP-V3 if/when `store`/`update` are actually implemented for either module, since the underlying `states.country_id` FK constraint (`cascadeOnDelete`) means a `Country` delete (if ever implemented) would cascade-delete dependent `State` rows silently.
- `State` model's `newFactory()` references `Modules\State\Database\factories\StateFactory`, but **no such factory file exists anywhere in the module** (confirmed via filesystem search) — calling `State::factory()` (e.g. from a test or seeder) would throw a class-not-found error. Not reachable from any live API endpoint, but worth flagging for the Python QA project if it considers using model factories to seed test data.
- Both `StateDatabaseSeeder` and `CountryDatabaseSeeder` are empty stubs (`Model::unguard()` + a commented-out `$this->call(...)`) — reference data for both tables must come from a separate SQL import/dump, not from `php artisan db:seed`.

**Confidence:** High — every behavior traced directly from the complete `StateController.php`, `StateRepository.php`, `StateResource.php`, `State.php` entity, and the `states`/`countries` migrations. The country-coupling absence was verified by reading the full repository class (no other methods exist beyond the three shown) rather than inferred from the route list.
