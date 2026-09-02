# StudentResults

Small, focused module: lets a student view their own already-evaluated results for one enrollment, rate the evaluation-feedback video, and (self-service) have their feedback file re-emailed to themselves. Distinct from the `Result` module's own admin-facing grading endpoints (`PUT /api/v1/results/{result}`, etc. — see `API_SPECIFICATIONS.md` §4) — this module is a read-mostly, student-scoped window onto the same `results` table. See [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for shared envelope/error/pagination conventions.

Three real actions across 4 route registrations (one action, `index`, is registered twice under two different guards/prefixes — genuinely two separate endpoints hitting the same controller method, not a duplicate). All response bodies in this module are hand-rolled `response()->json([...])` arrays — **`apiResponse()` is never used anywhere in this module's controller or trait.**

---

## `POST /student/v1/result/{result}/rate-evaluation-video` (route name `student.results.rate.evaluation_video`)
**Auth:** `['auth:student', 'json.response', 'last.login']` (this module's `student/v1` route group — note the extra `last.login` middleware not present on the module's other, `sanctum`-guarded group; not traced further here beyond noting it runs).
- **Route constraint:** `{result}` is regex-constrained to `[0-9]+` — a non-numeric value 404s at the routing layer before the controller runs at all (standard Laravel route-not-found shape, not this module's own error handling).
- **Controller method:** `rateEvaluationVideo(RateEvaluationVideoRequest $request, Result $result)` — `$result` is route-model-bound; a numeric id with no matching row triggers the standard `ModelNotFoundException` 404 shape from `_COMMON_CONVENTIONS.md`.
- **Request params (body):** `RateEvaluationVideoRequest` — `rating` required integer, `min:1|max:10`; `comment` nullable string max:255.
- **Ownership check:** `if ($result->student_id !== auth('student')->user()->id)` → `response()->json(['status' => 'error', 'message' => 'Unauthorized to do this action'], 422)` — note this is a **422**, not the more semantically-typical 401/403, for an authorization failure.
- **Behavior:** loads `student_assignment`/`student_assignment.enrollment` relations, then creates a row via `$result->studentResultVideoMapping()->create([...])` — `student_id`/`assignment_id`/`evaluator_id` copied from the `Result`, `course_id` from the loaded enrollment relation, `rating_value`/`comment` from the request. **No duplicate-rating guard** — calling this endpoint repeatedly for the same `Result` creates additional mapping rows rather than updating an existing rating (not confirmed whether a unique DB constraint exists on the underlying table to block this at the schema level — worth a direct duplicate-submission test).
- **Success:** `response()->json(['status' => 'success', 'message' => 'Rating added'])` — plain 200, `data` key entirely absent from the shape (not even an empty one).

## `POST /student/v1/result/{result}/email-feedback-file` (route name `student.results.email.feedback_file`)
**Auth:** same `student/v1` group as above (`auth:student`, `json.response`, `last.login`).
- **Route constraint:** `{result}` also `[0-9]+`-only.
- **Controller method:** `emailFeedbackFile(Result $result)`. **No FormRequest** — no body params at all, purely acts on the route-bound `Result`.
- **Ownership check:** identical shape/status to `rateEvaluationVideo` above — `422 {"status":"error","message":"Unauthorized to do this action"}` if `$result->student_id` doesn't match the caller.
- **No feedback file on the result:** `response()->json(['status' => 'error', 'message' => 'No feedback file found for this result'], 422)`.
- **External call:** `Http::timeout(60)->get($result->feedback_file)` — fetches the student's own already-generated feedback file from wherever it's hosted (S3 URL stored on the `Result` row) so it can be attached to an email; this is a live outbound HTTP call at test time, not mockable purely at this app's own DB boundary. A non-`successful()` response (`Log::error`'d with the `result_id`) returns `response()->json(['status' => 'error', 'message' => 'Failed to fetch the feedback file, please try again later'], 500)` — a genuine 500 here, not silently swallowed into a 200 the way some other external-proxy failures in this app are (see `_COMMON_CONVENTIONS.md`'s cross-cutting caution — this endpoint is a rare instance that actually surfaces the failure honestly).
- **Behavior on a successful fetch:** loads `student`, `student_assignment.enrollment.course`, `student_assignment.assignment.topic`; derives a filename (`feedback_file_original_name` column if set, else the basename parsed out of the S3 URL, else the literal fallback string `'feedback'`) and MIME type (from the external response's `Content-Type` header, semicolon-stripped, else `application/octet-stream`); logs an info-level entry with file name/mime/size; queues `Mail::to($result->student->email)->queue(new ResultFeedbackFileDownloadMail(...))` with the file content **base64-encoded inline into the mailable** (not re-uploaded/re-linked — the fetched bytes travel through the queue payload as base64).
- **Success:** `response()->json(['status' => 'success', 'message' => 'The feedback file has been emailed to your registered email address'])`.
- **Any other exception during the above** (caught broadly): logged (`Log::error`, `result_id` + message), `response()->json(['status' => 'error', 'message' => 'An internal error occurred'], 500)` — the real exception message is not leaked to the client here, unlike some other modules' exception-path responses.

## `GET /student/v1/student-results/index/{enrollment}` (route name `student-results.index`) — student-facing
**Auth:** `['auth:student', 'json.response', 'last.login']`.
## `GET /v1/student-results/index/{enrollment}` (route name `student-results.index`) — admin-facing, same route name reused
**Auth:** `['auth:sanctum', 'json.response']` — a **separate route group** in the same file (no `last.login`), registered under the plain `v1` prefix instead of `student/v1`. Both this and the entry above resolve to the **identical controller method**, `index(Enrollment $enrollment)` — genuinely two reachable endpoints (different URI prefixes, so no shadowing), one for the student app and one presumably for an admin-facing "view this student's results for this enrollment" screen. Documented together since the behavior is identical; only the guard differs.

- `{enrollment}` is route-model-bound to the `Enrollment` module's entity — a non-existent id triggers the standard `ModelNotFoundException` 404 shape. **No ownership check is performed on the `student/v1` (student-guarded) variant** — the method never verifies `$enrollment->student_id` against `auth('student')->user()->id`, unlike both other endpoints in this module — a student who knows/guesses another student's enrollment id can view that enrollment's results through this route. Worth a dedicated authorization-boundary test; not independently confirmed whether some outer layer (e.g. a global scope on `Enrollment`) restricts this — reading the controller method alone shows no such check.
- **Request params (query):** `rows` (page size, default 15, cursor-paginated family).
- **Behavior:** filters `Result` rows to `latest = Result::ACTIVE` **and** `is_review_done = Result::REVIEW_DONE`, scoped to this `$enrollment->id` via `student_assignment.enrollment` relation — i.e. only fully-graded, currently-active (non-superseded-by-a-later-attempt) results are ever returned by this endpoint; a `Result` still awaiting review, or one that's been superseded by a resubmission, is invisible here.
- **Success:** `StudentResultResource::collection(...)->additional(['meta' => {'course': {'id','course_name'}, 'batch': {'id','batch_name' (from batch_date)} or null id/name if no batch, 'assignment_meta': <see below>, 'range': <cursor family>, 'total': <int>}])`.
  - `assignment_meta` = `app(Modules\Student\Http\Controllers\StudentController::class)->course_package_meta($enrollment, $rows)` — a **cross-module call into the `Student` module's controller**, instantiated ad hoc via the container rather than injected; its exact shape is that module's own contract, not re-derived here.
  - **`StudentResultResource` shape:** raw `results` columns **except** `created_at`,`updated_at`,`evaluator_id`,`assignment_id`,`submitted_file`,`feedback_file_original_name`,`evaluation_date`,`evaluation_due_date`,`is_email_sent`,`feedback_to_student`,`is_review_done`,`waive_marks`,`feature_assignment`,`bootcamp_id`,`status`,`student_id` (a large exclusion list — a parity test should confirm exactly which raw columns *do* pass through, since this resource excludes far more than it keeps), plus `evaluator` (nested `{id,first_name,last_name,email,phone}` or null), `topic` (`$this->student_assignment->assignment->topic->only('title')` — ⚠️ **no null-safe operators on this chain**; if any of `student_assignment`/`assignment`/`topic` is unexpectedly null for a given `Result` row, this throws a fatal error while serializing the collection, not a per-row graceful omission), `result_scores` (`ResultExerciseScoresResource::collection($this->resultExerciseScores)` — that resource's own shape belongs to the `Result` module, not re-derived here).
- **Side effects:** read-only.

---

## Non-functional scaffolding (commented out, not registered)

Both route groups in `Modules/StudentResults/Routes/api.php` contain a commented-out `// Route::apiResource('student-results', 'StudentResultsController');` line. This is **not a live route at all** (fully commented out in source, unlike the "dead scaffolding" pattern seen elsewhere where the route registration is live but the target method is a stub) — no request can ever reach it; mentioned only for completeness since the task's route-file survey should account for why no `index`/`store`/`show`/`update`/`destroy` CRUD surface exists here despite the module's naming convention suggesting one might.

---

## Summary

- **Endpoint count:** 4 route registrations, 3 distinct controller methods (`rateEvaluationVideo`, `emailFeedbackFile`, `index` — the last reachable via 2 separate URIs/guards). All 3 are live and functioning.
- **Notable findings for parity testing:**
  1. **No `apiResponse()` usage anywhere in this module** — every response is a hand-rolled `response()->json([...])`, and unlike most of this app's hand-rolled endpoints, the shapes here are unusually consistent with each other (`{"status": "success"|"error", "message": "..."}`, `data` key omitted entirely rather than set to `null`/`[]`).
  2. `emailFeedbackFile` is one of the few endpoints in this whole codebase that **honestly surfaces an external-call failure** as a real 500 rather than masking it behind a 200 "success" body — worth noting as a positive counter-example to the cross-cutting caution in `_COMMON_CONVENTIONS.md`.
  3. `index()` (both the student- and admin-guarded variants) performs **no ownership check** between the authenticated student and the requested `{enrollment}` — a likely authorization gap on the student-facing variant specifically, worth a dedicated boundary test (can student A read student B's results by guessing/enumerating an enrollment id?).
  4. `StudentResultResource`'s `topic` field chain (`student_assignment->assignment->topic`) has no null-safety — a `Result` row with any broken/missing relation in that chain will fault the entire collection's serialization, not just that one row.
  5. `rateEvaluationVideo` has no duplicate-submission guard at the application layer.
- **Confidence:** High — `StudentResultsController` (all methods), `StudentResultsTrait`, `StudentResultsRepository`, `RateEvaluationVideoRequest`, and `StudentResultResource` were all read in full. `course_package_meta()` (Student module) and `ResultExerciseScoresResource` (Result module) are cross-module dependencies whose own internals are out of this file's scope, per the cross-module-delegation convention.

---

*Companion documents: [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md), [`../API_SPECIFICATIONS.md`](../API_SPECIFICATIONS.md) §4 (Assignment & Evaluation Lifecycle — the admin-facing `Result` grading endpoints this module's read-only student view sits alongside).*
