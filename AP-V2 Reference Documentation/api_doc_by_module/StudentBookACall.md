# StudentBookACall API

Covers every route declared in `Modules/StudentBookACall/Routes/api.php` (70 raw `Route::` declarations; several are the *same* controller method registered a second time under a different auth guard — those are documented once with all matching routes listed). This module is almost entirely a **thin proxy** in front of a separate scheduling sub-project's own API (a "scheduling app" reached via `MEETING_API_BASE_URL` / `config('services.meeting_api.base_url')`, and a "BookACall" booking-domain API reached via `BOOK_A_CALL_API` / `config('services.meeting_api.book_a_call_base_url')` — both env vars, same values, just accessed two different ways in different files). Local tables (`BookACallMeeting`, `Team`, `DefaultTeam`, `users.meeting_id`/`meeting_status`) mostly mirror/cache identifiers needed to call those external APIs and to resolve local user/student identity.

See [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for the app-wide response envelope, standard error shapes, and pagination conventions — this file only calls out where an endpoint deviates from or supplements those.

## Module-wide notes

- **No FormRequest classes exist anywhere in this module**, and only **one** endpoint (`updateRecordingUrl`) calls `$request->validate()`. Every other endpoint reads the request body with raw `$request->all()` / `$request->input` / property access — malformed input is either passed straight through to the external API (which does its own validation and whose error is relayed back, sometimes badly) or causes a PHP-level error caught by a generic `try/catch` returning a 500.
- **Three auth zones**, declared as three separate route groups in file order:
  1. **No middleware at all** (top of the file) — these are callback/webhook-style endpoints called *by* the external scheduling app itself, not by this app's own frontend. Treat every field here as attacker-controllable if the endpoint URL leaks.
  2. **`auth:sanctum` + `json.response`, prefix `v1`** — staff/instructor/admin-facing.
  3. **`auth:student` + `json.response`, prefix `student/v1`** — student-facing.
- **Confirmed dead/broken routes** — the following routes call a controller method that **does not exist** anywhere in the module (not in the controller, not in any trait it uses). Calling them throws a PHP `Error` ("Call to undefined method"), which surfaces as an uncaught-exception 500 via the framework's default handler, not a clean JSON error body:
  - `POST v1/team-event` → `EventController::createTeamEvent` — undefined.
  - `DELETE v1/event/delete/{eventId}` → `EventController::deleteEvent` — undefined.
  - `GET student/v1/event/{eventId}` → `EventController::getEventUser` — undefined.
  - `GET v1/instructors/export` → `InstructorController::export` — undefined.
  - `GET v1/team/instructors` → `InstructorController::TeamIndex` — undefined.
  - `POST v1/instructor/review/{instructorId}` → `InstructorController::storeInstructorReview` — undefined.
  - `GET v1/export/meetings/{userId}` → `MeetingBookingController::export` — undefined.
  - `POST student/v1/mark-as-complete/{bookingId}` → `StudentMeetingController::markAsComplete` — undefined.

  These are flagged individually below too. A parity migration should decide whether AP‑V3 needs to reproduce "500 on call" for these paths or simply drop them — they cannot currently return any real payload.
- **Response helper style:** every endpoint in this module hand-rolls `response()->json([...], $code)` (or, in three places, returns a raw external `Illuminate\Http\Client\Response`/its decoded array directly). Nothing in this module uses `apiResponse()` / `$this->apiResponse()`. Field names, casing, and even the type of `status` (string `"success"`/`"error"` vs boolean `true`/`false`) are inconsistent endpoint-to-endpoint — each is called out below.
- External base URLs used throughout: `MEETING_API_BASE_URL` (scheduling-app: events, availability slots, teams, tokens) and `BOOK_A_CALL_API` (booking-domain: bookings, reviews, no-shows, ratings, history). `getBookACallRole`/`getBookACallUserRole` reach the same `BOOK_A_CALL_API` value via `config('services.meeting_api.book_a_call_base_url')` instead of `env()` directly — same value, different access path.

---

## Public / unauthenticated routes

These carry no middleware group at all (no `auth:*`, no `json.response`), and are registered directly at the top of the route file, ahead of the two guarded groups.

### `POST /update-recording-url`
- **Controller:** `MeetingBookingController::updateRecordingUrl`
- **Request params:** `meetingId` (required), `recordingUrl` (required) — enforced via inline `$request->validate([...])`, **the only validate() call in this entire module**. On failure this produces the app's standard 422 validation shape (see conventions doc).
- **Side effects:** `BookACallMeeting::where('meeting_id', $request->meetingId)->update(['recording_url' => $request->recordingUrl])`.
- **Success:** `200 {"status":"success","message":"Recording url updated successfully"}` only if `$affectedRows > 0`.
- **Error:** if no row matched `meetingId`, **`422 {"status":"failed","message":"Failed to update Recording url"}`** — note `status` is the literal string `"failed"`, not `"error"`, and this is a 422 for what is really a "not found" condition, not a validation failure.

### `GET /member-list`
- **Controller:** `InstructorController::memberList` (unauthenticated copy; the same method is also reachable at `v1/member-list` under `auth:sanctum` — see below, identical body either way since the method itself does not check auth).
- **Request params:** `rows` optional int, default **200** (not 15).
- **Success:** `201 {"status":"success","data":[...MemberListResource...],"memeber":"Member Fetched Successfully"}` — note the **misspelled key `memeber`** (not `message`), and a `201` on what is a read/list operation.
- `MemberListResource` fields: `id`, `meeting_id`, `name` (from `full_name`), `email`.

### `POST /users/has-event-update`
- **Controller:** `EventController::updateHasEvent`
- **Request params (raw):** `userId` (matched against `users.meeting_id`, **not** the local `users.id`), `has_event`.
- **Side effects:** `User::where('meeting_id', $request->userId)->update(['has_event' => $request->has_event])` — no existence check; a non-matching `userId` silently updates 0 rows and still reports success.
- **Success:** `200 {"status":"success","data":[],"message":"Updated successfully"}` (default 200, no explicit code given).
- **Error:** on exception, still returns HTTP 200 (no status code passed to `response()->json()` in the catch branch) with `{"status":"error","data":[],"message":"Failed to Update"}` — **error path returns 200**, not 500.

### `POST /check-email`
- **Controller:** `EventController::checkStudentEmail`
- **Purpose:** invoked by the external scheduling app when a booking is created on its side for an email it doesn't recognize locally, to reconcile with this app's `Student`/`User` tables.
- **Request params (raw, from `$request->all()`):** `startTime`, `endTime`, `student_email`, `userId` (instructor's `meeting_id`), plus a large passthrough set forwarded on to BookACall (`id`, `title`, `eventId`, `scheduleId`, `description`, `metadata`, `location`, `status`, `meetingUrl`, `responses`, `attendeeTimeZone`, `adminTimeZone`, `event.teamId`). None of these are validated; missing keys throw an undefined-array-key PHP notice/warning inline (not a clean error response).
- **Behavior:**
  - If `student_email` doesn't match any local `Student` row → dispatches `CheckStudentInSA::dispatchSync($data)` **synchronously** (posts to `OTHER_APP_URL/api/check-email`) and the controller **returns nothing** (`null` body, effectively an empty 200 response — no explicit `return` on this branch).
  - If the student exists but is not `Student::ACTIVE`... actually no such check exists here (that check lives in `feedBackFromEmail` below, not here) — a matched student of any status proceeds.
  - If matched: builds a `newPayload` mapping the scheduling-app's booking shape into this app's booking shape and does one **External call**: `POST {BOOK_A_CALL_API}booking/create`.
- **Success:** `200 {"message":"Booking created successfully.","status":"success","bookACallResponse":<raw external JSON>}`.
- **Error:** on a failed/unsuccessful external call, `500 {"message":"Failed to create booking in BookACall.","status":"error","bookACallError":<raw external body>}`; on a thrown exception, `500 {"message":"An error occurred while creating the booking.","status":"error"}`.
- **Notes:** ⚠️ if `!$student` this method has no `return` statement in that branch — PHP falls through the outer `if/else` with nothing returned, which Laravel will render as an empty response body with default 200 status.

### `GET /remove-meetingId/{meetingId}`
- **Controller:** `StudentMeetingController::removeMeetingId`
- **Request params:** `meetingId` path param, matched against `users.meeting_id`.
- **Side effects (in a DB transaction):** clears `users.meeting_id`/`meeting_status` to `null`; soft-deletes (`deleted_at = now()`) all `CourseInstructorMapping` rows for that instructor; deletes the matching `UserEmail` row.
- **Success:** `200 {"status":"success","message":"Meeting ID and associated data removed successfully"}`.
- **Errors:** `404 {"status":"error","message":"User not found"}` if no user has that `meeting_id` (via `firstOrFail()`); `500 {"status":"error","message":"Failed to remove meeting ID"}` on any other exception (transaction rolled back).

### `GET /get-bookACall-roles`
- **Controller:** `EventController::getBookACallRole`
- **External call:** `GET {config('services.meeting_api.book_a_call_base_url')}get-bookACall-roles` (10s timeout).
- **Success:** `200 {"status":"success","data":<external "data" key, default []>,"message":"Roles fetched successfully"}`.
- **Error:** external non-2xx → same status code as the external response, `{"status":"error","message":"Failed to fetch Book a Call roles. Status: {code}"}`; exception → `500 {"status":"error","message":"<exception message>"}` (leaks internal exception text to the client).

### `GET /feedback-from-email/{studentEmail}` (named `feedback.from.email`)
- **Controller:** `StudentMeetingController::feedBackFromEmail`
- **Behavior:** if no `Student` matches `studentEmail` → dispatches `StudentFeedBackJob::dispatch($studentEmail)` (queued, posts to `OTHER_APP_URL/api/feedback-from-email/{email}`) and, like `checkStudentEmail`, **returns nothing** on this branch (empty 200 body).
- If matched but `status != Student::ACTIVE` → throws `ValidationException::withMessages(['message' => ['This Student is not Active for logging in!']])`, which the app's exception handler renders as the **standard 422 validation shape** (see conventions doc) — i.e. this uses an exception to produce a 422 rather than a FormRequest.
- If matched and active: mints/reuses a `tmp_verification_token` (regenerated only if missing or expired; otherwise just its expiry is bumped by a year) and returns `200 {"status":"success","token":...,"student_id":...,"student_email":...,"channel":1}` — **no explicit HTTP status on this branch either (falls back to Laravel default 200 for a plain array-turned-JsonResponse... actually here it's an explicit `response()->json([...])` so 200 default applies)**.

### `GET /get-bookACall-user-role/{meetingId}`
- **Controller:** `EventController::getBookACallUserRole`
- **Behavior:** looks up `User::where('meeting_id', $meetingId)`; if none found, `404 {"status":false,"message":"Meeting ID not found"}`. Otherwise calls `GET {book_a_call_base_url}get-user-role/{meeting_id}`.
- **Success:** `200 {"status":true,"data":<external "data" or null>,"message":"User role fetched successfully"}`.
- **Notes:** ⚠️ `status` in this endpoint's body is a **boolean** (`true`/`false`), unlike the string `"success"`/`"error"` convention used almost everywhere else in the module — a parity check must not assume a uniform `status` type across this module.

---

## Staff / instructor routes (`auth:sanctum`, `json.response`, prefix `v1`)

### Events

#### `GET /events/{userId}` and `GET student/v1/events/{userId}` — `EventController::index`
- Same method, reachable under both the sanctum (`v1/events/{userId}`) and student (`student/v1/events/{userId}`) guards — behavior is identical regardless of guard; the method itself does not branch on user type.
- **Request params:** `userId` path param → resolves `users.meeting_id`.
- **External call:** `GET {MEETING_API_BASE_URL}event-types/{meeting_id}`.
- **Success:** `200 {"data":<events array>,"links":{...all null...},"meta":{"path","per_page":15,"total_events","range":{"from":1,"to","total"}},"message":"Events Fetched Successfully"}` — a hand-built pagination shape (not the conventions-doc cursor shape); `links` is always all-null (dead scaffolding), and there is no real pagination — `total_events`/`range` are just the full in-memory count of whatever the external API returned.
- **Errors:** `404 {"message":"User meeting ID not found"}` if the user has no `meeting_id`; on external failure, external status code with `{"message":"Failed to fetch events.","error":<external body>}`; on exception, `500` with the same shape and the exception message as `error`.

#### `GET /admin/events/{userId}` — `EventController::adminIndex`
- Identical to `index()` above except it hits `GET {MEETING_API_BASE_URL}admin-event-view/{meeting_id}` instead of `event-types/`. Same response/error shapes.

#### `POST /team-event` — `EventController::createTeamEvent` — **⚠️ dead route, method undefined.** See module-wide notes.

#### `GET /team-event/{teamId}` and `GET student/v1/team-event/{teamId}` — `EventController::teamEvents` (defined in `EventsTrait`)
- **Request params:** `teamId` path param; optional `search` query string, URL-encoded and appended.
- **External call:** `GET {MEETING_API_BASE_URL}team-student-event/{teamId}[?search=...]`.
- **Success:** `200 {"team_type":"Team Event","team_title":<first event's team_title or null>,"data":[...],"links":{...null...},"meta":{...same hand-built shape as index()...},"message":"Events Fetched Successfully"}`.
- **Errors:** same pattern as `index()` (external status/body passthrough on failure; 500 on exception). No "meeting ID not found" branch here since there's no per-user lookup.

#### `DELETE /event/delete/{eventId}` — `EventController::deleteEvent` — **⚠️ dead route, method undefined.** See module-wide notes.

#### `GET /timeZone` — `EventController::getTimeZone`
- **External call:** `GET {MEETING_API_BASE_URL}time-zone`.
- **Success:** `200 {"status":"success","data":<events/tz list>,"pagination":<external "pagination" key or []>,"message":"Events fetched successfully"}` — note the misleading message ("Events fetched") on a timezone endpoint (copy-paste artifact), and `pagination` (not `meta`) as the wrapper key.
- **Errors:** external failure → external status with `{"status":"error","message":"Failed to fetch events.","error":<body>}`; exception → `500` same shape.

### Instructors

#### `GET /instructors` — `InstructorController::index`
- **Request params:** `rows` optional int, default 15.
- **Success:** `InstructorResource::collection(...)->additional(['meta' => []])` — an **empty `meta` object**, no `total`/`range` despite this being a paginated-looking listing.
- `InstructorResource` fields: `id`, `full_name`, `status`, `email`, `meeting_connection` (a hardcoded-format URL string `https://meeting-api.lawsikho.in/{first_name}-{last_name}-{id}`, not a real verified link). A large amount of previously-computed call-count logic in this resource is commented out dead code — those fields (`missed_calls`, `upcoming_calls`, etc.) do **not** appear in the live response despite existing in the source as comments.

#### `GET /member-list` (sanctum) — same `InstructorController::memberList` documented under the public section above; response is identical regardless of guard.

#### `GET /instructors/export` — `InstructorController::export` — **⚠️ dead route, method undefined.** See module-wide notes.

#### `GET /team/instructors` — `InstructorController::TeamIndex` — **⚠️ dead route, method undefined.** See module-wide notes.

#### `POST /instructor/review/{instructorId}` — `InstructorController::storeInstructorReview` — **⚠️ dead route, method undefined.** See module-wide notes.

#### `GET /resend/register/email/{userId}` (both `GET` and `POST` map to the same handler) — `InstructorController::resendRegisterEmail`
- **Request params:** `userId` path param → local `User` lookup (by primary key, not `meeting_id`, here).
- **External call:** `GET {MEETING_API_BASE_URL}resend-user/{meeting_id}`.
- **Success:** `200 {"status":"Success","message":"Email sent successfully to the user's email address."}` — note **capitalized** `"Success"`/`"Error"` values, inconsistent with the lowercase convention used almost everywhere else.
- **Errors:** `404 {"status":"Error","message":"User not found."}` if no local user; external failure → external status with `{"status":"Error","message":"Failed to retrieve data from the external API."}`; exception → `500` same shape with the exception message appended.

### Booking (staff-side)

#### `GET /meetings/{userId}` — `MeetingBookingController::myMeetings` (in `MeetingBookingTrait`)
- **Request params:** `userId` path param (used only for timezone resolution via `TimezoneHelper`); `rows` optional int (default 15); `meeting_status` optional — one of `missed_calls`/`cancelled_calls`/`today_calls`/`upcoming_calls`/`passed_calls`, else defaults to `today_calls` behavior.
- **Success:** `MeetingResource::collection(...)->additional(['meta' => [0 => {range array, unkeyed}, 'range' => {...}, 'today_calls', 'upcoming_calls', 'missed_calls', 'cancelled_calls', 'passed_meetings_count']])` — ⚠️ the `meta` array contains the range **twice**: once as a bare numeric-indexed `0 => [...]` entry (a bug — `$this->calculateRangeForCursor($rows)` is pushed into the array without a key) and again correctly keyed as `'range'`.
- `MeetingResource` makes a **live external HTTP call per row** (`teamName()` hits `{MEETING_API_BASE_URL}team-id/{teamId}` for every meeting in the page) to resolve `team_title` — this is an N+1 external-call pattern, not a batch lookup; a parity/load test should account for this.
- Fields: `event_id`, `instructor_name`, `meeting_id`, `student_name`, `student_email`, `student_phone`, `meeting_title`, `event_status`, `meeting_start_time`/`meeting_end_time` (converted to `adminTimeZone`), `meeting_link`, `meeting_duration` (minutes), `meeting_status`, `student_feedback`, `timezone`, `student_response`, `instructor_feedback`, `feedback_status` (`Yes`/`No`), `isAbleToJoin` (`Yes`/`No` based on whether start time is in the past), `attendeeTimeZone`, `adminTimeZone`, `team_id`, `team_title`, `team_type` (`course` vs `Team Event`), `recording_url`.

#### `GET /export/meetings/{userId}` — `MeetingBookingController::export` — **⚠️ dead route, method undefined.** See module-wide notes.

#### `GET /personal-meetings/slots` — `MeetingBookingController::personalMeetingsSlots`
- **Request params (raw, hand-concatenated into the query string — no URL-encoding applied to any of them):** `eventId`, `startDate`, `endDate`, `timeZone`; `userId` is **not** taken from the request — it's always `Auth::user()->meeting_id`.
- **External call:** `GET {MEETING_API_BASE_URL}personal-meeting/slots?...`.
- **Success:** `200 {"status":"success","message":"No slots found"}` if the external `slots` key is missing/empty; else `200 {"status":"success","slots":[...],"message":"Slots fetched successfully"}` — note the **top-level key is `slots`, not `data`**.
- **Errors:** external failure → external status `{"error":"Failed to fetch slots"}`; exception → `500 {"error":"Something went wrong"}`.
- **Notes:** ⚠️ none of `eventId`/`startDate`/`endDate`/`timeZone` are URL-encoded before being concatenated into the query string — a value containing `&` or other reserved characters will corrupt the request to the external API.

#### `POST /booking/{bookingId}/cancel` (also reachable, identically, at `student/v1/booking/{bookingId}/cancel` under `auth:student`) — `MeetingBookingController::cancelBooking` (in `MeetingBookingTrait`)
- **External call:** `POST {BOOK_A_CALL_API}booking/{bookingId}/cancel` forwarding `$request->all()` verbatim. No local DB write.
- **Success:** `200 {"data":[],"status":"success","message":"Booking has been cancelled"}`.
- **Errors:** external failure → external status code with `{"data":[],"status":"error","message":<external "message" key, or fallback "Failed to cancel the booking">}`; exception → `500` same shape with a fixed message.

#### `GET /booking/reschedule/{id}` (also at `student/v1/booking/reschedule/{id}`) — `MeetingBookingController::rescheduleShow` (in `MeetingBookingTrait`)
- **Purely local read**, no external call — the only booking-related read endpoint that doesn't proxy out.
- **Request params:** `id` path param, matched against `BookACallMeeting.meeting_id` (**not** the row's own primary key, despite the route parameter's generic name).
- **Success:** `200 {"status":"success","data":{meeting:{...},team:{...},course:{...},instructor:{...},event:{...}},"message":"Meeting fetched successfully"}` — every nested sub-object degrades to all-`null` fields via `??` if the relation is missing (no early 404).
- **Error:** any exception (including "no such meeting" — since `first()` returns `null` and the subsequent `$meeting->meeting_id` access on `null` throws) → generic `500 {"error":"Something went wrong"}`, no `status` key at all here (inconsistent with every other error shape in this file).

#### `PUT /booking/edit/{bookingId}` (staff variant) — `MeetingBookingController::editBookingInstructor` (in `MeetingBookingTrait`)
- **Request params (raw):** `startTime`, `endTime`, `timeZone` and/or `adminTimeZone` (prefers `adminTimeZone` if present), `instructor_comment`, plus anything else forwarded via `$request->all()` to the scheduling-app leg.
- **Two chained external calls:** `PUT {MEETING_API_BASE_URL}bookings/{bookingId}` then, if that yields a `data.id`, `PUT {BOOK_A_CALL_API}instructor/booking/edit/{id}`.
- **Success:** `200 {"status":"success","data":{...large flattened booking object with instructor/course lookups...},"message":"Meeting has been rescheduled"}`.
- **Errors/quirks:** on a failed first-leg call, returns `response()->json(['message' => $response['message'], 'status' => $response['status']], $response->status())` — **⚠️ `$response` here is the raw `Illuminate\Http\Client\Response` object, and `$response['message']`/`$response['status']` use ArrayAccess against it, which only works if the response's JSON body itself has top-level `message`/`status` keys; if it doesn't, this throws** (a latent bug, same shape as the one already flagged for the student-facing `editBooking` in `API_SPECIFICATIONS.md` §5 — this staff variant has the identical bug, just calling `instructor/booking/edit/{id}` on the BookACall leg instead of `booking/edit/{id}`).

#### `GET /personal-meetings` — `MeetingBookingController::personalMeetings` (in `MeetingBookingTrait`)
- Same shape/logic as `myMeetings()` but scoped to `Auth::user()->id` (no `userId` path param) and backed by `PersonalMeetingRepositoryInterface`/`PersonalMeetingResource` instead of the team-meeting equivalents. Same N+1-external-call caveat for `team_title` resolution, and the same doubled-range `meta` bug (`0 => [...]` plus `'range' => [...]`).
- `PersonalMeetingResource` duplicates the `instructor_feedback` key twice in its `toArray()` (harmless — second assignment just overwrites the first with the same value) and resolves `timezone` via `TimezoneHelper::getUserTimezone($request->userId)` even though this route has no `userId` in the request — that will resolve to a default/null timezone rather than the instructor's.

### Team (staff-side)

#### `GET /teams` (also at `student/v1/teams`) — `TeamController::index`
- **Request params:** `search` query string.
- **External call:** `GET {BOOK_A_CALL_API}teams-list?search=...&channel_id=1`.
- **Success:** `200 {"data":<external "teams" array>,"meta":{"meeting_accessible": Auth::user()->meeting_accessible}}` — only returned if the external body has `status === 'success'` **and** a `teams` key; otherwise falls into the "failed" branch even on an external HTTP 200 with a different-shaped body.
- **Notes:** ⚠️ if the external call is `successful()` (2xx) but its body doesn't have the expected `status`/`teams` keys, the method falls off the end of the `if` with **no `return` in that inner branch** for the success path other than the explicit one — check carefully; the outer `try` has no final `return` either, so an unexpected-but-2xx external body yields a `null`/empty response body at whatever status the inner logic left (in this exact code path, it explicitly returns the error JSON, so this is safe, but there is no catch-all `return` after the `if/else` inside the `try`).

#### `GET /new-teams` — `TeamController::newTeamindex`
- **Purely local read** (no external call) — `NewTeamResource::collection($this->teamRepository->allWithSearch(...))`, cursor-paginated per the conventions doc (`rows`/`cursor` query params, tampered cursor → `abort(500, 'Cursor value tempered')`).
- `NewTeamResource` fields: `id` (from `team_id`), `name`, `slug`, `status`, `teamMembers` (resolved by looking up each comma-separated `meeting_id` against local `users` — **N+1 local queries**, one per member), `count`, `type` (hardcoded `'Team Event'`), `description`, `organizationId`.

#### `GET /team-filter` — `TeamController::teamFilterList` (in `TeamTrait`)
- **Purely local read**: `Team::whereNotIn('status', [Team::DELETE, Team::PERSONALMEETING])->select('team_id as id','title as name')->get()`.
- **Success:** `200 {"status":"success","data":[{id,name},...],"message":"Teams Fetched Successfully"}`.

#### `POST /default-team` — `TeamController::storeDefaultTeam` (in `TeamTrait`)
- **Request params:** `team_ids` array (default `[]`).
- **Behavior:** resolves the caller's `meeting_id`; if absent, short-circuits with a "not registered" success response (see below). Otherwise diffs `team_ids` against the caller's existing `DefaultTeam` rows and creates one new `DefaultTeam` row per genuinely-new id (local write only, no external call).
- **Success:** `201 {"status":"success","message":"Default team(s) created successfully.","data":[<newly added ids>]}`; if nothing new to add, `200 {"message":"No new teams to add."}` (no `status`/`data` keys on this branch); if caller has no `meeting_id`, `200 {"status":"success","data":[],"message":"You are not registered in the Scheduling App yet."}`.
- **Error:** exception → `500 {"message":"Error: <exception message>"}`.

#### `GET /booking-calls/default-team` — `TeamController::getDefaultTeam` (in `TeamTrait`)
- **Purely local read** of the caller's `DefaultTeam` rows, resolved to `{id, name}` pairs via local `Team` lookup.
- **Success:** `200` with **both** `teams` and `data` keys holding the same array (redundant duplication) plus `status`/`message` that vary by which of three early-exit branches is hit (`"You are not registered..."`, `"No default teams found..."`, `"No teams found for the provided team IDs."`, or the real `"Default teams retrieved successfully."`) — all of them still `200 {"status":"success",...}`, i.e. **there is no non-200/error path for "nothing found" here**, only differing messages.
- **Notes:** ⚠️ `Auth::id() ?? 1` — if somehow unauthenticated, this silently falls back to **user id `1`** rather than failing; given the route sits behind `auth:sanctum` this is normally unreachable, but it's a latent authorization smell worth a boundary test.

#### `POST /delete-default-team` — `TeamController::deleteDefaultTeam` (in `TeamTrait`)
- **No request params** — deletes **all** `DefaultTeam` rows for the caller's `meeting_id` (not scoped to a specific team id despite the name suggesting a targeted delete).
- **Success:** `200 {"status":"success","message":"Default team(s) deleted successfully."}` or, if none existed, `200 {"status":"success","message":"No default teams found for the user to delete."}`.
- **Error:** `404 {"message":"Register in the Scheduling App first"}` if no `meeting_id`; `500 {"message":"Error: ..."}` on exception. Same `Auth::id() ?? 1` fallback as above.

#### `PUT /teams/{id}` — `TeamController::update`
- **Request params (raw):** full `$request->all()` forwarded to the external call; additionally reads `teamMembers` (array, imploded to CSV for local storage), `name`, `slug`, `description`, `organizationId` for the local mirror row.
- **External call:** `PUT {MEETING_API_BASE_URL}teams/{id}`.
- **Side effects:** on external success, updates the local `Team` row (matched by `team_id`) with the new `title`/`team_members`/hardcoded `type = 'Team Event'`/`slug` (prefixed with `env('REDIRECT_URL')`)/`description`/`organizationId`/`updated_at` (taken from the external response). **If no local `Team` row matches, the update is silently skipped** (`if ($team) { ... }`) but the endpoint still reports success.
- **Success:** `200 {"message":"Team updated successfully","data":<external "data">}`.
- **Errors:** external failure → external status `{"message":"Failed to update team data.","error":<body>}`; exception → `500 {"message":"Error: ..."}`.

#### `POST /team-members` — `TeamController::AddTeamMember`
- **Request params:** `userId` (local user id, resolved via `User::findOrFail` — **404 via `ModelNotFoundException` → the app's standard "Resource Not Found" 404 shape** if not found), `teamId`, `teamRoleId`.
- **Behavior:** two chained external `GET`/`POST` calls (`POST {MEETING_API_BASE_URL}team-members`, then `GET {MEETING_API_BASE_URL}teams/{teamId}` to fetch the team name for the invite email), then queues **`Mail::to($user->email)->send(new InviteTeamMember(...))`** — note this uses `->send()` (synchronous), not `->queue()`, unlike most other mail in this codebase, so the request blocks on SMTP delivery.
- **Success:** `200 {"status":"success","data":<external "data">,"message":"Team Member Created and Mail Sent Successfully"}`.
- **Errors:** external failure → external status with `[<decoded error body>]` (⚠️ wrapped in an extra numeric-indexed array — `response()->json([$error], ...)`, not `response()->json($error, ...)`, so the body is a **JSON array containing one object**, not the object itself); exception → `500 {"message":"Error: " . $e->getMessage()['message']}` — ⚠️ this line is itself buggy: `$e->getMessage()` returns a string, and indexing a string with `['message']` in PHP either emits a warning and returns an empty/garbled result or (on newer PHP) throws a `TypeError`/`Warning: Illegal string offset` — this catch branch is unlikely to work as intended and may itself error.

#### `GET /my-team` — `TeamController::myTeam`
- **External call:** `GET {MEETING_API_BASE_URL}my-team/{meeting_id}` (only if the caller has a `meeting_id`).
- **Success:** returns the **raw external JSON body directly** (`return $response->json();`) — no envelope at all, whatever shape BookACall returns is what the client gets; if the caller has no `meeting_id`, `200 {"status":"success","data":[],"message":"You are not registered in the Scheduling App yet."}` instead.
- **Error:** external failure → external status `{"message":"Failed to fetch data."}`; exception → `500 {"message":"Error: ..."}`.

#### `GET /get-token` — `TeamController::getToken`
- **External call:** `GET {MEETING_API_BASE_URL}get-token/{meeting_id}`.
- **Success:** `200 {"redirectUrl": "https://scheduling-app-development.lawsikho.dev/manage-calendar?userId={id}&token={email_token}"}` — ⚠️ **hardcoded to the `-development` scheduling-app host**, not environment-configurable; will point at the dev environment from any deployment tier unless this line is changed.
- **Errors:** `401 {"message":"User not authenticated."}` (redundant given the route already requires `auth:sanctum`, effectively unreachable); `404 {"message":"Register in the Scheduling App first"}` if no `meeting_id`; `500 {"message":"Incomplete response data."}` if the external body lacks `id`/`email_token`; `500 {"message":"Failed to retrieve data from the API."}` on external failure; `500 {"message":"Error: ..."}` on exception.

#### `GET /defaultTeamById` — `TeamController::getDefaultTeamById`
- **Request params:** `search` query param (despite the route name, this is a lookup by search term against team ids, not strictly "by id").
- **External call:** `GET {MEETING_API_BASE_URL}teamById?search=...`.
- **Success:** returns the **raw external JSON body directly**, no envelope.
- **Errors:** client/server error passthrough with the external status code, `{"error": "Client error: ..."}` / `{"error": "Server error: ..."}`; unexpected non-successful/non-error state → `500 {"error":"Unexpected error"}`; exception → `500 {"message":"Error: ..."}`.

#### `GET /get-teamMember/{teamId}` (student-side route, but handler lives in the shared `TeamController`) — `TeamController::getTeamMember`
- **External call:** `GET {BOOK_A_CALL_API}get-teammember/{teamId}` (note: this one uses `BOOK_A_CALL_API`, not `MEETING_API_BASE_URL`, unlike most of `TeamController`'s other methods).
- **Success:** `200 {"status":"success","data":<external "data">,"message":"Team Members fetched successfully"}`.
- **Error:** external failure → **always `500`** regardless of the external status code (`{"message":"Failed to fetch team members from third-party API"}}`); exception → `500 {"message":"Error: ..."}`.

#### Dead code in `TeamController` (not routed at all)
`TeamController::createTeam` and `TeamController::deleteTeam` are fully-implemented methods (create/delete a team both locally and via `{MEETING_API_BASE_URL}teams`) but **no route in this file points at either of them** — they are unreachable dead code. `Transformers/TeamResource` is imported into `TeamController` but never invoked anywhere in the module (the `index()` method returns a raw array instead) — an orphaned Resource class per the "only document what's actually wired" rule. `Transformers/EventResource`, `GetEventUserResource`, and `SpecificUserEventResource` are likewise never referenced by any live code path in this module.

### Availability / misc (staff-side)

#### `GET /slots` (also at `student/v1/slots`) — `StudentMeetingController::getSlots` (in `StudentMeetingTrait`)
- **Request params (raw, hand-concatenated, not URL-encoded):** `eventId`, `timeZone`, `startDate`, `endDate`, `delay_time`, `buffer_time`.
- **External call:** `GET {MEETING_API_BASE_URL}slots?...`.
- **Success/Error:** identical shape to `personalMeetingsSlots` above (`{"status":"success","message":"No slots found"}` on empty, else `{"status":"success","slots":[...],"message":"Slots fetched successfully"}`; `{"error":...}` on failure/exception).

#### `GET /team-slots` (also at `student/v1/team-slots`) — `StudentMeetingController::getTeamSlots` (in `StudentMeetingTrait`)
- Same as `getSlots` but adds `teamId` and optional `memberId` to the querystring against `{MEETING_API_BASE_URL}team/slots`.

#### `GET /login-bookcall/{user}` — `EventController::loginToBookACall` (in `EventsTrait`, route-model-bound to `User $user`)
- **Behavior:** builds a scoped permission map from the target user's Spatie permissions, strips the "my meeting management" bucket if the user has no `meeting_id` or isn't `meeting_status == 'Completed'`, then mints a JWT (`Firebase\JWT\JWT::encode`, signed with `env('LMS_SECRET')`, 10-hour expiry) embedding the target user's identity, permissions, and `request()->role`.
- **Success:** the method returns a bare PHP array `['key' => <jwt>]` (no explicit `response()->json()` call) — Laravel auto-converts this to a `200` JSON response `{"key": "<jwt>"}`.
- **Notes:** ⚠️ this reads `request()->role` directly with no validation of what "role" values are legal, and embeds it verbatim into a signed token payload.

#### `POST /import-csv` (named `users.importCsv`) — `BookACAllUtilityController::importUserCsv`
- **Request params:** `csv_file` (multipart file upload).
- **Side effects:** parses the CSV into associative rows (first row = headers) then calls `ImportUsersFromCsv::dispatch($csvData, $userRepository, $userJobRoleMapRepo, $userEmailRepository)`.
- **⚠️ This is a non-functional endpoint in practice:** `ImportUsersFromCsv`'s constructor takes **zero parameters** and its `handle()` method body is **empty**. PHP silently discards the extra arguments passed to `dispatch()` (no error), so the job is queued and will "succeed" on the worker, but it does **nothing at all** — none of the CSV rows are ever processed or written anywhere. The endpoint nonetheless always reports success.
- **Success:** `200 {"message":"User import started successfully."}` (no `status`/`data` keys).
- **Error:** `400 {"error":"No CSV file uploaded."}` if the file is missing. No other validation on the file's contents/headers.

---

## Student routes (`auth:student`, `json.response`, prefix `student/v1`)

Most methods reachable here are already documented above where they're shared with the staff/sanctum group (`getSlots`, `getTeamSlots`, `teamEvents`, `teams`/index, `cancelBooking`, `rescheduleShow`, `teamReschedule`). Only the student-exclusive routes/methods are detailed below; where a route reuses a method from the staff group, only the guard changes.

### `GET /event/{eventId}` — `EventController::getEventUser` — **⚠️ dead route, method undefined.** See module-wide notes.

### `GET /student-meetings` — `StudentMeetingController::studentMeetings` (in `StudentMeetingTrait`)
- **Request params:** `meeting_status` optional (defaults to `"upcoming_calls"` if absent).
- **External call:** `GET {BOOK_A_CALL_API}student/meetings/{studentId}/{channelId}` (channel hardcoded to `"1"`), forwarding the full (merged) request as query params.
- **Success:** returns the **raw external JSON body**, with one local addition — if the external body has a `meta` key, `meta.meeting_accessible` is injected from `Auth::user()->meeting_accessible` before returning.
- **Error:** ⚠️ on external failure, still returns `{"message":"Something went wrong, try again later.","status":"success"}` **with `status: "success"` on an error path**, at the external error's HTTP status code — a client checking only the body's `status` field (as opposed to the HTTP status code) would misread this as a success.

### `GET /student-dashboard-meetings` — `StudentMeetingController::studentDashboardMeetings` (in `StudentMeetingTrait`)
- Same request shape as `studentMeetings` but hits `GET {BOOK_A_CALL_API}dashboard-meetings/{studentId}/{channelId}` and does **not** inject `meeting_accessible`. Same `"status":"success"` on-error quirk as above.

### `POST /booking/create` — `MeetingBookingController::createBooking` (in `MeetingBookingTrait`)
- Already covered in detail in `API_SPECIFICATIONS.md` §5. Additional detail confirmed from source: on the initial scheduling-app call failing with a body shaped `{"status":"error","message":...}`, this endpoint returns **422** with that message (`{"status":"error","data":[],"message":<external message>}`) rather than passing through the external HTTP status — i.e. the first-leg failure is normalized to 422 specifically, while the second-leg (BookACall) failure passthrough uses `$bookACallResponse->status() ?: 422` (external status, or 422 if that status is falsy/zero).
- Batch/course-name resolution: if `type == 'package'`, course name comes from `Package`; otherwise from `Course`. If the request has `courseId`, this also computes `batch_id`/`batch_name` as **comma-joined strings** of every distinct batch the student is enrolled in for that course (not scoped to one specific batch) — sent to BookACall as `batch_id`/`batch_name`.

### `PUT /booking/edit/{bookingId}` (student variant) — `MeetingBookingController::editBooking` (in `MeetingBookingTrait`)
- Already covered in `API_SPECIFICATIONS.md` §5 (the `$response['message']` ArrayAccess-on-Response-object latent bug). Confirmed additional detail: this variant sends `student_comment` (not `instructor_comment`, which is what the staff-side `editBookingInstructor` sends) as part of the second-leg BookACall payload, and calls `{BOOK_A_CALL_API}booking/edit/{id}` (not the `instructor/` prefixed path the staff variant uses).

### `POST /no-show-student/{bookingId}` — `StudentMeetingController::noShowStudent` (in `StudentMeetingTrait`)
- **External call:** `POST {BOOK_A_CALL_API}no-show-student/{bookingId}/{studentId}`, forwarding `$request->all()`.
- **Error:** ⚠️ on external failure, returns `500 {"status":"error","message":"Data Added Successfully"}` — **the message text says success while `status` says error and the HTTP code is 500**; almost certainly a copy-paste mistake, but this is the actual current behavior a parity test must reproduce.
- **Success:** if the external call succeeds and returns a JSON body, that raw body is returned as-is; if it succeeds but the body is falsy/empty, the method **implicitly returns `null`** (no `return` after the `if` block) — an empty 200 response.

### `DELETE /no-show-student-delete/{bookingId}` — `StudentMeetingController::noShowStudentDelete` (in `StudentMeetingTrait`)
- **External call:** `DELETE {BOOK_A_CALL_API}no-show-student-delete/{bookingId}`, forwarding `$request->all()` as the delete body.
- **Success:** `200 {"status":"success","data":<external body>,"message":"No-show record deleted successfully."}`.
- **Errors:** `500 {"status":"error","data":[],"message":"Failed to delete no-show record."}` on external failure; `500 {"status":"error","data":[],"message":"No response received from the API."}` if the (successful) external response has no JSON body; `500 {"status":"error","message":"An error occurred while deleting the no-show record."}` on exception.

### `GET /timezones` — `MeetingBookingController::timezones` (in `MeetingBookingTrait`)
- **Request params:** `first` query param, default `'Asia/Kolkata'`.
- **External call:** `GET {MEETING_API_BASE_URL}timezones?first=...`.
- **Success:** returns the raw external body directly.
- **Error:** `200 {"status":"error","timezones":[],"message":"No timezone found."}` — **error condition returns HTTP 200**, no explicit status code passed.

### `POST /team-booking` — `TeamController::createTeamBooking` (in `TeamTrait`)
- **Request params (raw):** `startTime`/`endTime` (parsed with `timeZone`, converted to UTC), `courseId`, `eventId`, `description`, `teamId`, optional `memberId` (switches the scheduling-app endpoint from `team/bookings` to `team/booking/regular` and overrides the instructor id sent downstream).
- **Two chained external calls**, same pattern as `createBooking`: `POST {MEETING_API_BASE_URL}team/bookings` (or `.../team/booking/regular`) then `POST {BOOK_A_CALL_API}booking/create`.
- **Success:** `201 {"status":"success","data":{...},"message":"Booking created successfully"}` with `start_time`/`end_time` converted to the returned `attendeeTimeZone`.
- **"No slots" case:** `200 {"status":"success","data":[],"message":"No slots found."}` if the first-leg response lacks `data.id` — same 200-not-404 quirk noted for the plain `booking/create` endpoint.
- **Errors:** ⚠️ on the **first-leg** call failing outright (not successful), the message is hardcoded to `"This slots is not available for booking, please try for another time slot."` with `"status":"Error"` (capitalized, unlike the lowercase convention elsewhere) at the external status code — the actual external error detail is logged but not returned to the client. Second-leg failure returns `{"message":"Failed to create booking.","status":"error"}` (lowercase) at the external status code — **inconsistent casing of `"Error"` vs `"error"` between the two failure branches of the same method**.

### `POST /mark-as-complete/{bookingId}` — `StudentMeetingController::markAsComplete` — **⚠️ dead route, method undefined.** See module-wide notes.

### `PUT /meeting/add-rating/{meeting_id}` — `StudentMeetingController::addMeetingRating`
- Already covered in `API_SPECIFICATIONS.md` §5 (returns the raw `Illuminate\Http\Client\Response` object directly on success — confirmed from source, line `return $bookACallResponse;`). Additional confirmed detail: request body is read as `$request->rating` (a single scalar field), re-wrapped as `{'rating': $payload}` before forwarding to `PUT {BOOK_A_CALL_API}meeting/add-rating/{meeting_id}` — any other fields in the request body are silently dropped, not forwarded.

### `GET /reschedule-history/{meetingId}` — `StudentMeetingController::getRescheduleHistory` (in `StudentMeetingTrait`)
- **External call:** `GET {BOOK_A_CALL_API}reschedule-history/{meetingId}`. Returns the raw external body on success; `{"status":"error","message":"Failed to fetch reschedule history."}` at the external status code on failure; `500` with a fixed message on exception.

### `GET /no-show-history/{meetingId}` — `StudentMeetingController::getNoShowHistory` (in `StudentMeetingTrait`)
- Identical pattern to `getRescheduleHistory`, hitting `GET {BOOK_A_CALL_API}no-show-history/{meetingId}` instead.

### `POST /student/review` — `StudentMeetingController::storeStudentReview` — already covered in `API_SPECIFICATIONS.md` §5. Confirmed: `studentId` is appended to the URL path (`{BOOK_A_CALL_API}student/review/{studentId}`), and the entire request body is forwarded as-is.

### `GET /courses/instructor/{courseId}` — `BookACallCourseController::getInstructorsOfCourse`
- **Purely local**, no external call. Resolves the caller's active/paused/resume-requested/pause-requested `Enrollment`s for `courseId`; if the course/package is enrolled, returns instructors mapped to that course via `CourseInstructorMapping` filtered to `User::USER_APPROVED` status, `has_event = HAS_EVENT`, and a non-null `meeting_id`.
- **Success:** `200 {"status":"success","instrucors":[...],"message":"Instructors fetched successfully"}` — ⚠️ note the **misspelled key `instrucors`**; or, if not enrolled, `200 {"status":"success","instructors":[],"message":"No enrollment found for this course or package"}` — ⚠️ **the two branches use different key names for the same concept** (`instrucors` on the found path vs. correctly-spelled `instructors` on the empty path).

### `GET /student/courses` — `BookACallCourseController::getCoursesForStudent`
- **Request params:** `type` (required, must be `course` or `Package` — **case-sensitive, mixed-case for `Package`**; anything else → `400 {"error":"Invalid type. Allowed values are \"course\" or \"Package\"."}`), `package_id` (required only when `type == 'Package'`).
- **Purely local**, no external call — filters the caller's active-family enrollments by type and returns matching `Course` rows with an injected `type` field.
- **Errors:** `404 {"status":"error","data":[],"message":"Student not found"}` (effectively unreachable behind `auth:student`); `400 {"error":"Package ID is required for type \"package\"."}` if `type=Package` with no `package_id`; `404 {"error":"No active courses/bootcamps found for the student.","data":[]}` / `404 {"error":"No enrollments found for the specified package.","data":[]}` on empty results — **⚠️ these two "empty result" cases are documented as 404s here, unlike most other list endpoints in this app which return 200-with-empty-array for no results.**
- **Success:** `200 {"status":"success","courses":[{id,course_name,type},...],"message":"Courses fetched successfully"}`.

### `GET /student/packages/name` — `BookACallCourseController::getPackageNameForStudent`
- **Purely local**, no external call. Reports whether the student has any course/bootcamp enrollment (`{"type":"course","name":"Course/Bootcamp"}`) and lists every distinct package they're enrolled in (`{"type":"Package","package_id","name"}`), combined into one flat array.
- **Success:** `200 {"status":"success","data":[...],"message":"Courses and Packages Fetched successfully"}`.
- **Error:** `404 {"error":"error","data":[],"message":"Student not found"}` — ⚠️ note the **key is literally `"error": "error"`**, not `"status"`, on this one branch (inconsistent with the rest of the same method/controller, which otherwise uses `status`).

### `GET /teams` (student) — same `TeamController::index` documented above.

### `GET /get-teamMember/{teamId}` — same `TeamController::getTeamMember` documented above.

---

## Summary of Resource / Transformer usage

| Class | Used by (live routes) | Notes |
|---|---|---|
| `InstructorResource` | `GET v1/instructors` | Several fields present in source as commented-out dead code — not in the live response. |
| `MemberListResource` | `GET /member-list`, `GET v1/member-list` | |
| `MeetingResource` | `GET v1/meetings/{userId}` | Per-row external HTTP call for `team_title` (N+1). |
| `PersonalMeetingResource` | `GET v1/personal-meetings` | Duplicate `instructor_feedback` key in source (harmless); timezone resolved from a `request()->userId` that this route never sets. |
| `NewTeamResource` | `GET v1/new-teams` | Per-row local DB query for team members (N+1, local not external). |
| `TeamResource`, `EventResource`, `GetEventUserResource`, `SpecificUserEventResource`, `StudentMeetingResource` | **none** | Orphaned — imported/present in the codebase but never invoked by any routed controller method. |

## Endpoint count and confidence

- **70** raw `Route::` declarations counted in `Modules/StudentBookACall/Routes/api.php`; all are documented above (several map to the same controller method under a different guard, which is called out explicitly rather than duplicated in full).
- **8 routes are confirmed non-functional** (undefined controller method → fatal error at call time) and **1 route** (`/import-csv`) is functional-but-a-no-op (queues a job whose body does nothing). These are load-bearing findings for a parity migration — AP‑V3 either needs to reproduce "500 on call" / "silently accepts and discards" for these paths, or the migration scope should explicitly exclude them as known-dead surface.
- **Confidence:** high for request/response shapes and control flow, since every controller and trait method behind a live route was read directly from source rather than inferred. Field-level exactness of the *external* BookACall/scheduling-app response bodies (their own error message strings, exact schema) could not be confirmed from this codebase alone — those are opaque payloads from a separate sub-project and would need that project's own source or a live/staging call to pin down byte-for-byte.
