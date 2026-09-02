# EmailTemplate Module — API Documentation

The `EmailTemplate` module manages per-role (and, per its own model constants, per-admin-user or per-student, though only the role path is actually reachable — see below) email template records used elsewhere in the app for outbound mail content. It is a small, purely-local CRUD surface with no external calls. Not covered at all in `API_SPECIFICATIONS.md` — this is the first full pass. See [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for the app-wide envelope/error/pagination conventions — this file only calls out where a specific endpoint deviates.

## Module-wide notes

- **Auth:** every route in this module sits under `auth:sanctum` + `json.response`, prefix `v1` — staff/admin-only, no student-facing surface at all.
- **Response helper style:** the global `apiResponse()` helper function, consistently, across all three real endpoints.
- **`EmailTemplate` is polymorphic** (`model_type`/`model_id` via `morphTo()`) and can in principle belong to a `User` (admin), a `Student`, or a `Role` — but **only the `Role` attachment path is actually reachable from a live route** (see `GET /v1/email-templates/show` below); the `User`/`Student` model-type branches in `store()`'s validation and creation logic are live *validation* (they will accept and correctly wire up a `User`- or `Student`-owned template if you POST one), just never *read back* by any routed endpoint in this module — there is no `GET` variant that looks up a template by an arbitrary `model_type`/`model_id`, only the current admin's own role.
- **Route registration order:** the route file registers `GET /v1/email-templates/show` (a literal path segment, not a `{param}`) **before** `Route::apiResource('email-templates', 'EmailTemplateController')->only(['index', 'store', 'update'])` — this matters only in that `show` is deliberately **not** part of the apiResource set (the `only()` list excludes it), so there's no ambiguity between the literal `/show` path and a hypothetical `/{email_template}` route; both coexist safely.

---

### `GET /v1/email-templates` (apiResource `index`) — **dead route, confirmed broken**
- **Controller:** would-be `EmailTemplateController::index` — **this method does not exist anywhere in the controller** (confirmed: `EmailTemplateController` defines only `show`, `store`, and `update`; no `index`, `create`, `edit`, or `destroy` either, and the apiResource registration explicitly limits itself to `['index', 'store', 'update']`, so `index` is the one registered method with no backing implementation).
- **Behavior:** any call to `GET /api/v1/email-templates` throws a PHP `Error` ("Call to undefined method ... EmailTemplateController::index()"), surfacing as an uncaught-exception 500 via the framework's default handler — not a clean JSON error body. This is the same class of finding as `StudentBookACall.md`'s undefined-method dead routes.
- **Notes:** A parity migration should decide whether AP-V3 needs to reproduce "500 on call" for this exact path, or treat it as known-dead surface to drop. There is no working "list all email templates" endpoint anywhere in this module.

---

### `GET /v1/email-templates/show` (named `email-templates.show`)
- **Controller:** `EmailTemplateController::show`.
- **Auth:** `auth:sanctum` (module-wide).
- **Request params:** **none accepted at all** — despite the route having no `{id}`/`{email_template}` segment and no query params read anywhere in the method, this is **not** "show a specific template by id"; it resolves the template for the **calling admin's own role**: `$roleId = auth()->user()?->roles[0]->id;` then `EmailTemplateRepository::EmailTemplateOfARole($roleId)` → `EmailTemplate::where('model_type', Role::class)->where('model_id', $roleId)->first()`.
- ⚠️ **Latent bug — throws if the caller has no assigned roles.** `auth()->user()->roles` is a Spatie-style relation returning a `Collection`; `roles[0]` on an **empty** collection is `null` (ArrayAccess on a Collection returns `null` for a missing offset, no warning), and `null->id` under PHP 8's nullsafe-adjacent semantics for a plain `->` access on `null` is a **warning that evaluates to `null`**, not a fatal error at that specific line — so `$roleId` ends up `null`. That `null` is then passed to `EmailTemplateRepository::EmailTemplateOfARole(int $id)`, whose parameter is a **non-nullable `int`** with no default: passing `null` where a non-nullable scalar type is declared is a **`TypeError`** in PHP (even in Laravel's weak-typing mode, `null` is not among the values scalar type-coercion covers) — this is **not caught anywhere** in `show()`, so it propagates as an uncaught `TypeError`, rendered by Laravel's exception handler as a 500 (with the actual TypeError message shown only if `app.debug` is on). **A parity test calling this endpoint as an admin with zero assigned roles should expect a 500, not a clean "not found."**
- **Success (role resolved, template exists):** `200 apiResponse(['emailTemplate' => EmailTemplateResource::make($emailTemplate)])` → `{"data": {"emailTemplate": {...}}, "message": "Success", "status": "success"}` (default `apiResponse()` message/status).
- **Success (role resolved, no template exists for it):** `EmailTemplateOfARole()` returns `null` from `->first()`; `EmailTemplateResource::make(null)` — a `JsonResource` wrapping `null` renders as `null` (or, depending on the response macro, an empty object) rather than throwing — the endpoint still returns `200 {"data": {"emailTemplate": null}, "message": "Success", "status": "success"}`, **not a 404**. A parity test should not expect a 404 for "no template configured for this role" — it's a 200 with a null payload.
- **Notes:** `roles[0]` assumes **the first role in whatever order the relation loads in** is the "current" one for template-lookup purposes — if an admin has multiple roles, this is **not** deterministic/documented as "primary role," it's simply array-index `0` of however the ORM returns them (typically insertion/pivot order, not guaranteed stable) — worth a boundary test with a multi-role admin to see which role's template actually comes back.

---

### `POST /v1/email-templates` (apiResource `store`)
- **Controller:** `EmailTemplateController::store`.
- **Auth:** `auth:sanctum`.
- **Request params — `StoreEmailTemplateRequest`, genuinely applied:**
  - `model_type` — required, `Rule::in([EmailTemplate::MODEL_TYPE_ADMIN /* 'User' */, MODEL_TYPE_STUDENT /* 'Student' */, MODEL_TYPE_ROLE /* 'Role' */])`.
  - `model_id` — required; **conditionally validated against a different table depending on `model_type`** via three `Rule::when(...)` clauses: `exists:users,id` if `model_type === 'User'`, `exists:students,id` if `'Student'`, `exists:roles,id` if `'Role'` — note these three `Rule::when` clauses are evaluated against `$this->model_type` (the request's own value) at rule-build time, so an invalid/unexpected `model_type` value simply skips all three `exists` checks (only the `model_type` field's own `Rule::in` would catch it) — `model_id` would then only be checked for basic `required`, not existence, if `model_type` itself already failed validation.
  - `status` — required, `Rule::in([STATUS_ACTIVE=1, STATUS_PENDING=2, STATUS_DEACTIVE=0])`.
  - `type` — required, `Rule::in([TYPE_COURSE_COMPLETION='CourseCompletion', TYPE_REGISTER='Register'])` — note the request field is named `type`, stored to the model's `email_type` column (see below); only these two literal values are accepted, nothing else.
  - `mail_template` — required (no further shape/HTML validation).
- **Behavior (inside `DB::transaction`):** builds a new (unsaved) `EmailTemplate(['email_type' => $request->type, 'mail_template' => ..., 'status' => ..., 'created_by' => auth()->user()->id])`, resolves `$model` by `model_type` (via `UserRepositoryInterface`/`StudentRepositoryInterface`/`RoleRepositoryInterface::findById($request->model_id)` — note the `else` branch defaults to the **Role** repository, i.e. any `model_type` value that isn't literally `'User'` or `'Student'` falls through to being treated as a Role lookup, though `model_type`'s own `Rule::in` should already have rejected anything outside the three known values by this point), then `$model?->emailTemplate()->save($emailTemplate)` — a `MorphOne` relation `save()`, which sets `model_type`/`model_id` on the `EmailTemplate` row automatically before persisting. If `$model` is `null` (shouldn't happen given the `exists:` validation, but only reachable if the row was deleted between validation and this line — a TOCTOU gap), the `?->` silently no-ops and **the endpoint still reports success** with no `EmailTemplate` row actually created — a "2xx + success body ≠ proof of effect" case per the conventions doc's cross-cutting caution.
- **Success:** `201`? — **no, `apiResponse()` defaults to statusCode `200`, and `store()` never passes an explicit code** — `200 apiResponse([], 'Email Template created successfully')` → `{"data": [], "message": "Email Template created successfully", "status": "success"}`. ⚠️ **HTTP 200 on a create, not 201** — worth flagging since most other `store` endpoints across this codebase that use `apiResponse()` do pass `statusCode: 201` explicitly.
- **Error:** standard 422 validation shape (see conventions doc) on any rule violation; no bespoke error handling in the controller — an exception thrown inside the `DB::transaction` closure (e.g. the TOCTOU case above, if it ever actually threw) would propagate as an uncaught exception per the app's default handler, since `store()` declares `@throws Throwable` and does no local `try/catch`.

---

### `PUT/PATCH /v1/email-templates/{email_template}` (apiResource `update`)
- **Controller:** `EmailTemplateController::update`.
- **Auth:** `auth:sanctum`.
- **Request params:** `{email_template}` — standard Laravel route-model binding by primary key (`EmailTemplate $emailTemplate`); a non-existent id → the app's standard `ModelNotFoundException` 404 shape (`{"status":"error","message":"Resource Not Found","data":[]}`, see conventions doc) **before** the controller method body even runs. `UpdateEmailTemplateRequest`: `mail_template` — required, that's the **only** validated field — `model_type`/`model_id`/`status`/`type` cannot be changed via this endpoint at all (not accepted, not validated, silently ignored even if sent, since the controller only ever reads `$request->mail_template`).
- **Behavior:** `$emailTemplate->update(['mail_template' => ..., 'updated_by' => auth()->user()->id])` — a direct, unconditional update; no ownership/authorization check beyond the `auth:sanctum` guard (any authenticated admin can update **any** template regardless of which role/user/student it's attached to — no scoping to "your own role's template" the way `show()` implicitly scopes reads).
- **Success:** `200 apiResponse(['email_template' => $emailTemplate->fresh()], 'Email Template updated successfully')` → `{"data": {"email_template": {...raw model columns, NOT EmailTemplateResource-wrapped...}}, "message": "Email Template updated successfully", "status": "success"}` — ⚠️ **note this returns the raw Eloquent model** (all columns including `created_at`/`updated_at`/`created_by`/`updated_by`, no `creator`/`updater` nested objects), **not** `EmailTemplateResource::make(...)` — a different, richer/rawer shape than what `show()` returns for what is conceptually the same entity. A parity test must not assume the two endpoints' `EmailTemplate` representations are identical.
- **Error:** 404 (bad id, see above) or standard 422 (missing `mail_template`).

---

## Summary of Resource/Repository usage

| Class | Used by (live routes) | Notes |
|---|---|---|
| `EmailTemplateResource` | `GET /v1/email-templates/show` only | Excludes `created_at`/`updated_at`/`deleted_at` (the table has no `deleted_at` column at all — soft deletes aren't even configured — so excluding it is a no-op) and `created_by`/`updated_by`, replacing the latter two with nested `creator`/`updater` (`only('id','first_name','last_name')`). **Not used by `update()`**, which returns the raw model instead. |
| `EmailTemplateRepository` | `show()` only (`EmailTemplateOfARole`) | `UserRepositoryInterface`/`StudentRepositoryInterface`/`RoleRepositoryInterface` (from other modules) are used in `store()` for the polymorphic `findById()` lookup. |

## Endpoint count and confidence

- **4 route registrations**: the explicit `email-templates.show` route plus 3 of the `apiResource`'s verbs (`index`, `store`, `update` — `show`/`create`/`edit`/`destroy` were never registered via `->only([...])`). Of these 4, **1 is confirmed dead** (`index` — undefined method, 500 on call) and the remaining 3 are fully documented above, including the `show()` TypeError-on-no-roles bug.
- **High confidence** — every route's controller method, FormRequest, Resource, and repository call was read directly from source; the `roles[0]`/TypeError chain was traced through PHP's actual null-property-access and scalar-type-coercion semantics rather than assumed. Not independently confirmed here: what actually *consumes*/renders an `EmailTemplate`'s `mail_template` content elsewhere in the app (that's a different module's concern, out of scope for this file).

---

*Companion documents: [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md). Not previously covered in `../API_SPECIFICATIONS.md` — this is the first documented pass for this module.*
