# StudentFrontendEnrollment API

Covers every route declared in `Modules/StudentFrontendEnrollment/Routes/api.php` (73 raw `Route::` declarations). This module is the main student-portal-facing surface: enrollment/package/bootcamp listings, task/project boards (proxying a Kanboard instance), certificate request/delivery, five separate CSAT survey flows (class, assignment, evaluator, performance-coach, plus NPS), its own notification inbox, filter/lookup endpoints, and a Zoho Desk-backed student support ticketing system. Unlike `StudentBookACall`, most of this module reads/writes **local** tables directly — external calls are the exception here (Kanboard for tasks, Zoho Desk for support tickets, an internal FCM/campaign-stat service), not the rule.

See [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for the app-wide response envelope, standard error shapes, and pagination conventions. `API_SPECIFICATIONS.md` §2 already covers this module's certificate request/send endpoints in detail (reused, not re-derived, below).

## Module-wide notes

- **Auth:** every route in this file is `auth:student` + `json.response` + `last.login`, except one: `GET /task/{fileId}/download_attachment`, which drops `auth:student` (only `json.response` + `last.login`) — **this one download endpoint is reachable by anyone with a valid `fileId`, no student authentication at all.** `last.login` (middleware alias → `App\Http\Middleware\StudentActivity`) is a **side effect**, not a gate: on every request where `Auth::check()` is true and the request doesn't carry an `admin: true` header, it silently touches `students.last_login = now()` for the authenticated user — this fires on every single request in this file (including reads), so a parity test hitting `students.last_login` as a signal will see it move on GET requests too, not just logins.
- **FormRequest usage is inconsistent by design across the five CSAT-style surveys** (class/assignment/evaluator/performance-coach CSAT, NPS): each has its own near-identical FormRequest class (`rating` 1–10 int required, `comment` nullable, `reasons` array with each id validated `exists:` against that survey's own reason table) — correctly wired for the "new" (`/…-csat/{id}/submit`) routes, but the **five legacy/"previous" routes for the same surveys use no FormRequest at all** (raw `$request->` property access). See each section below.
- **One orphaned FormRequest:** `SubmitStudentAssignmentCSATRequest` exists and validates against `assignment_csat_form_reasons`, but the live `AssignmentCSATController::submit` route actually type-hints `SubmitStudentEvaluatorCSATRequest` instead (which validates `reasons.*` against `evaluator_csat_form_reason` — a different table). `SubmitStudentAssignmentCSATRequest` is dead code, never referenced by any route.
- **Response helper styles are mixed** across this module: some methods return `apiResponse()` (global helper), most hand-roll `response()->json([...])`, and several return a bare PHP array (Laravel auto-serializes a controller method's returned array to a `200` JSON response) — each endpoint below names which.
- **Duplicate route names** exist in the source and are not just cosmetic: `submit_evaluation` is assigned to *two different routes* (`POST /submit-evaluation` and `POST /submit-class-csat`) — Laravel's named-route lookup resolves to whichever was registered last, so `route('submit_evaluation')` anywhere in the app resolves to the **class-CSAT** route, not the evaluator one, even though the evaluator route also declares that name. Likewise `student.projects.tasks.show` is assigned to *three* different routes (`GET /student/projects/{project}/tasks/{id}`, `GET /task/{taskId}/details`, and `POST /task/{taskId}/comment`) — only the last-registered wins for `route()` resolution. These don't break direct URL access, only anything that generates a URL by route name.
- **Confirmed dead/broken routes** (undefined controller method — a live 500 at call time, not a clean error):
  - `GET student/notification/latest_five` → `NotificationController::latest_five` — undefined (the trait has `getLatestFive`, a different name, which is never called by any route).
  - `GET /student/assignment-csat-questions` → `Modules\AssignmentCSAT\Http\Controllers\AssignmentCSATController::getCSATFormReason` — undefined in that class or its trait (methods of this exact name exist only in unrelated modules — `StudentMyCourses`, `EvaluatorCSAT`, `PerformanceCoachCSAT` — none of which this route delegates to).
  - The two `.../tasks/{id}/comments` routes are **not** dead — see the Kanboard section below; `TaskController` mixes in `Modules\ProjectManagement\Http\Traits\ProjectTaskTrait`, which defines both `indexComment` and `storeComment`. (An earlier pass of this document incorrectly flagged them as undefined by checking only this module's own traits — corrected after verifying the cross-module `use kanboardTrait, ProjectTaskTrait;` on `TaskController`.)
- **Cross-module route delegation:** three routes point at controllers that live in a *different* module's namespace, declared here because this route file registers them:
  - `GET /atsapi/get-all-jobs` → `Modules\AtsAPI\Http\Controllers\AtsAPIController::getAllJobs` (real logic in `Modules\AtsAPI\Http\Traits\AtsApiTrait`).
  - `GET /assignment-csat/{student_assignment}` and `GET /student/assignment-csat-questions` → `Modules\AssignmentCSAT\Http\Controllers\AssignmentCSATController` (aliased in the route file as `ControllersAssignmentCSATController`) — a **different class** from this module's own `Modules\StudentFrontendEnrollment\Http\Controllers\AssignmentCSATController`, which handles the `submit` side of the same feature. Don't confuse the two when tracing behavior.
- **Relies on confirmed-deprecated modules:** the PC-CSAT routes (`/call-csat/...`) use `PerformanceCoachCallSchedule` (from `Modules\PerformanceCoach`) and `PerformanceCoachCSATForm`/`PerformanceCoachCSATFormReason` (from `Modules\PerformanceCoachCSAT`) — both modules are on the confirmed-not-in-active-use list elsewhere in this codebase's documentation. The route is declared here and will technically execute if hit, but treat it with the same caution as the deprecated modules themselves (unmaintained, may reference stale schema).

---

## Enrollment, package & bootcamp listings

Module-wide default auth (`auth:student`) applies; no deviations in this section.

### `GET /package` (`student.enrollment.package.name`) — `StudentFrontendEnrollmentController::enrollmentPackageNames`
- **Request params:** `rows` optional int (default 15), `search` optional (matches against package id or name), `page` optional (default 1).
- **Success:** `200 {"status":"success","data":[...EnrollmentPackagesResource...],"meta":{"total","current","perPage"}}`.
- `EnrollmentPackagesResource` fields: `packageId`, `packageName`, `packageImage`, `NumberOfCourse` (int), `is_with_batch` (1/0), `batch_id`.
- **Notes:** query groups by `package_id`, so this lists **distinct packages** the student holds a `PACKAGE_ENROLLMENT`-type enrollment for, not individual enrollment rows.

### `GET /package/{package:id}/enrollments` (`student.package.enrollments`) — `StudentFrontendEnrollmentController::packageEnrollments`
- **Request params:** `package` route-model-bound by id; `rows`, `page`, `search` (matches id/enrollment_code/package or course name), `batchAccess` optional `Y`/`N` filter on whether `batch_id` is set.
- **Success:** `200 {"status":"success","data":[...PackageEnrollmentsResource...],"meta":{"total","current","perPage","packageName"}}`.
- `PackageEnrollmentsResource` fields: `enrollmentId`, `enrollmentCode`, `status` (`Active`/`Paused`/`Inactive` string, mapped from the numeric enum), `course.{courseId,courseName,courseImage}`, `batch` and `courseCompletion` (both **conditionally included only when `batchAccess=Y`** via `$this->when(...)` — absent from the JSON entirely, not null, when that query param isn't `Y`), `exercise.{total,written,subjective}` (written/subjective as `"{done}/{total}"` strings), `is_pausable`, `pause_log`.
- **Notes:** no ownership/ownership-scope issue here since the query is always scoped to `auth('student')->user()->enrollments()`.

### `GET /bootcamp` (`student.enrollment.bootcamp.name`) — `StudentFrontendEnrollmentController::enrollmentBootcampNames`
- Same pattern as `/package` but for `Enrollment::BOOTCAMP_ENROLLMENT` type, grouped by `bootcamp_id`. `EnrollmentBootcampResource` fields: `bootcampId`, `bootcampName` (prefers the `bootcamp` relation's `name`, falls back to the enrollment's own `bootcamp_name` column), `bootcampImage` (always `null` — no image field wired up), `NumberOfCourse` (a live count of the student's **active** enrollments for that bootcamp, recomputed per row, not from the grouped query).

### `GET /bootcamp/{id}/enrollments` (`student.bootcamp.enrollments`) — `StudentFrontendEnrollmentController::bootcampEnrollments`
- **Request params:** `id` (bootcamp id, plain int param — not route-model-bound), `rows`, `page`, `search`.
- **Success:** `200 {"status":"success","data":[...BootcampEnrollmentsResource...],"meta":{"total","current","perPage","bootcampName"}}` — `bootcampName` in `meta` is taken from the **first row** of the (already-filtered) result set, so it can be `null` if the page's first item happens to lack a `bootcamp_display_name`, even if later rows have one.
- `BootcampEnrollmentsResource` adds `writtenAssignment` (`Y`/`N` — cross-references a same-bootcamp "writing" course enrollment, sharing logic with `progress_status` below) on top of the same fields as `PackageEnrollmentsResource`, and `batch`/`courseCompletion` are **always included** here (no `batchAccess` gate, unlike the package variant).
- **Ordering:** custom `ORDER BY` — batches with a null `start_date` sort last, active-status enrollments sort before others, then ascending by `start_date`.

### `GET /enrollments/{enrollment}/task` (`student.enrollment.tasks.index`) — `StudentFrontendEnrollmentController::enrollmentTasks`
- **Auth:** route-model-bound `Enrollment`; **ownership check** — `422 {"status":"error","message":"Unauthorized to do this action","data":null}` if `enrollment.student_id` doesn't match the caller (a 422 used for what's semantically a 403, consistent with the pattern already noted in `API_SPECIFICATIONS.md` §2).
- **Behavior:** if the enrollment is package-type-with-no-batch, returns an empty task list immediately. Otherwise **`$tasks = collect()` — always an empty collection**; there is no actual task-fetching logic in this method despite its name. This endpoint is effectively a stub that always returns `data: []` (with course/batch/package/bootcamp names in `meta`) for any enrollment that has a batch.
- **Success:** `200 {"status":"success","data":[],"meta":{"course","batch","package","bootcamp"}}` — always empty `data`, in every code path.

### `GET /enrollments/{enrollment}/faq` (`enrollment_faqs`) — `StudentFrontendEnrollmentController::enrollment_faqs` (logic lives in `CourseAssignmentTrait`)
- Same ownership 422 as above. Cursor-independent offset pagination via `page` (20/page, computed manually as `offset = page*20-20`, not Laravel's built-in paginator). Backed by `stdFrnEnrRepo->getFaqs()`; `CourseResource` strips `course_id`/timestamps/`id`/`status` and renames `question` → `questions`.
- **Success:** `200 {"status":"success","data":[...CourseResource...],"meta":{"total","current","perPage","course","batch","package":null,"bootcamp":null}}` (or a package-with-no-batch short-circuit, same shape with empty `data`/zeroed `meta`).

### `GET /course-faqs-student/{course_id}` (`course_faqs`, legacy) — `StudentFrontendEnrollmentController::course_faqs` (`CourseAssignmentTrait`)
- **No ownership check** (takes a raw `course_id`, not an `Enrollment`) — any authenticated student can pull any course's FAQs regardless of enrollment.
- **Response style:** returns a **bare PHP array**, not `response()->json()`: `{"status":1,"error":null,"data":[...]}` on results, or `{"status":1,"data":[],"error":"Data not available"}` if empty — note `status` is the **integer `1`** here (not the string `"success"` used by the non-legacy sibling above), and there is no HTTP-level error status for "not available", just a 200 with an `error` string.

### `GET /enrollments/{enrollment}/toppers` (`toppers_list`) — `StudentFrontendEnrollmentController::toppers_list` (`CourseAssignmentTrait`)
- **No explicit ownership check in this method** (unlike most other `{enrollment}`-scoped routes in this file) — relies entirely on `stdFrnEnrRepo->getTopperListData()` being correctly scoped; worth a boundary test with another student's enrollment id.
- **Success:** `200 {"status":"success","data":[{rank,submission,students:[{name}]}...],"meta":{course,batch,package,bootcamp}}` (top 5 distinct exercise-score tiers); `200 {"status":"error","data":[],"meta":{...}}` if no results — ⚠️ note this "no data" case uses `status: "error"` at HTTP 200, an inversion of the usual "error status but still 2xx" pattern seen elsewhere (here the *shape* says error while nothing actually went wrong, it's just empty).

### `GET /topper-list-student/{course}/{batch}` (`topper_list`, legacy) — `StudentFrontendEnrollmentController::topper_list` (`CourseAssignmentTrait`)
- Route-model-binds both `Course` and `CourseBatch` directly, **no ownership/enrollment check at all**. Returns a bare array `{"status":1,"data":[...],"error":null}` or `{"status":1,"data":[],"error":"Toppers Not Available"}`. Internally re-derives `course`/`batch`/`student` per result row via nested `whereRelation` chains rather than joining — a heavier/more indirect version of the same "toppers" concept as `/enrollments/{enrollment}/toppers`, with materially different grouping logic (buckets by raw exercise count, not percentile rank).

### `GET /enrollments/{enrollment}/results` (`enrollment_result`) — `StudentFrontendEnrollmentController::enrollment_result` (`CourseAssignmentTrait`)
- **⚠️ No ownership check at all** — takes any `{enrollment}` id and returns its results with no `student_id` comparison against the caller. This is the one clear authorization gap found in this module; every sibling `{enrollment}`-scoped endpoint in the "new" route block does check ownership, this one doesn't.
- Manual offset pagination (20/page). `NewStudentResultResource` (see full field list below under Resources) via `stdFrnEnrRepo->getEnrollmentResult()`.
- **Success:** `200` bare array `{"status":"success","data":[...],"meta":{total,current,perPage,course,batch}}`.

### `GET /result-listing/{enrollment}` (`result_listing`, legacy) — `StudentFrontendEnrollmentController::result_listing` (`CourseAssignmentTrait`)
- Also **no ownership check**. Uses `StudentResultResource` (a much larger/older field set — see Resources section) via `stdFrnEnrRepo->getResult()`. Bare-array response `{"status":1,"data":[...],"error":null}` or `{"status":1,"data":[],"error":"result not found"}`.

### `GET /student/getcalendy/{course}` (`student.getcalendy`) — `StudentFrontendEnrollmentController::getcalendy` (`CourseAssignmentTrait`)
- Route-model-binds `Course`, **no enrollment/ownership check** — any student can query calendly links for any course id. Builds a fixed 6-row array (Coach, Subjective Evaluator, Writing Evaluator, Placements Team, Writing Coach, Freelancing Team), each entry populated only if the course has that role assigned; ⚠️ if a role is *not* assigned, the code still does `$roleVar['type'] = '...'; array_push($data, $roleVar)` using whatever `$roleVar` held from a **previous loop iteration** (a stale/leftover PHP variable, since it's never reset to `[]` when the `if` is skipped) — rows can end up with a mismatched name/link belonging to a different role than their `type` claims. Returns bare array `{"status":1,"data":[...6 entries...],"error":null}`.

### `GET /enrollments/{enrollment}/calendy` (`student.getcalendyData`) — `StudentFrontendEnrollmentController::getcalendyData` (`CourseAssignmentTrait`)
- The "fixed"/newer version of the above: same 6 roles, but only pushes a row when that role **has a non-null `calendly_link`** (no stale-variable bug here), and includes `id`/`email`/`phone` per person, plus a `role` label. No ownership check on `$enrollment` either — resolves the course purely from `enrollment.course_id`.

### `GET /student/getStudentCourseBatch` (`student.getStudentCourseBatch`) — `StudentFrontendEnrollmentController::getStudentCourseBatch` (`CourseAssignmentTrait`)
- **⚠️ Likely broken as written:** builds a query with `leftJoin('projects as p1', ...)`/`leftJoin('projects as p2', ...)` but references `whereNotNull('p1.kan_project_id')`/`whereNotNull('p2.kan_project_id')` **before** those joins are added in the method chain (PHP evaluates the `->where...` calls in source order, and Eloquent applies `whereNotNull` referencing an alias that hasn't been joined yet at that point in the chain) — this will either throw a SQL error (unknown column/alias) or silently produce no matches depending on the DB driver's query-builder behavior; worth a direct regression test against a real DB rather than assuming the "happy path" in the code comments works.
- Returns bare array `{"status":1,"error":null,"data":[...ProjectEnrolmentResource with computed course_batch_name/courseId/batchId...]}`.

### `GET /enrollments/{enrollment}/progress-status` (`student.progress-status`) — `StudentFrontendEnrollmentController::progress_status`
- Same ownership 422 as `enrollmentTasks`. Computes pending subjective/written exercise counts and pass thresholds, with special-cased logic for bootcamp enrollments that cross-reference a sibling "writing" course enrollment in the same bootcamp (course category id `8`).
- **Success:** bare array `{"status":"success","data":{pendingSubjectiveExersise,pendingWrittenExersise,SubjectiveExersiseToPass,WrittenExersiseToPass}}` — ⚠️ note the **misspelled key `Exersise`** used consistently throughout this response (not a typo to "fix" in a parity test — it's the actual live field name).

---

## Certificates

Already detailed in `API_SPECIFICATIONS.md` §2 (`request-for-certificate`, `send-certificate`) — reused here without re-deriving. Confirmed from source: `enrollmentRequestForCertificate` additionally writes an `activity()` log entry (`event('Student Requested for Certificate!')`) and queues two emails via `->queue()` (not `->send()`): `CertificateGenerate` to the student, `CertificateGenerateAdmin` to a hardcoded `support@lawsikho.in`. `sendCertificate` queues a **third**, differently-shaped `CertificateEmail` (from the `CourseCompletionMaster` module) built from `student_name`/`course_name`/`batch_name`/`enrollment_code`/`certificate_link`/`certificate_path` — a different mail class from either of the two used by the request endpoint, worth noting since three certificate-related emails exist in the codebase across two "implementations" of certificate handling (this module's, plus the third path already documented in `API_SPECIFICATIONS.md` §5 under `StudentMyCourses`).

---

## Assignment submission & task/project board (Kanboard proxy)

All routes in this section proxy a self-hosted Kanboard instance over JSON-RPC (`http://kanboard.lawsikho.in/jsonrpc.php`, HTTP Basic Auth via `KANBOARD_USERNAME`/`KANBOARD_SECRET`), via `kanboardTrait`/`ProjectTaskTrait` (from the `ProjectManagement` module, mixed into `TaskController`). Kanboard's own JSON-RPC error/success shapes are opaque to this codebase and not re-derived here.

### `GET /students/tasks/{course_id}/{batch_id}` (`students.enrollment.tasks.index`, legacy) — `TaskController::index`
- **No FormRequest.** Looks up the `Project` for that course/batch, checks the caller is a Kanboard group member, then fetches columns + assignee-filtered tasks, enriching each task with a resolved `category_name` and a Kanboard-file `downloadLink`.
- Returns a **bare array**: `{"data":{columns,projectDetails,tasks},"status":1}` on success; `{"status":1,"data":[],"error":"Don't have kanboard project access."}` or `{"status":1,"data":[],"error":"Don't have kanboard access."}` on the two failure branches — **all three cases are HTTP 200**, differentiated only by the `error` key's presence.

### `GET /student/projects/{project}/tasks/{id}` (`student.projects.tasks.show`) — `TaskController::show`
- Fetches one Kanboard task + its comments + attachments. On a Kanboard `RequestException` for either the task or comments call, returns `{"status":1,"data":[],"error":"kanboard <method> api is not working"}` (bare array, 200). Success: `{"data":{...task+comments+attachments...},"status":1}`.

### `GET /task/{taskId}/details` (`student.projects.tasks.show`, duplicate name — legacy) — `TaskController::show_task`
- A heavier version of `show`: additionally resolves category name, project name/id, column-derived `status` label, and splits attachments into `admin_attachments` vs `student_attachments` (student-uploaded files are identified by matching filenames against local `ProjectTaskStudentFiles` rows — a name-based heuristic, not an id/foreign-key link). Each file's `path` is a locally-generated `route('student.projects.tasks.download_attachment', $fileId)` URL (note: this uses the download route documented below, which itself requires **no student auth**).
- **Response style:** actual `response()->json()` here (unlike `show`), `200 {"data":<trimmed task fields incl. comment/attachments>,"status":"success","meta":{course,batch,project}}`.
- **Edge case:** the local `$project` variable is only assigned inside the `if ($response['project_id'])` branch, via `Project::where('kan_project_id', ...)->firstOrFail()` — if no local `Project` row matches, `firstOrFail()` throws `ModelNotFoundException` (not a `RequestException`, so **not** caught by this method's `catch` block), surfacing as the app's standard 404 "Resource Not Found" shape (see conventions doc). If `project_id` itself is falsy, `$project` is never assigned at all, and the later `$project->course_id`/`$project->course->course_name` accesses become "read property on null" (PHP 8 warnings, not fatal — the fields resolve to `null` in the response) rather than a clean error.

### `POST /student/projects/{project}/tasks/{id}` (`student.projects.tasks.attachment.update`) — `TaskController::update`
- **Request params (`UpdateProjectTaskRequest` — a FormRequest from the `ProjectManagement` module, not this one; not re-derived here):** `name`, optional `description`/`category_id` (fall back to the current Kanboard values if omitted), `time_estimate`, optional `attachment` file.
- **Side effects:** updates the Kanboard task via JSON-RPC; if an `attachment` is present, **removes all existing task files first** (`removeAllTaskFiles`) then uploads the new one (base64-encoded) — this is a **replace-all, not append**, semantics worth calling out since the route name ("attachment.update") suggests a single-attachment add.
- **Success:** `apiResponse('', 'Task updated successfully')` — the global helper, `200 {"data":"","message":"Task updated successfully","status":"success"}`.

### `POST /student/projects/{project}/tasks/{id}/change-column` (`student.tasks.change-column`) — `TaskController::changeTaskColumn` (defined in `ProjectTaskTrait`, **not** on `TaskController` itself)
- **Request params (`UpdateTaskColumnRequest`, from `ProjectManagement`):** `column_id` required integer min:1. (Note: despite the route/method being named "...FromFrontend"-adjacent in the sibling legacy route below, this modern endpoint actually uses the **plain** `UpdateTaskColumnRequest`/`column_id`, not `UpdateTaskColumnFrontendRequest`/`columnId` — see the legacy route for that one.)
- **Behavior:** calls `moveTaskPosition($taskId, $project->kan_project_id, $request->get('column_id'))` directly — no internal try/catch around the Kanboard call in this method itself (its docblock declares `@throws RequestException`), so a Kanboard failure here is **not** caught locally and propagates to the app's generic exception handler (unlike the legacy route below, which does catch it).
- **Success:** `apiResponse('', 'Task column position changed successfully')` — global helper, `200 {"data":"","message":"Task column position changed successfully","status":"success"}`. No 422/failure branch exists in this method at all — it always returns success if `moveTaskPosition` doesn't throw.

### `POST /task/{task}/column-change` (`student.change-task-column`, legacy) — `TaskController::taskColumnChange` (this module's own method, not the trait's)
- **Request params (`UpdateTaskColumnFrontendRequest`):** `columnId` (camelCase) required integer min:1 — the field-name/casing difference from the modern route's `column_id` (snake_case) is real, not a typo.
- **Behavior:** fetches the Kanboard task first, resolves the local `Project` from the task's `project_id`, then delegates to the trait's `changeTaskColumnFromFrontend($request, $project, $taskId)` (a *different* trait method from the one behind the modern route above) and branches on its return value.
- **Response style:** bare PHP array returns (not `response()->json()`) for two of the three branches.
- **Success:** bare array `{"status":"success","message":"Column Change Successful"}`.
- **Errors:** `response([...], 422)` → `{"status":"error","message":"Column change unsuccessful! Please try again"}` if `changeTaskColumnFromFrontend` returns falsy — ⚠️ **this branch is dead code in practice**: `changeTaskColumnFromFrontend` always `return apiResponse(...)`, and a `JsonResponse` object is always truthy in PHP regardless of its content, so `if ($update)` can never be false unless `changeTaskColumnFromFrontend` throws instead (in which case it's caught by the outer `catch`, not this `else`) — the 422 path is unreachable under normal execution. On a Kanboard `RequestException` (from either the initial `getTask` call or from `moveTaskPosition` inside `changeTaskColumnFromFrontend`, since the outer `try` wraps both), bare array `{"status":1,"data":[],"error":"kanboard getTask api is not working"}` at an **implicit 200** (the error message is hardcoded to mention `getTask` even when the real failure came from `moveTaskPosition`). ⚠️ Also note: if `$response['project_id']` is falsy or no matching local `Project` is found, the method falls through both `if` blocks with **no `return` at all** — an implicit `null` return, which Laravel renders as an empty `200` body.

### `GET /student/projects/{project}/tasks/{id}/comments` (`student.tasks.comments.index`) — `TaskController::indexComment` (defined in `Modules\ProjectManagement\Http\Traits\ProjectTaskTrait`, mixed into `TaskController` via `use kanboardTrait, ProjectTaskTrait;`)
- **No FormRequest** — `Project $project` (route-model-bound, unused inside the method body itself beyond being required by the signature) + raw `$taskId`.
- **External call:** Kanboard `getAllComments($taskId)` via the mixed-in `kanboardTrait`.
- **Success:** `apiResponse(['comments' => $response->json('result')])` — global helper, `200 {"data":{"comments":<kanboard result>},"message":"Success","status":"success"}`.
- **Error:** on a Kanboard `RequestException`, `apiResponse('', 'kanboard get all comments api is giving error', 500)` — ⚠️ same **argument-position bug** as `download_attachment` below: `$status` (3rd positional param, typed `string`) receives the int `500` (PHP coerces it to the string `"500"` in non-strict mode), while `$statusCode` (4th param) keeps its default `200` — so this "500" error is actually served as **HTTP 200** with `"status":"500"` in the body, not a real 500.

### `POST /student/projects/{project}/tasks/{id}/comments` (`student.tasks.comments.store`) — `TaskController::storeComment` (same `ProjectTaskTrait`)
- **Request params (`StoreTaskCommentRequest`, from `ProjectManagement` — note: this is the plain/staff-oriented comment request, not `StoreTaskCommentStudentRequest`):** `content` required string. ⚠️ Field name is **`content`**, not `comment` — easy to confuse with the sibling legacy route `POST /task/{taskId}/comment` below, which uses `StoreTaskCommentStudentRequest`'s `comment` field instead.
- **Behavior:** fetches the Kanboard task, then posts a comment authored as `auth()->user()->kanboard_id` — ⚠️ **uses the default auth guard (`auth()->user()`), not `auth('student')->user()`**, unlike most student-scoped writes elsewhere in this module. Since the route is gated by `auth:student` middleware only, whether the default guard also resolves a user here depends on the app's `auth.defaults.guard` config and whatever other guard state exists on the request — worth a dedicated boundary test to confirm this doesn't resolve to `null` (which would throw on `->kanboard_id`) in a real student-only request context.
- **Side effects:** dispatches `SendEmailsToMentorsOnTaskCommentAdded` (only if the project has mentors) and unconditionally dispatches `SendEmailsToStudentsOnTaskCommentAdded`.
- **Success:** `apiResponse('', 'Comment created successfully')` → `200 {"data":"","message":"Comment created successfully","status":"success"}`.
- **Errors:** same `apiResponse('', '<message>', 500)` argument-position bug as above (effectively HTTP 200, not 500) on either Kanboard call (`getTask`/`createComment`) throwing `RequestException`.

### `POST /task/{taskId}/comment` (`student.projects.tasks.show`, duplicate name — legacy) — `TaskController::add_task_comment_student`
- **Request params (`StoreTaskCommentStudentRequest`, from `ProjectManagement`):** `comment` required string (no length limit in the rule).
- Delegates to the trait's `storeCommentStudent($request, $project, $taskId)` (posts the Kanboard comment as `auth()->user()->kanboard_id` — default guard, not `auth('student')`, same nuance as the other comment-store route above), then branches on its return value.
- **Success:** bare array `{"status":"success","message":"commenting successful"}`.
- **Errors:** `response([...], 422)` → `{"status":"error","message":"Commenting unsuccessful! Please try again"}` if `storeCommentStudent` returns falsy — ⚠️ **dead code, same as `changeTaskColumn`'s analogous branch**: `storeCommentStudent` always `return apiResponse(...)` (a `JsonResponse`, always truthy), so this branch can only be reached if it throws instead, which is caught below, not here. `response([...], 422)` `{"status":"error","message":"kanboard getTask api is not working"}` on a `RequestException` — this one *does* correctly return 422 on the Kanboard-exception branch, unlike `changeTaskColumn`/`taskColumnChange` above which fall back to implicit 200 for the same exception type. **This inconsistency (some Kanboard-exception catches return 422, others return implicit 200) recurs across this whole controller — check the specific method, don't assume a uniform status code for "Kanboard is down."**

### `GET /filter/project/{course}` — `TaskController::getProjectByCourse`
- Route-model-binds `Course`. Filters Kanboard-linked `Project` rows down to ones the student has a batch-matching enrollment for. Bare array `{"status":"success","data":[{id,name},...]}` or `{"status":"error","data":[]}` if none match — **no HTTP-level distinction between "found" and "not found", both 200.**

### `GET /task/{fileId}/download_attachment` (`student.projects.tasks.download_attachment`) — `TaskController::download_attachment`
- **Auth: `json.response` + `last.login` only — no `auth:student`.** This is the one route in the entire module reachable without student authentication (see module-wide notes). Anyone who can guess/obtain a Kanboard file id can download that file.
- Fetches file metadata + content from Kanboard, writes it to a temp file under `storage_path('tmp')`, and streams it back via `response()->download(...)->deleteFileAfterSend(true)`.
- **Errors:** `apiResponse('', '<message>', 500)` on either Kanboard call throwing `RequestException` — ⚠️ note the **positional-argument mismatch**: `apiResponse($data, $message, $status)` expects `$status` to be a *string* (default `'success'`) per its signature in `app/Helpers/functions.php`, but this call passes the integer `500` into that third `$status` positional slot, not a fourth `$statusCode` slot — meaning **the response is not actually being set to HTTP 500** (it defaults to the helper's own default `200`, and the literal integer `500` ends up serialized into the JSON body's `status` field instead of setting the HTTP code). A parity test expecting an HTTP 500 on Kanboard failure here will find a 200 instead. Also: `response()->json(['status'=>'error','message'=>'File not found'])` (no explicit code → 200) if the Kanboard file lookup itself reports `false`.

---

## Class CSAT

### `GET /class-csat/{classCode}` (`student.class-csat.questions`) — `ClassCSATController::classCSATFormReason`
- **Request params:** `classCode` (base64-encoded `ClassOccurranceDate` id).
- **Ownership check:** confirms the caller participated in that class occurrence; `200 {"status":"error","message":"Student doesn't belongs in this class"}` if not (note: **200, not 403/404**, for an authorization failure).
- **Success:** `200 {"status":"success","course","package","class","Expert", "lowRateOptions":{question,options},"midRateOptions":{...},"highRateOptions":{...}}` — `course`/`package`/`Expert` are comma-joined name strings, not arrays; note the **capitalized key `Expert`** amid otherwise-lowercase keys.

### `POST /class-csat/{classCode}/submit` (`student.class-csat.submit`) — `ClassCSATController::submit`
- **Request params (`SubmitStudentClassCSATRequest`):** `rating` (1–10 int, required), `comment` (nullable string, max 255), `reasons` (required array, each `exists:class_csat_form_reason,id`).
- **Duplicate-submission check:** `422 {"status":"error","message":"Class CSAT already submitted","data":null}` if a `ClassCSATForm` already exists for this class+student.
- **Side effects:** creates one `ClassCSATForm` row plus one `ClassCSATFormReasonMaping` row per submitted reason, in a DB transaction.
- **Success:** `200 {"status":"success","message":"Class Rating Successfully"}`.

### `GET /check-eligibility-class-csat/{class_occurance_date_id}` (legacy, no FormRequest) — `ClassCSATController::check_eligibilty` (`ClassCSATTrait`)
- **Request params:** path param is actually a **base64-encoded** class-occurrence id (despite its plain-looking name), decoded internally.
- Returns a bare array in every branch, always `"status":1`, differentiated only by `error`: `{"status":1,"data":ret_var,"error":"Error"}` if the student isn't a participant or already submitted (⚠️ **the literal string `"Error"` is used as a generic marker here, not a real error description** — both "not a participant" and "already submitted" share this same generic `error` value, only `data.msg` differs); `{"status":1,"data":[$final_data],"error":null}` on eligible; `{"status":1,"data":[],"error":"Sorry!!! Some Error Occured"}` as a catch-all if the class lookup itself fails.

### `GET /student/class-csat-questions/{parent_id}` (`class-csat.questions`, legacy) — `ClassCSATController::questions` (`ClassCSATTrait`)
- **No auth-relevant logic** — pure lookup keyed by a hardcoded mapping (`parent_id` 1 or 2 → question-group 1; 4 or 5 → group 26; anything else → group 12). Bare array `{"data":[...],"question":[...],"error":null,"status":1}`.

### `POST /submit-class-csat` (named `submit_evaluation` — **duplicate name**, legacy) — `ClassCSATController::submit_class_csat` (`ClassCSATTrait`)
- **No FormRequest** — raw `$request->rating`/`$request->details`/`$request->otherComment`/`$request->reason` (array). **No duplicate-submission check at all** (unlike the "new" `submit` endpoint above) — a student can submit this legacy path repeatedly for the same class.
- `classDateRelId` is read from the request and base64-decoded before being stored as `class_date_relation_id`.
- **Success:** bare array `{"status":1,"data":"successful","error":null}`; note the success-detection in source (`if ($data)`) is checking the *transaction's return value* (the created row's id), so `data` will only ever read `"Unsuccessful"` if the DB insert itself returned a falsy id — in practice this branch is effectively unreachable under normal DB behavior.

---

## Assignment CSAT

### `GET /assignment-csat/{student_assignment}` (`student.assignment-csat.questions`) — cross-module: `Modules\AssignmentCSAT\Http\Controllers\AssignmentCSATController::getAssignmentCSATFormReason` (via `AssignmentCSATTrait` in that module, not this one)
- Route constrained to numeric `student_assignment`. Not re-derived in depth here since the implementing class lives outside this module — see `Modules/AssignmentCSAT` if a parity test needs its exact field shape.

### `POST /assignment-csat/{student_assignment}/submit` (`student.assignment-csat.submit`) — `AssignmentCSATController::submit` (this module's own class)
- **Request params (`SubmitStudentEvaluatorCSATRequest`** — see orphaned-FormRequest note above): `rating`, `comment`, `other`, `reasons[]` (validated against `evaluator_csat_form_reason`, **not** `assignment_csat_form_reasons` despite this being the assignment-CSAT endpoint — a cross-wired validation table).
- **Ownership check:** `422 {"status":"error","message":"Unauthorized to do this action","data":null}` if the assignment's enrollment doesn't belong to the caller.
- **Duplicate check:** `422 {"status":"error","message":"Assignment CSAT already submitted","data":null}` if already submitted.
- **Side effects:** creates `AssignmentCSATForm` + one `AssignmentCSATFormReasonsMapping` row per reason, in a transaction. A `triggerAssignmentCsatEvent` webhook-dispatch method exists on the controller but is **commented out at the call site** — no `WebhookTriggered` event actually fires despite the import and full method being present.
- **Success:** `200 {"status":"success","message":"Assignment Rating Successfully"}`.

### `GET /student/assignment-csat-questions` (`assignment-csat.questions`, legacy) — **⚠️ dead route, `getCSATFormReason` undefined on the delegated-to class.** See module-wide notes.

### `POST /submit-assignment-csat` (`assignment.submit_evaluation`, legacy, no FormRequest) — `AssignmentCSATController::submit_assignment_csat` (this module's `AssignmentCSATTrait`)
- Raw `$request->student_id`/`enrollment_id`/`assignment_id`/`course_id`/`batch_id`/`package_id`/`rating`/`comment`/`other`/`reason_id` (array) — **`student_id` is taken directly from the client-supplied body, not the authenticated identity**, same class of issue already flagged for the admin/system NPS endpoint in `API_SPECIFICATIONS.md` §5 (a caller can submit CSAT attributed to an arbitrary student id). **No duplicate check** on this legacy path either.
- **Success:** `apiResponse([], 'Submitted')` — global helper, `200 {"data":[],"message":"Submitted","status":"success"}`.

---

## Evaluator CSAT

### `GET /evaluation-csat/{result}` (`student.evaluation-csat.questions`) — `EvaluatorCSATController::evaluatorCSATFormReason`
- Route constrained to numeric `result`. **No ownership check on this GET** (unlike its `submit` sibling below) — any authenticated student can view any result's CSAT question set by id.
- **Success:** `200 {"status":"success","topic":<assignment topic title>,"lowRateOptions":{...},"midRateOptions":{...},"highRateOptions":{...}}`.

### `POST /evaluation-csat/{result}/submit` (`student.evaluation-csat.submit`) — `EvaluatorCSATController::submit`
- **Request params (`SubmitStudentEvaluatorCSATRequest`):** `rating`, `comment`, `other`, `reasons[]` (`exists:evaluator_csat_form_reason,id`).
- **Ownership check:** `422 {...,"message":"Unauthorized to do this action"}` if `result.student_id !== caller`. **Duplicate check:** `422 {...,"message":"Evaluator CSAT already submitted"}`.
- Same commented-out-webhook pattern as `AssignmentCSATController::submit` (`triggerResultEvaluationCsatEvent` exists but is never called).
- **Success:** `200 {"status":"success","message":"Evaluator Rating successfully"}`.

---

## Performance Coach CSAT

⚠️ See module-wide note — depends on entities from the confirmed-deprecated `PerformanceCoach`/`PerformanceCoachCSAT` modules.

### `GET /call-csat/{pc_call_schedule_id}` (`student.pc-csat.questions`) — `PerformanceCoachCSATController::performanceCoachCSATFormReason`
- Route-model-binds `PerformanceCoachCallSchedule`. **No ownership check** on this GET. Returns `lowRateOptions`/`midRateOptions`/`highRateOptions`/`commonQuestionOptions` — four groups (one more than the other CSAT question endpoints, which only have three).
- **Notes:** the `midRateOptions.question` text string sent to the client (`'How can we improve so that you have a very satisfying experience? '`) does **not match** the string actually used in the `where('question', ...)` DB lookup two lines below it (`'What can we do to improve our services to you?'`) — a copy-paste mismatch. If the DB doesn't have a reason row with that second exact string, `options` for this bucket silently resolves to `null` regardless of what the displayed `question` text claims.

### `POST /call-csat/{pc_call_schedule_id}/submit` (`student.pc-csat.submit`) — `PerformanceCoachCSATController::submit`
- **Request params (`SubmitPerformanceCoachCSATRequest`):** `rating`, `comment`, `other`, `reasons[]` (`exists:performance_coach_csat_form_reason,id`).
- **⚠️ Ownership check uses the wrong guard:** `$performance_coach_call_schedule->student_id !== auth()->user()->id` — this calls the **default** auth guard, not `auth('student')` (every other ownership check in this module explicitly uses `auth('student')->user()->id`). Since the route is already gated by `auth:student` middleware this is very likely equivalent in practice, but it's an inconsistency worth flagging if the app ever resolves a different default guard in this context.
- **Duplicate check:** `422 {...,"message":"Performance Coach Call CSAT already submitted"}`.
- **Success:** `200 {"status":"success","message":"PC Call Rating successfully"}`.

---

## NPS

### `GET /nps/{enrollment}` (`student.nps.show`) — `NPSController::show`
- Ownership 422 as usual. Branches on `enrollment.type` and how many NPS forms already exist for the enrollment (0/1/2), and on a 30-day window since the first assignment was sent — mirrors the "due" logic already described for the admin-facing NPS endpoint in `API_SPECIFICATIONS.md` §5, but this is the **student-facing survey-availability check**, a separate code path from that admin one (different controller, different `NPSForm` vs `NPSFormV2` model even).
- Every branch returns `200 {"status":"success", ...}` — including "already submitted both", "package enrollment (n/a)", "enrollment not completed yet", "no assignment sent yet", "one month not completed yet" — **there is no non-2xx response anywhere in this method**; a caller must inspect `message`/`data` to know which of ~6 distinct states applies.

### `POST /nps/{enrollment}/submit` (`student.nps.submit`) — `NPSController::submit`
- **Request params (`SubmitStudentNpsRequest`):** `rating` (1–10 int), `description` (required string, max 500), `reasons` (nullable array, each `exists:nps_form_reason,id`).
- Mirrors the same due/count branching as `show()`; only actually creates an `NPSForm` row (via private `createNps()`) on the two branches where survey type 1 or 2 is genuinely due — every other branch returns a `200 {"status":"success","message":"..."}` with no write. `createNps()` writes to either the `experience` column (rating ≤ 8) or `suggestions` column (rating > 8), never both, and creates one `NPSFormReasonsMapping` row per submitted reason id only if `reasons` was present.
- **Success (write path):** `200 {"status":"success","message":"Nps submitted successful"}`.

### `GET /student/nps-questions` (`nps.questions`, legacy, no FormRequest) — `NPSController::getNPSReason` (`NPSTrait`)
- Returns **all** `NPSFormReason` rows with no filtering (`$this->npsFormReasonModel::query()->get()`) — an Eloquent collection, auto-serialized to a plain JSON array (no envelope at all, no `status`/`data` wrapper).

### `POST submit-nps` (`nps.submit`, legacy, no FormRequest) — `NPSController::submit_nps` (`NPSTrait`)
- Raw `$request->enrollment_id`/`course_id`/`batch_id`/`survey_type`/`rating`/`reason`/`experience`/`suggestions`/`reason_id` (array) — **no ownership check, no duplicate check, `student_id` taken from `auth('student')->user()->id`** (correctly scoped here, unlike the legacy assignment-CSAT submit above). Creates one `NPSForm` row + one `NPSFormReasonMaping` row per `reason_id`.
- **Success:** `apiResponse([], 'Submitted')` — `200 {"data":[],"message":"Submitted","status":"success"}`.

### `GET student/v2/nps-questions` (`student.nps.show` — **same name as the v1 show route above**) — `NPSController::checkNpsDue`
- **Different prefix (`student/v2`), same route name as the v1 `GET /nps/{enrollment}` route** — another named-route collision (see module-wide notes), resolved last-registered-wins.
- **No request params** (no `{enrollment}` in the path — this checks whether *any* NPS is due for the caller globally, based on `Student.created_at` vs `env('STATIC_ENROLLMENT_DATE')`/`env('NPS_DUE_DAYS')`).
- **Notes:** `env('STATIC_ENROLLMENT_DATE' ?? '2023-01-01 00:00:00')` — ⚠️ the `??` is applied to the **string literal** `'STATIC_ENROLLMENT_DATE'` (always truthy), not to the result of `env(...)` — the fallback `'2023-01-01 00:00:00'` can **never actually be used**; if the env var is unset, `env()` returns `null` and that `null` is used as-is, not the intended default.
- **Success:** `200 {"status":"success","message":"..."}` (not-yet-eligible / no-nps-due branches) or `200 {"status":"success","data":{type,reason,reason2,...}}` (nps due — one `NPSFormReasonResource`-wrapped question group per due survey type).

### `POST student/v2/nps/submit` (unnamed) — `NPSController::submitNps`
- **Request params (`SubmitStudentNpsRequest`):** same rules as the v1 submit endpoint. Also reads `$request['type']` directly (not part of the FormRequest's validated rules — `type` has no validation rule at all in `SubmitStudentNpsRequest`, so a missing/malformed `type` is not caught by validation).
- **Duplicate check:** `200 {"status":"error","message":"You have already responded"}` if an `NPSFormV2` already exists for this student+type (⚠️ **200, not 409/422**, on a duplicate).
- **Side effects:** creates one `NPSFormV2` row (routing the description into `experience` if rating ≤ 8, else `suggestions`) + `NPSFormReasonsMappingV2` rows for both a `reason` and `reason2` field (two separate reason buckets, unlike the v1 form's single `reasons` field) + dispatches `InsertNPSReportData::dispatch(...)` (queued job, not documented further here — outside this module).
- **Success:** `200 {"status":"success","message":"Thank you for your responses."}`; if the internal `createNewNps()` helper throws, it **returns a JSON response from inside a `catch` block that is itself inside a method not typed to return one** — this response object is then evaluated as a boolean by the caller (`if ($this->createNewNps($request))`), and a `JsonResponse` object is always truthy in PHP, so **this exception path is misreported as success** (`200 {"status":"success","message":"Thank you for your responses."}`) even though the row was never created — a real bug worth a dedicated regression test (force a DB error and confirm the client-visible response is nonetheless "success").

---

## Notifications

This module's `NotificationController` is a **separate, third implementation** from the `StudentNotifications`/`Notification` modules already covered in `API_SPECIFICATIONS.md` §5 (which notes those two share one backing store) — this one shares the **same underlying tables** (`Modules\Notification\Entities\Notification`/`NotificationUser`/`NotificationComment`) but is a distinct controller with its own routes/response shapes.

### `GET /notification` (`student.notification.index`) — `NotificationController::index`
- **Request params:** `rows` (default 15), `tag` (array, filters by tag title), `search` (matches notification title), `page`.
- **Success:** `200 {"status":"success","data":[...StudentNotificationResource...],"meta":{total,current,perPage}}`.
- `StudentNotificationResource` fields: `id`, `title`, `category`, `tag` (first tag only), `description`, `createdBy` (first name only), `createdAt`/`sentAt` (formatted `Y-m-d H:i`), `numbersOfComments`, `read` (`Y`/`N` string derived from `read_at`), `activityAlertCount`.

### `GET /notification/{notificationUser}/details` (`student.notification.show`) — `NotificationController::show`
- Route constrained to numeric `notificationUser`. Ownership 422 if `notificationUser.user_id !== caller`. **Side effect:** unconditionally marks the notification read (`update(['read_at' => now()])`) as part of a GET request — reading the detail view always consumes the unread state, with no way to view without marking read.
- **Request params:** optional `commentRequired=Y` query flag — if present, the response additionally nests the full comment thread (with one level of replies); otherwise a lighter response without comments.
- **Success:** `200 {"status":"success","data":{id,title,category,tag,description,createdBy,createdAt,sentAt,numbersOfComments,activityAlertCount[,comments]}}` — comment author resolution special-cases `USER_TYPE_2` (student-authored comments) by re-querying `Student` for `full_name`, vs. `$item->user?->first_name` for staff-authored ones.

### `POST /notification/{notificationUser}/comment` (`student.notification.comment.store`) — `NotificationController::storeComment`
- **Request params (`StoreStudentNotificationCommentRequest`):** `comment` (required string, max 600), `parentCommentId` (nullable, `exists:notification_comments,id`).
- **⚠️ No ownership check on this write** — any authenticated student can post a comment against any `notificationUser` id, not just their own notification. Creates one `NotificationComment` row tagged `USER_TYPE_2` (student).
- **Success:** `200 {"status":"success","message":"Comment created successfully"}`.

### `GET /notification/bell` (`student.notification.bell`) — `NotificationController::bell`
- Top-5 unread notifications ordered by the parent notification's `sent_at` (via a correlated subquery `orderByDesc`, not a simple column order). `200 {"status":"success","data":[...StudentNotificationResource, up to 5...],"meta":{"totalUnread": <full unread count, independent of the take(5) limit>}}`.

### `POST /notification/all/read` (`student.notification.read.all`) — `NotificationController::readAll`
- Bulk `UPDATE ... SET read_at = now() WHERE read_at IS NULL` scoped to the caller. `200 {"status":"success","message":"Read successful"}` — always this message, even if there was nothing unread to update.

### `GET student/notification/latest_five` (`notification.latest_five`, legacy) — **⚠️ dead route, `latest_five` undefined.** See module-wide notes (the trait method is named `getLatestFive`, never wired to this route).

### `GET student/notification` (`notification.index`, legacy) — same `NotificationController::index` documented above; identical response regardless of which of the two paths (`/notification` vs `student/notification`) is used.

---

## Filters, tokens, campaign stats, ATS jobs

### `GET /filter/package` (`student.package.filter`) — `FiltersController::package`
- **Request params:** `packageId` optional (narrows to one package).
- Distinct packages the caller has a non-`PENDING` enrollment against. `200 {"status":"success","data":[...PackageListForFilterResource...]}` — resource is just `{id, name}` from the related `package`.

### `GET /atsapi/get-all-jobs` (`get-all-jobs`) — cross-module, `Modules\AtsAPI\Http\Controllers\AtsAPIController::getAllJobs` (real logic in `AtsApiTrait`)
- **Auth quirk:** in addition to the module's `auth:student` guard, this method independently requires an `ats-token` request header formatted `Bearer <token>` (`getAtsBearerToken()`) — **throws `AtsApiException` (uncaught by this method) if missing/malformed**, which will surface as whatever the app's generic exception handler does with an unrecognized exception class (not one of the standard shapes in the conventions doc — likely a raw 500).
- **Request params:** optional `location`, `experienceMin`/`experienceMax`, `work_mode`, `salaryMin`/`salaryMax`, `industry` — all passed through as external query params.
- **Behavior:** resolves job ids from local `CourseJobMapping` scoped to the caller's active-enrollment courses (`status=1`, not expired, `is_draft='1'`), then calls an external ATS API (`config('app.ats_api_url')/api/v1/es/joblist/all`) forwarding the caller's own bearer token.
- **Success (no jobs):** `200 {"success":true,"data":[],"message":"No jobs found for enrolled courses"}` — note this endpoint uses **`success` (boolean)**, not `status`, unlike almost everything else in this module.

### `POST /student/token_save` (`students.token_save`) — `StudentFrontendEnrollmentController::saveStudentToken`
- **Request params:** `token` required string max 255 (inline `$request->validate()`, not a FormRequest class).
- **Side effects:** creates an `fcmTokens` row for the student, then dispatches **two** jobs: `SendStudentSubscriberTokenToFCM::dispatch($student, $token, $request->all())` and `SendStudentSubscriberTokenToScheduleApp::dispatch($student, $token)` (both from the `Student` module, not detailed further here).
- **Success:** `201 {"message":"Student Token saved successfully."}`.

### `POST /student/campaign_stat` (`students.campaign_stat`) — `StudentFrontendEnrollmentController::updateCampaignStat`
- **Request params:** `id` required int, `slug` required string (inline `validate()`).
- **External call:** `POST {config('app.fcm_api_url')}/v1/stat-count` (30s timeout). **On failure, throws a raw `\Exception`** — not caught anywhere in this method, so it propagates to the app's generic exception handler (not a clean documented error shape; likely a 500 with the exception's own message per Laravel's default JSON-exception rendering for API requests).
- **Success:** `201 {"message":"Student Campaign Stat updated successfully."}` — note this is returned **regardless of whether the log line executed**, i.e. the 201 always follows a successful external call (the only way to reach the `return` is past the `throw`).

### `GET /enrollment-form-status` (`student.enrollment.status`) — `StudentFrontendEnrollmentController::getStudentEnrollmentStatus`
- No params. Checks for any `EnrollmentQuestionAnswer` rows for the caller. Returns a **bare array**, `{"message":"Enrollment updated!","apStatus":3,"status":1}` or `{"message":"Enrollment missing!","apStatus":2,"status":1}` — `status` is always `1` in both branches (it's not an error/success flag here, just a constant).

### `GET /email-verify-status` (`student.email-verify-status`) — `StudentFrontendEnrollmentController::getIfEmailVerified`
- Bare array `{"message":"Email verified!","status":1}` or `{"message":"Email not verified!","status":0}` based on `students.email_verified_at` — here `status` **is** meaningful (1 verified / 0 not), unlike the enrollment-status endpoint right above it that also returns a `status` key but with a constant, unrelated meaning. Don't assume `status` means the same thing across these two neighboring endpoints.

### `GET /set-last-login-for-verify-later` (`student.set-last-login-for-verify-later`) — `StudentFrontendEnrollmentController::setLastLogingForVerifyLater`
- No params. Sets `students.first_time_login = 0`. **Success:** `apiResponse([], 'First Time Login Updated Successfully')` — global helper, `200 {"data":[],"message":"...","status":"success"}`. (Note the method name itself has a typo — `LastLoging` — carried through from source; only relevant if anything reflects on the method name, the route/response are unaffected.)

---

## Student Support (Zoho Desk proxy)

All logic lives in `StudentSupportTrait`, mixed into the near-empty `StudentSupportController` (each controller method is a one-line delegate). This is an **external-proxy cluster**: every endpoint talks to Zoho Desk's REST API (`ZOHO_DESK_BASE_URL`, default `https://desk.zoho.in/api/v1`) using an OAuth token cached in `Cache::get('zoho_access_token')` / refreshed via `ZOHO_DESK_CLIENT_ID`/`_CLIENT_SECRET`/`_REFRESH_TOKEN`. Local DB usage is minimal: `students.zoho_contact_id` (created on first ticket) and S3 (`Storage::disk('s3')`) used as a download cache for attachments.

### `GET /student-support` (`student.support.index`) — `StudentSupportController::index` → `listTickets`
- **Request params:** `page` (default 1), `limit` (default 10), optional `status`.
- **Notes:** ⚠️ calls `usleep(2000000)` — a **hardcoded 2-second synchronous sleep** on every single call, to "wait for Zoho's search index to catch up" per the inline comment. This will make the endpoint feel slow/laggy in any load test and holds a PHP worker/thread for the full 2 seconds regardless of whether it was actually needed.
- If the student has no `zoho_contact_id` yet (never created a ticket), short-circuits to `200 {"status":"success","message":"No tickets found","data":[],"meta":{...all-zero counts...}}` without calling Zoho at all.
- **Success:** `200 {"status":"success","message":"Tickets retrieved successfully","data":<raw Zoho ticket array>,"meta":{current_page,total_records,total_pages,total_open,total_closed,next_page,prev_page,next_page_url,prev_page_url,limit,has_more}}` — pagination is hand-built from Zoho's own `count`/`from`/`limit`, not this app's usual cursor convention.

### `GET /student-support/ticket-counts` (unnamed) — `StudentSupportController::getTicketCounts`
- Also has the same 2-second `usleep`. Returns `200 {"status":"success","message":"Ticket counts retrieved successfully","data":{total_open,total_closed}}`, or an all-zero `data` with `"message":"No tickets found"` if no `zoho_contact_id` yet.

### `POST /student-support` (`student.support.store`) — `StudentSupportController::store` → `createSupportTicket`
- **Request params (inline `validate()`):** `subject` required string, `description` required string, `attachments` nullable array (`attachments.*` file, max 20MB each).
- **Side effects:** creates the ticket in Zoho (using an existing `zoho_contact_id` if the student has one, else `contact:{email,lastName,firstName,phone}`); on first-ever ticket, persists the returned `contactId` to `students.zoho_contact_id`. Uploads any attachments **in parallel** via `Http::pool()`.
- **Success:** `200 {"status":"success","message":"Support ticket created successfully","data":<Zoho ticket + attachment_status>,"meta":{total_open,total_closed}}` — `total_open` in `meta` is manually incremented by 1 client-side (`$counts['total_open'] + 1`) to compensate for Zoho's search-index lag, i.e. **this number is a client-side estimate, not a freshly-queried true count.**
- **Errors:** `500 {"status":"error","message":"Unable to connect to Zoho support"}` if the OAuth token can't be refreshed; `400 {"status":"error","message":"Failed to create support ticket in Zoho","error":<Zoho body>}` on a Zoho-side failure (note: **400**, an unusual choice for an upstream failure passthrough elsewhere in this app usually uses the upstream's own status); `500` generic on any other exception.

### `GET /student-support/{ticketId}` (`student.support.show`) — `StudentSupportController::show` → `showTicket`
- Fetches ticket + attachment metadata (no content) from Zoho. `200 {"status":"success","message":"Ticket details retrieved successfully","data":<ticket+attachments>}`. **No ownership check against `zoho_contact_id`** on this read (unlike the download endpoints below, which do check) — any authenticated student who knows/guesses a `ticketId` can view another student's ticket details via this route.

### `GET /student-support/{ticketId}/conversations` (`student.support.conversations`) — `StudentSupportController::conversations` → `getTicketConversations`
- Heavy post-processing: filters to public, non-draft `thread`-type items; matches attachments to messages by a ±30-second timestamp window (a heuristic, not a real foreign key); strips an invisible zero-width-space marker (`\u{200B}`) used elsewhere to tag "sent from the student portal" content; reconstructs an `author` block per item with several fallback chains distinguishing `END_USER` (student) from `AGENT`. **No ownership check** here either.
- **Success:** `200 {"status":"success","message":"Ticket conversations retrieved successfully","data":<processed Zoho conversation payload>}`.

### `GET /student-support/{ticketId}/thread/{threadId}` (unnamed) — `StudentSupportController::getFullThreadContent`
- Simple passthrough of one Zoho thread's full content. No ownership check.

### `POST /student-support/{ticketId}/reply` (`student.support.reply`) — `StudentSupportController::reply` → `sendReplyToTicket`
- **Request params (inline `validate()`):** `content` nullable string, `attachments` nullable array (max 10MB each).
- Uploads any attachments first (parallel pool), then — if `content` is present or no attachments were sent — posts to Zoho's `sendReply` endpoint with the student impersonated via `impersonatedUserId`/`impersonatedUser` headers, prefixing the content with the same invisible zero-width-space marker used in `conversations()` to flag it as portal-originated.
- **Success:** `200 {"status":"success","message":"Reply processed","data":{reply,attachments}}` — this succeeds even if **only** attachments were sent (no textual reply call made at all in that case, `replyData` stays `null`).

### `PATCH /student-support/{ticketId}/reopen` (`student.support.reopen`) — `StudentSupportController::reopen` → `reOpenTicket`
- Calls the shared `updateTicketStatus($ticketId, 'Open', ...)` first; if that fails, returns its response as-is. Then optionally uploads attachments and/or posts a comment (impersonated), and merges everything into one response with manually-adjusted `meta.total_open`/`total_closed` counts (`+1`/`-1` to pre-compensate for Zoho index lag, same pattern as ticket creation).
- **Notes:** ⚠️ if `getZohoAccessToken()` fails on this **second** call inside the method (after the reopen status call already succeeded), the method returns the **earlier** `$statusResponse` (the successful reopen) rather than an error — meaning a token failure at this exact point is silently swallowed and the client sees a success response for the reopen even though the comment/attachment step never ran.

### `PATCH /student-support/{ticketId}/close` (`student.support.close`) — `StudentSupportController::close` → `closeTicket` → `updateTicketStatus($ticketId, 'Closed', ...)`
- Same shared status-update helper as reopen. **Notes:** ⚠️ inside `updateTicketStatus`'s success branch, `fetchTicketCounts($accessToken, ($impersonatedUserId ?: $student->zoho_contact_id ?? null))` references a `$student` variable that is **never defined inside this private method** (it's only defined in the calling `reOpenTicket`/`closeTicket` methods, not passed in as a parameter) — this will throw an "undefined variable" warning/notice at minimum, and if `$impersonatedUserId` is also falsy, likely resolves to fetching counts for a `null` contact id. A parity/regression test should confirm what `close`'s response `meta` counts actually look like in practice given this bug.

### `GET /student-support/{ticketId}/attachments/{attachmentId}/download` (`student.support.attachment.download`) — `StudentSupportController::download` → `downloadAttachment`
- **This is the "student-side" attachment download** — includes an ownership check (`ticketData['contactId'] != student->zoho_contact_id` → `403`). Downloads from Zoho, caches to S3 (`zoho_attachments/{ticketId}/{attachmentId}_{safeFileName}`), serves from S3 on subsequent requests (`Storage::disk('s3')->download(...)`) rather than re-fetching Zoho every time.
- **Errors:** `500` generic on token/ticket-fetch failure; `403 {"status":"error","message":"Unauthorized access to this attachment"}` on ownership mismatch; `500 {"status":"error","message":"Failed to download attachment from Zoho"}` on the content fetch failing.

### `GET /student-support/admin-reply-attachment/{ticketId}/thread/{threadId}/attachments/{attachmentId}/download` (**same route name `student.support.attachment.download` — duplicate**, this is the second of two routes sharing that name) — `StudentSupportController::downloadAdminsideAttachment`
- Same S3-cache-then-serve pattern, but resolves attachment metadata from a **thread's** attachment list (`/tickets/{ticketId}/threads/{threadId}`) instead of the ticket's own attachment list — for downloading attachments that arrived on an admin-side reply thread rather than the ticket root. Same ownership check as the student-side download.

---

## Summary of Resource classes not otherwise detailed inline

| Resource | Used by | Key fields |
|---|---|---|
| `NewStudentResultResource` | `GET /enrollments/{enrollment}/results` | `resultId`, `feadbackFile` (sic), `videoFeedback`, `waived`, `markDeduction`, `evaluationCsatEligible`, `SubmissionDate`, `plag.{score,file}`, `evaluationVideoRate`, `assignment.{...}`, `resultScore[]`, `evaluator.{name,email,phone}`. |
| `StudentResultResource` | `GET /result-listing/{enrollment}` (legacy) | ~40-field legacy shape merging most raw `Result` columns with many computed extras (`ai_evaluation.*`, `csat_filled_up`, `feature_assignment`, `vComment`/`vRating` from a separate video-mapping table, etc.) — see source for the full list; materially larger/older than `NewStudentResultResource`, the two are **not** interchangeable. |
| `ProjectEnrolmentResource` | `GET /student/getStudentCourseBatch` | Raw model fields minus timestamps, plus a `course_name` field that is (confusingly) actually set to the **`batch_id`** value in the resource itself, then overwritten again by the controller after resource construction — the resource's own `course_name` value is always discarded in practice. |
| `ClassCSATResource` | not found wired to any live route in this file (only `ClassCsatCheckResourse` is used, by the trait's `check_eligibilty`) — appears orphaned. |
| `ClassCsatCheckResourse` | `check_eligibilty` (legacy class-CSAT eligibility) | Strips most raw `Classes` columns, adds `class_id`, `className`, `expertName`/`hostName` (comma-joined strings built by trimming a trailing `", "` with `substr(...,0,-2)` — will mis-trim a name that itself happens to end in `, `), `course_names`/`pkg_names` (same comma-join pattern, N+1 local lookups per row). |
| `GetCalendyResource` | **none** — orphaned, not referenced by any controller/trait in this module (both `getcalendy` and `getcalendyData` build their response arrays by hand instead). |

## Endpoint count and confidence

- **73** raw `Route::` declarations in `Modules/StudentFrontendEnrollment/Routes/api.php`; all documented above.
- **2 routes are confirmed dead** (undefined controller method → fatal error at call time): `GET student/notification/latest_five` and `GET /student/assignment-csat-questions`. (The two `.../tasks/{id}/comments` routes were initially miscategorized as dead in an earlier pass of this research — corrected after verifying they're implemented in the cross-module `ProjectTaskTrait` mixed into `TaskController`; they are live, see the Kanboard section above.)
- **Structural surprises worth flagging to the team**, beyond the 2 dead routes: the unauthenticated attachment-download route; the no-ownership-check gap on `enrollment_result`; the `env('STATIC_ENROLLMENT_DATE' ?? ...)` operator-precedence bug; the `close()`/`updateTicketStatus` undefined-`$student`-variable bug; the `NPSController::submitNps` exception-swallowed-as-success bug; the `apiResponse('', 'message', 500)` argument-position bug recurring across several Kanboard-exception branches (intended 500s are actually served as 200s); three duplicate route *names* (`submit_evaluation` ×2, `student.projects.tasks.show` ×3, `student.support.attachment.download` ×2); and five parallel "new vs. legacy" CSAT/NPS endpoint pairs where the legacy path skips validation, ownership checks, and/or duplicate-submission checks that the newer path enforces — a parity migration should decide deliberately, per legacy route, whether AP‑V3 needs to preserve that looser legacy behavior or is allowed to only implement the stricter modern equivalent.
- **Confidence:** high for control flow and response shapes for everything backed by local DB logic (the large majority of this module), since all controllers, traits (including the two cross-module ones actually mixed in — `ProjectTaskTrait`/`kanboardTrait` from `ProjectManagement`), and FormRequests behind every live route were read directly from source. Lower confidence on the exact byte-for-byte shape of external payloads this module merely proxies (Zoho Desk ticket/conversation JSON, the ATS job-search API, Kanboard's JSON-RPC bodies) — those come from systems outside this repository and would need a live/staging credential or that system's own documentation to pin down exactly.
