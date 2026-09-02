# User Module API Documentation

The `User` module is the admin/staff-facing CRUD, search, notification, and profile surface for `App\Models\User` (staff accounts — admins, evaluators, course anchors, instructors — as opposed to `Student`). It also owns a set of unauthenticated system-to-system endpoints used to keep a separate "other app" (the scheduling/meetings sub-project) in sync with this app's user records. This module was **not covered in the existing `API_SPECIFICATIONS.md`**; everything below was traced from source directly, not expanded from prior documentation.

**Module-wide auth:** `Modules/User/Routes/api.php` has two groups, both prefixed `/api/v1/...`:
1. `auth:sanctum` + `json.response` — all CRUD, search, notification, profile, and export endpoints (the large majority).
2. `json.response` **only — no authentication** — six `meeting-*`/`alternate-email` endpoints intended for server-to-server calls from the external scheduling app. Called out explicitly below; these are real, reachable, unauthenticated write endpoints.

See [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for the app-wide response envelope styles, standard error shapes, and pagination conventions referenced below instead of being repeated per endpoint.

`UserController` (`Modules/User/Http/Controllers/UserController.php`) directly implements `index`, `store`, `show`, `update`, `destroy`, `get_lms`, and a `getBookACallRole` method — **the last of which is dead code, see below**. Every other routed method's body lives in one of two traits pulled in via `use ActivityLog, UserTrait, UserNotificationsTrait;`: `UserTrait` (`Modules/User/Http/Traits/UserTrait.php`) and `UserNotificationsTrait` (`Modules/User/Http/Traits/UserNotificationsTrait.php`). `UserTrait` itself pulls in `App\Traits\ActivationAndDeactivationProcess` — the **same** shared activity-log-and-comment helper used by `Student`'s `activate`/`deactivate`.

**Response-helper style is genuinely mixed within this one module:** `UserController`'s own 5 CRUD methods use `$this->apiResponse(...)` (instance method, inherited from the base `App\Http\Controllers\Controller`); essentially every trait method instead calls the **global** `apiResponse(...)` function. Both produce the identical `{"data","message","status"}` shape — only the call site differs — but a few trait methods (`userProfile`, `storeUserProfile`) call `$this->apiResponse(...)` too, so don't assume "controller vs. trait" cleanly predicts which style a given endpoint uses; check each one.

## ⚠️ Confirmed dead code in `UserController`

- **`getBookACallRole()`** (`UserController.php`) is a byte-for-byte near-duplicate of `Modules\StudentBookACall\Http\Controllers\EventController::getBookACallRole()`, but **no route in `Modules/User/Routes/api.php` (or anywhere else) points to `UserController::getBookACallRole`** — confirmed by grep across the whole `Modules/` and `routes/` trees. The only live route for this action is `GET get-bookACall-roles` in `Modules/StudentBookACall/Routes/api.php`, hitting the `EventController` copy. The `User` module's copy is unreachable.
- **`UserTrait::sqlQuery()`** — a raw `DB::select($request['query'])` executor gated by a hardcoded `auth()->user()->id == 185` check — has **no route registered anywhere** in the codebase (confirmed by grep). It is unreachable dead code, not a live endpoint; not documented as one below. Flagged here only because it's a structurally notable (raw-SQL-execution) piece of dead code a migration should be aware of, in case it's wired up elsewhere unexpectedly.
- **`Modules\User\Http\Resources\UserCollection`** exists but is never instantiated/referenced anywhere in the module (confirmed by grep) — an orphaned Resource class.

---

## Own-profile endpoints

### `GET /user-profile` (route name `user.profile`, trait `userProfile`)
- **Success response:** `$this->apiResponse(UserProfileResource::make(Auth::user()))`. `UserProfileResource`: raw-merged `title`,`first_name`,`last_name`,`email`,`phone`, plus `role` (`getRoleNames()[0]` — **`null` if the user has zero roles**, not an error), `country` (nested `{id,short,name,phone_code}` or `null`).

### `PATCH /user-profile` (route name `user.profile-store`, trait `storeUserProfile`)
- **Request body:** inline `$request->validate()`: `title` required max:10; `first_name`/`last_name` required max:50; `phone` required, regex `^([0-9\s\-\+\(\)]*)$`, min:10 max:15 (**a different, looser phone rule than the `Propaganistas\LaravelPhone` rule used everywhere else in this codebase** — no country-aware validation here); `country_id` required (no `exists:` rule — an arbitrary integer, or even a non-existent id, passes validation here, unlike almost every other `country_id` field in this codebase).
- **Success response:** `$this->apiResponse(UserProfileResource::make($users), 'User profile updated successfully', statusCode: 201)` — **201 on an update**, not the conventional 200.
- **Error response:** `$this->apiResponse(null, 'Failed to update user profile: {exception message}', statusCode: 500)` on any exception — **`data` is `null`**, and note the 3-argument call skips the `$status` parameter positionally, so `$status` silently defaults to `'success'` even on this 500 error path (the 4th positional arg `statusCode` is passed via named argument, but `$status` is never overridden) — the body would read `{"data": null, "message": "Failed to update...", "status": "success"}` at HTTP 500. Worth a dedicated test since this contradicts the message/status pairing every other error path in this codebase uses.

---

## Search & notifications

### `GET /search/users` (route name `users.search`, trait `search`)
- **Success response:** `UserSearchResource::collection(...)->additional(['meta' => ['total' => ...]])`. `UserSearchResource`: all raw fields except `first_name`/`last_name`/`status` (excluded), plus `full_name` — **computed as `$this->first_name . '' . $this->last_name` (empty-string separator, not a space)**, e.g. `"JohnDoe"` not `"John Doe"`. Preserve this concatenation bug exactly; a parity test comparing this endpoint's `full_name` against the properly-spaced `full_name` column elsewhere in the app will see a mismatch by design.

### `GET /search/specific-users` (route name `users.specific.search`, trait `searchUsersWithArray`)
- **Success response:** global `apiResponse(UserSearchResource::collection(...))` — note this one **does** wrap in the resource (unlike `Student`'s equivalent `searchStudentsWithArray`, which returns the raw repository array un-wrapped) — the same `full_name` concatenation quirk above applies here too.

### `GET search/roles` (unnamed route, trait `search_roles`)
- **Success response:** global `apiResponse($this->userRepository->searchRoles())` — raw repository output, not resource-wrapped.

### `GET users/notifications` (route name `users.notifications.index`, trait `notifications`)
- Query: `rows` (default 15), `search` (optional, `LIKE` against the notification's raw `data` JSON text), `cursor` (base64-JSON).
- **Success response:** `UserNotificationResource::collection(...)->additional(['meta' => ['total', 'range']])`, using Laravel's native `cursorPaginate($rows)` on the polymorphic `notifications` relation. `range` is computed by a **separately-implemented** cursor-range calculator in this trait (`calculateRangeForsCursor` — note the typo in the method name itself, `Fors` not `For`) rather than reusing `UserTrait::calculateRangeForCursor` — a third near-duplicate of the same cursor-math pattern seen across this codebase, this one keyed on `created_at` comparisons rather than `id`.
- `UserNotificationResource`: raw fields except `created_at`/`updated_at`/`notifiable_type`/`type` (excluded).

### `GET users/notifications/un-read` (route name `users.notifications.un-read`, trait `undReadNotifications`)
- **Success response:** global `apiResponse(['notifications' => [...up to 5 unread, newest first...], 'notifications_count' => N])`. Each notification's `data` column is `json_decode`d and `created_at` reformatted to ISO-8601.
- **⚠️ Latent bug in the "unauthenticated" branch:** `if (!$user) { return apiResponse(['message' => 'User not authenticated.'], 401); }` — the second positional argument to `apiResponse()` is `$message` (a `string`), not a status code. This call passes `401` into the `$message` slot (PHP coerces it to the string `"401"`), leaving `$status` at its default `'success'` and `$statusCode` at its default `200`. **The actual response in that branch would be `{"data": {"message": "User not authenticated."}, "message": "401", "status": "success"}` at HTTP 200** — not a real 401. In practice this branch is normally unreachable because the route sits behind `auth:sanctum` (a failed guard is rejected by the middleware before the controller runs, producing the standard 401 shape from `_COMMON_CONVENTIONS.md` instead), but if `Auth::user()` can ever be null while the guard still passes (e.g. a token whose user was deleted), this bug would surface. Worth a dedicated boundary test.

### `GET users/notifications/mark/read` (route name `users.notifications.mark-all-as-read`, trait `markAsReadAll`)
- **Success response:** global `apiResponse('', 'Notifications marked as read')` — `data` is an empty string.

### `GET users/notifications/{id}/mark/read` (route name `users.notifications.mark-single-as-read`, trait `markSingleAsRead`)
- **Success response:** `apiResponse('', 'Notification marked as read')` if found and marked; `apiResponse('', 'No Notification exists')` if not — **both return HTTP 200 with `status: 'success'`**; there is no error-shaped response for a not-found id here, only a differing `message` string. A status/shape-only check cannot distinguish "marked" from "nothing to mark."

---

## Admin CRUD (`apiResource('users', 'UserController')`)

### `POST /v1/users` (`store`)
- **Request body** (`Store` FormRequest): `title` nullable, one of `Mr.,Mrs.,Ms.,Miss.,Other`; `first_name`/`last_name` required, `regex:/^[a-zA-Z0-9 ]*$/` (alphanumeric + spaces only — no hyphens/apostrophes, notably stricter than `Student`'s equivalent fields which have no such regex); `email` required, `unique:users` (no `email:` format rule applied, only `string`); `alternativeEmail` — validated (`email`, `unique:user_emails,email`) but **never referenced anywhere in `UserController::store()`'s body** — an orphaned validation rule with no corresponding write; `meeting_email` nullable email, `unique:user_emails,email`, plus a custom `PrimaryEmailCheck` rule; `calendly_link`/`meeting_url` nullable URL; `country_id` required `exists:countries,id`; `phone` required + country-aware phone rule; `password` required, `confirmed` (**no complexity/`Password::defaults()` rule**, unlike `Student`'s store which does apply `Password::defaults()` when a password is supplied); `status` required, one of `0,1,2,3`; `role` required `exists:roles,name`; `job_roles` optional array each `exists:job_roles,id`.
- **Success response:** `$this->apiResponse(['user' => UserResource::make($user->fresh())], 'User Created Successfully', statusCode: 201)`.
- **Side effects, in order, several synchronous:** wrapped `DB::transaction()` creates the `User` row, conditionally updates `calendly_link` from `meeting_url`, creates `JobRoleMapping` rows per `job_roles[]` entry, and — if `meeting_email` was sent — creates a `UserEmail` row **and** dispatches `UpdateUserInOtherApp` (queued); assigns the `role` via Spatie; logs "user created". *Outside* the transaction: if `role` contains the substring `"Course Anchor"`, synchronously POSTs to an external Course Calendar API; if `meeting_email` was sent, synchronously POSTs to `{OTHER_APP_URL}/api/v1/users/meeting-details` to look up/copy back a `meeting_id`/`meeting_status`; if `is_instructor == "true"` and no `meeting_id` was set, **synchronously** (`dispatchSync`, not queued) calls `AddUserToMeetingsAPI` — a `RequestException` here returns a bare `response()->json(['error' => ...], 500)`, bypassing `apiResponse()` entirely; finally, if `ats == 1` and no `user_detail` exists yet, dispatches `SendUserDetailsToExternalApi` (queued, failure caught and logged, does not fail the request). A single `store` call can therefore issue up to 3 synchronous outbound HTTP calls before responding.

### `PUT`/`PATCH /v1/users/{user}` (`update`)
- **Request body** (`Update` FormRequest) — every field nullable except `user_id` (required, `exists:users,id`, redundant with the route's own `{user}` binding) — `email`/`phone`/`country_id`/`role`/`calendly_link`/`meeting_url`/`job_roles` all optional; uniqueness checks (`email`, `alternativeEmail`, `meeting_email`) use `->ignore($this->input('user_id'), ...)`, meaning the ignore-id comes from the **body's** `user_id` field, not the route's `{user}` parameter — if these ever diverge (e.g. a caller sends a different `user_id` in the body than the URL), the uniqueness check would be scoped to the wrong record. `job_role.*` (singular, not `job_roles.*`) rule is a likely typo — it validates a field name (`job_role`) that is never actually submitted since `job_roles` (plural) is the field name used everywhere else including this same request's own `job_roles` array rule; effectively a no-op rule.
- **Behavior when `meeting_email` is absent:** clears the `UserEmail` mapping entirely and dispatches `UnlinkUserConnection` — i.e. omitting `meeting_email` on an update **unlinks** any previously-set one; this is not a "leave unchanged" no-op field.
- **Success response:** `$this->apiResponse(['user' => UserResource::make($user->fresh())], 'User updated successfully')`.
- **Side effects:** same "Course Anchor" and `ats`/`SendUserDetailsToExternalApi` side effects as `store`; additionally re-syncs the Spatie role via `syncRoles()` (replaces rather than adds).

### `DELETE /v1/users/{user}` (`destroy`)
- **Success response:** `$this->apiResponse([], 'User deleted successfully')`.
- **Side effects:** if `str_contains($user->role, 'Course Anchor')` — **note `$user->role` here, a singular accessor, not the `roles` relation used elsewhere** — synchronously POSTs to the external Course Calendar API's delete endpoint before deleting the local row.

### `GET /v1/users/{user}` (`show`)
- **Success response:** `$this->apiResponse(['user' => UserResource::make($user)])`.
- `UserResource`: raw-merged `id`,`title`,`first_name`,`last_name`,`email`,`phone`,`status`,`meeting_id`,`meeting_status`,`meeting_link_status`,`ats`, plus `role` (first role name or `null`), `job_roles` (nested collection), `country` (nested or `null`), `is_instructor` (boolean, `meeting_id !== null`), `alternativeEmail` **and** `meeting_email` (both aliased to the exact same value — the first linked `UserEmail`'s `email` — despite the two concepts being validated as separate fields on `store`/`update`), `isAccepted` (`"no"`/`"yes"`/`null` derived from `meeting_status`), `scheduling_app_slug` (**hardcoded `null`**, always), `meeting_url` (aliased from `calendly_link`).

### `GET /v1/users` (`index`)
- Query: `rows` (default 15), `cursor` (base64-JSON, standard scheme, `abort(500, 'Cursor value tempered')` on tamper).
- **Success response:** `UserResource::collection(...)->additional(['meta' => ['total', 'active_user', 'deactive_user', 'range']])`.

---

## Activation / status change

### `POST /users/status/change` (route name `user.status.change`, trait `changeStatus`)
- **Request body:** `user_ids` required array each `exists:users,id`; `comment` required string; `status` required, one of `activate|deactivate`.
- **Success response:** `apiResponse([], 'users deactivated successfully', statusCode: 200)` or `'users activated successfully'` — note both messages are **lower-case** (`"users..."`, not `"Users..."`), unlike `Student`'s equivalent (`'Activated Successfully'`/`'Deactivated Successfully'`, capitalized) — a case-sensitive string-match assertion copied from the `Student` module's test suite would fail here.
- **Side effects (deactivate only):** sets `status = User::USER_DISABLED`; deletes **every** Sanctum token for each affected user (forced logout); for each user with a non-null `meeting_id`, synchronously POSTs to `{BOOK_A_CALL_API}user-delete/{meeting_id}` (failure only logged, does not block); `addActivityLogsAndComments()` (the same shared helper `Student`'s activate/deactivate uses).
- **Side effects (activate):** sets `status = User::USER_APPROVED`; same activity-log-and-comment helper; **no** token/meeting-related side effects on this branch (asymmetric with deactivate, same asymmetry pattern as `Student`'s activate/deactivate).

---

## Export

### `GET users/export` (route name `users.export`, trait `export`)
- **Request:** `Validator::make()` validates only that `data` (if present) is an array — no deeper per-field rules, unlike `Student`'s equivalent export endpoints which validate the full filter-clause shape.
- **Success response:** global `apiResponse('', 'Users Csv file exporting started')`.
- **Side effects:** queues `UserCSVDownloadStart` on `default_medium` — fire-and-forget, same pattern as `Student`'s CSV exports.

---

## Misc authenticated utility endpoints

### `GET get-lms` (unnamed route, controller `get_lms`)
- **Success response:** the method **returns a plain PHP array** (`['key' => <JWT string>]`) directly from the controller action — Laravel auto-converts an array return value into a `200 response()->json()` response. **This is not `apiResponse()`, not `$this->apiResponse()`, and not an explicit `response()->json()` call** — a fourth, even more minimal response style than the three named in the common conventions doc (no `message`/`status` key of any kind, just the bare payload).
- The JWT is signed with `env('LMS_SECRET')`, expires in exactly 36000 seconds (the inline comment claiming "Plus 2 minutes" is stale/incorrect — it's 10 hours, not 2 minutes) and embeds the caller's own `first_name`/`last_name`/`email`.

### `POST /user/token_save` (route name `user.token_save`, trait `saveUserToken`)
- **Request body:** inline `validate()`: `user_id` required `exists:users,id`; `token` required string max:255.
- **Success response:** hand-rolled `response()->json(['message' => 'User Token saved successfully.'], 201)` — no `data`/`status` key at all.
- **Side effects:** creates an `fcmTokens()` row; dispatches `SendUserSubscriberTokenToFCM` and `SendUserSubscriberTokenToScheduleApp` (both queued, fire-and-forget).

### `POST /user/campaign_stat` (route name `user.campaign_stat`, trait `updateCampaignStat`)
- **Request body:** inline `validate()`: `id` required integer; `slug` required string.
- **Success response:** hand-rolled `response()->json(['message' => 'Student Campaign Stat updated successfully.'], 201)` — **the message says "Student" even though this is a `User`-module endpoint with no student involved at all**, likely copy-pasted from elsewhere; preserve the message text exactly.
- **Behavior:** synchronously POSTs to `{fcm_api_url}/v1/stat-count`; **on a non-successful response, throws a raw `\Exception`** rather than returning a structured error — this will surface as an uncaught-exception 500 (whatever the app's global exception handler renders for a generic `Exception`, not one of the standard shapes in `_COMMON_CONVENTIONS.md`), not a clean 4xx/502.

### `GET /users/{user}/activity` (route name `users.activity`, trait `activity`)
- **Error response:** `apiResponse([], 'User Not Found', 'error', 404)` if the id doesn't resolve.
- **Success response:** `App\Http\Traits\ActivityLog::logListOfUser()` — **a different pagination/shape from `Student`'s `activity` endpoint** despite both living in the same shared `ActivityLog` trait: this one is scoped to a **single calendar day** (`historical_date` query param, default today) via `whereDate('created_at', ...)`, matches activity where the user is *either* the causer *or* the subject (`orWhereMorphRelation`), and uses the standard page-number-as-`cursor` paginator (same mechanism as `Student`'s `logOfStudent`, i.e. `?cursor=` is a plain page number, not base64-JSON). Resource is `ActivityResponse` (not `ActivityResource`): `id`,`actionName` (title-cased, underscores replaced with spaces), `causedBy` (causer's `full_name`), `actionedAt` (`d M, Y h:i A` format — different from `Student`'s `Y-m-d G:i:s`), `description`, and `actionedByHimself` (`"Yes"`/`"No"` string, comparing the log's causer id against the `{user}` in the URL).

### `GET /user/permissions` (route name `permissions.user.index`, trait `permissions`)
- **Success response:** global `apiResponse(['permissions' => [...role names...]])`.

---

## Unauthenticated system-to-system endpoints (`json.response` only, no `auth:sanctum`)

All six of the following are publicly reachable with no authentication of any kind — they exist to let an external "other app" (the meetings/scheduling sub-project) push updates back into this app's `User`/`UserEmail` records. Every one validates via inline `$request->validate()`/`Validator::make()` (no FormRequest classes), and every success/error path uses the global `apiResponse()` helper.

### `POST /users/update/alternate-email` (route name `user.update.alternate-email`, trait `updateWithAlternateEmail`)
- **Request:** `user_email` required email; `secondary_email` nullable email; `meeting_id`/`meeting_status` nullable.
- Looks the user up by `user_email`; creates or overwrites their **first** `UserEmail` row (by whatever `id` sorts first — not necessarily the most recent) with `secondary_email`. **Error:** `apiResponse([], 'User not found', 'error', statusCode: 422)` if no match.
- **Success:** `apiResponse([], "User's Alternative Email updated successfully", statusCode: 200)`.

### `POST /users/remove-link` (route name `user.remove-link`, trait `removeLinkWithAlternateEmail`)
- **Request:** `email` required email — looked up against `UserEmail.email`, **not** `User.email` (the parameter name is misleading — it's the *secondary/alternate* email being removed, not the user's primary one).
- **Error:** `apiResponse([], 'No Data Found to Unlink', statusCode: 422)`.
- **Success:** `apiResponse([], "User's Alternative Email Link Removed successfully", statusCode: 200)`.

### `POST /users/meeting-status-update` (route name `user.meeting-status-update`, trait `meetingStatusUpdate`)
- **Request:** `user_email` required email; `meeting_id` required integer; `meeting_status` required.
- **Side effect:** dispatches `OtherAppMeetingStatusUpdate` (queued) — i.e. this endpoint both *receives* a meeting-status push from the other app **and** turns around and dispatches a job that (presumably) pushes it back out — check `OtherAppMeetingStatusUpdate`'s own destination before assuming this is a one-way sync if tracing an end-to-end loop.

### `POST /users/meeting-status-update-from-other-app` (route name `user.meeting-status-update-from-other-app`, trait `meetingStatusUpdateFromOtherApp`)
- **Request:** `user_email` required email only — `meeting_status`/`meeting_id` are read from the request **without being declared in the validation rules at all** (both effectively optional/unvalidated despite being written to the `User` row).
- Looks the user up via `UserEmail.email` (not `User.email`) — **a different lookup table than the very similarly-named `meetingStatusUpdate` endpoint above**, which looks up by `User.email` directly. The two "meeting status update" endpoints are not interchangeable.

### `POST /users/meeting-id-update-from-other-app` (route name `user.meeting-id-update-from-other-app`, trait `meetingIdUpdateFromOtherApp`)
- **Request:** `user_email` required email; `meeting_id` required (no type constraint); `meeting_status` nullable.
- Looks up via `UserEmail.email`, then **additionally filters** to rows where `meeting_link_status != 'primary'` (or is null) before applying the update — if the matched user's `meeting_link_status` is already `'primary'`, the inner `User::query()->...->first()` returns `null` and the subsequent `$updateUser->meeting_id = ...` line **is a null-property write, which throws** — an uncaught-exception 500, not a clean 4xx, in that specific case. Confirmed by reading the method body directly (no null-check between the query and the property assignment).

### `POST /users/meeting-details` (route name `user.meeting-details`, trait `getUserMeetingDetails`)
- **Request:** `email` required email.
- **Success response:** `apiResponse($getUser, 'User Meeting details', statusCode: 200)` where `$getUser` is `User::where('email', ...)->where('meeting_link_status', 'primary')->first(['meeting_id','meeting_status','has_event'])` — **`$getUser` is `null` (not an error) if no matching primary-linked user is found**; the response is still a 200 with `data: null` in that case, not a 404.

---

## Summary

**Routes documented:** all 27 routes in `Modules/User/Routes/api.php` (21 in the authenticated group — 16 individually-declared plus the 5-route `apiResource` — and 6 in the unauthenticated group) — 23 distinct actions in total. `getBookACallRole` and `sqlQuery` are confirmed dead code (no route anywhere) and are not counted as documented endpoints.

**Structural surprises:**
- Two confirmed dead controller/trait methods (`getBookACallRole`, `sqlQuery`) and one orphaned Resource class (`UserCollection`).
- An entire 6-endpoint unauthenticated write surface for cross-app meeting/email sync — a significant attack-surface note for parity/security testing, distinct from the rest of the module's `auth:sanctum` posture.
- At least two genuine argument-order/type bugs in `apiResponse()` calls (`storeUserProfile`'s error path, `undReadNotifications`'s unauthenticated branch) that silently produce wrong status codes/messages — both confirmed by reading the exact call sites.
- `UserSearchResource`'s `full_name` concatenation omits the space between first/last name — confirmed in source, not a typo in this doc.
- Two similarly-named "meeting status update" endpoints key off different tables (`User.email` vs. `UserEmail.email`) — easy to conflate.

**Confidence:** High — every endpoint traced directly from `UserController.php`, `UserTrait.php`, `UserNotificationsTrait.php`, `Store`/`Update` FormRequests, and the referenced Resource classes; the shared `ActivityLog`/`ActivationAndDeactivationProcess` traits were read in full rather than assumed to match `Student`'s behavior.
