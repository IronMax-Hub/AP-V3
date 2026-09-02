# StudentAuth Module API Documentation

The `StudentAuth` module is the **student-facing** authentication surface: two-step email+password login, forgot-password (email → OTP → new password), post-login OTP email verification, LMS SSO token minting, and password change/update. Distinct from the `Auth` module (admin/staff login) and from `Student`'s own `ssoValidation`/`edmingleSsoValidation` routes, which are declared in *this* module's route file (cross-module delegation — see below) but implemented in `Modules\Student\Http\Traits\StudentTrait`.

**Module-wide:** all routes are prefixed `student/v1`, carry `json.response` + `last.login` middleware. Two sub-groups: a `guest` group (no `auth:student`, for pre-login flows) and an `auth:student` group (for the OTP/logout/password-change flows that need an authenticated student). Per-route auth is called out below since it varies within the file.

See [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for the app-wide response envelope styles, standard error shapes, and pagination conventions. **Security-sensitive note:** this file documents existing authentication behavior exactly as implemented, including bugs — it is not a security audit and makes no attempt to flag/fix anything found.

---

## Encrypted-password convention (applies to every endpoint below that accepts a `password` field)

Every password-bearing field in this module (`login/password-verification`'s `password`, `forgot-password/create-password`'s `password`/`password_confirmation`, `change-password`'s `password`/`confirm_password`) is expected to arrive **pre-encrypted by the client**, decrypted server-side via `AuthController::decrypt($value, env('APP_PASS_PHRASE'))` (`Modules\Auth\Http\Controllers\AuthController`, OpenSSL `aes-256-cbc`, key derived EVP_BytesToKey-style). Sending a plaintext password fails the subsequent `Hash::check`/equality comparison silently (surfaces as "Password is incorrect." or a mismatch error, not a clean "wrong format" message) rather than being rejected outright as malformed input.

---

## Guest (unauthenticated) routes

### `POST /student/v1/login/email-verification` (route name `student.login.email.verification`, `StudentAuthController::emailVerification`)
- **Auth:** none (route is in the `guest` middleware group at the Laravel-route level, not gated by an app auth guard).
- **Request body** (`LoginAndPasswordForgetEmailVerificationRequest`): `email` required, `email` format, `exists:students,email` (custom message on `.exists`: `"Email doesn't exists."`).
- **Behavior:** looks up the student additionally requiring `status == Student::ACTIVE` — **this second condition is not covered by the FormRequest's `exists` rule**, so an email that exists but belongs to a non-`ACTIVE` student still passes validation and only fails at this explicit `if (!$student)` check in the controller.
- **Error response:** `ValidationException::withMessages(['message' => ['You are not an authorized user to do this action']])` (standard 422 shape) if the student isn't found *or* isn't `ACTIVE`.
- **Success response:** `apiResponse(['token' => $token], 'Email verified.')`. `$token` = `"{student->id}{40-char random string}{first 2 chars of full_name}"`, stored on `tmp_verification_token` with a 5-minute expiry (`tmp_verification_token_expire_at`). This is a **short-lived verification token, not a Sanctum session token** — pass it to `password-verification`, do not use as a Bearer token.
- **Side effects:** if `$student->last_login` is null (i.e. this is the student's first-ever completed login), sets `first_time_login = 1`. No activity log written on this step.

### `POST /student/v1/login/password-verification` (route name `student.login.password.verification`, `StudentAuthController::passwordVerification`)
- **Auth:** none.
- **Request body** (`LoginPasswordVerificationRequest`): `token` required string `exists:students,tmp_verification_token` (custom message: `"Token invalid."`); `password` required string; `remember_me` optional (any truthy value).
- **Behavior order (note the sequencing):** looks up the student purely by `tmp_verification_token` (the `exists` rule already confirmed *some* row has this token, but the controller re-queries independently); checks `tmp_verification_token_expire_at->lt(now())` **before** checking whether `$student` is null — if the token both doesn't exist as an active row's token *and* somehow the FormRequest passed (shouldn't happen in practice, but the code order matters for interpreting a null-`$student` edge case) this could raise a null-property error on `$student?->tmp_verification_token_expire_at->lt(...)`; in the normal case (valid-but-expired token) this returns the expired-token error below without ever reaching the password check.
- **Error response (expired token):** `apiResponse('', 'Token invalid.', 'error', 400)` — **HTTP 400, not 422** — logs a failed login activity (`addLoginActivityLog($student->id, 'login', 'failed', 'Student Login Failed dut to token expired')` — note the literal typo `dut` in the log description, preserved verbatim in the DB row, not client-visible).
- **Error response (wrong password):** `ValidationException::withMessages(['password' => ['Password is incorrect.']])` (standard 422) if `Hash::check(decrypt($password), $student->password)` fails — also logs a failed-login activity first.
- **Success response:** `apiResponse($data, 'Password verified.')` where `$data` = `{token, addressRequired: 'Y'|'N', lms: 'Y'|'N', enrollmentDataRequired: 'Y'|'N', profileImage, userInfo: {id, name, email, phone}, meeting_accessible}`. `token` is a genuine Sanctum plaintext token (`$student->createToken($student->full_name)->plainTextToken`). `addressRequired` is `'Y'` if any of `country`/`country_id`/`phone`/`address`/`city`/`pin_code` is empty, **or** `state` is empty while `country` is (case-insensitively) `'india'` — a student outside India with no `state` is not flagged. `profileImage` falls back to a hardcoded UAT S3 URL if `$student->image` is empty.
- **Side effects:** the newly-created Sanctum token's `expires_at` is always explicitly overwritten — `remember_me` truthy → `now()+30 days` pinned to `23:59`; otherwise → **today's date pinned to `23:59`**, i.e. a same-day-only session unless `remember_me` is sent. Successful-login activity log (`addLoginActivityLog($student->id, 'success', ...)`).

### `POST /student/v1/forgot-password/email-verification` (route name `student.forget-password.email.verification`, `PasswordResetController::emailVerification`)
- **Auth:** none.
- **Request body:** same `LoginAndPasswordForgetEmailVerificationRequest` as login step 1 (`email` required, `exists:students,email`).
- **⚠️ No `status == ACTIVE` check here** (unlike the sibling `StudentAuthController::emailVerification` above) — a pending/disabled student **can** request a password-reset OTP. Also, unlike the login version, **this controller does not guard against `$student` being null before dereferencing `$student->id`** — since the FormRequest's `exists:students,email` rule already guarantees a matching row exists by the time the controller runs, `$student` cannot actually be null in practice through this route, but note the missing defensive check (the login-step-1 sibling has an explicit `if (!$student)` even though its own FormRequest carries the identical `exists` rule — the two are inconsistent in defensiveness despite validating the same thing).
- **Success response:** `apiResponse(['token' => $token], 'OTP sent to your email inbox.')` — same token-generation scheme as login step 1 (id + 40 random chars + first 2 of name, 5-minute expiry).
- **Side effects:** queues `StudentForgetPasswordOTPMail` (contains a separate `verification_otp` value on the student record — not the `tmp_verification_token` itself; the email presumably renders `$student->verification_otp`, which must already be set/generated elsewhere, as this controller does not set it here — verify the `Student` model/observer for where `verification_otp` is populated if writing a parity test against email content).

### `POST /student/v1/forgot-password/otp-verification` (route name `student.forget-password.otp.verification`, `PasswordResetController::otpVerification`)
- **Auth:** none.
- **Request body** (`PasswordForgetOTPVerificationRequest`): `token` required string `exists:students,tmp_verification_token`; `otp` required string.
- **Error responses:** both hand-rolled `apiResponse('', ..., 'error', 422)` — `data` is an **empty string**, not `[]`/`null`: `'Token invalid.'` if student not found by token **or** `tmp_verification_token_expire_at` has passed; `'Invalid otp.'` if `$student->verification_otp != $request->input('otp')` (loose `!=` comparison, not strict).
- **Success response:** `apiResponse(['token' => $newToken], 'OTP verified.')` — issues a **brand-new** token (same generation scheme, fresh 5-minute expiry), overwriting the step-1 token; the step-1 token is dead after this call, callers must use the token from *this* response for step 3.
- **Side effects:** if `email_verified_at` was previously null, sets it to `now()` as a side effect of this call (not documented in the response) — so a forgot-password flow can silently mark a never-verified email as verified.

### `POST /student/v1/forgot-password/create-password` (route name `student.forget-password.create-password`, `PasswordResetController::createPassword`)
- **Auth:** none.
- **Request body** (`CreateNewPasswordRequest`): `token` required string `exists:students,tmp_verification_token`; `password` required, `Rules\Password::defaults()` (min 8 chars per Laravel default), **pre-encrypted** (see convention note above); `password_confirmation` required, same rule, also pre-encrypted — **Laravel's built-in `confirmed` rule is NOT used**, so the FormRequest cannot detect a mismatch on its own; the confirmation check happens manually in the controller **after decryption**.
- **Error response (bad/expired token):** `apiResponse('', 'Token invalid.', 'error', 422)` — `data` is an empty string.
- **Error response (mismatch after decryption):** hand-rolled `response()->json([...], 422)` matching the *shape* of the standard validation-error envelope (`{"status":"error","message":"Form Validation failed","data":{"errors":{"password":["The password confirmation doesn't match"]}}}`) but **not actually thrown as a `ValidationException`** — an independently constructed literal array that happens to look the same.
- **⚠️ Mismatch detection quirk:** because comparison happens on the **decrypted plaintext**, two different ciphertexts that happen to decrypt to the same plaintext are treated as matching (correct), but the inverse edge case — malformed ciphertext that decrypts to garbage matching another garbage string — is unlikely but not impossible; more practically, any client bug in the encryption step that produces non-matching ciphertext for identical plaintexts would incorrectly reject valid input. Treat this as "compares decrypted values only," not "compares what the client actually sent."
- **Success response:** `apiResponse([], 'Password created successfully')`.
- **Side effects:** `Hash::make($decryptedPassword)` written to `students.password`; queues `StudentPasswordChange` mail. **Not confirmed whether existing Sanctum tokens for this student are revoked** — no `$student->tokens()->delete()` call is present in this method, so prior sessions likely remain valid after a password reset; verify this is the intended behavior before assuming logout-on-reset.

---

## Cross-module route delegation: `Student` module's SSO endpoints, declared here

These two routes live in `Modules/StudentAuth/Routes/api.php`'s `guest` group but their controller is `Modules\Student\Http\Controllers\StudentController`, whose real method bodies are pulled in via `use StudentTrait;` (`Modules/Student/Http/Traits/StudentTrait.php`) — documented here because this route file declares them, per the cross-module-delegation convention.

### `POST /student/v1/sso-validation` (route name `students.login-from-admin.sso-validation`, trait `ssoValidation`)
- **Auth:** none.
- **Request body:** inline `$request->validate(['token' => 'required|string'])` — no FormRequest class.
- **Purpose:** the consuming end of the admin-side "login as student" impersonation flow (`GET /v1/students/login-from-admin/{student}` in the `Student` module, which mints a 5-minute `tmp_verification_token`) — this route exchanges that token for a real student Sanctum session.
- **Error response:** `response()->json(['status'=>'error','message'=>'SSO Failed'], 401)` if no student matches the token, or the token has no expiry set, or it's expired — **hand-rolled shape, no `data` key at all**, deviates from every other error shape in this file.
- **Success response:** `response()->json(['status'=>'success','message'=>'SSO verified','data'=>{token, addressRequired, lms, enrollmentDataRequired, profileImage, userInfo:{name,email,phone}, meeting_accessible}])` — note `userInfo` here **omits `id`** (present in the regular login flow's `userInfo`) — a genuine shape difference between this SSO path and `password-verification`'s otherwise-near-identical payload.
- **Side effects:** mints a fresh Sanctum token via `$student->createToken(...)` — **the token's `expires_at` is not explicitly overridden here** (unlike `password-verification`, which always pins `expires_at` to end-of-day or +30 days) — so this SSO-issued token uses whatever Sanctum's default expiry configuration is, a different lifetime policy from the normal login path.

### `POST /student/v1/edmingle/sso-validation` (route name `students.login-from-edmingle.sso-validation`, trait `edmingleSsoValidation`)
- **Auth:** none.
- **Request body:** inline `$request->validate(['token' => 'required|string'])`.
- **Behavior:** decodes `token` as a JWT (`Firebase\JWT\JWT::decode`, `RS256`, public key from `env('JWT_TOKEN_PUBLIC_KEY')`) — this is a **different token format entirely** from the app's own `tmp_verification_token` scheme used everywhere else in this file (a real signed JWT from the Edmingle LMS side, not an opaque random string). Validates presence of `email`/`iss`/`exp`/`iat` claims, that `exp` hasn't passed, and that `iss` matches `env('JWT_TOKEN_EDMINGLE_ISSUER')` exactly.
- **Error response:** `apiResponse('', 'Invalid Token', 'error', 401)` for **every** failure mode (bad JWT signature/decode exception, missing claims, expired, wrong issuer, or no matching `Student` by email) — all collapse to the identical message/status, so a client cannot distinguish "malformed JWT" from "expired" from "unknown email" from this response alone.
- **Success response:** `response()->json(['status'=>'success','data'=>{token, addressRequired, lms, enrollmentDataRequired, profileImage, meeting_accessible, userInfo:{name,email,phone}}])` — **no top-level `message` key at all** (the `success`/error paths across this one method are inconsistent: error uses `apiResponse()`, success uses raw `response()->json()` with a different key set — `addressRequired` here is computed differently too: simply `is_null($student->address) ? 'Y' : 'N'`, not the multi-field check used by every other login-family endpoint in this module).
- **Side effects:** updates `last_login = now()` on the student; mints a new Sanctum token (again, no explicit `expires_at` override, same as the plain SSO route above).

---

## Authenticated (`auth:student`) routes

### `GET /student/v1/lms` (route name `student.lms`, `StudentAuthController::lms`)
- **Auth:** `auth:student`.
- **Success response:** hand-rolled `response()->json(['token' => <JWT>])` — **no `apiResponse()` envelope, no `status`/`message` keys**. The JWT (`Firebase\JWT\JWT::encode`, `HS256`, secret `env('LMS_SECRET')`) carries claims `iss: 'LMS Law Sikho'`, `iat`, `exp` (`iat + 36000` seconds = **10 hours**, despite the inline comment claiming "Plus 2 minutes"), `first_name` (= `full_name`), `last_name` (always empty string), `email`.
- **Notes:** this mints an outbound JWT for the student to present to the LMS side — the inverse direction of `edmingleSsoValidation` above (which *consumes* an inbound Edmingle JWT). The stale code comment ("2 minutes") vs. actual 10-hour expiry is a documentation-in-code bug worth flagging, though it doesn't affect runtime behavior.

### `POST /student/v1/student/send-otp` (route name `student.send-otp`, `sendOtp`)
- **Auth:** `auth:student`.
- **Error response:** `ValidationException::withMessages(['message' => ['You are not an authorized user to do this action']])` if `auth()->user()` is somehow null (defensive; shouldn't occur given the `auth:student` middleware already ran).
- **Success response:** `apiResponse([], 'Verification code sent successfully')`.
- **Side effects:** generates `$otp = rand(1000, 9999)` (4-digit, **not cryptographically random** — `rand()`, not `random_int()`); sets `otp`/`otp_expire_at` (+10 minutes) on the student; synchronously (`Mail::to(...)->send(...)`, not `->queue(...)`) sends `OtpMail` — this blocks the request on mail delivery, unlike most other mail sends in this codebase which are queued.

### `POST /student/v1/student/verify-otp` (route name `student.verify-otp`, `verifyOtp`)
- **Auth:** `auth:student`.
- **Request params:** reads `request('otp')` directly (global helper, not `$request->input()` via an injected `Request` — the method signature takes no parameters at all) — no FormRequest, no explicit validation of presence/format.
- **Error response (no user):** `apiResponse([], '...', 'error', 500)` — **HTTP 500 used for what is semantically a 401/403** (defensive branch, same as `sendOtp`).
- **Error response (wrong OTP):** `apiResponse([], 'Invalid verification code. Please enter the correct code sent to your registered email address.', 'error', 500)` — **also HTTP 500**, not 422/400, for plain wrong-input from a normal user. Uses loose `!=` comparison (`$student->otp != request('otp')`) — note this branch is checked **before** the expiry check, so a wrong OTP always reports "invalid code" even if it's *also* expired.
- **Error response (expired, but otherwise correct-looking OTP already ruled out above):** `ValidationException::withMessages(['message' => ['OTP expired']])` (standard 422) if `otp_expire_at < now()`.
- **Success response:** `apiResponse([], 'Verification code verified successfully', 'success', 200)` if `$student->otp == request('otp')` (loose comparison again). Sets `otp`/`otp_expire_at` to null, `email_verified_at = now()`, `first_time_login = 0`.
- **Unreachable fallback:** a final `apiResponse([], 'Something went wrong...', 'error', 500)` exists after the success branch — logically unreachable given the preceding `!=`/expiry checks already exhaust the possibilities, but present in source.

### `POST /student/v1/student/resend-otp` (route name `student.resend-otp`, `resendOtp`)
- **Auth:** `auth:student`.
- **Behavior/response:** byte-for-byte identical implementation to `sendOtp` above (same error branch, same `rand(1000,9999)`, same synchronous `Mail::send`, same success message `'Verification code sent successfully'`) — genuinely duplicated code, not a distinguishable "resend" behavior (e.g. no rate-limit or previous-OTP invalidation logic beyond what a fresh `sendOtp` call would also do).

### `GET /student/v1/student/is-email-verified` (route name `student.is-email-verified`, `checkifEmailVerified`)
- **Auth:** `auth:student`.
- **Error response:** `ValidationException::withMessages(['message' => ['You are not an authorized user to do this action']])` if no authenticated user (defensive, shouldn't occur).
- **Success response:** **returns a bare PHP integer, `0` or `1`** — `0` if `email_verified_at` is null **and** `first_time_login == 1`; `1` otherwise (including the case where `email_verified_at` is null but `first_time_login != 1` — i.e. a student who has logged in before but never verified their email still reads as `1`/"verified" from this endpoint, a likely logic gap). **No JSON envelope of any kind** — Laravel will serialize a bare int return as the literal response body `0` or `1` (with `Content-Type: application/json`), not `{"data":...}` — a client parsing this as an object will fail.

### `POST /student/v1/student/logout` (route name `student.logout`, `destroy`)
- **Auth:** `auth:student`.
- **Success response:** `apiResponse([], 'User logged out successfully')`.
- **Side effects:** `auth()->user()->tokens()->delete()` — deletes **all** Sanctum tokens for the student (logout-everywhere, not single-session revocation).

### `POST /student/v1/student/update-password` (route name `student.update-password`, `NewPasswordController::update_password`, throttled `throttle:6,1`)
- **Auth:** `auth:student` + `throttle:6,1` (6 requests/minute).
- **Request params:** **no FormRequest, no `validate()` call at all** — raw `json_decode(file_get_contents('php://input'), true)`; only key read is `password`. A missing `password` key causes an undefined-array-key warning/notice on `Hash::make($input['password'])` in PHP 8 (surfaces as `null` being hashed, i.e. a valid-looking hash of an empty value gets stored — **no validation error is raised for a missing password field**, it silently "succeeds" with a hash of nothing).
- **Success response:** hand-rolled array (auto-JSON-encoded), **not via `apiResponse()`**: `{"status": 1, "data": {"user_name": <email>, "password": <the plaintext password the caller sent, echoed back>}, "message": "'Password Updated successfully'"}` — **note the literal embedded single-quotes inside the message string itself** (`"'Password Updated successfully'"`, quotes-within-quotes, preserve verbatim), and note the response **echoes the new plaintext password back to the caller** in `data.password`.
- **Side effects:** updates the student's `password` (hashed) via `StudentRepository::update()`; synchronously (`Mail::to(...)->send(...)`) sends `StudentChangePasswordMail`.
- **Notes:** a large block of alternate, more defensive logic (checking `current_password`, comparing against the existing hash, distinct messages for "same as before"/"current password doesn't match") exists **commented out** below the live `return` statement — none of it executes; the live behavior has no old-password verification of any kind, meaning any authenticated student can set a new password without proving knowledge of the current one via this specific endpoint.

### `POST /student/v1/change-password` (route name `student.change-password`, `NewPasswordController::change_password`, throttled `throttle:6,1`)
- **Auth:** `auth:student` + `throttle:6,1`.
- **Request params:** takes `ChangePasswordRequest` as a type-hint (`password` required, `confirm_password` required — presence-only, no format/length/complexity rule) — **but the method body never reads from the validated `$request` object**; it independently re-decodes `json_decode(file_get_contents('php://input'), true)` for the actual field access (`$input['password']`, `$input['confirm_password']`). Both fields must be **pre-encrypted** (same `AuthController::decrypt()` convention as the login flow) — the FormRequest's presence-only rules do run first (so a genuinely missing key still 422s via the FormRequest), but no format constraint (e.g. `Password::defaults()`) is enforced on the decrypted plaintext here, unlike `createPassword` in the forgot-password flow.
- **Error response (decrypted mismatch):** `response([...], 422)` — **uses the bare `response()` helper, not `response()->json()`** (relies on Laravel's content negotiation to serialize as JSON, which it will for an API request, but it's a different call than every other hand-rolled response in this module) — body: `{"status": "error", "message": "Password change unsuccessful! Please try again"}` — **no `data` key**.
- **Success response:** `{"status": "success", "message": "'Password Updated successfully'"}` — **plain array, not `apiResponse()`**, again with the same literal embedded-single-quotes message text as `update_password` above, and again **no `data` key** here (unlike `update_password`'s version, which does include one).
- **Side effects:** updates `password` (hashed) via `StudentRepository::update()`; synchronously sends `StudentChangePasswordMail`. A commented-out `$this->triggerEventForPasswordChange(...)` call exists but does not run.

---

## Summary

**Routes documented:** all 13 routes in `Modules/StudentAuth/Routes/api.php` (11 implemented in this module's own controllers, 2 cross-delegated to `Modules\Student\Http\Traits\StudentTrait` via `Modules\Student\Http\Controllers\StudentController`).

**Notable bugs/discrepancies found:**
- `PasswordResetController::emailVerification` (forgot-password step 1) has no `status == ACTIVE` guard, unlike `StudentAuthController::emailVerification` (login step 1) — a disabled/pending student can still request a password-reset OTP even though they can't log in normally.
- `verifyOtp`/`sendOtp`/`resendOtp` use HTTP 500 for ordinary client-input error conditions (wrong OTP, no auth user) rather than 4xx.
- `checkifEmailVerified` returns a bare, un-enveloped integer (`0`/`1`), not JSON object — the one endpoint in this module (besides `lms`) with no `status`/`data` structure at all.
- `resendOtp` is byte-for-byte duplicate code of `sendOtp` — there is no actual "resend" semantics (no invalidation of a prior OTP, no rate distinction).
- `update_password` has zero validation on its raw `php://input` payload and **echoes the new plaintext password back in the response body** (`data.password`).
- `change_password` type-hints `ChangePasswordRequest` for presence-only validation but then ignores the validated request object entirely, re-parsing `php://input` for actual field access — the FormRequest's presence checks still run (so missing keys still 422 first), but no password-strength rule applies to this endpoint's plaintext (unlike `createPassword`'s `Password::defaults()`).
- Both `update_password` and `change_password` success messages contain literal embedded single-quotes: `"'Password Updated successfully'"` — verbatim, not a documentation typo.
- `sso-validation` and `edmingle/sso-validation` (Student module, declared in this route file) do not pin the newly-minted Sanctum token's `expires_at` the way the normal `password-verification` login path does — a different, unpinned session-lifetime policy for SSO-issued tokens.
- `edmingle/sso-validation`'s success response omits a top-level `message` key and computes `addressRequired` with different logic (single-field null check) than every other login-family endpoint (multi-field + India/state check) — a genuine response-shape and business-logic divergence worth a dedicated parity test.
- `sso-validation`'s `userInfo` omits `id` (present in `password-verification`'s `userInfo`).

**Confidence:** High — every endpoint read directly from `StudentAuthController.php`, `PasswordResetController.php`, `NewPasswordController.php`, all 5 FormRequest classes, and the two cross-delegated `StudentTrait` methods (`ssoValidation`, `edmingleSsoValidation`), including their commented-out dead code blocks.
