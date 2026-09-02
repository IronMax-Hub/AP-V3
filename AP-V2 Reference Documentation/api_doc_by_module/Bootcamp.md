# Bootcamp

Admin-facing surface for the `bootcamps` entity — listing (with/without book associations), search/reference lookups used by other modules' UIs, attaching/replacing book-delivery mappings, a CSV export of the book-master data, and an activity log. **No create/update/delete action for the `Bootcamp` entity itself exists anywhere in this module** — a `Bootcamp` row is only ever created/updated via the `LawSikho` ingestion gateway's `POST /v1/bootcamp_from_lawsikho` (see [`./LawSikho.md`](./LawSikho.md) and `API_SPECIFICATIONS.md` §7's correction) — confirmed again here by reading every method on `BootcampController`/`BootcampBooksTrait` in full: none of them write to `name`/`title`/`refund_eligible_course`. See [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for shared envelope/error/pagination conventions.

**Module-wide auth:** all 9 routes are under `Route::middleware(['auth:sanctum', 'json.response'])->prefix('v1')` — admin/staff guard, not `auth:student`.

**Class-location note:** `BootcampController` composes `BootcampBooksTrait` (all book-mapping and search/listing logic) and the app-wide `App\Http\Traits\ActivityLog` (used by `activity()`). Only `index()` and `calculateRangeForCursor()` (the cursor-pagination helper) and `export()` are defined directly on the controller; every other route below resolves to a trait method.

---

## `GET /v1/bootcamps`
- **Controller method:** `index()` (defined directly on the controller).
- **Request params (query):** `rows` (int, page size, default 15); `cursor` (opaque base64 token, standard cursor family — a tampered cursor triggers `abort(500, 'Cursor value tempered')`).
- **Behavior:** the underlying `BootcampRepository::searchQuery()` applies **`whereHas('books')`** — this listing only ever includes bootcamps that have **at least one** `BootcampBook` mapping. A freshly-created bootcamp with zero books attached (e.g. one just created via LawSikho's ingestion endpoint) will **not** appear here until at least one book is attached via `POST /v1/bootcamps/books` below — contrast with `search`/`all_bootcamps` further down, which have the opposite/no such filter. Also supports `search` (query, matches `id`/`name`/`title` LIKE, or the concatenated `"{name} - {title}"` string) and `bootcamp_id` (array, `whereIn('id', ...)`).
- **Success:** `BootcampResource::collection($data)->additional(['meta' => ['range' => <cursor family>, 'total' => <int, filtered by the same whereHas('books') + search/bootcamp_id filters>]])`.
- **`BootcampResource` shape:** all raw `bootcamps` columns except `created_at`,`updated_at`,`books_mapping`, plus `books` — `booksMapping` relation mapped down to `[{id, name, delivery_start_date}, ...]` (`id`/`name` pulled from the nested `book` relation, `delivery_start_date` from the mapping row itself).
- **Side effects:** read-only.

## `GET /v1/bootcamps/search`
- **Trait method:** `search()`.
- **Request params (query):** `search` (optional, same LIKE-across-id/name/title/concatenated-name-title pattern as `index`); `offset`/`limit` (optional, default `0`/`10` — **not** the `rows`/`cursor` cursor family used by `index`, a distinct bespoke offset-based pagination scheme for this endpoint).
- **Behavior:** filters to `whereDoesntHave('books')` — the **inverse** of `index()`'s filter: this endpoint only lists bootcamps that have **no** book mapping yet, i.e. it exists specifically to populate a "pick a bootcamp to attach books to" UI (candidates for `POST /v1/bootcamps/books`), excluding ones already configured.
- **Success:** `SearchBootcampResource::collection(...)->additional(['meta' => ['total' => <count, filtered but not offset/limited>]])` — the resource-collection pagination family. `SearchBootcampResource` shape: `{id, name}` where `name` = `"{name} - {title}"` if `title` is set, else just `name` (a computed display label, not a raw column).

## `POST /v1/bootcamps/books`
- **Trait method:** `storeBootcampBooks(Request $request)`. **No FormRequest** — inline `$request->validate([...])`: `bootcamp_id` required, `exists:bootcamps,id`, integer; `books` required array; `books.*.id` — `required_with:books`, integer, `exists:books,id`; `books.*.delivery_start_date` — `required_with:books`, date, `date_format:Y-m-d`.
- **Behavior** (inside `DB::transaction`): creates one `BootcampBook` row per entry in `books` (**appends**, does not check for/replace an existing mapping for the same `book_id`+`bootcamp_id` pair — calling this twice with overlapping books creates duplicate mapping rows, since there's no uniqueness guard visible in this method). Writes one `Activity::create()` row (`log_name: 'Bootcamp Book Added'`, `event: 'Bootcamp Book is Stored '` — trailing space in the literal event string, preserved verbatim; `causer_id: auth()->user()->id`, `causer_type: null` — note `causer_type` is explicitly `null` rather than the actual user's class, unlike the framework's own `activity()->causedBy()` helper which would set both; this is a direct `Activity::create()` call, bypassing that helper).
- **Success:** `apiResponse('', 'Books added to the bootcamp', statusCode: 201)`.

## `PUT /v1/bootcamps/{bootcamp}/books`
- **Trait method:** `updateBootcampBooks(Request $request, Bootcamp $bootcamp)` — `{bootcamp}` is route-model-bound; a non-existent id triggers the standard `ModelNotFoundException` 404 shape.
- **Request params (body):** same `books`/`books.*.id`/`books.*.delivery_start_date` rules as `storeBootcampBooks` above (no `bootcamp_id` field here — it comes from the route parameter instead).
- **Behavior:** `$bootcamp->booksMapping()->delete()` **unconditionally first** (deletes every existing `BootcampBook` row for this bootcamp), **then** creates fresh rows for everything in the request's `books` array inside `DB::transaction` — a **full replace, not a merge/diff**. A partial-update request (e.g. sending only 1 of the bootcamp's 3 currently-mapped books) will **remove the other 2** rather than leaving them untouched — matches the correction already noted in `API_SPECIFICATIONS.md` §3 for this same behavior. Same `Activity::create()` pattern as `store` (`log_name: 'Bootcamp Book Updated'`, `event: 'Bootcamp Book is Updated '` — again a trailing space, preserved verbatim).
- **Success:** `apiResponse('', 'Bootcamp book updated successfully')` — default 200 (unlike `store`'s explicit 201).

## `GET /v1/search/all_bootcamp`
- **Trait method:** `all_bootcamps()`.
- **Request params (query):** `search`, `offset`, `limit` — identical pattern to `bootcamps/search` above, **except no `whereDoesntHave`/`whereHas('books')` filter at all** (that line is present in source but fully commented out) — this endpoint returns every bootcamp regardless of book-mapping state, making it functionally a third, unfiltered-by-books variant of the same search shape.
- **Success:** same `SearchBootcampResource::collection(...)->additional(['meta' => ['total' => ...]])` shape as `bootcamps/search`.

## `GET /v1/search/specific-bootcamp-list`
- **Trait method:** `specific_bootcamp_list()`.
- **Request params (query):** `search` — expected to be an **array of bootcamp ids** (`whereIn('id', request('search'))`); a scalar value would need Laravel's automatic query-string array parsing to behave as intended (e.g. `search[]=1&search[]=2`).
- **Success:** `apiResponse($query)` — the plain `apiResponse()` envelope (`{"data": [{"id","name","title"}, ...], "message": "Success", "status": "success"}`) wrapping **raw model attributes**, not a Resource — a different shape from every other search/lookup endpoint in this module (no `name`-with-title-fallback computed label here; `name` and `title` are returned as separate raw columns instead).

## `GET /v1/student_specific_bootcamps`
- **Trait method:** `student_specific_bootcamps(Request $request)`.
- **Request params (query):** `student_id` — inline-validated `required` (custom message: `"Student ID is Required"` — standard 422 shape from `_COMMON_CONVENTIONS.md` otherwise); `search`, `offset`, `limit` optional, same LIKE/pagination pattern as the other search endpoints.
- **Behavior:** filters to bootcamps with `whereHas('enrollments')` **and** (redundantly, since `student_id` is required) `whereRelation('enrollments', 'student_id', request('student_id'))` — i.e. bootcamps this specific student is actually enrolled in.
- **Success:** same `SearchBootcampResource::collection(...)->additional(['meta' => ['total' => ...]])` shape as the other `Search*` endpoints.

## `GET /v1/bootcamps/book_master/export`
- **Controller method:** `export(Request $request)` (defined directly on the controller).
- **Request params (body/query):** `Validator::make($request->all(), ['data' => ['nullable', 'array']])` — only `data` is actually validated; everything else in the request passes through unvalidated to the job.
- **Behavior:** fire-and-forget — dispatches `BootcampBookMasterCSVDownload::dispatch($request?->user(), $request?->all(), $data['data'] ?? [])->onQueue('default_medium')` and returns immediately; no synchronous file in the response.
- **Success:** `apiResponse('', 'Bootcamp Book-master Csv file exporting started')` — HTTP 200. Poll/check for the resulting email (`BootcampBookMasterCSVCompleteMail`, per the `Emails/` directory — not traced further here) rather than expecting a synchronous download.
- **Side effects:** the queued job (out of this controller's scope) presumably builds and emails a CSV — not independently traced line-by-line here.

## `GET /v1/bootcamps/{bootcamp_id}/activity` (route name `bootcamps.activity`)
- **Trait method:** `activity($id)`.
- **Not-found branch:** `if (!$this->bootcampRepo->findById($id))` → `apiResponse([], 'Bootcamp Not Found', 'error', 404)` — called with the **correct** 4-argument order (`data, message, status, statusCode`), so this genuinely returns **HTTP 404** (unlike the `apiResponse()`-argument-order bug documented in `StudentDashboardManagement.md` — that bug does not reproduce here; confirmed by re-reading `app/Helpers/functions.php`'s actual signature and this call site's argument order side-by-side).
- **Found branch:** delegates to `App\Http\Traits\ActivityLog::logOfBootcampBookMaster($id, ['id','description','causer_id','event','created_at'])` — **note the call site in `BootcampBooksTrait` spells this `logOfBootcampBookmaster` (lowercase `m` in "master")**, while the actual method on `ActivityLog` is `logOfBootcampBookMaster` (capital `M`). This is **not a bug** — PHP method names are case-insensitive at the call site (unlike PHP class-constant names), so this resolves correctly at runtime; flagged only as a cosmetic inconsistency worth knowing if grepping the codebase for this method name.
- **Success:** cursor-paginated `ActivityResource::collection($paginator)->additional(['meta' => ['next_page_url','prev_page_url','range' => {'from','to','total'}]])`, filtered to `Activity` rows where `subject_type = Modules\Bootcamp\Entities\BootcampBook::class` and `subject_id = $id` — i.e. this is the activity log for **book-mapping changes on this bootcamp** (from `storeBootcampBooks`/`updateBootcampBooks` above), not a general "all activity referencing this bootcamp" log. `rows` query param controls page size (default 15).

---

## Summary

- **Endpoint count:** 9 routes, all live and functioning (no dead/broken scaffolding in this module — unlike `Notification`/`StudentNotifications`, there is no `apiResource` registration here at all, only explicit named routes, and every named route resolves to a real, implemented method).
- **Structural surprises / notes for parity testing:**
  1. **`GET /v1/bootcamps` (index) and `GET /v1/bootcamps/search` apply opposite book-mapping filters** (`whereHas('books')` vs `whereDoesntHave('books')`), while `GET /v1/search/all_bootcamp` applies neither — three visually-similar "list bootcamps" endpoints with three different implicit filters. A parity test must not assume these are interchangeable.
  2. `updateBootcampBooks` (`PUT .../{bootcamp}/books`) is a **destructive full-replace**, not a merge — confirmed directly from source, matching the existing note in `API_SPECIFICATIONS.md` §3.
  3. `storeBootcampBooks` has no duplicate-mapping guard — repeat calls with overlapping `book_id`s create duplicate `BootcampBook` rows.
  4. No create/update/delete exists for the `Bootcamp` entity itself in this module — confirmed by reading every method; the only place a `Bootcamp` row is actually written is `LawSikho`'s `bootcamp_from_lawsikho` (see `./LawSikho.md`).
  5. The `activity()` endpoint's `apiResponse([], 'Bootcamp Not Found', 'error', 404)` call genuinely returns HTTP 404 — this module does **not** exhibit the apiResponse-argument-order bug found elsewhere in the codebase (e.g. `StudentDashboardManagement`); every non-200 status in this module is called with the correct argument order.
- **Confidence:** High — `BootcampController`, `BootcampBooksTrait`, `BootcampRepository`, `BootcampResource`, `SearchBootcampResource`, and the `Bootcamp` entity were all read in full. `App\Http\Traits\ActivityLog::logOfBootcampBookMaster` was independently read to confirm both its real behavior and the case-insensitive-method-name non-bug.

---

*Companion documents: [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md), [`./LawSikho.md`](./LawSikho.md) (the actual `Bootcamp::create()`/update call site), [`../API_SPECIFICATIONS.md`](../API_SPECIFICATIONS.md) §3 (original pass) and §7 (the `Bootcamp::create()` correction, confirmed and cross-referenced above).*
