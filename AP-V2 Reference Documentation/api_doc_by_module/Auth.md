# Auth Module API Documentation

The `Auth` module is the **admin/staff-facing** authentication surface: registration, encrypted-password login/logout, forgot/reset password (Laravel's built-in password-broker flow), authenticated password change, and Laravel email-verification scaffolding. Distinct from `StudentAuth` (the student-facing two-step login/OTP/forgot-password flow, which does **not** reuse Laravel's password-broker).

**Module-wide:** all routes prefixed `/v1`, carry `json.response`. Two sub-groups: a `guest` group (register/login/forgot-password/reset-password) and an `auth:sanctum` group (logout/email-verification-notification/verify-email/update-password). Per-route auth called out below.

See [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for the app-wide response envelope styles, standard error shapes, and pagination conventions. This module's endpoints mix the `$this->apiResponse()` instance-method style with hand-rolled `response()->json()` — noted per endpoint. **Security-sensitive note:** this documents existing behavior exactly as implemented, including bugs, for parity-testing purposes — not a security audit, no fixes suggested.

## Shared encrypted-password convention

Every password field accepted by this module (`login`'s `password`, `reset-password`'s `password`/`password_confirmation`, `update-password`'s `current_password`/`password`/`password_confirmation`) is expected **pre-encrypted by the client** via the same OpenSSL `aes-256-cbc` / EVP_BytesToKey scheme documented in `StudentAuth.md` — here implemented as a **private copy of the identical `decrypt()`/`evpKDF()` method pair**, duplicated verbatim in both `AuthController` and `NewPasswordController` (not shared via a trait/base class) rather than a single canonical implementation.

---

## Guest routes

### `POST /v1/register` (`RegisteredUserController::store`)
- **Auth:** none (`guest` middleware).
- **Request params:** no FormRequest — inline `$request->validate([...])`: `name` required string max:255; `email` required string email max:255 `unique:users`; `password` required, `confirmed` (Laravel's built-in confirmation rule — expects a `password_confirmation` field, **plaintext**, not the encrypted-password convention used everywhere else in this module), `Rules\Password::defaults()`.
- **Success response:** `$this->apiResponse(['email','name' => $user->full_name,'token' => $user->createToken($user->name)->plainTextToken], 'User registered successfully')`.
- **Side effects:** creates a `User` row (`full_name`, `email`, `Hash::make($password)` — note: `password` here is taken as **plaintext** straight from the request, since this endpoint uses Laravel's native `confirmed` rule rather than the encrypted-password convention — a genuinely different contract from `login`/`reset-password`/`update-password` in the same module); dispatches `event(new Registered($user))` (triggers Laravel's default email-verification-notification listener, if configured).
- **Notes:** per `documentation/API_SPECIFICATIONS.md`, this route "exists but wasn't confirmed live/used" by the team — verify with the team whether admin self-registration is actually reachable/intended in production before building extensive parity coverage around it. `$user->createToken($user->name)` — note this passes `$user->name`, but `User` model's registration fields set `full_name`, not `name`; if the `User` model has no `name` accessor/attribute, this likely evaluates to `null` as the token name (cosmetic only — doesn't affect the token string itself).

### `POST /v1/login` (`AuthController::store`)
- **Auth:** none (`guest` middleware).
- **⚠️ Route binds the generic `Illuminate\Http\Request`, not the `LoginRequest` FormRequest** that exists in this same module (`Modules/Auth/Http/Requests/LoginRequest.php`) — confirmed by the method signature (`store(Request $request)`). `LoginRequest` is **dead/unused code** for this route: its `rules()` (`email`/`password`/`remember_me` presence+format), its `authenticate()` (via `Auth::attempt`), and — notably — its **rate-limiting** (`ensureIsNotRateLimited()`, 5 attempts per `email|ip` key, `Lockout` event) never execute. A missing `email`/`password` field does not produce a clean 422 here; it falls through to the manual lookup/decrypt logic below.
- **Request params (as actually validated — none, purely ad-hoc controller logic):** `email` (used in a raw `where('email', ...)` lookup, no format check); `password` (expected pre-encrypted, see shared convention above); `remember_me` (passed straight to `createToken(..., rememberMe: $request->remember_me)` — no boolean coercion, whatever truthy/falsy value is sent).
- **Behavior order:** loads `User::with('roles')->select(id,email,status,edmingle_id,first_name,last_name,title,password,last_login,meeting_id)->where('email', $request->email)->first()`; if not found → error; if `status == User::USER_DISABLED` → error (checked **before** password verification, so a disabled account gets a distinct message even with a correct password); only then decrypts + `Hash::check`s the password.
- **Error responses (both standard 422 `ValidationException::withMessages(['email' => [...]])`):** `"The provided credentials are incorrect."` (no such user, or wrong password); `"Your account is not active."` (status disabled).
- **Success response:** `$this->apiResponse($data, 'User logged in successfully')` where `$data` = `{id, email, title, first_name, last_name, role: <first role name only, via getRoleNames()->first()>, is_registered_in_scheduling_app: 0|1 (from meeting_id), token}`.
- **Side effects:** dispatches `LogUserActivity` job (queued); if `edmingle_id` is null, dispatches `SyncUserWithLMS` job (queued); `User::where('id',...)->update(['last_login'=>now()])` — uses a query-builder update specifically to **bypass Eloquent model events/observers** (per the inline comment). Token created via `createToken($user->first_name, rememberMe: $request->remember_me)` — **no explicit `expires_at` override** here (unlike the student login flow, which always pins expiry to end-of-day or +30 days) — this admin token's lifetime is whatever Sanctum's `rememberMe` parameter/default config produces; verify empirically rather than assuming a same-day expiry like the student flow.
- **Notes:** `lmsCurl()` — a private helper using raw `curl_init()` against hardcoded Edmingle tutor-login/search URLs — exists on this controller but is **never called from any routed method** shown here; dead code, not exercised by `store`/`destroy`.

### `POST /v1/forgot-password` (`PasswordResetLinkController::store`, route name `password.email`)
- **Auth:** none (`guest`).
- **Request params:** inline validate — `email` required, email format (no `exists:users,email` check — an unknown email is handled by the password-broker itself, not rejected at validation time).
- **Behavior:** `Illuminate\Support\Facades\Password::sendResetLink(['email' => ...])` — Laravel's standard password-broker (uses the framework's default `password_resets` table + notification, not a custom OTP scheme like `StudentAuth`).
- **Success response:** `$this->apiResponse([], 'We have emailed your password reset link!')` — only returned if the broker's status constant is exactly `Password::RESET_LINK_SENT`.
- **Error response:** any other broker status (e.g. `Password::INVALID_USER` for an unknown email, `Password::RESET_THROTTLED`) → `ValidationException::withMessages(['email' => [__($status)]])` (standard 422, message text is whatever Laravel's default `passwords.*` translation line resolves to for that status, e.g. `"We can't find a user with that email address."`) — **this means an unknown email is distinguishable from a known one via the response** (unlike some other modules' deliberately-vague "email doesn't exist" handling), a potential email-enumeration consideration for parity/security testing even though this task is documentation-only.

### `POST /v1/reset-password` (`NewPasswordController::store`, route name `password.update`)
- **Auth:** none (`guest`).
- **Request params:** inline validate — `token` required; `email` required email format; `password` required, `Rules\Password::defaults()`. **`password_confirmation` is read (`$request->password_confirmation`) but never included in the `validate()` call at all** — a request omitting it entirely still passes validation; `decrypt(null-ish value)` on a missing field will behave per the `decrypt()` method's own guards (returns `false` if the base64-decoded value doesn't start with `'Salted__'` — an empty/missing string almost certainly hits this branch and returns `false`).
- **Behavior:** decrypts both `password` and `password_confirmation` (via the module's own private `decrypt()`/`evpKDF()` — same algorithm as `AuthController`'s copy, independently duplicated) and compares them **before** invoking the password broker.
- **Error response (decrypted mismatch, including the "confirmation omitted" edge case where one side decrypts to `false` and the other to a real password):** hand-rolled `response()->json([...], 422)` — shape mimics the standard validation-error envelope (`{"status":"error","message":"Form Validation failed","data":{"errors":{"password":["The password confirmation doesn't match"]}}}`) but is **not** an actual `ValidationException` — a manually constructed literal matching that shape.
- **Behavior (broker call):** `Password::reset($request->only('password','password_confirmation','token','email'), function($user) use ($password) { $user->forceFill(['password'=>Hash::make($password), 'remember_token'=>Str::random(60)])->save(); event(new PasswordReset($user)); })` — **note the callback hashes the already-decrypted `$password` variable, not `$request->password`** (the raw encrypted ciphertext is never itself passed to the broker's password-setting logic — only used for the broker's own internal `confirmed`-style validation via `$request->only(...)`, which will actually compare **encrypted ciphertext strings** to each other for Laravel's own internal password-confirmation check inside `Password::reset`, not the decrypted plaintext — a separate, redundant confirmation comparison from the manual one above operating on different values entirely).
- **Success response:** `$this->apiResponse([], 'Your password has been reset!')` only if `$status == Password::PASSWORD_RESET`.
- **Error response (broker failure, e.g. bad/expired token):** `ValidationException::withMessages(['email' => [__($status)]])` (standard 422).

---

## Authenticated (`auth:sanctum`) routes

### `POST /v1/logout` (`AuthController::destroy`, route name `logout`)
- **Auth:** `auth:sanctum`.
- **Success response:** `$this->apiResponse([], 'User logged out successfully')`.
- **Side effects:** writes an activity log entry (`event: 'log out'` string via the fluent `activity()->causedBy($std)->performedOn($std)->log('log out')` call) — **oddly, `causedBy`/`performedOn` are both given a freshly-`new User()` instance** (an empty, unsaved model with no `id`), then a `->tap()` callback overwrites `$activity->causer_id` to the real `auth()->user()->id` after the fact — the `subject_id`/`subject_type` (from `performedOn`) are left pointing at the meaningless blank `User` model (likely `subject_id = null`), a genuine activity-log data-quality quirk worth flagging for anyone reading logout audit logs; `auth()->user()->tokens()->delete()` — deletes **all** Sanctum tokens (logout-everywhere, not single-session).

### `POST /v1/email/verification-notification` (`EmailVerificationNotificationController::store`, route name `verification.send`, throttled `throttle:6,1`)
- **Auth:** `auth:sanctum` + `throttle:6,1`.
- **Success response (already verified):** `$this->apiResponse([], 'Email already verified.')`.
- **Success response (notification sent):** `$this->apiResponse([], 'verification-link-sent')` — note the message is the literal Laravel translation-key-style string `'verification-link-sent'`, not a human-readable sentence (this is Laravel's stock scaffolding string, left as-is rather than replaced with prose).
- **Side effects:** `$request->user()->sendEmailVerificationNotification()` — standard Laravel `MustVerifyEmail` notification (email content/link format is framework-default unless the `User` model customizes it).
- **⚠️ Commented out in the route file:** this route and the next (`verify-email/{id}/{hash}`) are present in `Modules/Auth/Routes/api.php` as **live, uncommented routes** inside the `auth:sanctum` group — despite `documentation/API_SPECIFICATIONS.md`'s admin-login section showing them commented out in the *StudentAuth* module's equivalent block; **in the `Auth` module specifically, these two routes are active**, not dead — verify which module's copy a given piece of prior documentation was referring to before assuming either is unreachable.

### `GET /v1/verify-email/{id}/{hash}` (`VerifyEmailController::__invoke`, route name `verification.verify`, `signed` + `throttle:6,1`)
- **Auth:** `auth:sanctum` **and** Laravel's `signed` middleware (URL must carry a valid signature over `id`/`hash`/expiry — an unsigned or tampered URL is rejected by the `signed` middleware itself before the controller runs, producing Laravel's standard 403 "Invalid signature" response, not a JSON `apiResponse()` shape).
- **Request params:** framework `EmailVerificationRequest` (validates `hash` matches `sha1($user->getEmailForVerification())`).
- **Response type: this endpoint does NOT return JSON at all** — it returns an HTTP redirect (`redirect()->intended(config('app.frontend_url') . RouteServiceProvider::HOME . '?verified=1')`) in both the "already verified" and "newly verified" branches. **A pure-JSON API test harness expecting a `data`/`status` body here will need to instead assert on the 302 response's `Location` header** pointing at the configured frontend URL with a `?verified=1` query string.
- **Side effects:** if not already verified, `$request->user()->markEmailAsVerified()` + `event(new Verified($request->user()))`.

### `POST /v1/update-password` (`NewPasswordController::update_password`, route name `update-password`, throttled `throttle:6,1`)
- **Auth:** `auth:sanctum` + `throttle:6,1`.
- **Request params:** inline validate — `current_password` required string max:255; `password` required, `Rules\Password::defaults()`. **`password_confirmation` is again read but never included in the `validate()` call** — same omission pattern as `reset-password` above; all three (`current_password`, `password`, `password_confirmation`) are expected pre-encrypted per the shared convention.
- **Error response (new-password confirmation mismatch after decryption):** hand-rolled `response()->json([...], 422)` — identical shape to `reset-password`'s mismatch error (`"The password confirmation doesn't match"`).
- **Error response (current password wrong):** `apiResponse(data: {message: "Current Password Doesn't match"}, message: "Current Password Doesn't match", status: 'error', statusCode: 422)` — via the **global** `apiResponse()` helper function (not `$this->apiResponse()`), one of the few places in this module that uses the global function rather than the instance method; note the literal apostrophe in `"Current Password Doesn't match"` (escaped as `\'` in source — renders as a normal apostrophe in the actual JSON string).
- **Error response (new password same as current):** same global-`apiResponse()` pattern, `message: 'Password Same as Before'`, also 422.
- **Success response:** `$this->apiResponse(data: {message: 'Password Updated successfully'}, message: 'Password Updated successfully')` — default 200, uses `$this->apiResponse()` (instance method) here, in contrast to the two error branches immediately above it in the same method which use the global function — a genuinely inconsistent helper-style choice **within a single method**.
- **Side effects (only on the success path):** `User::where('id', ...)->update(['password' => Hash::make($new_password)])` (query-builder update, bypasses model events, same pattern as the login flow's `last_login` update); synchronously (`Mail::to(...)->send(...)`, not queued) sends `ChangePasswordMail` to the user.
- **Notes:** this is the **admin-side** equivalent of `StudentAuth`'s `change-password`/`update-password` pair, but with a materially different (and more defensive) implementation — it genuinely verifies `current_password` via `Hash::check` before allowing a change (unlike `StudentAuth::update_password`, which has no old-password check at all, and unlike `StudentAuth::change_password`, whose old-password-check logic exists only as commented-out dead code). Do not assume symmetric behavior between the two modules' same-named endpoints.

---

## Summary

**Routes documented:** all 8 routes in `Modules/Auth/Routes/api.php`.

**Notable bugs/discrepancies found:**
- `POST /v1/login` binds the generic `Request`, leaving the module's own `LoginRequest` FormRequest — including its 5-attempts-per-`email|ip` rate limiter — completely dead/unused. Confirms and matches the existing finding in `documentation/API_SPECIFICATIONS.md`.
- `decrypt()`/`evpKDF()` are duplicated verbatim across `AuthController` and `NewPasswordController` (and, per `StudentAuth.md`, a third near-identical copy exists there too) rather than shared via a trait — a maintenance/consistency risk if the algorithm ever needs to change, not currently a functional bug.
- `reset-password` and `update-password` both read `$request->password_confirmation` without including it in their `validate()` call — a client that omits the field entirely still passes validation, relying entirely on the subsequent manual-decrypt-and-compare branch to catch the absence.
- `reset-password`'s manual plaintext-mismatch check and Laravel's own internal `Password::reset()` confirmation check operate on **different value pairs** (decrypted plaintext vs. raw encrypted ciphertext) — two redundant but non-equivalent confirmation checks stacked on the same request.
- `AuthController::destroy`'s logout activity log is attributed to a blank, unsaved `new User()` instance for `causedBy`/`performedOn`, with only `causer_id` patched after the fact via `->tap()` — `subject_id`/`subject_type` on that log row do not point at the real actor.
- `update_password` mixes the global `apiResponse()` helper (both error branches) and `$this->apiResponse()` instance method (success branch) within the same method body — direct confirmation of the "check every endpoint independently" guidance in `_COMMON_CONVENTIONS.md`, down to inconsistency *within* a single method.
- `GET /v1/verify-email/{id}/{hash}` returns an HTTP redirect, not JSON — the one non-JSON response in this entire module.
- `AuthController::lmsCurl()` is dead code — a private helper with no caller among the routed methods.
- Contrary to a note elsewhere describing `email/verification-notification`/`verify-email` routes as commented-out, in **this** module's route file both are live and reachable — that commented-out status applies to a different module's file, not this one.

**Confidence:** High — every endpoint read directly from `AuthController.php`, `RegisteredUserController.php`, `PasswordResetLinkController.php`, `NewPasswordController.php`, `EmailVerificationNotificationController.php`, `VerifyEmailController.php`, and `LoginRequest.php`.
