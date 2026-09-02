# Common API Conventions

> Shared behavior referenced by every file in `documentation/api_doc_by_module/`. Read this once; per-module files only call out where a specific endpoint **deviates** from what's documented here — they don't repeat it.
>
> Traced from `app/Http/Controllers/Controller.php`, `app/Helpers/functions.php`, `app/Exceptions/Handler.php`. Source of this section: `documentation/API_SPECIFICATIONS.md` §1 (kept in sync — if that section changes, update both).

## Response helper styles in use

This codebase does **not** use one consistent response style. Four distinct styles appear across modules — every per-module file names which style each endpoint actually uses:

1. **Global `apiResponse($data, $message = 'Success', $status = 'success', $statusCode = 200)`** helper function (`app/Helpers/functions.php:17`) → `{"data": ..., "message": "...", "status": "success"}`.
2. **`$this->apiResponse(...)`** — identical shape, called as a base-`Controller` instance method (`app/Http/Controllers/Controller.php:22`) instead of the global function. Same output, different call site — some modules use this exclusively.
3. **Hand-rolled `response()->json([...])`** — bypasses both helpers above. Common enough that you must never assume a `data` key is present, or that `status` is a string, without checking the specific endpoint. Seen with `data: null` vs `""` vs `[]` vs omitted; `status` as string `"success"` vs integer `1` vs integer `200`.
4. **Ad-hoc external pass-through envelope** — thin proxy modules (e.g. `ReferralSystem`) return `{"data": <raw external payload>}` on success and forward the downstream service's own error shape/status code directly, with no normalization to this app's conventions at all.

A second envelope, `studentApiResponse($data, $error = null, $status = 1)` → `{"status": 1|0, "data": ..., "error": ...}` (`app/Helpers/functions.php:33`), exists but is confirmed used only inside the deprecated (not-in-use) `Forum` module — **do not expect this shape from any documented endpoint.**

## Standard error shapes (`app/Exceptions/Handler.php::render()`)

- **422 validation failure** (`ValidationException`): `{"status": "error", "message": "<comma-joined first errors>", "data": {"errors": {"field": ["message", ...], ...}}}`. The per-field `errors` object is nested under `data.errors`, not top-level.
- **404 route not found** (`NotFoundHttpException`): `{"status": "error", "message": "Url Not Found!", "data": []}`.
- **404 model not found** (`ModelNotFoundException`, e.g. a route-model-binding miss): `{"status": "error", "message": "Resource Not Found", "data": []}`.
- **Other HTTP exceptions** (manually-thrown 403/409/etc.): `{"status": "error", "message": "<exception message>", "data": []}` at that status code.
- **401 unauthenticated — guard-dependent shape, a real inconsistency:** if the `student` guard failed, response is `{"status": 0, "message": "User is Unauthenticated"}` (**no `data` key**, `status` is the integer `0`). For every other guard (`sanctum`/`web`), it's `{"data": [], "status": "error", "message": "User is Unauthenticated"}`. A parity test must branch on which guard it's testing when asserting 401 body shape.

Many controllers implement their own error handling that doesn't match any of the above — always check the specific endpoint's module file.

## Pagination

No single consistent wrapper. Two families exist:

- **Resource-collection endpoints** (most `search`/reference-lookup endpoints): `{"data": [...], "meta": {"total": N}}` — no `message`/`status` key at all.
- **Cursor-paginated `index()` endpoints** (most catalog/admin listing endpoints): query params `rows` (page size, default 15) and `cursor` (opaque base64 token from a prior response's `meta`, not a page number); response `{"data": [...], "meta": {"total": N, "range": {"from": N, "to": N, "total": N}}}`. A malformed/tampered `cursor` triggers `abort(500, 'Cursor value tempered')` — a 500, not a 4xx, on bad client input.

## Structural gotchas to expect per module (see individual files for specifics)

- **Logic in traits, not controllers:** several controllers are near-empty and pull all real method bodies in via `use SomeTrait;` — the per-module file documents the endpoint regardless of which file the code physically lives in.
- **Dead `apiResource` scaffolding:** `create`/`show`/`edit` actions that return a Blade `view()` call, or `store`/`update`/`destroy` with an empty body, are non-functional boilerplate left over from `php artisan module:make-controller`, not real JSON endpoints. Flagged explicitly where present rather than given a fabricated shape.
- **Orphaned FormRequest/Resource classes:** a class can exist and be imported without actually being wired to the route that "should" use it (e.g. a `Store*Request` imported but the method signature still type-hints the generic `Request`). Only classes confirmed actually invoked are documented as the live contract.
- **Cross-module route delegation:** a module's own `Routes/api.php` can point at a controller belonging to a *different* module's namespace. Documented under the file for the module whose route file declares it, with a note of the controller's real location.
- **External-proxy endpoints:** response shape and error codes are dictated by a remote service (Edmingle, the referral system, the book-a-call sub-project, etc.), not by this app — called out as an "External call" rather than an ordinary "Side effect."

## Cross-cutting QA caution

Several endpoints throughout this API return a 2xx status with a "success"-looking body (`status: 1`, `status: "success"`) even on a semantic no-op or failure path. **Never treat "2xx + success-shaped body" as sufficient proof an action succeeded** — check the accompanying `error`/`message` field, and where the action has real consequence, verify via a follow-up read rather than trusting the write response alone. Specific instances are flagged inline in the relevant module file.

---

*Companion documents: [`../DEVELOPER_DOCUMENTATION.md`](../DEVELOPER_DOCUMENTATION.md) (tech stack, module inventory, auth internals, DB schema), [`../USER_WORKFLOWS.md`](../USER_WORKFLOWS.md) (traced end-to-end workflows), [`../API_SPECIFICATIONS.md`](../API_SPECIFICATIONS.md) (original domain-grouped pass — superseded in depth by the per-module files here, kept as historical/cross-reference). See [`README.md`](./README.md) for the full module index and deprecated-module exclusion list.*
