# Webhook Module — API Documentation

The `Webhook` module owns two unrelated things that happen to share one module folder: (1) admin CRUD screens for configuring outbound webhook subscriptions (`webhooks`/`webhook_events` tables) and (2) a small ingest endpoint (`failed-api-responses`) that logs *this app's own* outbound-integration failures to a file-based log channel. Despite what `API_SPECIFICATIONS.md` §6 previously concluded, the `webhooks`/`webhook_events` tables **are** read by live code — see the correction below. This module has no inbound-webhook *receiver* endpoint at all (nothing here verifies an external caller's signature) — it is the *sender* side of outbound webhooks plus their admin config screens.

See [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for the app-wide envelope/error/pagination conventions — this file only calls out where a specific endpoint deviates from those.

## Correction to `API_SPECIFICATIONS.md` §6

That document states (Webhook Module section): *"confirmed via grep that no code anywhere reads or dispatches against `webhooks`/`webhook_events` — testing here validates CRUD mechanics only, not any real integration."* **This is no longer accurate — verified against current source:**

- `Modules\Webhook\Http\Traits\WebhookTrait::processWebhook()` queries `WebhookEvent::where('event_name', $event)` and `Webhook::where('event_id', $eventId)->where('status', Webhook::ACTIVE)->get()`, then dispatches `SendWebhookJob` (queued) per matching active webhook — a real `Http::post()` to that webhook's stored `webhook_url`, with an `X-Webhook-Secret` header set from the webhook row's own `webhook_secret`, logging every attempt to `WebhookLog` and retrying up to 5 times (10-minute delay) on failure.
- This trait is invoked by `Modules\Webhook\Listeners\HandleWebhook`, registered against `Modules\Webhook\Events\WebhookTriggered` in `app/Providers/EventServiceProvider.php`.
- `event(new WebhookTriggered(...))` is fired from **at least a dozen other modules' live code paths** (confirmed via grep): `Enrollment` (course/package/bootcamp enrollment, batch migration), `Result`, `StudentProfile`, `StudentMyCourses`, `StudentPerformanceCoach`, `CourseCompletionMaster`, `Notification`, `LawSikho`, `Student`, `StudentAssignment` (including the async `AssignAssignmentsByFiltersJob`), and three `StudentFrontendEnrollment` controllers (NPS, EvaluatorCSAT, AssignmentCSAT).
- **Practical implication for parity testing:** creating a `Webhook` row (via `POST /v1/webhooks`) pointed at an event name that's actually fired elsewhere in the app (e.g. `Course.Enrollment.AP`) is a genuine, live integration test, not dead scaffolding — a test harness can seed a `webhook_events` row + an active `webhooks` row and assert an HTTP call actually lands. The `webhooks`/`webhook_events` **admin CRUD routes themselves** (documented below) are still low-value to test in depth (no validation, near-stub controllers) — the *effect* of the data they create is what's real.

## Module-wide notes

- **Three route groups, no shared middleware pattern:**
  1. `GET /webhook` (unprefixed) — `auth:api` middleware. **Broken at the framework level**: `config/auth.php`'s `guards` array defines only `web`, `sanctum`, and `student` — there is **no `api` guard configured anywhere in this app**. Any request to this route throws `InvalidArgumentException: Auth guard [api] is not defined.` before the controller closure ever runs — a 500, not a clean auth failure. This route is unreachable as anything other than an error.
  2. `auth:sanctum` + `json.response`, prefix `v1` — the `webhooks`/`webhook-events` `apiResource` CRUD plus the `test-route` endpoint.
  3. `json.response` only (no auth) — `POST /v1/failed-api-responses`, the one endpoint here with real validation and purpose.
- **No FormRequest actually validates `webhooks`/`webhook-events` writes**, despite both `StoreWebhookRequest` classes existing in the codebase (see per-endpoint notes) — every apiResource `store`/`update` in this module reads a plain `Illuminate\Http\Request` and mass-assigns `$request->all()` with zero validation.
- **Dead `apiResource` scaffolding:** `create`/`show`/`edit` on both `WebhookController` and `EventController` return bare Blade `view()` calls (`webhook::create`/`show`/`edit`) — non-functional stubs, not real JSON endpoints. `update`/`destroy` on both controllers have **empty bodies** — calling them succeeds silently (200, no body) without touching the database at all.

---

## `GET /webhook` (unprefixed, named route none)
- **Controller:** inline closure in `Modules/Webhook/Routes/api.php`, guarded by `auth:api`.
- **Auth:** `auth:api` — **broken**, see module-wide notes. Every call 500s with an `InvalidArgumentException` before reaching the closure.
- **Notes:** Effectively dead/unreachable as working code. A parity migration should decide whether to reproduce "500 on any call" or drop this path entirely.

---

## `apiResource('webhooks', WebhookController)` — `auth:sanctum`, `json.response`, prefix `v1`

### `GET /v1/webhooks` — `WebhookController::index`
- **Non-functional stub.** Returns `view('webhook::index')` — a Blade view, not JSON. Calling this through an API client (expecting JSON) gets back rendered/attempted HTML, not a `{"data":...}` shape. Do not fabricate a JSON contract for this endpoint.

### `GET /v1/webhooks/create` — `WebhookController::create`
- **Non-functional stub** — `view('webhook::create')`, same caveat as `index`.

### `POST /v1/webhooks` — `WebhookController::store`
- **Auth:** `auth:sanctum` (module-wide) — note the controller itself calls `auth()->user()->id` directly with no null-check; if this were ever reachable without a resolved user it would throw, but the route guard makes that practically unreachable.
- **Request params: no FormRequest actually applied.** The method signature type-hints the generic `Illuminate\Http\Request`, not either of the two `StoreWebhookRequest` classes imported at the top of the file (`App\Http\Requests\StoreWebhookRequest as RequestsStoreWebhookRequest` and `Modules\Webhook\Http\Requests\StoreWebhookRequest`) — **both imports are unused; neither is type-hinted on `store()`, so neither's `rules()` ever runs.** Per the "only document what's actually wired" rule, the `webhook_event_id`/`url`/`status`/`secret` validation rules defined on `Modules\Webhook\Http\Requests\StoreWebhookRequest` (required/exists/url/boolean/min:32) are **dead code, not the live contract.** In practice: `Webhook::create(array_merge($request->all(), ['created_by' => auth()->user()->id]))` — any fields sent are mass-assigned against the model's `$fillable` (`webhook_url`, `webhook_name`, `webhook_secret`, `event_id`, `status`, `failure_count`, `app_name`, `created_by`, `updated_by`); anything outside `$fillable` is silently dropped by Eloquent, not rejected.
- **Success response — malformed shape:** `response()->json(['message' => 'Webhook created successfully', 'webhook' => $webhook, 201])` — ⚠️ the literal integer `201` is passed as a **third array element inside the JSON body** (keyed `0` since it's the first unkeyed value in that array), **not** as the HTTP status code argument to `response()->json()`. The actual HTTP status is the Laravel default **200**, not 201. A test asserting `status_code == 201` will fail; a test inspecting the body will see a stray `"0": 201` key.
- **Side effects:** creates a raw `Webhook` row. No event fires, no job dispatches, from this endpoint itself (the eventual outbound delivery only happens later, when some *other* module fires `WebhookTriggered` for this webhook's configured `event_id`).

### `GET /v1/webhooks/{webhook}` — `WebhookController::show`
- **Non-functional stub** — `view('webhook::show')`, ignores the injected `$id`.

### `GET /v1/webhooks/{webhook}/edit` — `WebhookController::edit`
- **Non-functional stub** — `view('webhook::edit')`.

### `PUT/PATCH /v1/webhooks/{webhook}` — `WebhookController::update`
- **Empty body.** Returns Laravel's default (`null`/empty 200) — accepts the request, does nothing, no error.

### `DELETE /v1/webhooks/{webhook}` — `WebhookController::destroy`
- **Empty body.** Same as `update` — silently no-ops.

---

## `apiResource('webhook-events', EventController)` — `auth:sanctum`, `json.response`, prefix `v1`

### `GET /v1/webhook-events` — `EventController::index`
- **The one real read endpoint in this CRUD pair.** `WebhookEvent::select('id', 'event_name')->get()`.
- **Response helper style:** hand-rolled `response()->json([...])`, not `apiResponse()`.
- **Success:** `200 {"events": [{"id":..., "event_name":...}, ...], "status": 200}` — ⚠️ note the key is `events`, not `data`, and `status` is the **integer `200`** duplicated as a body field (redundant with the actual HTTP status, and inconsistent with the string `"success"`/`"error"` convention used almost everywhere else in this app).

### `GET /v1/webhook-events/create` — `EventController::create`
- **Non-functional stub** — `view('webhook::create')`.

### `POST /v1/webhook-events` — `EventController::store`
- **No FormRequest — raw `$request->all()`** mass-assigned via `WebhookEvent::create()`. Note `WebhookEvent`'s `$fillable` is an **empty array** (`protected $fillable = [];`) — Eloquent mass-assignment with an empty `$fillable` allowlist means **every field is silently rejected**; `WebhookEvent::create($request->all())` will create a row with **only the model's default/auto columns populated** (`id`, timestamps), and `event_name` (or any other submitted field) will **not** be persisted, regardless of what's sent. This is a real, verifiable bug: the endpoint reports success but the submitted data is dropped.
- **Success:** `200 {"message": "Event created successfully", "status": 200, "event": <the freshly-created row>}` — the returned `event` object will confirm the bug above (its `event_name` etc. will be `null`/absent, not the submitted value).

### `GET /v1/webhook-events/{webhook_event}` — `EventController::show`
- **Non-functional stub** — `view('webhook::show')`.

### `GET /v1/webhook-events/{webhook_event}/edit` — `EventController::edit`
- **Non-functional stub** — `view('webhook::edit')`.

### `PUT/PATCH /v1/webhook-events/{webhook_event}` — `EventController::update`
- **Empty body** — silent no-op, same as `WebhookController::update`.

### `DELETE /v1/webhook-events/{webhook_event}` — `EventController::destroy`
- **Empty body** — silent no-op.

---

## `POST /v1/test-route` (named `test`) — `auth:sanctum`, `json.response`
- **Controller:** `WebhookController::test`.
- **Request params:** none read/used.
- **Success:** `200 {"message": "this is test webhook route "}` (trailing space in the literal string, preserved verbatim) — a smoke-test endpoint with no side effects.

---

## `POST /v1/failed-api-responses` (named `failed-api-responses.store`) — `json.response` only, no auth

- **Controller:** `FailedApiResponseController::store`.
- **Purpose:** a sink for *this application's own* outbound third-party-integration failures to self-report into a dedicated log channel — not something an external caller would normally hit; there is no consumer of this endpoint visible in the codebase's own outbound-call sites (i.e. nothing in this repo currently calls it), so its caller is presumably an external tool or a manual/ops trigger.
- **Request params — `StoreFailedApiResponseRequest`, genuinely applied:** `source` (string, required, max:255), `url` (string, required, max:2048), `method` (string, nullable, max:10), `status_code` (integer, nullable), `request_payload` (nullable, any type), `response_body` (nullable, any type), `headers` (array, nullable), `error_message` (string, nullable), `occurred_at` (date, nullable). Validation failures produce the app's standard 422 shape (see conventions doc).
- **Side effects:** `LogFailedApiResponseJob::dispatch($request->validated())` (queued) — writes a structured error-level entry to `Log::channel('api_failed_responses')` with the validated fields (`occurred_at` defaults to `now()` if not sent, inside the job, not at enqueue time).
- **Success:** `202 apiResponse([], 'Failed API response queued for logging', 'success', 202)` → `{"data": [], "message": "Failed API response queued for logging", "status": "success"}` — the one endpoint in this module using the app-wide `apiResponse()` helper, and the only one to correctly return `202` for a queued/async action.
- **Notes:** No auth on this endpoint at all — anyone can queue an arbitrary log entry into `api_failed_responses`; a log-flooding/log-injection boundary test is a reasonable candidate given the free-form `error_message`/`request_payload`/`response_body` fields.

---

## Endpoint count and confidence

- **7 distinct route registrations** map to real controller actions worth documenting individually (`GET /webhook`, the 5 `webhooks`/`webhook-events` apiResource actions that do something beyond a Blade stub — `store`×2, `index` on events only, `update`/`destroy` no-ops counted once each — plus `test-route` and `failed-api-responses`); counting every `apiResource` HTTP verb literally, the two `Route::apiResource()` calls register **14** routes (7 each for `webhooks` and `webhook-events`), all enumerated above, plus 2 standalone routes (`test-route`, `failed-api-responses`) and the broken top-level `/webhook` — **17 total route registrations**.
- **High confidence** on all shapes/control-flow — every controller and trait was read directly from source. The one thing not independently re-verified here (out of scope for this file) is the *content* of `WebhookTrait::processWebhook()`'s payload transform for every possible caller — see the `LawSikho`/`Enrollment` module docs for callers' exact payload shapes if a parity test needs the full outbound-delivery contract, not just this module's own routes.

---

*Companion documents: [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md), [`../API_SPECIFICATIONS.md`](../API_SPECIFICATIONS.md) §6 (superseded above re: `webhooks`/`webhook_events` being live — see correction section at top of this file).*
