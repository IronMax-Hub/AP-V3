# StudentDashboard

Student-facing dashboard aggregation surface: topper lists, latest-pending-assignments/latest-classes widgets, NPS survey submission, the "dashboard journey" checklist (mark-complete/feedback/rating on onboarding steps), and an Edmingle LMS proxy (calendar, today's classes, announcements, unread counts, join-class). Two controllers back this module: `StudentDashboardController` (thin — composes `StudentDashboardTrait` + the **cross-module** `StudentDashboardManagement\Http\Traits\StudentDashboardManagementTrait`) and `StudentLmsController` (composes `StudentLmsTrait`, plus two of its own real methods: `getStudentCalendar()`, `readStudentAnnouscement()`).

**Module-wide auth:** every route uses `auth:student` + `json.response`. The three route groups in `Routes/api.php` differ slightly: the first (`prefix('v1')` — topperlist/NPS/latest-assignments/apiResource) omits `last.login`; the second and third (`prefix('student/v1')` — Edmingle proxy + journey-step actions) add `last.login`, which only touches `students.last_login` as a side effect (see [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for the shared auth/error/pagination conventions and the `auth:student` 401 shape).

⚠️ **Cross-module trait dependency, confirmed:** `StudentDashboardTrait`'s journey-step methods (`studentJourneyStpes`, `markCompleted`, `addUpdateFeedback`, `addRating`, `markUncompleted`, `deleteFeedback`) call `getSubjectType()`, `calcualteTotalSubSteps()`, and `filterSubSteps()` — none of which are defined in `StudentDashboardTrait` itself. They live in `Modules\StudentDashboardManagement\Http\Traits\StudentDashboardManagementTrait`, which is why `StudentDashboardController` explicitly composes **both** traits (`use StudentDashboardTrait; use StudentDashboardManagementTrait;`). This is real, load-bearing cross-module coupling, not an accident — see the `StudentDashboardManagement.md` file for those methods' definitions.

---

## Topper lists, latest widgets, NPS, journey summary (`prefix('v1')`, no `last.login`)

### `GET /api/v1/student-topperlist-dashboard`
Topper leaderboard for the logged-in student's own most-recent non-bootcamp enrollment.
- **Auth:** `auth:student`.
- **Trait method:** `StudentDashboardTrait::topperlist_logged_student()`. Resolves the enrollment internally via `Enrollment::where('student_id', ...)->where('bootcamp_id', null)->orderBy('id', 'DESC')->first()` — **no enrollment id is taken from the request**; if the student has zero non-bootcamp enrollments: `{"status": 1, "data": [], "error": "No Enrollment Found For this Student"}`.
- **Success:** `{"status": 1, "data": [<course_batch pair>, "list" => [...], "studentPositions" => <int|null>], "error": null}`. `list` entries group students by identical total exercise score (`cnt`)/sum of `obtain_marks`, each with `course_name`/`batch_name`/`fullname`/a hardcoded `"status": "A"` (source comment: `// static, have to change after discussion`). `studentPositions` computation has an accumulation bug: `$pos` is incremented inside the per-result loop without being reset, so with multiple qualifying results it can overcount the caller's rank — treat this field's exact value as unreliable for parity assertions beyond "present when results exist."
- **No-results case:** `{"status": 1, "data": [], "error": "Toppers Not Available"}`.
- **Response shape is NOT `TopperListResource`** — `TopperListResource` is imported by the trait but **never instantiated anywhere** (confirmed via grep); the response is a hand-built nested array. Treat `TopperListResource` as dead/orphaned code.

### `GET /api/v1/student-topperlist-dashboard/{enrollment}`
Same computation as above (`topperlist(Enrollment $enrollment)`), but scoped to an explicit, route-model-bound enrollment instead of "most recent." **No ownership check** — any authenticated student can pass any enrollment id. Identical response shapes/quirks (including the `studentPositions` overcount risk and the dead `TopperListResource`).

### `GET /api/v1/student-dashboard/get-latest-pending-assignments`
- **Trait method:** `getLatestFivePendingAssignment()`.
- **Success:** `{"status": 1, "data": AssignmentsDetailsResource::collection(...), "error": null}` (same `AssignmentsDetailsResource` used by `StudentMyCourses`'s `get-assignments/{enrollment}`); empty case: `{"status": 1, "data": [], "error": "Some error occured"}` (typo preserved verbatim — literal source spelling).

### `GET /api/v1/student-dashboard/get-latest-class/dashboard`
- **Trait method:** `getLatestThreeClass()`.
- **Success:** `{"status": 1, "data": LatestThreeClassResourse::collection(...), "error": null}`; empty case: `{"status": 1, "data": [], "error": "class not found"}`.

### `GET /api/v1/student-dashboard/get-courses-for-assignment-submission`
- **Trait method:** `coursesForAssignmentSubmission()`.
- **Success:** `{"status": 1, "data": CourseForAssignmentSubmissionResource::collection(...), "error": null}`; empty case: `{"status": 1, "data": [], "error": "Assignment not found"}` (misleading message — this endpoint lists eligible *courses*, not assignments).

### `GET /api/v1/student-dashboard/get-courses-list-for-dropdown`
- **Trait method:** `getCoursesListForDropdown()`.
- **Success:** returns `DropDownCourseResourse::collection(...)` **directly** — not wrapped in `{status, data, error}` like its siblings above; Laravel serializes an `AnonymousResourceCollection` as `{"data": [...]}` automatically. This is the only endpoint in this cluster with a bare `{"data": [...]}` envelope instead of the `status`/`error` pattern.

### `GET /api/v1/student-dashboard/nps-survey-data/{enrollment}`
Due-check for whether an NPS survey should be shown to the student for this enrollment.
- **Trait method:** `getSurveyData(Enrollment $enrollment)`. No ownership check.
- **Due (30-day mark, survey type 1):** condition is `$enrollment` has a `StudentAssignment` whose `created_at` is > 30 days old **and** no existing type-1 NPS submission for this enrollment. Response: `{"status": 1, "survey_status": 1, "name", "Email", "courseName", "batchName", "message": "", "course_id", "batch_id", "enrollId", "resones": <all NPSFormReason rows>}` — **`resones` is a literal typo in the live response key, not `reasons`; preserve verbatim in any V3 comparison.**
- **Due (completion, survey type 2), two sub-branches** (MCQ-valid-and-mcq_completed==1, or MCQ-not-required-and-mcq_completed==0), both gated on no existing type-2 submission: same shape with `survey_status: 2`.
- **Not due:** `{"status": 1, "data": [], "error": "survey Not needed "}` — **trailing space in `"survey Not needed "` is literal in source.**
- **`Email`** is capitalized (not `email`) in the due-response shape — verbatim key casing from source, not a typo introduced here.

### `GET /api/v1/student-dashboard/get-package-name-with-course-count`
- **Trait method:** `getPackageNameWithCourseCount()`. Returns `PackageCourseCountResource::collection(...)` directly (bare `{"data": [...]}` envelope, same pattern as `get-courses-list-for-dropdown`).

### `GET /api/v1/check-enrollment/{enrollment}`
- **Trait method:** `check_enrollment(Enrollment $enrollment)`. Re-fetches via `Enrollment::find($enrollment->id)` (redundant given route-model-binding already loaded it).
- **Success:** `apiResponse($enroll, 'Enrollment Found', 'success', 200)` → `{"data": <raw Enrollment model, all columns, no Resource wrapping>, "message": "Enrollment Found", "status": "success"}`. This is the only endpoint in this cluster using the global `apiResponse()` helper with all 4 args passed correctly (both `$status` and `$statusCode` explicit) — contrast with the bug found in `StudentDashboardManagement.md`.
- Since `$enrollment` is already route-model-bound, the internal re-`find()` returning null is unreachable in practice.

### `POST /api/v1/add-nps`
Legacy/v1 NPS submission path — distinct from `NPS` module's `POST /v2/nps` (see `documentation/API_SPECIFICATIONS.md` §5 for that comparison).
- **Trait method:** `storeNPS()`. No FormRequest — raw `json_decode(file_get_contents('php://input'), true)`.
- **Request params (JSON body):** `rating` (int, drives which of three insert branches runs: `>8` → `suggestions` column + `reason:'N'`; `>6` → `experience` column + `reason:'N'`; else → `experience` column + `reason:'Y'`), `answer`, `enrollId`, `courseId`, `batchId`, `surveyType`, `reason` (array of reason ids — iterated to create `NPSFormReasonMapping` rows). All accessed as direct array keys — **a missing key throws an undefined-index error/warning, not a clean validation response.**
- **Success:** `{"status": 1}`; nominal-failure branch (row not created): `{"status": 1, "error": "Some error occurred"}` — **`status` stays `1` on both.**
- **No duplicate-submission check at all** — unlike the `NPS` module's own `/v2/nps` endpoint (which has a `checkIfDuplicate()`, itself separately confirmed buggy).
- **Route-verb note:** only `Route::post('/add-nps', ...)` is registered in the current `Routes/api.php` — **no `Route::get('/add-nps', ...)` exists in this file.** The prior `API_SPECIFICATIONS.md` note ("`GET /api/v1/add-nps` → `POST /api/v1/add-nps`") could not be corroborated against the current route file; treat this route as **POST-only** unless a GET registration is found elsewhere (e.g. an API-version-specific route file not covered by this survey). Flagging explicitly per the "don't fabricate" constraint rather than repeating the unconfirmed claim.

### `apiResource('student-dashboard', 'StudentDashboardController')` — registered but non-functional
Registers `index`/`create`/`store`/`show`/`edit`/`update`/`destroy` under `/v1/student-dashboard`. **None of these seven methods exist** on `StudentDashboardController`, `StudentDashboardTrait`, or `StudentDashboardManagementTrait`(confirmed by grep for `function index`/`store`/`show`/`update`/`destroy`/`create`/`edit` across all three files — zero matches). Calling any of these seven routes throws Laravel's "Call to undefined method" error at runtime; there is no graceful degradation. Same category of finding as `StudentMyCourses`'s dead `apiResource` block — not live, testable surface.

---

## Journey-step student actions (`prefix('student/v1')`, with `last.login`)

These mutate the per-enrollment "dashboard journey" checklist that a student sees/interacts with; the admin-side configuration of what steps exist lives in `StudentDashboardManagement` (separate file). All six share a helper, `updateStep()` (in `StudentDashboardTrait`), which does a `firstOrCreate` on `StudentDashboardJourneyStepsMapping` keyed by `(student_id, subject_id, subject_type, step_id)`.

### `GET /api/student/v1/student-dashboard/student-enrollments`
- **Trait method:** `studentEnrollments()`. Returns all of the caller's `ACTIVE` normal-course, bootcamp, and package enrollments as three parallel collections.
- **Success:** `{"status": "success", "courses": StudentCourseResource::collection(...), "packages": StudentPackageResource::collection(...), "bootcamps": StudentBootcampResource::collection(...)}`. Each resource item: `{"enrollmentId", "id" (course/package/bootcamp id), "name", "steps": <percentage>}` — `steps` is computed per-row by re-invoking `getSubmittedSteps()` (from `StudentDashboardManagementTrait`, imported a second time directly into each of these three Resource classes) — an N+1-style per-enrollment computation.

### `GET /api/student/v1/student-dashboard/student-joureny-steps` (route name has the same typo as the path: `joureny`)
- **Trait method:** `studentJourneyStpes(Request $request)`.
- **Request params (query):** `enrollmentId` (required), `type` (required, `in:course,bootcamp,package`), `subjectId` (required) — validated via inline `$request->validate()`, standard 422 on failure.
- **Success (no journey steps configured for this enrollment):** `{"status": "success", "data": []}`.
- **Success (steps exist):** `{"status": "success", "data": [<formatted step tree, filtered to only steps that have subSteps>], "percentage": <int 0-100>}`. Each top-level step: `{id, title, description, status, mark_highlight, subSteps: [...], isDeleted}`; each substep additionally carries `imageUrl`, `rating`, `comment` (`{id, feedback, created_at, updated_at}` or `null`).
- **Side effects:** read-only.

### `PATCH /api/student/v1/student-dashboard/mark-completed/{stepId}`
- **Trait method:** `markCompleted(Request $request, $stepId)`. `{stepId}` is a raw scalar (not route-model-bound) checked manually via `checkExistStep()`.
- **Request params (body):** `subjectId`, `subjectType` (`course`/`bootcamp`/`package`) — read via `$request->subjectId`/`$request->subjectType` inside `updateStep()`, no formal validation; `enrollmentId` optional.
- **Step-not-found:** `response()->json(['status' => 'success', 'message' => '  Step not found.'], 404)` — ⚠️ **`status: "success"` on a 404**, plus a literal double-leading-space typo in the message (`'  Step not found.'`), both verbatim from source.
- **Success:** `response()->json(['status' => 'success', 'message' => 'Step marked as completed successfully.'], 200)`.
- **Any exception:** `response()->json(['status' => 'error', 'message' => 'An error occurred while updating step.'], 500)`.
- **Side effects:** `firstOrCreate`s/updates the `StudentDashboardJourneyStepsMapping` row to `status = COMPLETED`; writes an `Activity` log row (`addActivityLog`, event `Mark completed`); **dispatches `UpdateSequenceId::dispatch($studentId, $subjectId, $subjectType)`** as a queued job — a real asynchronous side effect that a synchronous parity test won't observe unless the queue is run inline/synced.

### `PATCH /api/student/v1/student-dashboard/add-update-feedback/{stepId}`
- **Trait method:** `addUpdateFeedback(Request $request, $stepId)`.
- **Request params (body):** `feedback` (string); `id` (optional — if present, **updates** an existing `StudentDashboardJourneyComment` by that id instead of creating a new one; if the id doesn't resolve to a real comment, throws an `Exception('Feedback not found')` caught by the generic top-level handler → the same `500 {"status": "error", "message": "An error occurred while updating step."}` shape, which **swallows the more specific "Feedback not found" message** — the client never sees it).
- **Step-not-found / success / error shapes:** identical pattern to `mark-completed` above (same 404 typo, same envelope).
- **Side effects:** creates or updates a `StudentDashboardJourneyComment` (`type = FEEDBACK`); logs an `Activity` row (`add feedback` or `update feedback`).

### `PATCH /api/student/v1/student-dashboard/add-rating/{stepId}`
- **Trait method:** `addRating(Request $request, $stepId)`. Request param: `rating`. Same 404/success/error envelope pattern. Updates `StudentDashboardJourneyStepsMapping.rating`; logs `Activity` (`rating`).

### `PATCH /api/student/v1/student-dashboard/mark-unCompleted/{stepId}`
Route registers the callback as `'markUnCompleted'`; the trait defines it as `markUncompleted` (lowercase `c`) — **functionally identical**, since PHP method dispatch is case-insensitive, but worth knowing the on-disk spelling differs from the route-array literal if grepping for the method name.
- **Trait method:** `markUncompleted(Request $request, $stepId)`. Request param: `reason` (string).
- **Success:** sets mapping `status = NOT_COMPLETED`, creates a `StudentDashboardJourneyComment` (`type = REASON`, `feedback = reason`), logs `Activity` (`mark uncompleted`).
- **Cascading un-complete:** also finds and force-marks-`NOT_COMPLETED` (+ `rating = 0`) every **later** mapped step for the same student/subject via a `where('step_id', '>', ...)->where('step_parent_id', '>', ...)->where('step_parent_sequence_id', '>', ...)->where('step_sequence_id', '>', ...)` compound filter, logging an `Activity` row for each. ⚠️ This compound `>`-chained filter is unusual (ANDs four independent `>` conditions on different columns) — worth a dedicated regression test with a real multi-step dataset to confirm it actually selects "every step after this one" as intended rather than an unintentionally narrow/wrong subset.
- Same 404/500 envelope pattern as the siblings above.

### `PATCH /api/student/v1/student-dashboard/delete-feedback/{stepId}`
- **Trait method:** `deleteFeedback(Request $request, $stepId)`. Request param: `id` (the comment id to delete) — if provided but not resolvable, throws `Exception('Feedback not found')`, again swallowed into the generic 500 message (same pattern as `add-update-feedback`). If `id` is omitted entirely, the method silently does nothing to any comment but still logs an `Activity` row and returns the success shape — **a no-op still reports success.**
- Same 404/success/500 envelope pattern.

### `GET /api/student/v1/student-dashboard/get-opportunities`
- **Trait method:** `getOpportunities(Request $request)`.
- **Request params (query):** `page` (default 1), `perPage` (default 4).
- **Guard:** if `auth()->user()->lms_id` is null → `{"message": "Student does not have LMS ID", "code": 200}` (note: **`code` key, not `status`**, and this is a hand-rolled response, HTTP 200).
- **External call:** GET to `{edmingle_api_endpoint}admin/student/announcement/{lmsId}` with a hardcoded `cf_filter` (a large fixed list of opportunity-category tag names, e.g. "Daily Opportunities", "Legal Jobs", etc. — not configurable per-request) plus `page`/`per_page`. Uses `config('app.edmingle_api_key')` with a **hardcoded fallback key** `3852d91791d0dddbd1f963b8581c9d19` and org id fallback `792` if config values are unset.
- **Success:** raw Edmingle JSON body is returned, with `created_at`/`updated_at` on each `announcements[]` entry reformatted from Unix timestamp to ISO-8601 — response shape is otherwise whatever Edmingle returns (external-proxy caveat per common conventions).
- **Edmingle non-2xx:** returns `$response->body()` directly (raw string, not JSON-wrapped, not this app's error envelope).
- **Any exception:** `response()->json(['error' => $e->getMessage()], 500)`.

---

## Edmingle LMS proxy & generic curl utilities (`StudentLmsController` / `StudentLmsTrait`, `prefix('student/v1')`, with `last.login`)

All of the following are thin proxies to `https://lawsikho-api.edmingle.com/...` (or `config('app.edmingle_api_endpoint')`, same host in practice) — response bodies are whatever Edmingle returns, reshaped minimally where noted. Per common conventions, treat these as external-proxy endpoints: mock at the `Http::`/Guzzle boundary rather than asserting hardcoded live-Edmingle field shapes.

### `GET /api/student/v1/student-dashboard/calendar`
- **Controller method (real, not trait):** `StudentLmsController::getStudentCalendar(Request $request)`.
- **Request params:** `month` (required — validated inline, standard 422 on missing).
- **Delegates to trait:** `getStudentCalendars($month)` — GET `{edmingle_api_endpoint}user/schedule/month` with `apikey`/`ORGID`/`month`/`user_id` (`auth()->user()->lms_id`).
- **Success:** `{"code": 200, "message": "Success"|"No Classes found", "data": CalendarResourse::collection(...)}` — hand-rolled array (not `apiResponse()`/`response()->json()`, relies on automatic array serialization). `CalendarResourse` maps a positional array (`$this[0]`…`$this[13]`) from Edmingle's raw class-schedule rows into named fields (`attendance_id`, `class_date`, `course_name`, `start`/`end` ISO timestamps, `signin_status`, `class_id`, `title`, `tutor_name`, etc.) — **fragile to any change in Edmingle's array column order**, since access is purely positional, not keyed.
- **Edmingle call failure:** caught inside `getStudentCalendars()`, returns `response()->json(['error' => $e->getMessage()], 500)` — but note the *outer* method (`getStudentCalendar`) doesn't special-case this return value, so on this failure path the client actually receives the raw Laravel `JsonResponse` object nested oddly if PHP's array/object handling doesn't error first; not independently verified against a live failure — flagged as an edge case worth a `Http::fake()` test rather than asserted with full confidence.

### `GET /api/student/v1/student-dashboard/today-classes`
- **Trait method:** `getTodayClass()`. Calls `getStudentCalendars(now()->format('m-Y'))` internally, then filters to rows where the row's timestamp element (`$row[1]`) equals the start of today.
- **Side effect (significant):** unconditionally calls `generateEdmingleStudentToken()` **every time this endpoint is hit** — mints a fresh JWT (`Firebase\JWT`, `env('LMS_SECRET')`), calls Edmingle's `/sso?jwt=...` endpoint live, and on success **overwrites** `students.edmingle_api_key` / `students.edmingle_expire_at` for the caller. Repeated test calls will keep rotating the stored token — do not assert token stability across calls to this endpoint, and prefer mocking Edmingle's `/sso` response in tests rather than hitting it live repeatedly.
- **Success:** `{"code": 200, "message": "No Class found for today"|"Success", "data": TodaysClassResourse::collection(...)}` (same positional-array fragility as `CalendarResourse`).

### `GET /api/student/v1/student-dashboard/class-updates`
- **Controller:** `getClassUpdate()` → trait `getClassUpdates()`.
- **No-LMS-id guard:** `{"message": "Student does not have LMS ID", "code": 200}`.
- **External call:** GET `admin/student/pushnotifications/{lmsId}`; reformats each `notifications[].notification_time` from Unix timestamp to ISO-8601.
- **Edmingle non-2xx:** returns the **raw `Illuminate\Http\Client\Response` object** as `$data` (not `->json()`/`->body()`) — unusual return type, worth confirming actual serialized shape in a live/mocked test rather than assuming it degrades to a clean JSON error.
- **Any exception:** `response()->json(['error' => 'An error occurred while processing the request'], 500)`.

### `GET /api/student/v1/student-dashboard/announcements`
- **Controller:** `getStudentAnnouncements(Request $request)` → trait `getAnnouncementsList($request)`.
- **Request params (query, all optional, forwarded via `searchAndFilter()`):** `bundle_ids`, `search`, `read_unread`, `urgency`, `start`+`end` (both required together), `cf_filter` (JSON string, re-encoded/urlencoded before forwarding), plus `page`/`perPage` (default 1/10).
- **No-LMS-id guard / external call / timestamp reformatting:** same pattern as `class-updates`.
- ⚠️ On a non-successful Edmingle response, the method computes `$errorCode`/`$errorMessage` locals but **never returns them or anything else** — the method implicitly returns `null`, which Laravel serializes as an empty body (`null` JSON) with HTTP 200. A parity test expecting an error response from this path will not get one.

### `POST /api/student/v1/student-dashboard/read-annouscement` (route/method name typo preserved verbatim from source)
- **Controller:** `readStudentAnnouscement(Request $request)`.
- **Request params:** `institution_announcement_id` (required — validated inline, standard 422 on failure).
- **Delegates to trait `updateStatus($id)`:** POST to `.../user/announcement/{id}/status` with **hardcoded** `apikey: c4f23d4c1164b4749d18d4e62929e5f1` / `orgid: 792` (not the caller's own per-student Edmingle key) and `Content-Type: text/plain`. Returns Edmingle's raw JSON body directly — no local envelope, no try/catch (an Edmingle-side exception here would surface as an uncaught error, not a graceful 500).

### `GET /api/student/v1/student-dashboard/unread-count`
- **Trait method:** `getUnreadCount()`. GET to `.../institution/user/unread/count` with the **same hardcoded** `apikey`/`orgid` as `read-annouscement` above (not per-student). Returns Edmingle's raw JSON body. No try/catch.

### `GET /api/student/v1/join-class`
- **Trait method:** `joinClass(Request $request)`.
- **Request params (query):** `class_id`.
- **External call:** uses the **caller's own** `Student.edmingle_api_key` (looked up fresh from the DB by `Auth::user()->id`, not the request-scoped user object) — meaning this endpoint depends on the token most recently minted by `today-classes` (or another flow that calls `generateEdmingleStudentToken()`); if that's never been called, `apikey` will be `null` and the downstream Edmingle call will likely fail with an auth error from Edmingle's side.
- **Success:** `{"success": true, "data": <Edmingle response>}`.
- **Non-200 from Edmingle:** `response()->json(['status' => <edmingle status code>, 'message' => 'Error occurred while joining the class. Please try again.'], <same status code>)`.
- **Any exception:** `response()->json(['status' => 422, 'message' => $e->getMessage()], 422)`.

### `POST /api/student/v1/read-announcement` (distinct from `read-annouscement` above — different spelling, different endpoint, different Edmingle call)
- **Trait method:** `readAnnouncement(Request $request)`.
- **Request params (body):** `institution_announcement_id`, `page` (default 1), `perPage` (default 10).
- **No-LMS-id guard:** same `{"message": "Student does not have LMS ID", "code": 200}` shape.
- **External call:** POSTs **form params** (not JSON) to `.../admin/student/announcement/{lmsId}` — the announcement id is embedded as a `JSONString` form field, `apikey`/`ORGID` from config with the same hardcoded fallbacks as elsewhere in this trait. ⚠️ **This posts to what looks like the announcement-listing endpoint, not a dedicated "mark read" endpoint** (contrast with `read-annouscement`'s `.../announcement/{id}/status` URL) — worth confirming with the team whether this genuinely marks anything as read or is effectively a mislabeled re-fetch.
- **Success:** `{"success": true, "data": <Edmingle response>}`; non-200 throws an `UnauthorizedException` (from `Spatie\Permission`, an unusual choice for an HTTP-status condition) which is caught by the same method's own `catch (\Exception $e)` and turned into `response()->json(['status' => 422, 'message' => 'Error fetching announcement data: ' . $e->getMessage()], 422)`.

### `GET /api/student/v1/internal-get-curl` and `POST /api/student/v1/internal-post-curl`
Generic outbound-URL-fetch utilities.
- **Trait methods:** `InternalCurlGetRequest(Request $request)` / `InternalCurlPostRequest(Request $request)`.
- **Request params:** `url` (required — validated inline).
- ⚠️ **`InternalCurlPostRequest` does not actually issue a POST** — despite the method name and the route being `Route::post(...)`, its body calls `$client->get($url)`, byte-for-byte identical to `InternalCurlGetRequest`. Both endpoints are, in current behavior, GET-only proxies regardless of which route is hit.
- ⚠️ **No allowlist/validation on `url` beyond "required"** — this is a same-origin-unrestricted outbound-fetch proxy reachable by any authenticated student (SSRF-shaped surface); worth flagging to the security-review owner separately from pure API-parity concerns, and worth an explicit boundary test (e.g. an internal/private-network URL) if parity-testing this behavior intentionally.
- **Success:** `{"success": true, "data": <decoded JSON body of whatever `url` returned>}`; non-200: `response()->json(['status' => <code>, 'message' => 'Error occurred while Fetching the data. Please try again.'], <code>)`; exception: `response()->json(['status' => 422, 'message' => $e->getMessage()], 422)`.

---

## Summary

- **Endpoints documented as live:** 27 named routes (10 in the `v1` cluster excluding the dead `apiResource`, 6 journey-step actions, 11 Edmingle-proxy/curl-utility routes) + the confirmed-broken 7-route `apiResource` block = matches the "~29 raw grep hits" scope (28 explicit `Route::` calls + 1 `apiResource` line).
- **Structural surprises:** (1) confirmed cross-module trait composition is load-bearing, not incidental — `StudentDashboardController` cannot function without `StudentDashboardManagementTrait`; (2) `TopperListResource` is fully dead/orphaned (imported, never instantiated) — both topperlist endpoints hand-build their response arrays instead; (3) at least three journey-step actions (`add-update-feedback`, `delete-feedback`, indirectly `mark-completed`'s queued job) have failure/edge paths whose specific error text is swallowed into a generic 500 message; (4) `InternalCurlPostRequest` never performs a POST despite its name and route verb; (5) two hardcoded (non-per-student) Edmingle API keys are used for `read-annouscement`/`unread-count`, while `join-class`/`today-classes` use the per-student rotating key — an inconsistency worth knowing before assuming "the app always uses the student's own Edmingle session."
- **Confidence:** High for response envelopes, validation rules, and side effects — traced directly from both controllers and both traits in full, cross-checked against `documentation/API_SPECIFICATIONS.md` §5 (which this file both reuses and, in the `add-nps` GET/POST case, could not fully corroborate — flagged explicitly rather than repeated as fact). Medium confidence on exact Edmingle response shapes and on two flagged edge-case return paths (`getStudentCalendar`'s failure branch, `getClassUpdates`'s raw-Response-object branch) — code-structure-based reasoning, not exercised against a live/mocked Edmingle response.
