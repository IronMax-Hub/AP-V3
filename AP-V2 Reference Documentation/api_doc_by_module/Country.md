# Country Module API Documentation

The `Country` module owns the static `countries` reference table (id, ISO short code, name, common name, phone code) used for dropdowns/typeahead elsewhere in the app (e.g. `Enrollment`, `StudentProfile`).

**Module-wide auth:** both routes in `Modules/Country/Routes/api.php` are `auth:sanctum` + `json.response`, mounted under `/api/v1/...`. No deviation.

See [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for the app-wide response envelope styles, standard error shapes, and pagination conventions referenced below instead of being repeated per endpoint.

`CountryController` (`Modules/Country/Http/Controllers/CountryController.php`) is a complete, self-contained controller — no traits pulled in. **It implements only `index()` and `search()`.** Both use `$this->apiResponse()` / a Resource collection; there is no hand-rolled `response()->json()` anywhere in this module.

## ⚠️ `apiResource('countries', 'CountryController')` — only 2 of 5 wired actions exist

```php
Route::get('/search/countries', [CountryController::class, 'search'])->name('countries.search');
Route::apiResource('countries', 'CountryController');
```
`Route::apiResource(...)` registers routes for all five actions — `index`, `store`, `show`, `update`, `destroy`. **`CountryController` defines only `index()`.** `store`, `show`, `update`, and `destroy` do not exist anywhere in the class (confirmed by reading the complete controller source, 57 lines). Calling any of `POST /api/v1/countries`, `GET /api/v1/countries/{country}`, `PUT/PATCH /api/v1/countries/{country}`, or `DELETE /api/v1/countries/{country}` triggers a PHP `Error: Call to undefined method Modules\Country\Http\Controllers\CountryController::store()` (or `show`/`update`/`destroy`) — an uncaught-exception **500**, not a clean 404/405 JSON error. This is the same landmine pattern documented for `CourseFaq`'s missing `show()`, except here 4 of the 5 `apiResource` actions are missing, not just one. There is no `StoreRequest`/`UpdateRequest`/write-side Resource anywhere in the module — confirming these are genuinely absent, not merely undocumented.

---

## `GET /api/v1/countries` (`index`, route name `countries.index`)
- **Request params:** none.
- **Success response:** `$this->apiResponse($this->countryRepo->getAllCountry())` → `{"data": [...], "message": "Success", "status": "success"}`. `getAllCountry()` is a plain `Country::all()` — **every** row/column in the `countries` table, unfiltered and **not wrapped in `CountryResource`** (unlike `search`, below) — so `iso3` and `num_code` (excluded from `search`'s output) ARE present here, along with the raw Eloquent model's default JSON shape (no `Arr::only`/`Arr::except` trimming at all).
- **Notes:** `index` and `search` return **structurally different shapes** for the same underlying rows — `index` is the full raw model, `search` is trimmed to 5 fields via `CountryResource` and prepends a synthetic India row (see below). A parity test must not assume the two endpoints are interchangeable.

## `GET /v1/search/countries` (`search`, route name `countries.search`)
- **Request params (all optional, no FormRequest — read via global `request()` helper inside the repository, not the controller):**
  - `search` — free-text; server-side applied as `WHERE short LIKE %search%` OR `common_name LIKE %search%` OR `common_name LIKE %search%` (duplicated clause — literal copy-paste artifact in `CountryRepository::searchCountries()`/`countryCount()`, functionally harmless since it's an `OR` against the same column twice) OR `phone_code LIKE %search%`.
  - `offset` — optional int, default `0`.
  - `limit` — optional int, default `10`. **Not `rows`/`cursor`** — this endpoint uses the plain `offset`/`limit` query-param pair, not either pagination family described in `_COMMON_CONVENTIONS.md`.
- **Success response:** `CountryResource::collection(...)->additional(['meta' => ['total' => ...]])` → `{"data": [...], "meta": {"total": N}}` (resource-collection shape, no `message`/`status`). Each item trimmed via `Arr::only(..., ['id', 'short', 'name', 'common_name', 'phone_code'])` — `iso3`/`num_code` are dropped.
- **⚠️ Hardcoded India injection, confirmed in source:** before building the response, the controller does:
  ```php
  $collection->filter(fn($item) => $item['id'] !== 99);
  $collection->prepend(['id' => 99, 'short' => 'IN', 'name' => 'INDIA', 'common_name' => 'India', 'phone_code' => 91]);
  ```
  Any real DB row with `id == 99` is filtered OUT of the result set and replaced by this hardcoded literal, unconditionally, on **every call regardless of the `search` term** — even a `search` value that wouldn't otherwise match India's real row still gets this synthetic row prepended first. **A parity test must expect this exact India row shape as element `[0]` of `data` on every `search` call**, not derived from the DB seed data.
  - `->filter()` on a `Collection` returns a **new** filtered collection; the local `$collection` variable's underlying items are **not mutated by this line** since the return value is discarded — however `->prepend()` on the next line **does** mutate `$collection` in place (Laravel's `Collection::prepend()` is a mutating method, unlike `filter()`). Net effect: the `filter()` call is dead/no-op — **the real id-99 row (if one exists in the `countries` table) is never actually removed**, and would appear as an ordinary result IN ADDITION TO the hardcoded India prepend if the DB seed happens to contain an id-99 row that also matches the search term. This is a genuine bug distinct from "intentional hardcoding" — confirmed by re-reading `Collection::filter`/`Collection::prepend` semantics against the exact two lines in `CountryController::search()`. **A parity test should verify whether the seeded `countries` table actually has an `id=99` row** (see `CountryDatabaseSeeder`) to know whether this duplicate-row bug is observable in practice.
- **`meta.total`:** `countryCount()` — counts rows matching the same `search` filter, **excluding** the synthetic India row (it's a pure DB `COUNT(*)`, unaware of the controller-level prepend/filter) — so `meta.total` can be off-by-one relative to `data.length` depending on whether a real id-99 row exists and matches the filter.
- **Dead code:** the method contains an unreachable `return $this->apiResponse($collection->values()->all());` statement after the actual `return CountryResource::collection(...)` — PHP never executes it; noted only because it hints the endpoint's response shape was changed at some point without cleaning up the old line, not because it has any runtime effect.

---

## Summary

**Routes documented:** 2 `Route::` declarations (1 explicit `search` + 1 `apiResource` contributing 5 action bindings) → **7 total route registrations, only 2 reachable as real endpoints** (`index`, `search`); `store`/`show`/`update`/`destroy` are registered routes that fatal with an uncaught `Error` (500) when hit, since the corresponding controller methods don't exist.

**Notable findings for parity testing:**
- **Confirmed bug:** 4 of 5 `apiResource` actions (`store`, `show`, `update`, `destroy`) have no controller method — any call 500s with "Call to undefined method," not a clean error shape. `Country` is effectively **read-only** in practice despite `apiResource` implying full CRUD.
- **Confirmed bug:** `search()`'s `$collection->filter(...)` to exclude a real `id=99` row is a no-op (discarded return value of a non-mutating `Collection` method) — the hardcoded India row prepend still happens, but any genuine `id=99` DB row is NOT actually excluded as the code intends.
- `index()` and `search()` return different shapes for the same table (full raw model vs. 5-field trimmed resource) — do not assume parity between them.
- `search()`'s duplicate `common_name LIKE` OR-clause is copy-paste noise, not a functional bug.
- `meta.total` from `search()` does not account for the synthetic India row or the (buggy, non-excluded) real id-99 row — potential off-by-one vs. `data.length`.

**Confidence:** High — every behavior traced directly from the complete `CountryController.php`, `CountryRepository.php`, `CountryResource.php`, and the `countries` migration. The `filter()`/`prepend()` mutability bug was independently verified against Laravel's `Illuminate\Support\Collection` semantics (`filter` returns new instance, `prepend` mutates in place), not assumed from the code's apparent intent.
