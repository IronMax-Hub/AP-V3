# ReferralSystem Module — API Documentation

The `ReferralSystem` module is a **thin proxy** in front of a separate external referral-partner service (base URL `REFERRAL_BASE_URL`, default `http://referral-system-api-development.lawsikho.dev`). It has **no local tables of its own** — the one endpoint that reads local data (`GET /v1/referral-system/students`) queries the `Student` model directly; every other endpoint forwards to the external service and relays its response back with minimal reshaping. See [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for the app-wide envelope/error/pagination conventions — this file only calls out where a specific endpoint deviates.

## Module-wide notes

- **Two route groups, only one guarded:**
  1. `json.response` only, prefix `v1/referral-system` — **no auth guard at all**. Contains the one admin-facing endpoint, `GET students`.
  2. `json.response` + `last.login` (`App\Http\Middleware\StudentActivity`) + `auth:student`, prefix `student/v1/referral-system` — the five student-facing proxy endpoints.
- **Response helper style — ad-hoc external pass-through**, exactly as flagged in `_COMMON_CONVENTIONS.md`: every proxy endpoint returns `response()->json(['data' => $data])` on success, where `$data` is the external service's own decoded JSON body verbatim, with **no normalization** of its shape/status/message fields to this app's conventions. There is no `message`/`status` key added by this app on the success path — only whatever the external service's own body contains, nested under `data`.
- **Error shape — also non-standard:** every proxy endpoint's `catch` block returns `response()->json(['error' => $errorMessage], $errorCode)`, where `$errorMessage` is `\Illuminate\Http\Client\RequestException::getMessage()` (leaks the underlying HTTP client's exception text, e.g. `"Client error: ... "`) and `$errorCode` is `RequestException::getCode()`. **This `catch` block only fires for `RequestException`** — which Laravel's `Http` client only throws when you explicitly call `->throw()` on the response. None of the five proxy methods call `->throw()`, so **a 4xx/5xx response from the external service does not actually throw** and will instead fall through to the normal success path, returning `200 {"data": <external error body>}` with this app's own HTTP status forced to 200 regardless of what the external service returned. The `catch` blocks are effectively dead code for ordinary HTTP-level failures — they'd only fire on a genuine connection-level exception (DNS failure, timeout past client config, etc., if those are wrapped as `RequestException` by the underlying Guzzle/PSA layer) or if the codebase's `Http` client is globally configured to throw. **Treat "external service returned a 4xx/5xx" and "network-level failure" as two different, differently-shaped outcomes for every proxy endpoint below** — this is the single most important quirk in this module for parity testing.
- **No local database tables**, no FormRequest classes anywhere in this module, no Resource actually wired to any live route except `ReferralSystemResource` (see below).
- **Orphaned Resource classes:** `Modules\ReferralSystem\Http\Resources\GeneralResource` and `Modules\ReferralSystem\Http\Resources\CourseSpecificResource` exist in the codebase but are **never referenced by any controller method** — confirmed via grep, they appear nowhere outside their own class-definition files. Do not describe them as live response shapes.
- **Unused dependency:** `ReferralSystemController`'s constructor injects `ReferralSystemInterfaceRepository $referralRepo` (bound to `ReferralSystemRepository`, which wraps the `Student` model with a cursor-paginated search helper, `allWithSearch()`/`allWithSearchTotalCount()`), but **no controller method ever calls `$this->referralRepo`** — the repository and its cursor-pagination capability are dead weight; `referralSystem()` queries `Student::query()` directly instead.

---

## Admin-facing (no auth)

### `GET /v1/referral-system/students` (named `student.referral`)
- **Controller:** `ReferralSystemController::referralSystem`.
- **Auth:** none — only `json.response`. No guard of any kind protects this route.
- **Request params (all optional query params, no FormRequest — passed as a raw array into a model scope):**
  - `search` — LIKE-matched (`%...%`) against `full_name` OR `email` OR `phone` (via `Student::scopeSearchForReferral`).
  - `name` — ⚠️ **exact-match** (`where('full_name', $filterData['name'])`), **not** a LIKE/partial match despite `search` being fuzzy — a parity test must not assume `name` behaves like `search`.
  - `addedStartDate` / `addedEndDate` — **both required together** if either is present; validated inline (`Validator::make([...])->validate()`) to `date_format:Y-m-d` — a genuine 422 (standard shape, see conventions doc) if provided in the wrong format. If both present and valid, filters `Student.created_at` between `startOfDay(addedStartDate)` and `endOfDay(addedEndDate)`.
- **Success response:** `ReferralSystemResource::collection($data)` where `$data = Student::query()->searchAndFilterForReferral($request->all())->get()` — a **plain, unpaginated `get()`** (not cursor-paginated, despite the injected-but-unused repository supporting cursor pagination) — every matching student is returned in one response. Default Laravel resource-collection wrapper: `{"data": [{"id","name" (from full_name),"email","phone","created_at","updated_at"}, ...]}` — no `meta`/`message`/`status` key at all (this is the plain `JsonResource::collection()` wrapper, distinct from both pagination families described in the conventions doc, since there is no paginator instance involved here).
- **Notes:** Given no auth guard and no pagination cap, this endpoint returns the **entire unfiltered student table** if called with no query params at all — a real DoS/data-exposure surface worth flagging explicitly for parity/security testing, consistent with the existing `API_SPECIFICATIONS.md` §6 flag on this exact endpoint ("no auth guard at all").

---

## Student-facing (`auth:student`, `last.login`, `json.response`, prefix `student/v1/referral-system`)

### `GET /generalCode` (named `student.generalCode`)
- **Controller:** `ReferralSystemController::generalCode`.
- **Request params:** none — `studentId` is always `Auth::user()->id` (the authenticated student), `channelId` is hardcoded `1`.
- **External call:** `GET {REFERRAL_BASE_URL}api/v1/plan/generalRefferalLink/{studentId}/{channelId}` — note the external path segment is literally `Refferal` (misspelled, preserved as-is since it's the external contract, not this app's typo).
- **Success:** `200 {"data": <external decoded JSON body>}`.
- **Error:** see module-wide `RequestException`-only-catches note above; in practice, most external failures pass through as `200 {"data": <external error body>}`.

### `GET /courseSpecific` (named `student.courseSpecific`)
- **Controller:** `ReferralSystemController::courseSpecific`.
- **Request params (query, unvalidated):** `courseType`, `lsSaId` — both read via the `request()` helper, not the injected `Request`; missing values are interpolated into the URL as the literal string `""` (no early validation/rejection).
- **External call:** `GET {REFERRAL_BASE_URL}api/v1/plan/getCourseBasedRefferallink?courseType={courseType}&lsSaId={lsSaId}&studentId={studentId}&channelId=1` — again, `Refferal` misspelled in the external path, and note **none of the query values are URL-encoded** before string interpolation; a value containing `&` or other reserved characters will corrupt the outbound query string.
- **Success/Error:** same shape/caveats as `generalCode`.

### `GET /courseInfo` (named `student.courseInfo`)
- **Controller:** `ReferralSystemController::courseInfo`.
- **Request params (query, unvalidated):** `courseType`.
- **External call:** `GET {REFERRAL_BASE_URL}api/v1/plan/courseInfo?studentId={studentId}&channelId=1&courseType={courseType}`.
- **Success/Error:** same shape as above; this method additionally `Log::error()`s the exception message/code before returning (the other proxy methods mostly don't log on this path, except `studentEarningDetail` and `studentMailSend` below).

### `GET /studentEarningDetail` (named `student.studentEarningDetail`)
- **Controller:** `ReferralSystemController::studentEarningDetail`.
- **Request params:** none.
- **External call:** `GET {REFERRAL_BASE_URL}api/v1/referral-link/studentEarningDetails/channel/{channelId}?studentId={studentId}` (channel hardcoded `1`).
- **Success/Error:** same shape as `courseInfo`, including the `Log::error()` call on the (rarely-reached) exception path.

### `POST /mailSend` (named `student.SendMail`)
- **Controller:** `ReferralSystemController::studentMailSend`.
- **Request params (raw, no FormRequest):** `referralId` (read via `$request->input('referralId')`), `emails` (read via `$request->emails` — passed through as-is into `{"emails": <value>}`, no shape/type validation of any kind on `emails` before it's JSON-encoded and forwarded).
- **External call:** `POST {REFERRAL_BASE_URL}api/v1/referral-link/{referralId}/send/mail` with header `Content-Type: application/json`, body `{"emails": <request's emails value>}`.
- ⚠️ **`referralId` is interpolated directly into the outbound URL path with no validation, sanitization, or type check** — a path-traversal/injection-style boundary test against the external URL construction is worth including even though this is "just" a proxy, per the methodology note about external-proxy endpoints still needing input-handling scrutiny at the boundary this app controls.
- **Success:** `200 {"data": <external decoded body via ->json()>}` — note this one method uses `$response->json()` (Laravel's built-in JSON decode) rather than `json_decode($response->getBody(), true)` like the other four methods — functionally equivalent for a JSON body, but a different call site worth knowing if debugging a body-shape mismatch.
- **Error:** same `RequestException`-only-catches caveat as the rest of the module.

---

## Endpoint count and confidence

- **6 routes total**: 1 admin (`students`, no auth) + 5 student-facing (`generalCode`, `courseSpecific`, `courseInfo`, `studentEarningDetail`, `mailSend`), all enumerated above.
- **High confidence** on this app's side of every endpoint (request handling, URL construction, response wrapping, the `RequestException`-only catch-block gap) — traced directly from `ReferralSystemController` source. **Low/no confidence on the external referral-partner service's own response shapes, error bodies, or status codes** — those are opaque payloads from a separate system; a parity test needs either a staging credential/account for `REFERRAL_BASE_URL` or to mock at the `Http::` facade level, per the methodology's external-call guidance. This module is a strong candidate for `Http::fake()`-based testing given how directly it passes bodies through.

---

*Companion documents: [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md), [`../API_SPECIFICATIONS.md`](../API_SPECIFICATIONS.md) §6 ("Referral System" — original brief pass, expanded in full above; the no-auth finding on `GET students` and the unescaped `referralId` finding are both confirmed still accurate).*
