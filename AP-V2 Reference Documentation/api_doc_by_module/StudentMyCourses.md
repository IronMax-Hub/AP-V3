# StudentMyCourses

Student-facing "my courses" self-service surface: course/enrollment listings (standalone, package, bootcamp), assignment retrieval + submission, CSAT/evaluator-CSAT reason lookups, certificate requests, mock-question Q&A, video ratings, and a global search endpoint. Almost all business logic lives in `Modules\StudentMyCourses\Http\Traits\StudentMyCoursesTrait`, which `StudentMyCoursesController` pulls in via `use StudentMyCoursesTrait;` — the controller class itself only defines `courseListForFilter()` plus five thin pause/resume/migrate wrappers (see the dead-route note below). A second, single-action controller (`StudentGlobalSearchController`) backs `GET /search`.

**Module-wide auth:** every route in this file is under `Route::middleware(['auth:student', 'json.response', 'last.login'])->prefix('student/v1')`. `last.login` is a side-effect-only middleware (`App\Http\Middleware\StudentActivity`) that updates `students.last_login = now()` on every authenticated request (skipped when the request carries header `admin: true`) — it does not gate access. See [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for the `auth:student` 401 shape, standard error shapes, and response-helper style definitions referenced below.

---

## Dead/disabled routes — not documented as live endpoints

`Routes/api.php` has five routes **commented out**: `POST .../pause/{enrollment}`, `POST .../resume/{enrollment}`, `GET .../pause-status/{enrollment}`, `GET .../future-batches/{enrollment}`, `POST .../migrate/{enrollment}`. Their controller methods (`pause`, `resume`, `pauseStatus`, `futureBatches`, `migrate`) and the trait methods they delegate to (`pauseCourse`, `resumeCourse`, `isCoursePausable`, `pauseCourseStatus`, `getFutureBatches`, `migrateToFutureBatch`) are fully implemented in code (course-pause/resume/migrate-to-future-batch workflow with 3/30-day lock windows, refund-eligibility tag check, `EnrollmentPauseLog` audit rows) but **not reachable from any registered route** — confirmed not live in this branch. Do not test these as API endpoints; if AP-V3 exposes equivalent routes, that's new surface, not a reproduction of current behavior.

Also dead: `globalSearch()` in the trait is a full alternate implementation of global search (uses the same repo methods as `StudentGlobalSearchController` but hand-rolled) — **not wired to any route**. The only live global-search endpoint is `GET /search` (documented below), which uses the separate `StudentGlobalSearchController`.

---

## Course / enrollment listings

### `GET /api/student/v1/filter/course`
Course dropdown for filtering, scoped to the logged-in student's own enrollments.
- **Auth:** `auth:student`.
- **Controller method:** `StudentMyCoursesController::courseListForFilter()` (defined directly on the controller, not the trait).
- **Request params (query):** `forProject` (`'Y'`/`'N'`, optional — `'N'` excludes package enrollments via `whereNull('package_id')`; `'Y'` restricts to courses that have a `projects` row); `courseId` (optional, filters to one course).
- **Success response:** `response()->json(['status' => 'success', 'data' => CourseListForFilterResource::collection(...)])`, hand-rolled `response()->json()`. Each item: `{"id": <course_id>, "name": <course_name>}`, deduplicated via `groupBy('course_id')`. Excludes `Enrollment::PENDING` enrollments.
- **Errors:** none handled explicitly; a logged-in student with no enrollments returns `data: []`.
- **Side effects:** none.

### `GET /api/student/v1/student-my-courses/get-course-by-id/{enrollment}`
Single-enrollment detail (route-model-bound `Enrollment`).
- **Auth:** `auth:student`. **No ownership check** — any authenticated student can fetch any enrollment id by guessing/incrementing it; no `student_id` comparison against the caller.
- **Trait method:** `getCourseById(Enrollment $enrollment)`.
- **Success:** `{"status": 1, "error": null, "data": <GetCourseByIdResource>}` — hand-rolled array (not `apiResponse()`). `GetCourseByIdResource` merges most `Enrollment` columns (minus a long exclusion list) plus computed `batch_id`/`batch_name`/`course_id`.
- **"Not found" case:** binding failure on a truly non-existent id 404s before reaching the method (standard `ModelNotFoundException` shape per common conventions); the method's own `$data == null` branch is effectively unreachable since `GetCourseByIdResource::make($enrollment)` never returns null for a bound model — dead defensive code.
- **Side effects:** none.

### `GET /api/student/v1/student-my-courses/get-course-name-by-id/{course}`
- **Auth:** `auth:student`. **No enrollment-ownership check at all** — returns any course's name by id regardless of whether the student is enrolled in it.
- **Trait method:** `getCourseNameById(Course $course)`.
- **Success:** `{"status": 1, "error": null, "data": "<course_name>"}` (bare string, not wrapped in an object).
- **Side effects:** none.

### `GET /api/student/v1/student-my-courses/reasons/{parent_id}`
CSAT reason-picklist lookup for assignment submission feedback.
- **Auth:** `auth:student`.
- **Trait method:** `getCSATFormReason($parent_id)`. `{parent_id}` is a raw path segment, not route-model-bound (no `exists` check).
- **Request params:** none besides the path segment.
- **Success:** `{"data": [...AssignmentCSATFormReasons rows as {id, resp}...], "question": [<parent question row or null>], "error": null, "status": 1}`. ⚠️ **`$parent_id` value is not actually used to look anything up directly** — it's mapped through a hardcoded switch: `1`/`2` → parent `1`; `4`/`5` → parent `14`; anything else (including an invalid id) → default parent `8`. Any garbage `{parent_id}` silently resolves to the "default" reason set rather than erroring.
- **Side effects:** none.

### `GET /api/student/v1/student-my-courses/evaluator-csat/reasons/{parent_id}`
Same shape as above but against `EvaluatorCSATFormReason` and a different mapping: `1`/`2` → `1`; `4`/`5` → `17`; else → default `12`.
- **Trait method:** `getEvaluatorCSATFormReason($parent_id)`.
- Same response envelope, same "any other id falls to default" quirk.

### `GET /api/student/v1/student-my-courses/get-course-criteria/{enrollment}`
- **Auth:** `auth:student`.
- **Trait method:** `getCourseCriteria(Enrollment $enrollment)`. ⚠️ **Explicitly labeled in-code as a dummy stub** (`/** This Is dummy for checking Main code need to be done ass soon as possible */`) — the `$enrollment` parameter is bound but **completely unused**; the method always returns the identical hardcoded payload regardless of which enrollment id is requested.
- **Success:** `{"status": 1, "data": {"bootcampPlag": "N", "min_sub_exe": "12", "min_wri_exe": "5", "weeckly": 0, "written": 1}, "error": null}` — static for every call. `weeckly` is a literal typo in the source key, not a documentation error.

### `GET /api/student/v1/student-my-courses/get-all-enrollments`
- **Auth:** `auth:student`.
- **Trait method:** `getAllEnrollments()`. Scoped to `auth()->user()->id`.
- **Success:** `{"status": 1, "error": null, "data": AllEnrollmentListingResource::collection(...)}`; empty-result branch returns `{"status": 1, "data": [], "error": "Enrollment not found"}` — still `status: 1`.
- **Response shape:** `AllEnrollmentListingResource` merges most `Enrollment` columns plus `batch_id`/`batch_name`/`certificatFile`/`certified` (`Y`/`N`)/`complete`/`course_id`/`course_img`/`course_name`/`mcqVaild`/`passCriteria`/`pkg_name`/`reqForCertificate` (`Y`/`N`).

### `GET /api/student/v1/enrollments` (note: **different** from the above — separate endpoint, similar name)
- **Auth:** `auth:student`.
- **Trait method:** `allEnrollments()`.
- **Request params (query):** `page` (int, for the standalone-course slice only — 20/page), `search` (filters package/bootcamp names or ids via `LIKE`), `rows` (page size for the package/bootcamp Laravel-paginated slices, default 15).
- **Success:** hand-rolled array — **not JSON-wrapped by `response()->json()` at the trait level** (relies on the framework's automatic array→JSON conversion): `{"status": "success", "course": StandAloneEnrollmentResource::collection(...), "library": <paginated data array via .response()->getData()->data>, "bootcamp": <same>}`. `course` uses manual offset pagination (not a `meta.total`), while `library`/`bootcamp` use real Laravel paginators but only the raw `data` array is extracted — **the pagination metadata (`current_page`, `last_page`, `total`, etc.) is discarded**, not exposed to the client at all for this endpoint.
- **Side effects:** none.

### `GET /api/student/v1/enrollments/course`
- **Auth:** `auth:student`.
- **Trait method:** `get_all_enrollments()` (snake_case — distinct method from `getAllEnrollments()`/`allEnrollments()` above; three near-identically-named methods with different behavior, a naming-collision risk worth explicit boundary tests).
- **Request params:** `page` (int, offset pagination, 20/page).
- **Success:** `{"status": "success", "data": StandAloneEnrollmentResource::collection(...), "meta": {"total": <int>, "current": <int>, "perPage": 20}}`.
- **Empty-result case:** `{"status": "error", "data": [], "error": "Enrollment not found"}` — this one **does** flip `status` to `"error"`, unlike most sibling endpoints in this module that keep `status: 1`/`"success"` even when empty.

### `GET /api/student/v1/student-my-courses/get-all-package-enrollments`
- **Auth:** `auth:student`.
- **Trait method:** `getEnrollmentRelatedToPackage()`.
- **Success:** `{"status": 1, "error": null, "data": PackageCourseCountResource::collection(...)}`; empty case keeps `status: 1` with `"error": "Package Enrollment not found"`.

### `GET /api/student/v1/student-my-courses/get-package-enrollments/{package_id}`
- **Auth:** `auth:student`. `{package_id}` is a raw scalar, not route-model-bound.
- **Trait method:** `getPackageEnrollments($package_id)`.
- **Success:** `{"status": 1, "error": null, "data": PackageCourseEnrollmentResource::collection(...), "package_name": <name>}`. ⚠️ **A non-existent `package_id` likely throws** — `$this->packageRepo->findById($package_id)` returning null would make `$package['name']` an error/undefined-index rather than a clean 404, worth a boundary test.
- **Response shape:** each `PackageCourseEnrollmentResource` item computes `enrollment_code`/`enrollment_id`/`count` by internally instantiating `app(StudentMyCoursesController::class)` and calling its own trait methods (`getEnrollmentCode`, `getCount`) per row — N+1 query pattern, not a correctness issue for parity testing but worth knowing if response times matter.

### `GET /api/student/v1/student-my-courses/get-assignments/{enrollment}`
- **Auth:** `auth:student`. No ownership check on `$enrollment`.
- **Trait method:** `getAssignmentsRelatedToEnrollment(Enrollment $enrollment)`.
- **Success:** `{"status": 1, "error": null, "data": AssignmentsDetailsResource::collection(...)}`; empty case keeps `status: 1` with `"error": "Assignments not found"`.

### `GET /api/student/v1/enrollments/{enrollment}/assignments`
Distinct endpoint from the above (snake_case method, different resource, different pagination/ownership behavior).
- **Auth:** `auth:student`.
- **Trait method:** `get_assignments_related_to_enrollment(Enrollment $enrollment)`. **This one DOES check ownership**: `if ($enrollment->student_id !== auth('student')->user()->id)` → `422 {"status": "error", "message": "Unauthorized to do this action", "data": null}`.
- **Request params:** `page` (int, 100/page offset pagination).
- **Success:** `response()->json(['status' => 'success', 'data' => NewAssignmentDetailsResource::collection(...), 'meta' => {'total', 'current', 'perPage': 100, 'course': <course_name>, 'batch': <batch_date>}])`.
- **Note:** the sibling `get-assignments/{enrollment}` route has no ownership check while this one does — an inconsistency worth a dedicated cross-endpoint authorization test.

### `POST /api/student/v1/assignment/{student_assignment}/rate-note/{topicDocDetail}`
- **Auth:** `auth:student`.
- **Trait method:** `rate_note(Request $request, StudentAssignment $studentAssignment, TopicDocDetail $topicDocDetail)`.
- **Request params:** `rating` (required, integer), `comment` (required, string) — validated via inline `$request->validate()` (standard 422 shape from common conventions on failure).
- **Ownership check:** `$studentAssignment->enrollment->student_id !== $student?->id` → `422 {"status": "error", "message": "Note rate unsuccessful! Please try again", "data": null}` (a *misleading* generic message for what is actually an authorization failure, not a general failure).
- **Success:** `{"status": "success", "message": "Note rate successful"}` — creates a `StudentAssignmentVideoMapping` row (despite the "video" name, this is generic note/video-doc rating storage; `topic_doc_details_id` set from `$topicDocDetail`, not necessarily a video).
- **Side effects:** DB insert only.

### `GET /api/student/v1/enrollments/{enrollment}/get_question`
Mock-interview/course question retrieval.
- **Auth:** `auth:student`. `{enrollment}` here is **not** route-model-bound — it's `$enrollment_id`, looked up manually.
- **Trait method:** `getQuestionRelatedToEnrollment($enrollment_id)`.
- **Success (has unanswered questions):** `response()->json(['data' => <MockQuestion question strings>, 'message' => 'success'], 200)`.
- **Success (already answered):** `apiResponse([], 'Question already answered')` → `{"data": [], "message": "Question already answered", "status": "success"}`, still HTTP 200.
- **No questions configured for the course:** `apiResponse([], 'Question is not there for this course')` — same shape, also HTTP 200. **Three distinct outcomes are only distinguishable by `message` text**, not status code or a dedicated flag.
- ⚠️ A non-existent `$enrollment_id` produces `Enrollment::where(...)->first(['course_id','student_id'])` returning `null`; the subsequent `$enrollment['course_id']` array-access on `null` will error rather than a clean 404 — boundary test candidate.

### `POST /api/student/v1/students/question_answer`
- **Auth:** `auth:student`.
- **Trait method:** `storeQuestionAnswer(Request $request)`.
- **Request params:** validated via `Validator::make()` (not a FormRequest class): `question` (required array of strings), `answer` (required array of strings, positionally paired with `question` by array key — no length-match rule enforced beyond both being present), `enrollment_id` (required, integer, `exists:enrollments,id`).
- **Validation failure:** `response()->json(['error' => $validator->errors()], 400)` — **not the standard 422 envelope**; uses `400` and a bare `error` key (no `status`/`message`/`data`).
- **Duplicate-submission check:** if any `MockAnswer` row already exists for `enrollment_id`, returns the **bare string** `'Question answer already submitted for this enrollment'` — not JSON-wrapped, not even an array; Laravel will serialize this as a plain-text/JSON string body with HTTP 200.
- **Success:** `apiResponse([], 'Answer saved successfully', statusCode: 200)` → `{"data": [], "message": "Answer saved successfully", "status": "success"}`.
- **Side effects:** bulk-inserts `MockAnswer` rows via `MockAnswer::insert()` (one per question/answer pair), each stamped with `enrollment->student_id` (not necessarily the caller's own id, since `enrollment_id` is client-supplied and only checked for existence, not ownership) — ⚠️ **no check that the enrollment belongs to the authenticated student.**

---

## Certificate request

### `POST /api/student/v1/student-my-courses/requestForCertificate`
Third distinct certificate-request implementation in this codebase (see `documentation/API_SPECIFICATIONS.md` §5 for the other two, in `StudentFrontendEnrollment` and `Enrollment`).
- **Auth:** `auth:student`.
- **Trait method:** `requestForCertificate()`. No FormRequest — raw `json_decode(file_get_contents('php://input'), true)`.
- **Request params (JSON body):** `enrollment_code` (string, required — looked up via `Enrollment::where('enrollment_code', ...)->first()`, **not** by numeric id); `bootcampId` (optional, read but **never actually used** anywhere in the method body after being extracted — dead variable).
- **Success:** `{"status": 1}`. Sets `enrollment.request_for_certificate = Enrollment::ACTIVE` and saves.
- **Failure ("some issue"):** `{"status": 1, "error": "Some issue occurred"}` — **`status` stays `1` on this branch too**; only the `error` key distinguishes it. In practice this branch is reached only if `$update` (an `Enrollment::find(...)` re-fetch) is falsy, which given the immediately-preceding `->save()` on the same model is effectively unreachable unless the enrollment was concurrently deleted.
- ⚠️ **A non-matching `enrollment_code`** causes `Enrollment::query()->where(...)->first()` to return `null`, then `Enrollment::find($fetch['id'])` array-accesses a null — this throws (likely a 500), not a clean 404. Confirmed by direct code reading; a dedicated boundary test on an unknown `enrollment_code` is warranted.
- **Side effects / external calls:** queues **one email** to the hardcoded address `admin@ipleaders.in` via `Mail::to($adminEmail)->queue(new CertificateRequestMail(...))`. **No email/acknowledgement is sent to the student** — unlike the `StudentFrontendEnrollment` variant, which sends two.

---

## Video / result ratings

### `POST /api/student/v1/student-my-courses/add-video-rating`
- **Auth:** `auth:student`.
- **Trait method:** `addVideoRating()`. No FormRequest — raw `json_decode(file_get_contents('php://input'), true)`.
- **Request params (JSON body):** `student_assignment_id`, `topicId`, `videoUrl` (matched via `LIKE`), `comment`, `ratingId` — all read as direct array-index accesses; a missing key throws an undefined-index warning/error rather than a validation error.
- **Success:** `{"status": 1, "error": null}` on a saved row; `{"status": 1, "error": "Failed to process!Please try again later"}` if the save silently didn't produce an id — **`status` is `1` either way.**
- **Side effects:** creates a `StudentAssignmentVideoMapping` row.

### `POST /api/student/v1/student-my-courses/add-result-video-rating`
- Same pattern as above (`addResultVideoRating()`), raw JSON body: `evaluator_id`, `assign_id`, `courseId`, `id` (→ `result_id`), `comment`, `ratingId`. Creates a `StudentResultVideoMapping` row. Success shape omits `error` key entirely (`{"status": 1}`) rather than `error: null`; failure shape is `{"status": 1, "error": "Failed to process!Please try again later"}` — same "`status` stays 1 regardless" quirk.

---

## Assignment submission (two live implementations)

### `POST /api/student/v1/student-my-courses/submit-assignment/{studentAssignment}` — the real self-service submission endpoint
Full multipart file upload; see `documentation/API_SPECIFICATIONS.md` §4/§5 for the previously-documented core contract (`uploadfile` field, raw `$_FILES` access, no FormRequest, S3 storage under `uploads/assignments/submitted/`, CSAT dedup-check-then-create). This pass adds one significant correction after tracing the code line-by-line:

- ⚠️ **The ">10,000,000 byte" rejection is dead code — it does not actually reject anything.** The check (`if ($_FILES['uploadfile']['size'] > 10000000) { $res = [...]; }`) only assigns to a local `$res` variable; there is **no `return`, `throw`, or `exit` in that branch**. Execution falls straight through into the file-store/CSAT/plagiarism/result-creation logic below, which builds its **own**, separate `$res` inside a `DB::transaction()` closure that does **not** `use ($res)` from the outer scope — so the size-exceeded `$res` is computed and then discarded, never returned to the client. **An oversized file is uploaded to S3 and submitted exactly as a normal one would be**; the only way an oversized upload would actually fail is a lower-level PHP/webserver limit (`upload_max_filesize`/`post_max_size`) rejecting it before reaching this code at all. A parity test asserting a clean in-app rejection for a large file will not observe one from this endpoint — confirm actual behavior against a live/staging instance before hardcoding this assumption into a V3 comparison, since it contradicts what a size limit's presence in the code would suggest.
- **Duplicate-submission guard:** `if ($studentAssignment->status === StudentAssignment::STATUS_SUBMITTED && $pragData['plagiarism_result'] < 40)` → `{"status": 1, "error": "Can not submit an already submitted assignment"}` (still `status: 1`, still HTTP 200).
- **CSAT auto-create:** if no existing CSAT row for this student+assignment+enrollment (or +package), creates one from `$request->rating`/`$request->desc`/`$request->selectedOrderIds` (comma-separated reason ids) as a side effect of the *same* request — no separate endpoint call needed.
- **Success:** `{"status": 1, "data": {"fileData": {...file metadata...}, "plag": {"status": 1, "msg": "success"}}}`. Non-1 plag-processing branch: `{"status": 1, "data": {...}, "error": <plag message>}` — again `status: 1` regardless.
- **Side effects:** S3 upload; `Result` row creation (`Result::ACTIVE` or `Result::RESUBMIT` if plagiarism ≥ 40 — plagiarism checking here calls the internal `checkPlagiarism()`/Unicheck integration, which is live code in this method though the sibling `assignmentSubmit` below has hardcoded it off); `resultExerciseScores` rows per exercise; `StudentAssignment` status flips to `STATUS_SUBMITTED` and `submit_counter` decrements.

### `POST /api/student/v1/enrollments/submit-assignment/{studentAssignment}`
A second, separately-routed assignment-submission implementation with a different field name and different validation posture.
- **Auth:** `auth:student`.
- **Trait method:** `assignmentSubmit(Request $request, StudentAssignment $studentAssignment)`.
- **Request params:** multipart, field **`attachment`** (not `uploadfile`) — **is** validated: `$request->validate(['attachment' => ['required', 'file', new SimpleAllowedFileTypeRule($studentAssignment)]])`, a real 422 on missing/invalid-type file (standard validation-exception shape per common conventions). `adminId` optional (see below).
- **Duplicate-submission guard:** identical logic/message to `submitAssignment` above, but returned via `response([...], 422)` — a real 422 this time, not a 200-with-status-1.
- ⚠️ **Same dead-code size check as `submitAssignment`** — the `$_FILES['attachment']['size'] > 10000000` branch sets a local `$res` that is discarded the same way; oversized files are not rejected by this code path either.
- **Plagiarism check is hardcoded off:** `$plagiarism = false; // added because unicheck has been removed` — the entire Unicheck branch is unreachable dead code left in place; every submission takes the `else` (non-plagiarism) path, which sets `Result::ACTIVE` and computes `evaluation_due_date` via `calculateEvaluationDueDate()` (last date + 7 days, or today + 7 days if the assignment's submission window already passed).
- **`adminId` (optional body field):** if present, after a successful submit an `Activity` log row is created (`Spatie\Activitylog`, `causer_id = adminId`, no verification that this id is a real/authorized admin) recording "submitted on behalf of student". This is a **submit-on-behalf-of-student** code path reachable from the **student-facing** route with no distinguishing auth — any authenticated student can pass `adminId` in the body and it will be trusted verbatim for the activity-log attribution (does not change *whose* assignment is submitted, only the logged causer).
- **Success:** `{"status": "success", "message": "Attachment upload successful"}` — this is the one of the pair with a clean success envelope; the interior failure branch (`$response['status'] != 1`) instead returns `{"status": 1, "data": {...}, "error": <msg>}`.
- **Any exception:** caught at the top level — emails `chhandak@lawsikho.in` and `mayukh.b@lawsikho.in` (hardcoded) via `sendSubmissionErrorEmail()`, then returns `response()->json(['message' => 'some technical issue occured. Please try after some time!', 'status' => 'error'], 500)`.

---

## Result preview

### `GET /api/student/v1/student-my-courses/get-result-preview/{assignment_id}`
- **Auth:** `auth:student`. `{assignment_id}` is a raw scalar, no ownership check.
- **Trait method:** `getResultPreview($assignment_id)`.
- **Success:** `{"status": 1, "error": null, "data": [<StudentResultPreviewResource>]}` — **`data` is an array wrapping a single resource**, not a bare object (note the `[$data]` in source) — a parity test should not assume `data` is directly the result object.
- **Response shape:** `StudentResultPreviewResource` merges most `Result` columns (minus a long exclusion list) plus a computed `feedBackFilePath`.

---

## Global search

### `GET /api/student/v1/search`
- **Auth:** `auth:student`.
- **Controller:** `StudentGlobalSearchController::__invoke()` (single-action, invokable controller — **not** part of `StudentMyCoursesTrait`; injects `StudentGlobalSearchCacheService`, `StudentGlobalSearchRepositoryInterface`, `StudentGlobalSearchFilterService`).
- **Request params (query):** `search` (required, non-empty after `trim()`); `type[]` (any of `course`/`library`/`bootcamp`/`assignment`, or `all`/omitted for all four); `date` (`today`/`this_week`/`this_month`, else unfiltered); `rows` (int, default 15 — caps standalone/library/bootcamp result slices via `array_slice`, **not** a real paginator).
- **Validation failure:** `response()->json(['status' => 'error', 'message' => 'Search term is required'], 422)` — no `data` key.
- **Success:** hand-rolled `response()->json(['status' => 'success', 'enrollments' => {'course': [...], 'library': [...], 'bootcamp': [...]}, 'assignments' => [...]])`.
  - `course` → `GlobalSearchStandaloneEnrollmentResource` (per-enrollment: `enrollmentId`, `enrollmentCode`, nested `course{courseId,courseName,courseImage}`, nested `batch{batchId,batchName}`|`null`, `status`).
  - `library` → `GlobalSearchLibraryEnrollmentResource`, grouped by `package_id` (one row per package with a `courses[]` sub-array).
  - `bootcamp` → `GlobalSearchBootcampEnrollmentResource`, grouped by `bootcamp_id`, same shape pattern.
  - `assignments` → `GlobalSearchAssignmentResource` (`assignmentId`, `enrollmentId`, `assignmentType`, `assignmentStatus` ∈ `Pending`/`submitted`/`evaluated`, nested `topic{id,name}`, `SubmissionLastDate`).
- **Side effects:** reads from `StudentGlobalSearchCacheService` (an enrollment/assignment index cache, presumably per-student, keyed by `auth('student')->user()->id`) — cache staleness (if the underlying cache isn't invalidated on enrollment/assignment changes) could cause search results to lag real data; worth a "create enrollment → search immediately" regression test if parity-testing this endpoint.

---

## `apiResource('student-my-courses', 'StudentMyCoursesController')` — registered but non-functional

`Route::apiResource(...)` registers all seven RESTful routes (`index`, `create`, `store`, `show`, `edit`, `update`, `destroy`) under `/student/v1/student-my-courses`. **None of `index`/`create`/`store`/`show`/`edit`/`update`/`destroy` exist anywhere on `StudentMyCoursesController` or `StudentMyCoursesTrait`** (confirmed by grep — the only trait method matching this naming family is unrelated). Calling any of these seven routes will hit Laravel's "Call to undefined method" runtime error, not a graceful 404/501 — this is different from `StudentDashboardManagement`'s apiResource, whose dead actions at least return an empty body or a Blade view. Do not treat these seven routes as live surface for parity testing; if AP-V3 implements a working `student-my-courses` CRUD API here, that is new functionality with no current-behavior baseline to compare against.

---

## Summary

- **Endpoints documented as live:** 24 named routes + `GET /search` (separate controller) = **25** functioning endpoints, plus the 7-route `apiResource` block confirmed **registered but broken** (undefined controller methods) and 6 confirmed **dead/unreachable** (5 commented-out routes + 1 unrouted `globalSearch()` trait method). Raw `Route::` call count in the file is ~24 explicit calls + 1 `apiResource` line + 5 commented-out (still present as source lines) ≈ the "~29 raw grep hits" cited in scope.
- **Structural surprises:** (1) the assignment file-size rejection is provably dead code in *both* submission endpoints — a meaningful correction to the assumption in the existing `API_SPECIFICATIONS.md`; (2) three different "get all enrollments"-shaped methods (`getAllEnrollments`, `allEnrollments`, `get_all_enrollments`) coexist with different pagination/response shapes; (3) inconsistent ownership checks across near-duplicate endpoint pairs (`get-assignments/{enrollment}` vs `enrollments/{enrollment}/assignments`); (4) a full second global-search implementation (`globalSearch()`) sits dead in the trait alongside the live dedicated controller; (5) the `apiResource` block is pure dead route registration.
- **Confidence:** High for all documented request/response shapes and the dead-code findings — traced directly from the controller, both traits' full source, and the invoked FormRequest/Resource classes. Two items marked with explicit uncertainty inline (the `get-package-enrollments/{package_id}` null-package boundary case, and cache-staleness behavior of the global-search index) were reasoned from code structure but not exercised against a running instance.
