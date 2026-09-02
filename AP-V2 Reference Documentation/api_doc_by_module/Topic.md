# Topic Module API Documentation

The `Topic` module owns `topics` (assignment/exercise topic names, e.g. "Contract Law Basics") and `topic_doc_details` (reference-material links/notes attached to a topic — title, URL, note text). It also exposes an async CSV export of the topic list. Topics are referenced elsewhere (e.g. `Result`'s `CourseFeaturedAssignmentMapping`, and assignments generally) but this file covers only the routes declared in `Modules/Topic/Routes/api.php`.

**Module-wide auth:** every route in `Modules/Topic/Routes/api.php` is `auth:sanctum` + `json.response`, mounted under `/api/v1/...`. No deviation.

See [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for the app-wide response envelope styles, standard error shapes, and pagination conventions referenced below instead of being repeated per endpoint.

`TopicController` pulls in `TopicTrait` (`Http/Traits/TopicTrait.php`) via `use TopicTrait;` for two things: the cursor-range calculator `calculateRangeForCursor()` (used by `index()`), and the **routed `export()` method itself**, which is defined entirely in the trait, not the controller — `TopicController` never declares `export()` directly; it inherits it from the trait. `TopicDocDetailsController` is a separate, standalone controller (no trait) handling `topic-doc-details`.

---

## `GET /api/v1/topics` (`index`, route name `topics.index`)
- **Request params:** `rows` — optional int (cast via `(int) request('rows')` only if `request()->has('rows')`), default `15` if absent. No `search` param handled directly by the controller, but the underlying repository query supports one (see below) — however this route never reads it explicitly; it flows through only if the client appends `?search=...` and Laravel's global `request()` helper picks it up inside the repository regardless of what the controller declared.
  - `cursor` — optional opaque base64 token, standard scheme (see `_COMMON_CONVENTIONS.md`); malformed cursor → `abort(500, 'Cursor value tempered')` via `TopicTrait::calculateRangeForCursor()`.
- **Success response:** `TopicResource::collection($this->topicRepo->allWithSearch(columns: ['*'], relations: [], count: $rows))->additional(['meta' => [...]])`.
  - `TopicResource` shape: `id`, `title` (via `Arr::only`), plus `doc_details` — a nested `TopicDocDetailsResource::collection($this->docDetail)` for **every** topic in the list (an eager-load-free relation access per item — `relations: []` is passed to `allWithSearch()`, so `docDetail` is lazy-loaded once per topic row, an N+1 query pattern worth flagging for performance/parity timing tests even though it doesn't affect response correctness).
  - `TopicDocDetailsResource` (nested) shape: all `topic_doc_details` columns except `created_at`/`updated_at`/`created_by`/`updated_by`, plus `creator` (`{id, first_name, last_name}` via `->only()` on the `creator` relation) and `updater` (same shape, `?->only(...)` — null-safe, so `null` if `updated_by` was never set).
  - `meta`: `{"total": N, "total_topic": N, "range": {"from": N, "to": N, "total": N}}` — **`total` and `total_topic` are always identical values** (both call the same `topicRepo->total_topic()` method) — a redundant duplicate key, not two different counts; don't expect them to ever diverge.
- **Notes:** `allWithSearch()` internally applies the `search` query param (`WHERE title LIKE %search%`) if present via `->when(request('search') && request('search') !== '', ...)` inside `TopicRepository::searchQuery()` — so `GET /api/v1/topics?search=X` **is** a working filter, just undocumented at the controller-signature level (no explicit `request('search')` read in `index()` itself; it's picked up implicitly by the repository).

## `GET /v1/search/topics` (`search`, route name `topics.search`)
- **Request params (no FormRequest, read via `request()` inside the repository):** `search` — matched as `WHERE id LIKE %search% OR title LIKE %search%` (same `id`-as-string substring-match quirk as `JobRole::search()` — see that module's doc for the exact false-positive-match behavior, identical here); `offset` (default `0`); `limit` (default `10`) — **not** `rows`/`cursor`, a different pagination style from this same controller's own `index()` a few lines above.
- **Success response:** `SearchTopicResource::collection(...)->additional(['meta' => ['total' => ...]])` → `{"data": [...], "meta": {"total": N}}`, trimmed to `id`+`title` only (no `doc_details` nesting here, unlike `index()`).
- **Minor source artifact:** `searchTopicsCount()`'s title clause is written as `->orWhere('title', 'LIKE', '%' . '%' . request('search') . '%')` — the doubled `'%' . '%'` string-concatenates to the same single `%` prefix as normal (`'%%term%'` is a no-op double-wildcard, functionally identical to `'%term%'` in SQL `LIKE`), so this is cosmetic copy-paste noise, not a behavioral bug — flagged only so it isn't mistaken for a real double-wildcard behavior difference from `searchTopics()`'s own where-clause.

## `GET /v1/search/specific-topics` (`searchTopicsWithArray`, route name `topic.specific.search`)
- **Request params:** `search` — no FormRequest, no type validation; repository does `$builder->whereIn('id', request('search'))` when present.
- **⚠️ Same confirmed crash pattern as `JobRole::searchJobRolesWithArray()`:** if `search` is sent as a scalar (e.g. `?search=5`) rather than an array (`?search[]=5&search[]=8`), Laravel's query-grammar binding compilation throws an uncaught `TypeError` — surfaces as a **500**, not a validation error. Must be reproduced exactly (crash-on-scalar), not "helpfully" coerced in AP-V3.
- **Success response:** global `apiResponse($this->topicRepo->searchTopicsWithArray())` → `{"data": [...], "message": "Success", "status": "success"}`. Raw model rows for columns `id`, `title` only (no Resource wrapping), no `meta`/`total` key — matching the identical `JobRole::searchJobRolesWithArray()` shape/absence-of-meta pattern.
- **Notes:** if `search` is omitted, the `whereIn` is skipped entirely and **all** topics (`id`, `title` only) are returned — same "unfiltered fallback" behavior as `JobRole`'s equivalent endpoint.

---

## `apiResource('topic-doc-details', 'TopicDocDetailsController')` — 4 of 5 wired actions functional

### `GET /api/v1/topic-doc-details` (`index`)
- **Request params:** none.
- **Success response:** `TopicDocDetailsResource::collection($this->topicDocDetailRepo->all())` — **every** `topic_doc_details` row across **all** topics, unfiltered/unpaginated (`all()` is the base repository's unrestricted find-all, no `topic_id` scoping, no `rows`/`cursor`, no `offset`/`limit`) — a potentially unbounded response on a large table. Same `TopicDocDetailsResource` shape as nested under `TopicResource.doc_details` above.

### `POST /api/v1/topic-doc-details` (`store`)
- **Request body** (`StoreTopicDocDetail` FormRequest, `authorize()` always `true`): `topic_id` required, `exists:topics,id`; `title` required string max:255; `link` required, `url` format; `note` required string.
- **⚠️ The FormRequest's overridden `validated()` (which injects `created_by`) is dead code for this action:** the controller does **not** call `$request->validated()` at all for `store()` — instead it does `$request->request->add(['created_by' => auth()->user()->id]); ... $this->topicDocDetailRepo->create($request->all());`, mutating the request's raw input bag directly and passing the **entire** `$request->all()` (not the validated subset) into `create()`. Functionally the end result (`created_by` present, `topic_id`/`title`/`link`/`note` present) is the same as if `validated()` had been used, but it means **any extra, non-validated field the client sends in the body also gets persisted** if the underlying `topic_doc_details` table/model happens to accept it (`TopicDocDetail` uses `protected $guarded = []`, i.e. **mass-assignment is fully open** — every column is fillable) — a client could smuggle arbitrary column values (e.g. `id`, `created_by` override before the trait's own overwrite... though the explicit `->add()` call happens after user input parsing and before `->all()`, so a client-supplied `created_by` in the body would be **overwritten** by the server-forced value, not smuggled through) into the `create()` call for any column not explicitly stripped. Confirm this openness is intentional before assuming AP-V3 should replicate it verbatim vs. tighten it — but for **parity testing purposes**, the current behavior accepts and persists unvalidated extra fields.
- **Success response:** `$this->apiResponse(['topic_doc_detail' => TopicDocDetailsResource::make($topicDocDetail)], 'Topic doc detail created successfully', statusCode: 201)`.
- **Side effects:** `created_by` forced server-side to the authenticated user id (as described above). No activity log on create.

### `PUT/PATCH /api/v1/topic-doc-details/{id}` (`update`)
- **Request body** (`UpdateTopicDocDetail`): `topic_id`/`title`/`link`/`note` all `nullable` (same validation rules as store, just optional). Its overridden `validated()` **is** actually used here (`$this->topicDocDetailRepo->update($id, $request->validated())`), injecting `updated_by` — the opposite of `store()`'s pattern, i.e. the two sibling FormRequests achieve the same "force server-side actor id" goal via **two different mechanisms** within the same controller.
- **Error response:** `$this->apiResponse([], 'Topic doc detail Not Found', 'error', 404)` if `findById($id)` returns falsy — a plain repository lookup, not route-model binding.
- **Success response:** `$this->apiResponse(['topic_doc_detail' => TopicDocDetailsResource::make($this->topicDocDetailRepo->findById($id))], 'Topic doc detail updated successfully')` — re-fetches the row after update rather than reusing an in-memory instance.

### `DELETE /api/v1/topic-doc-details/{id}` (`destroy`)
- **⚠️ Confirmed bug — null-pointer crash instead of a 404 on a missing id.** The exact source order in `TopicDocDetailsController::destroy()`:
  ```php
  $topicDocDetail = $this->topicDocDetailRepo->findById($id);
  $subject_id = $topicDocDetail->id;      // <-- dereferences BEFORE the null check below
  if (!$topicDocDetail) {
      return $this->apiResponse([], 'Topic doc detail Not Found', 'error', 404);
  }
  ```
  `$subject_id = $topicDocDetail->id;` runs **before** the `if (!$topicDocDetail)` guard. If `findById($id)` returns `null` (id doesn't exist), this line throws a PHP `Error: Attempt to read property "id" on null` — an uncaught **500**, and the intended 404 branch immediately below it is **unreachable** for the exact case it was written to handle. **A parity test hitting `DELETE /api/v1/topic-doc-details/{nonexistent-id}` must expect a 500, not the 404 the code's own error-handling branch appears to promise.** This is the same class of "dead/unreachable guard clause" bug as `Country::search()`'s no-op `filter()`, just via null-dereference instead of a discarded return value.
- **Success response (id exists):** `$this->apiResponse([], 'Topic doc detail deleted successfully')`.
- **Behavior:** hard delete at the repository level (`$this->topicDocDetailRepo->delete($id)`), but `TopicDocDetail` uses the `SoftDeletes` trait (confirmed: `use HasFactory, SoftDeletes;` in the entity, and a dedicated migration `2023_11_10_100756_add_deleted_at_to_topic_doc_details.php` adds the `deleted_at` column) — so `BaseRepository::delete()`'s plain Eloquent `->delete()` call actually performs a **soft** delete (sets `deleted_at`), not a hard row removal, despite the surrounding code not distinguishing the two. Row is recoverable at the DB level.
- **Side effects:** direct `Spatie\Activitylog\Models\Activity::create([...])` call (`log_name: 'Topic doc detail deleted'`, description string-interpolates the acting user's first/last name, `causer_type => User::class`, `subject_id` = the **pre-crash** `$subject_id` variable) — bypasses the app's `activity()` helper, same hand-rolled pattern seen in `CourseFaq::destroy()`. **This code is only reached when the id exists** (the crash above happens first on a missing id, before this log write would ever be attempted).

### `GET /api/v1/topic-doc-details/{id}` — ⚠️ confirmed broken, not a real endpoint
No `show()` method exists on `TopicDocDetailsController` (confirmed reading the complete 118-line controller — only `index`, `store`, `update`, `destroy` are defined). `Route::apiResource('topic-doc-details', ...)` still registers the route; hitting it throws "Call to undefined method ...::show()" — an uncaught 500. Same landmine pattern as `CourseFaq`'s missing `show()`, and the same family of bug as `Country`/`State`/`StudentDegree`/`StudentUniversity`'s missing `store`/`show`/`update`/`destroy` — but here it's the **sole** missing action, the other four are genuinely implemented.

---

## `GET /api/v1/topics/export` (`export`, route name `topics.export`, method lives in `TopicTrait`, inherited by `TopicController`)
- **Request body/params:** `data` — optional array (`Validator::make($request->all(), ['data' => ['nullable', 'array']])->validate()`), a standard Laravel 422 on failure if `data` is present but not an array. All **other** query/body params (e.g. `search`) are passed through unvalidated as `$request->all()` into the job.
- **Success response:** global `apiResponse('', 'Topics Csv file exporting started')` → `{"data": "", "message": "Topics Csv file exporting started", "status": "success"}`. **`data` is the literal empty string `""`, not `null`/`[]`/omitted** — matches the "`data` shape varies by endpoint" caution in `_COMMON_CONVENTIONS.md`. Returns immediately; the actual CSV build/upload/email happens fully asynchronously.
- **Side effects (async, `default_medium` queue):** `TopicCSVDownloadStart::dispatch($request->user(), $request->all(), $data['data'] ?? [])`. The job:
  1. Queries `Topic::query()->withSearchAndFilters($this->request, $data)->latest('id')->lazy()` — the scope only reads `filters['search']` (`WHERE title LIKE %search%`) and `filters['status']` from the raw request array passed in; **`status` is applied to a `topics` table `WHERE status = ...` clause, but the `topics` table has no `status` column at all** (confirmed against the migration — only `id`, `title`, `created_by`, `updated_by`, timestamps exist) — if a caller ever sends a `status` param to this export endpoint, the job would throw a DB "unknown column" error **inside the queued job**, not surfaced to the caller's original 200 response at all (since the response was already sent before the job runs) — a silent async failure a parity test cannot observe via the HTTP response alone; would need to inspect queue/failed-job state or the follow-up email/notification (or its absence) to detect.
  2. Writes a local temp CSV (`storage_path("tmp/{filename}")`) with a single `Title` column header, one row per topic's `title` (no other columns exported, even though `TopicResource`/`index()` expose `doc_details` — the export intentionally only covers the topic title list).
  3. Uploads to S3 (`exports/tmp/topic/{filename}`), deletes the local temp file.
  4. **External call / notification:** `$this->user->notifyNow(new TopicCSVCompleteNotification(...))` (immediate, synchronous-within-the-job notification dispatch) and `Mail::to($this->user->email)->send(new TopicCSVCompleteMail(...))` — both carry the S3 file URL. Neither is awaited/reflected in the original HTTP response; a parity test must treat this as a fire-and-forget side effect to verify out-of-band (e.g. via a test mail/notification fake), not via the export endpoint's own response body.
- **Notes:** `export()`'s only own request validation is the `data` array check; every other input (`search`, `status`, etc.) flows through unvalidated into the async job, where a bad `status` value can crash the job invisibly to the original caller.

---

## Summary

**Routes documented:** 6 `Route::` entries (4 explicit `Route::get` + 1 `apiResource` contributing 5 action bindings) → **9 total route registrations, 8 reachable as real endpoints**, 1 confirmed-broken (`topic-doc-details.show`).

**Notable findings for parity testing:**
- **Confirmed bug:** `TopicDocDetailsController::destroy()` dereferences `$topicDocDetail->id` before its own null-check, so a delete against a nonexistent id crashes with a 500 instead of returning the 404 the code appears to implement — the guard clause is unreachable for its intended case.
- **Confirmed bug/landmine:** `topic-doc-details`'s `apiResource` registers `show`, but no `show()` method exists — 500 on `GET /api/v1/topic-doc-details/{id}`.
- **Confirmed crash:** `searchTopicsWithArray` throws an uncaught `TypeError` if `search` is sent as a scalar instead of an array — identical bug family to `JobRole::searchJobRolesWithArray()`.
- **Confirmed latent bug (async, invisible to the caller):** the CSV export job's `status` filter references a column that doesn't exist on `topics` — would crash the queued job silently if ever exercised, with no trace in the original 200 response.
- `index()`'s `meta.total`/`meta.total_topic` are duplicate values from the same underlying call, not two distinct counts.
- `store()` vs `update()` on `topic-doc-details` force the acting-user-id field (`created_by`/`updated_by`) via two different mechanisms (raw request-bag mutation + `->all()` vs. FormRequest-overridden `validated()`) — same end effect, different code path, and `store()`'s use of `->all()` over an open (`$guarded = []`) model means any extra client-supplied field is persisted without validation.
- `TopicDocDetail`'s soft-delete (`deleted_at` added in a later migration) means `destroy()` is recoverable at the DB level despite the code reading as an unconditional delete.

**Confidence:** High — every endpoint traced directly from the complete `TopicController.php`, `TopicDocDetailsController.php`, `TopicTrait.php`, both FormRequests, all three Resources (`TopicResource`, `SearchTopicResource`, `TopicDocDetailsResource`), both repositories, both entities, the `TopicCSVDownloadStart` job, and the `topics`/`topic_doc_details` migrations. The `destroy()` null-dereference-before-null-check bug and the export job's missing `status` column were independently re-verified against the exact source line order and the exact migration column list, not inferred from naming.
