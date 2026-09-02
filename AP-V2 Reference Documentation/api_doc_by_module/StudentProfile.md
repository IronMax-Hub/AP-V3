# StudentProfile Module API Documentation

The `StudentProfile` module is the **student's own self-service profile surface**: viewing personal info, filling in address/enrollment details, uploading CV/ID-proof/profile image, and looking up country/state reference data scoped to the logged-in student. It is distinct from `Student` (the admin-facing CRUD/search/activation module) — the two modules manage the same `Student` entity from opposite sides of the auth boundary.

**Module-wide auth:** every route in `Modules/StudentProfile/Routes/api.php` is `auth:student` + `json.response` + `last.login`, mounted under `/api/student/v1/...`. No route in this file deviates from this. `last.login` (`App\Http\Middleware\StudentActivity`) has a real side effect worth knowing up front: **on every single request to this module** (success or not, as long as the `student` guard authenticates), it runs `DB::table('students')->where('id', $user->id)->update(['last_login' => now()])` — unless the request carries a header `admin: true`. A parity/load test hitting these endpoints repeatedly will keep bumping `last_login` as a side effect of merely calling them.

See [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for the app-wide response envelope styles, standard error shapes, and pagination conventions referenced below instead of being repeated per endpoint.

## ⚠️ Response-helper style: this module cannot use `$this->apiResponse()`

`StudentProfileController` (`Modules/StudentProfile/Http/Controllers/StudentProfileController.php`) extends the bare `Illuminate\Routing\Controller`, **not** `App\Http\Controllers\Controller` — so the `apiResponse()` instance method that most other modules rely on is simply not available here. Every endpoint in this module therefore uses one of three other styles, and it varies **method by method** with no consistent rule:
1. The **global** `apiResponse()` helper function (used only in `savePersonalInformation`'s Edmingle-failure branch).
2. Hand-rolled `response()->json([...])`.
3. **A plain PHP array returned directly from the trait method** — Laravel auto-converts an array return value into a `200 response()->json()`. Several endpoints below use this; it means there is no way for these specific methods to return any HTTP status other than 200 no matter what happened internally (errors are only distinguishable via a `status`/`error` field in the body).

Nearly all controller logic lives in `StudentProfileTrait` (`Modules/StudentProfile/Http/Traits/StudentProfileTrait.php`), pulled into the controller via `use StudentProfileTrait;`. The controller class itself defines only `index()`. The trait itself pulls in `Modules\Student\Http\Traits\StudentTrait` (`use StudentTrait;`) purely to reuse its `updateRevenueProfile()` helper — none of `StudentTrait`'s routed methods are reachable from this module.

## ⚠️ Duplicate route registration: `POST address`

```php
// First group
Route::post('address', [StudentProfileController::class, 'addressSave'])->name('student_profile.addressSave');
// Second group (separate Route::middleware(...)->group(...) call, identical middleware stack)
Route::post('address', [StudentProfileController::class, 'addressSave'])->name('student_profile.addressSave');
```
The exact same method+path+name is registered **twice**, in two separate route groups in the same file. Laravel's router matches the **first** registered route for a given method+URI, so the second registration is dead/unreachable — but both exist in the route list (contributing to the "~19 raw route-grep hits" count for this file: there are 19 `Route::` calls, but only 18 distinct reachable endpoints). Not a bug with observable behavioral consequence (both point to the identical controller action), but worth knowing so a route-count-based parity check isn't thrown off by it.

---

## Profile reads

### `GET /student-profile` (route name `student_profile.index`, **controller** `index`)
- **Success response:** `StudentProfileResource::collection($this->studentProfileRepo->getStudentData())` — resource-collection shape, `{"data":[...]}` (no `meta`/pagination observed — `getStudentData()` is expected to scope to the authenticated student, so this returns at most one row's worth of data as a collection, not a real paginated list).
- `StudentProfileResource`: raw-merged `id`,`email`,`phone`,`address`,`pin_code`,`city`,`state`,`country`,`gender`,`reg_code`, plus `enrollment` — computed by calling back into `app(StudentProfileController::class)->getQuestionAnswer(...)`, i.e. the Resource resolves a controller instance out of the container mid-serialization rather than taking a plain value; each entry is `{question, answer}`.

### `GET getProfile` (route name `student_profile.getProfile`, trait `getProfile`)
- **Success response:** a **plain returned array** (not `response()->json()`, not `apiResponse()`): `{"status": 1, "data": [{"fullname","reg_code","status","student_email","student_mobile"}, ...], "error": null}` if `getProfile()` (repository) returns any rows, or `{"status": 1, "data": [], "error": "Profile Not Found"}` otherwise — **`status` is `1` in both the found and not-found cases**; only the `error`/`data` fields distinguish them, and both paths return HTTP 200. This is a genuinely different shape from the `GET /student-profile` endpoint above (different keys entirely, `student_email`/`student_mobile` here vs. `email`/`phone` there) despite the very similar names — do not conflate them.

### `GET getEnrollFormData` (route name `student_profile.getEnrollFormData`, trait `getEnrollFormData`)
- **Success response:** hand-rolled `response()->json(['status' => 1, 'data' => ['details' => [...], 'responseCode' => 1], 'error' => null])`. `details` is built only if the student has at least one `EnrollmentQuestionAnswer` row (`$details` is otherwise **undefined**, guarded here only by the `?? []` at the response-building call site) — combines raw enrollment Q&A with a synthesized "know about Lawsikho" answer, plus a nested, differently-shaped `$generate_student` sub-object (birthday/city/country/etc., mostly duplicating `Student` columns) as `$details[0]`.

### `GET /profile/personal-info` (route name `student_profile.personal_info`, trait `personal_info`)
- **Success response:** hand-rolled `response()->json(['status' => 'success', 'data' => {...}])` — **no `message` key at all**. `data` includes duplicate/aliased keys for the same underlying column: `linkedin_link` **and** `linked_in_link` (both present, both reading `$student->linked_in_link` — always in sync since they're the same source, but a client must pick one canonical key rather than assume they could diverge), `cv` **and** `cv_title` (both reading `cv_title`). Contains the literal misspelled field **`is_message_send_aggreed`** ("aggreed") — this is the actual column/field name in this codebase, not a typo introduced by this documentation; preserve it exactly. Also decodes `terms_and_conditions_details_json` and flattens its `ip_address`/`browser`/`os`/`device`/`checked_timestamp` sub-fields to the top level of `data` *in addition to* returning the raw `terms_and_conditions_details_json` string itself — the same information appears twice, in two shapes.

### `GET profile/enrollment-form-details` (route name `student_profile.enrollment_form_details`, trait `enrollmentFormDetails`)
- **Success response:** a **plain returned array** — `{"status": "success", "data": [...]}` if the student has any question/answer rows, else `{"data": [], "error": "No Data Found", "status": "error"}` — note the differing key order and the fact that **`status` is the string `"error"`, not the integer `1`/`0` seen elsewhere in this module**, and this is still returned at HTTP 200 (plain-array return, so no status code control is possible here regardless). Each `data` entry: `{questionId, question, answer, is_other}`, with a synthesized "know about Lawsikho" entry (`questionId: 0`) prepended if applicable — note this synthesized entry omits the `is_other` key entirely (only present on the real question entries), so `data` is not a uniform shape across all its own items.

### `GET getOriginalRegistrationDetails` (route name `student_profile.getOriginalRegistrationDetails`, trait `getStudentOriginalRegistrationDetails`)
- Reads a frozen JSON snapshot (`StudentOriginalRegistrationDetails.original_registration_details_json`) captured the first time the student ever called `addressSave` (see below) and updated on every subsequent `addressSave` call.
- **Error response:** hand-rolled `response()->json(['status' => 'error', 'data' => null, 'error' => 'Student original registration details not found'])` if no snapshot row exists yet (e.g. the student has never called `addressSave`) — **HTTP 200**, no explicit status code set.
- **Success response:** hand-rolled `response()->json(['status' => 'success', 'data' => {...20 fields...}])` — reconstructs the flattened `terms_and_conditions_details_json` sub-fields the same way `personal_info` does, plus `country_code` looked up fresh from the `Country` table by the snapshot's stored `country_id` (not itself frozen in the snapshot).

---

## Reference/lookup data (student-scoped duplicates of the app-wide Country/State lookups)

As `API_SPECIFICATIONS.md` notes, `filter/country`/`filter/state` here are a *separate, `auth:student`-guarded* pair hitting the same underlying `Country`/`State` tables as the `auth:sanctum` admin-side lookup endpoints — not the same routes, just the same data.

### `GET getAllCountry` (trait `getAllCountry`) vs. `GET filter/country` (trait `getCountries`)
Both return **all** countries as a flat array of `common_name` strings (no pagination, no id) — but with different envelopes:
- `getAllCountry`: plain returned array `{"data": [...names...], "error": null, "status": 1}` (integer status).
- `getCountries`: plain returned array `{"status": "success", "data": [...names...]}` (string status, and — on the empty-table branch, unreachable in practice since `Country::all()` is always at least an empty (truthy) `Collection` object, never falsy — `{"data": null, "error": "No Countries Found", "status": "error"}`). **Because `Country::all()` returns a `Collection` object, which is always truthy even when empty, the `if ($countries)` check in both these methods can never actually take the "not found" branch** — the error shape exists in source but is unreachable dead code.

### `GET getAllState` (trait `getAllState`) vs. `GET filter/state` (trait `getStates`)
Identical pattern to the country pair above, one field renamed (`name` instead of `common_name`), same `status: 1` vs. `status: "success"` inconsistency, same unreachable "not found" branch for the same reason (`State::all()` is always truthy).

### `GET filter/country_code` (route name `student_profile.get_country_code`, trait `getCountryCode`)
- **Success response:** plain returned array `{"status": "success", "data": [{"id","common_name","phone_code"}, ...]}` — unlike the two pairs above, this one returns full objects (id + phone code), not just name strings. Same unreachable-truthy-collection caveat applies to its own `if ($countries)` check.

### `GET getIfAddress` (route name `student_profile.getIfAddress`, trait `getIfAddress`)
- **Success response:** plain returned array. If the student's `address`/`pin_code`/`country`/`city`/`state` are **all** null: `{"data": true, "error": null, "status": 1}`. Otherwise: `{"data": null, "error": "Address filled up", "status": 1}` — **`status` is `1` in both cases**; the semantically-inverted naming (`data: true` means "address is NOT filled", `data: null` + an "Address filled up" message means "it IS filled") is easy to misread — a caller must check `data`, not just look for a truthy/success-shaped response.

### `GET getUserForEnrollApi` (route name `student_profile.getUserForEnrollApi`, trait `getUserForEnrollApi`)
- **Success response:** plain returned array. `{"status": 1, "data": {"fullname","id","student_mobile","student_username"}, "error": null}` if the repository's `getProfile()` returns rows (only the **last** iterated row's data survives — the loop overwrites `$details` each pass rather than accumulating), else `{"status": 1, "data": [], "error": "Profile Not Found"}`.

---

## Address & personal-information writes

### `POST address` (route name `student_profile.addressSave`, trait `addressSave`) — the FormRequest-validated, documented path
- **Request body** (`AddressRequest`): `name` required; `phone` required + country-aware phone format (via `_phoneIso` derived from `country_id`); `address`/`city`/`country`/`pincode` required (untyped — any non-empty value); `country_id` required `exists:countries,id`; `is_message_send_aggreed`/`is_terms_and_condition_checked` required, `in:0,1`; `cv` optional file, `pdf,doc,docx`, max 5120KB; `linkedin_link` optional URL max:255.
- **Success response:** **a plain returned array**, `{"message": "Registration form submited successfully", "status": "success"}` — note the literal typo **"submited"** (one `t`) is in the actual source string, preserve exactly; **no `data` key at all**, and this is not routed through `apiResponse()`/`response()->json()` — just a raw array, auto-JSON'd by Laravel to HTTP 200.
- **Side effects, in order:** optional CV upload to S3 (`uploads/students/profile/cv/{filename}`); if `student->lms_id` is set, a **synchronous** Edmingle contact-info-update HTTP call (`updateLms()` — failures are caught and only sent to Sentry if configured, otherwise silently swallowed, **the request still succeeds** even if this call fails, unlike `Student::updateEmail`'s equivalent Edmingle call which can 422 the whole request on failure); an activity log entry ("Student profile updated" / "Student information edited by student himself."); the `Student` row itself updated (`full_name`,`address`,`country`,`phone`,`country_id`,`city`,`state`,`pin_code`,`is_terms_and_condition_checked`,`is_message_send_aggreed`,`linked_in_link`,`cv_title`,`terms_and_conditions_details_json`); and a `StudentOriginalRegistrationDetails` snapshot row is created (first call) or merge-updated (subsequent calls) — **this snapshot table write is a side effect not mentioned in the previously-existing spec for this endpoint**, confirmed by reading `updateStudentOriginalRegistrationDetails()` directly.
- **⚠️ Dead code, no mail actually sent on address change:** `StudentProfileTrait::checkIFAddressChangedMail()` — a fully-implemented method that would email `dipanjan@lawsikho.in`/`sudeep@ipleaders.in`/`bipul@lawsikho.in` a diff of changed address fields — is **never called from anywhere** (confirmed by grep: its definition is the only occurrence of its name in the file). Do not expect this notification email to be sent by this endpoint despite the method existing in the same trait.
- **`getMetaData()`** (device/browser/OS/IP capture from the User-Agent header, stored into `terms_and_conditions_details_json`) is a hand-rolled regex parser, not the `Jenssegers\Agent` library that's imported at the top of the trait file but never actually used (an earlier, commented-out `Agent`-based implementation of the same method sits directly above the live one in source) — treat User-Agent parsing here as approximate/best-effort string matching, not a real device-detection library.

### `POST saveAddress` (route name `stduent_profile.saveAddress` — note the typo in the route *name* itself, "stduent") — the separate, untraced action, now resolved
This is confirmed to be a **genuinely different, much thinner action** than `addressSave` above, not a typo/alias for it:
- **Request body:** raw `Request`, **no FormRequest, no validation of any kind** — `address`, `country`, `city`, `state`, `zipcode` are read directly off the request with no format/required checks.
- **Behavior:** writes only `address`, `country`, `city`, `state` (`null` if falsy), and `pin_code` (from `zipcode`) onto the `Student` row. **Does not touch `phone`, `full_name`, `country_id`, `linked_in_link`, `cv_title`, or any terms-and-conditions field** — a much narrower write than `addressSave`. No activity log, no Edmingle call, no `StudentOriginalRegistrationDetails` snapshot, no S3 upload.
- **Success response:** plain returned array, `{"data": true, "error": null, "status": 1}`.
- **Notes:** since this endpoint accepts completely unvalidated input, a caller could send no fields at all (writing nulls/empty over existing address data) with no error raised.

### `PATCH personal-information` (route name `savePersonalInformation`, trait `savePersonalInformation`)
- **Request body** (`PersonalInformationRequest`): `name` required max:200; `phone` required + country-aware phone format; `address`/`city`/`country` required (untyped); `pincode` required; `status` optional string; `profileImage` optional, `png,jpg,jpeg`, max 10240KB; `cv` optional, `pdf,doc,docx`, max 10240KB; `id_proof` optional, `png,jpg,jpeg`, max 10240KB; `country_id` required `exists:countries,id`; `linkedin_link` optional URL max:255; `gender` optional string.
- **Success response (now confirmed — not previously traced in the existing spec):** hand-rolled `response()->json(['message' => 'Profile updated successfully', 'status' => 'success'])` — **no `data` key**, default HTTP 200. If `auth('student')->user()` is somehow null despite the `auth:student` guard passing, an earlier guard clause instead returns `response()->json(['message' => 'Profile not updated', 'status' => 'error'])` — also HTTP 200, no explicit status code.
- **⚠️ Confirmed field-name bug — `linkedin_link` is validated but never actually saved:** the FormRequest validates a field named **`linkedin_link`**, but the code that persists it reads a **different** key: `'linked_in_link' => $request->linked_in_link ?? null`. Since `PersonalInformationRequest` never declares a `linked_in_link` rule, `$request->linked_in_link` resolves via the underlying `Request`'s raw input bag — it will only be non-null if the caller happens to *also* send an entirely separate, unvalidated `linked_in_link` key in the same payload. **A client that sends only the documented/validated `linkedin_link` field will have it silently discarded and `student->linked_in_link` set to `null`** on every call to this endpoint. This is a genuine, reproducible bug — preserve it exactly; do not "fix" the field name when asserting expected behavior. (Note this bug is specific to `savePersonalInformation` — the sibling `addressSave` action correctly reads `$request->linkedin_link` matching its own `AddressRequest` rule.)
- **Side effects:** up to 3 S3 uploads (`profileImage`→`image`, `cv`→`cv_title`, `id_proof`→`id_image`), each independently optional; a **synchronous** Edmingle contact-info update if `lms_id` is set — **on failure here, the request is aborted with `apiResponse([], '...We are facing problem to update in Edmingle: ...', 'error', 422)`** (using the **global** `apiResponse()` function, the one place in this whole module that uses it) — contrast with `addressSave`'s equivalent Edmingle call, which swallows failures and still succeeds; three independent "remove" flags (`isCvRemoved`, `isIdProofRemoved`, `isProfileImageRemoved` — none declared in the FormRequest's rules, read raw and unvalidated) each null out the corresponding column, but **only if no replacement file was uploaded in the same request** (`&& !$request->hasFile(...)`); an activity log entry; and a call to `StudentTrait::updateRevenueProfile($student, $request, 1)` — the truthy 3rd argument routes it down the branch that sends `registered_user_email: ''` (always blank) to the revenue gateway, unlike the email-update flow elsewhere that sends the real email.

### `POST profile/cv/email` (route name `student_profile.emailCv`, trait `emailCv`)
- **Error response:** `response()->json(['status' => 'error', 'message' => 'No CV found on your profile'], 422)` if `cv_title` is empty; `response()->json(['status' => 'error', 'message' => 'Failed to fetch your CV, please try again later'], 500)` if the synchronous `Http::get($student->cv_title)` fetch fails; `response()->json(['status' => 'error', 'message' => 'An internal error occurred'], 500)` on any other exception.
- **Success response:** `response()->json(['status' => 'success', 'message' => 'Your CV has been emailed to your registered email address'])` — no `data` key.
- **Side effects:** synchronously re-downloads the student's own CV from its stored (S3) URL, base64-encodes the body in memory, and queues a `StudentCvMail` with the file as an attachment — **the file is fetched fresh on every call**, not cached/reused, so a large CV means a real synchronous download inside the request before the queued mail is dispatched.

### `POST profile/id-proof/email` (route name `student_profile.emailIdProof`, trait `emailIdProof`)
Identical pattern to `emailCv` above, operating on `id_image`/`StudentIdProofMail` instead of `cv_title`/`StudentCvMail`; same three error shapes (422 "No ID proof found on your profile", 500 fetch-failure, 500 generic).

---

## Summary

**Routes documented:** 19 `Route::` declarations in `Modules/StudentProfile/Routes/api.php`, resolving to **18 distinct reachable endpoints** (the duplicate `POST address` registration collapses to one reachable action, `addressSave`).

**Structural surprises:**
- `StudentProfileController` extends the bare `Illuminate\Routing\Controller`, not the app's `App\Http\Controllers\Controller` — `$this->apiResponse()` is unavailable module-wide; nearly every endpoint instead returns a hand-built array or `response()->json()` call, with no consistent envelope across even closely-related endpoints (e.g. `getAllCountry` vs. `getCountries`, `getProfile` vs. `GET /student-profile`).
- A duplicate route registration for `POST address` (harmless — same target — but worth knowing for route-count parity checks).
- `saveAddress` is confirmed to be a real, much thinner, completely unvalidated sibling of `addressSave` — not a typo or dead alias.
- A confirmed field-name mismatch bug in `savePersonalInformation` silently discards the validated `linkedin_link` input.
- A dead private method (`checkIFAddressChangedMail`) that would send an address-change notification email but is never invoked.
- Several `if ($collection)` truthiness checks on `Country::all()`/`State::all()` that can never take their "not found" branch, because Eloquent's `all()` always returns a (possibly empty, but truthy) `Collection` object — the "no data" error shapes in those methods are unreachable dead code.

**Confidence:** High — every endpoint traced directly from `StudentProfileController.php` and the full `StudentProfileTrait.php` (read in its entirety), plus `AddressRequest`/`PersonalInformationRequest`/`StudentProfileResource`. The `linkedin_link`/`linked_in_link` mismatch and the `checkIFAddressChangedMail` dead-code finding were independently verified by re-reading the exact lines and grepping for other call sites, not inferred.
