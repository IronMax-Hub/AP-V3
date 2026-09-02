# AtsAPI Module — API Documentation

The `AtsAPI` module bridges this app's `Course`/`Enrollment` data with an external Applicant Tracking System ("ATS"/job-opportunity service, base URL `config('app.ats_api_url')`). It exposes one write endpoint (job-to-course mapping ingestion, called by an external caller) and two read endpoints (course list for the ATS to consume, and a per-student job list proxied from the ATS). See [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for the app-wide envelope/error/pagination conventions — this file only calls out where a specific endpoint deviates.

## Correction / verification of the `API_SPECIFICATIONS.md` §7 "AtsGateWay" finding

`API_SPECIFICATIONS.md` §7 states the `AtsGateWay` double-processing bug is *"real in code but currently unreachable"* because the `ats.gateway` middleware alias is registered but never attached to any route. **Re-verified against current source — this claim still holds exactly as stated:**

- `Modules\AtsAPI\Providers\AtsAPIServiceProvider::boot()` registers the alias: `$router->aliasMiddleware('ats.gateway', AtsGateWay::class);`.
- `Modules/AtsAPI/Routes/api.php` (current content, re-read for this pass) wraps all three of this module's routes in a single group: `Route::middleware(['json.response'])->prefix('v1')->group(...)`. **`ats.gateway` does not appear anywhere in the route file.**
- `Modules\AtsAPI\Http\Middleware\AtsGateWay::handle()` itself still contains the described bug in its dead code: for `$request->channel == 'Lawsikho'` it calls `$next($request)` (proceeds normally); for `'SkillArbitrage'` it POSTs the payload to an external SkillArbitrage-portal URL and returns that response directly (short-circuits, never calls `$next`); for **any other value** (including no `channel` at all) it does **both** — fires the same external POST **and** calls `$next($request)`, meaning the request would be processed twice (once by the external SkillArbitrage system, once by this app's own `saveJobAndCourseMapping`) if this middleware were ever wired in. This remains dormant, unreachable dead code exactly as previously documented — **no change to report.**

## Module-wide notes

- **No auth guard on any route in this module** — all three routes carry only `json.response`. `POST /v1/save-job-and-course-mapping` and `GET /v1/atsapi/get-all-courses` are genuinely callable with zero credentials. `GET /v1/atsapi/get-all-jobs` has an unusual partial-auth dependency — see its own section below; it is **not** protected by any Laravel auth middleware either, but its behavior branches on whether `auth()->user()` happens to resolve.
- **Dead `apiResource`-style scaffolding on the controller:** `AtsAPIController::index/create/show/edit` return bare Blade `view()` calls (`atsapi::index`/`create`/`show`/`edit`); `store`/`destroy` have **empty bodies**. None of these five methods are wired to any route in this module's `Routes/api.php` at all (no `apiResource('atsapi', ...)` call exists) — they're leftover `php artisan module:make-controller` boilerplate, entirely unreachable, not even dead routes.
- **Response helper style:** hand-rolled `response()->json([...])` throughout; `success` is a **boolean** field, not the app-wide `status` string convention.
- **Real implementation lives partly in a trait:** `AtsAPIController` does `use AtsApiTrait;` — `getAllCourses()` and `getAllJobs()` (plus their private helpers `getJobIds()`, `getQueryParams()`, `getAtsBearerToken()`) are defined in `Modules/AtsAPI/Http/Traits/AtsApiTrait.php`, not the controller. Only `saveJobAndCourseMapping()` is written directly on the controller.
- **Orphaned trait method:** `AtsApiTrait::saveCourseJobMapping($courseId, $jobId, $channel, $userId)` has an **empty body** and is never called from anywhere (not routed, not invoked internally) — dead code, not a live contract. `AtsApiTrait::updateCourseJobMapping()` is likewise defined but not called from any routed method in this module (confirmed via grep of the trait/controller — no call site).

---

### `POST /v1/save-job-and-course-mapping` (named `save-job-and-course-mapping`)
- **Controller:** `AtsAPIController::saveJobAndCourseMapping`.
- **Auth:** none.
- **Request params — inline `$request->validate([...])`, not a FormRequest class:**
  - `job_id` — string, required.
  - `course_id` — array, nullable.
  - `channel` — string, required.
  - `is_draft` — string, required, `in:Draft,Published`.
  - `user_id` — nullable, **accepted but never actually used** (see below).
  - `job_expiry_date` — date, nullable, `after:today`.
  - Validation failure → caught explicitly (not left to the global handler) and returned as `422 {"success": false, "message": "Validation failed", "errors": <Laravel's per-field errors array>}` — **note this is a hand-rolled shape, not the app-wide standard 422 envelope** (no `data.errors` nesting; `errors` is top-level).
- **Behavior:**
  - `$status = $request->channel == 'Lawsikho' ? '1' : '0'` — computed but only used as the stored `status` column value, unrelated to `is_draft`/publish state.
  - `$courseIds = $request->course_id ?: [null]` — an empty/absent `course_id` array becomes a single-element array containing `null`, so a `CourseJobMapping` row with `course_id = null` is created/updated for that `job_id` if none was specified.
  - Existing `CourseJobMapping` rows for this `job_id` whose `course_id` is **not** in the newly-submitted `$courseIds` are updated to `status = '0'` (soft-deactivated, not deleted) — a partial-update-as-diff pattern.
  - For every id in `$courseIds`, `CourseJobMapping::updateOrCreate(['job_id' => ..., 'course_id' => ...], [...])` sets `user_id` (⚠️ **always `auth()->user()->id ?? 1`, ignoring the `user_id` the caller sent** — confirms the existing `API_SPECIFICATIONS.md` §6 finding still holds: on this unauthenticated route, `auth()->user()` is essentially always null, so every row is stamped `user_id: 1` regardless of caller), `is_draft` (`'1'` if `Published` else `'0'`), `status` (the `$status` computed above), **`channel` hardcoded to the literal string `'Lawsikho'`** (⚠️ confirms the existing finding: whatever the caller actually sent for `channel` — e.g. `SkillArbitrage` — is discarded; every row is unconditionally stored as `channel: 'Lawsikho'`, even though `channel` is also used, correctly, to compute `$status` a few lines earlier), and `expiry_date` (from `job_expiry_date`).
- **Success:** `200 {"success": true, "message": "Job and course mapping saved/updated successfully"}`.
- **Error (non-validation exception):** `500 {"success": false, "message": "Failed to save job and course mapping", "error": <exception message if app.debug, else "An unexpected error occurred">}`.
- **Side effects:** local DB writes only (`course_job_mappings` table via `CourseJobMapping`); every failure path is also `Log::error()`'d with the full request body and, for the generic-exception branch, file/line.
- **Notes:** ⚠️ `array_diff($existingCourseIds, $courseIds)` (the deactivation-diff step) is a loose string-based comparison — if any existing row has `course_id = null`, PHP's `array_diff` casts to string for comparison (`null` → `''`), which can produce inconsistent diff results when mixing `null` and real ids across calls; not independently reproduced here in full but worth a dedicated boundary test (submit once with `course_id` omitted, then again with a real array, and check whether the `null`-course_id row is correctly deactivated).

---

### `GET /v1/atsapi/get-all-courses` (named `get-all-courses`)
- **Controller:** `AtsAPIController::getAllCourses` (defined in `AtsApiTrait`).
- **Auth:** none.
- **Request params:** none.
- **Behavior:** `Course::query()->where('deleted_at', null)->where('status', 1)->get(['id', 'course_name'])`, mapped to `{"id":..., "name": <course_name>}` per row. (`where('deleted_at', null)` is Laravel's two-argument-null idiom, equivalent to `whereNull('deleted_at')` — not a bug, just an unusual way to write it.)
- **Success:** the raw mapped `Collection` is returned directly from the method — Laravel auto-serializes it to a **bare JSON array**, `[{"id":1,"name":"..."}, ...]`, with **no envelope of any kind** (no `data`/`status`/`message` wrapper).
- **Notes:** No auth and no pagination — returns every active course's id/name in one response; low-sensitivity data (course names), but worth noting alongside the module's other no-auth endpoint for a consistent "unauthenticated access" test sweep.

---

### `GET /v1/atsapi/get-all-jobs` (named `get-all-jobs`)
- **Controller:** `AtsAPIController::getAllJobs` (defined in `AtsApiTrait`).
- **Auth:** none via middleware — but the method's own logic depends on `auth()->user()` resolving, **conditionally**. **Correction to `API_SPECIFICATIONS.md` §6**, which states this endpoint *"requires ... a resolvable `auth()->user()` despite no guard middleware on the route — will throw on a genuinely unauthenticated call."* Re-traced from current source — **this is only true when the (implicitly null) student ends up with at least one matching job mapping, which cannot happen for a genuinely unauthenticated caller.** The actual control flow:
  1. `getJobIds($request)` runs first, unconditionally: `Enrollment::where('student_id', auth()->user()->id)->where('status', 1)->pluck('course_id')`. If unauthenticated, `auth()->user()` is `null`; PHP 8's "attempt to read property on null" is a **warning, not a fatal error**, so `->id` evaluates to `null`. `where('student_id', null)` — Laravel's two-arg-null idiom again — becomes `whereNull('student_id')`, which in practice matches no real enrollment rows (no legitimate enrollment has a null `student_id`). So an unauthenticated call gets `$courseIDs = []`, then `CourseJobMapping::whereIn('course_id', [])->...->pluck('job_id')` also yields `[]`.
  2. `getAllJobs()` checks `if (empty($jobIds))` **before** ever calling `getAtsBearerToken()` (the method that throws `AtsApiException` for a missing/malformed `ats-token` header) or making the external HTTP call — so for an unauthenticated caller (or an authenticated one with no matching active/published/unexpired course-job mapping), the method returns early with `200 {"success": true, "data": [], "message": "No jobs found for enrolled courses"}` and **never throws, never checks the `ats-token` header at all.**
  3. The `ats-token` bearer-header requirement (custom header, not `Authorization`) and the dependency on a resolvable authenticated user **only actually matter on the path where `$jobIds` is non-empty** — i.e. only for a genuinely authenticated student with at least one active, published, non-expired `CourseJobMapping` row for a course they're enrolled in (`Enrollment.status = 1`). On that path, a missing/malformed `ats-token` header throws `AtsApiException`, caught by the surrounding generic `catch (\Exception $e)` and turned into `500 {"success": false, "message": "An error occurred while fetching jobs", "error": <message if app.debug, else "Internal server error">}` — so the failure mode is a handled 500, not an uncaught fatal, even on that path.
  - **A parity test targeting "unauthenticated access" on this endpoint should expect `200` + empty-jobs body, not a thrown error** — update any existing assumption built on the older `API_SPECIFICATIONS.md` wording.
- **Request params (query, all optional, read via `$request->has()`/property access, no FormRequest):** `location`, `experienceMin`, `experienceMax`, `work_mode`, `salaryMin`, `salaryMax`, `industry` — each forwarded to the external ATS query string only if present; `sort` is hardcoded to `'all'` (not client-controlled despite a `sort` mention in the trait's own docblock).
- **External call (only reached when `$jobIds` is non-empty):** `GET {config('app.ats_api_url')}/api/v1/es/joblist/all?{querystring}` with headers including `authorization: Bearer {ats-token header value, 'Bearer ' prefix stripped}`, `x-api-key: config('app.ats_api_key')`, `x-api-secret: config('app.ats_api_secret')`, plus a large set of hardcoded browser-impersonation headers (`origin`/`referer` pointing at `opportunity-app-development.lawsikho.dev`, a hardcoded `user-agent` string, `sec-ch-ua`/`sec-fetch-*`) — worth flagging that this endpoint impersonates a specific frontend origin/browser rather than identifying itself as a server-to-server integration.
- **Success (external call path):** if the external response status is exactly `200`, returns `$response->json()` **directly** — whatever shape the ATS service returns, unwrapped, is the entire response body (no `data`/`success` envelope added by this app on this specific branch).
- **Error (external call path):** any non-200 external status → `500 {"success": false, "message": "Failed to fetch jobs from external API", "error": <external status code>}` (note: **always 500 regardless of what the external status actually was** — a 404 or 429 from the ATS service is still surfaced as a 500 here).
- **Notes:** `getJobIds()` filters `CourseJobMapping` to `status = '1'` (string) AND `expiry_date >= today` AND `is_draft = '1'` — i.e. only "published, active, not-yet-expired" mappings count; this must line up with how `saveJobAndCourseMapping` above actually sets those three columns to construct a meaningful end-to-end test (create a mapping, enroll a student in its course, then confirm the job id surfaces here).

---

## Endpoint count and confidence

- **3 routes** in `Modules/AtsAPI/Routes/api.php`, all documented above in full.
- **High confidence** on this app's own logic (validation, DB writes, control flow, the corrected unauthenticated-access behavior for `get-all-jobs`) — traced directly from `AtsAPIController`, `AtsApiTrait`, `AtsGateWay`, and `AtsAPIServiceProvider` source, cross-checked against the route file and `config/auth.php`. **Low confidence on the external ATS service's own response shape/error bodies** for `get-all-jobs`'s success path — that's an opaque third-party payload; mock at the `Http::` facade level for parity testing rather than assuming a fixed schema.

---

*Companion documents: [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md), [`../API_SPECIFICATIONS.md`](../API_SPECIFICATIONS.md) §6 ("AtsAPI") and §7 (the `AtsGateWay` correction — reconfirmed accurate above) and the `LawSikho.md` file in this directory, whose own module-wide notes also reference the §7 `AtsGateWay` correction.*
