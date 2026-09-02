# Event Catalog

> **Generated:** 2026-08-29 · **Branch surveyed:** `New-Dummy-Prod-0605`
> **How this differs from `documentation/EVENT_LIST.md`:** that document is the narrative analysis — it explains *how* this session discovered that most of this codebase's formal event layer is dead code, with the file:line evidence and reasoning. **This document is the reference lookup** — one catalog entry per event, in a consistent field format, for when you already know (or need to look up) a specific event by name and want its producer/consumer/payload without re-reading the analysis. Every fact here is sourced from the same verification pass as `EVENT_LIST.md`; nothing here is new research, only reformatted for lookup.
> **Companion documents:** `documentation/EVENT_LIST.md` (read this first for context and findings), `documentation/BOUNDED_CONTEXT_*.md`, `documentation/CONTEXT_MAP.md`

## Legend

- **Status: 🟢 LIVE** — the dispatch call site is real, uncommented code, confirmed reachable.
- **Status: 🔴 DEAD** — the dispatch call site exists in source but is commented out; the event never fires today.
- **Status: 🟡 PLUMBING ONLY** — the event class/listener/infrastructure is live and would work correctly, but nothing in the business-logic call graph currently constructs it.
- **Payload — ✅ verified**: the exact array literal was read at the dispatch site for this catalog.
- **Payload — pattern**: not individually re-read for this entry; inferred from the standard envelope confirmed live at 12+ other `WebhookTriggered` dispatch sites (see §2's shared envelope note).

---

## 1. Formal Laravel Events

### `Illuminate\Auth\Events\Registered`
- **Type:** Framework event
- **Status:** 🟢 LIVE
- **Bounded context:** Identity
- **Producer:** `Modules/Auth/Http/Controllers/RegisteredUserController.php:36`
- **Consumer(s):** `Illuminate\Auth\Listeners\SendEmailVerificationNotification` (framework)
- **Trigger:** A new admin/staff user completes registration
- **Payload:** the registered `User` model instance

### `App\Events\BootcampAdditionalEnrollmentAdded`
- **Type:** Custom domain event
- **Status:** 🔴 DEAD
- **Bounded context:** Enrollment / Learning
- **Producer (commented out):** `Modules/Enrollment/Http/Traits/EnrollmentTrait.php:3576`
- **Consumer(s) (registered, never invoked):** `App\Listeners\AddBootcampAdditionalEnrollmentToBookDelivery`
- **Trigger (intended):** An additional bootcamp enrollment is added to an existing student
- **Payload:** `Modules\Enrollment\Entities\Enrollment $enrollment`
- **Notes:** `DEVELOPER_DOCUMENTATION.md` §12 (written the same day) describes this as live — it is not; corrected in `EVENT_LIST.md` §1

### `Modules\Package\Events\PackageUpdateStudentCompleted`
- **Type:** Custom domain event
- **Status:** 🟢 LIVE
- **Bounded context:** Enrollment / Learning
- **Producer:** `Modules/Package/Jobs/PackageUpdateStudent.php:86`
- **Consumer(s):** `Modules\Package\Listeners\SendPackageUpdateEmailNotification`
- **Trigger:** A package-update background job finishes
- **Payload:** `$userEmail` (string)
- **Notes:** Fires a confirmation email via `CourseAndAssignmentsToStudentForPackageUpdate` mailable

### `Modules\Webhook\Events\WebhookTriggered`
- **Type:** Custom domain event (generic, string-keyed)
- **Status:** 🟡 PLUMBING ONLY
- **Bounded context:** Communication
- **Producer:** never called live from business logic (§2 below covers every intended call site, all dead)
- **Consumer(s):** `Modules\Webhook\Listeners\HandleWebhook` → `WebhookTrait::processWebhook()` → `Modules\Webhook\Jobs\SendWebhookJob`
- **Trigger:** intended to be "any named business event," see §2
- **Payload:** `string $eventName, mixed $payload`
- **Notes:** The class and its listener chain work correctly; it's the callers, not the plumbing, that are dead

### `Modules\Package\Events\PackageEnrollmentStudentAssignmentsCompleted`
- **Type:** Custom domain event
- **Status:** 🔴 DEAD (doubly — not registered, not dispatched)
- **Bounded context:** Enrollment / Learning
- **Producer (commented out):** `Modules/Enrollment/Jobs/PackageEnrollmentStudentAssignments.php:88`
- **Consumer(s):** *not wired* — `Modules\Package\Listeners\SendEmailWhenJobsCompleted` type-hints this event as a second `handle()` parameter alongside `PackageUpdateStudentCompleted`, a signature Laravel's dispatcher cannot satisfy from any single-event `$listen` entry; this event is absent from `EventServiceProvider::$listen` entirely
- **Trigger (intended):** Bulk package-enrollment student-assignment job completes
- **Payload:** none (empty constructor)

---

## 2. Business webhook events — `WebhookTriggered` catalog (all 🔴 DEAD)

**Shared envelope**, confirmed live at every dispatch site read for this catalog: `WebhookTrait::processWebhook()` wraps whatever payload a trigger method builds into a final outbound shape — `channel`, `site`, `refId`, `studentDetails{name,email,phone}`, `actions{type,actionType,actionDescription}`, `payload{enrollmentId,timestamp}`, `display_json`. The per-event payloads below are what each trigger method passes in *before* that wrapping; every one uses the same base shape (`type`, `actionType`, `actionDescription`, `student`, `enrollmentId`, `timestamp`, `display_json`) with event-specific values.

**None of the entries below fire in production.** Every dispatch call is commented out (`EVENT_LIST.md` §2 has the full 53-call-site audit). They're cataloged with real detail because the dispatch/subscription/retry infrastructure that would carry them is fully functional — this is what you'd be re-enabling, not designing from scratch, if the team ever revives this system.

### Enrollment context

#### `Course.Enrollment.AP`
- **Producer (dead):** `triggerCourseEnrollmentEvent()`, `Modules/Enrollment/Http/Controllers/EnrollmentController.php`
- **Trigger:** Staff manually enrolls a student in a course via the Assignment Portal
- **Payload — ✅ verified:** `type: 'ap_enrollment'`, `actionType: 'Student is enrolled in course'`, `actionDescription` (conditional text incl. batch-shift note), `student`, `enrollmentId`, `timestamp`, `display_json: {course_name}`
- **Receiving logic:** the only 3 events with a real `switch` case in `WebhookTrait::getActionDescription()` — itself dead code with zero callers

#### `Course.Enrollment.Lawsikho`
- **Producer (dead):** `triggerCourseEnrollmentEvent()`, same file, same wrapper — event name is the parameter that varies
- **Trigger:** Student purchases a course via the main LawSikho site
- **Payload — ✅ verified:** identical shape to `Course.Enrollment.AP`, `actionDescription` swaps to "purchased from lawsikho" wording

#### `Bootcamp.Enrollment.AP`
- **Producer (dead):** `triggerBootcampEnrollmentEvent()`, `Modules/Enrollment/Http/Traits/EnrollmentTrait.php`
- **Trigger:** Staff manually enrolls a student in a bootcamp
- **Payload — ✅ verified:** `type: 'ap_enrollment'`, `actionType: 'Student is enrolled in bootcamp'`, conditional `actionDescription`, `student`, `enrollmentId`

#### `Bootcamp.Enrollment.Lawsikho`
- **Producer (dead):** `triggerBootcampEnrollmentEvent()`, `Modules/Enrollment/Http/Controllers/EnrollmentController.php` (15 call sites, all dead)
- **Trigger:** Student purchases a bootcamp via LawSikho
- **Payload — ✅ verified:** same shape as `Bootcamp.Enrollment.AP`
- **Receiving logic:** one of the 3 live `switch` cases in `getActionDescription()` (itself uncalled)

#### `Package.Enrollment.Lawsikho`
- **Producer (dead):** `triggerPackageEnrollmentEvent()`, `Modules/Enrollment/Http/Traits/EnrollmentTrait.php:2264`
- **Trigger:** Student purchases a package via LawSikho
- **Payload — ✅ verified:** `type: 'ap_enrollment'`, `actionType: 'Student is enrolled in package'`, `actionDescription` incl. package name, `student`, `enrollmentId`, `timestamp`, `display_json: {package_name}`

#### `Course.Migrate.AP`
- **Producer (dead):** `triggerCourseMigrateEvent()`, `Modules/Enrollment/Http/Traits/EnrollmentTrait.php:3111`
- **Trigger:** An enrollment is migrated to a different batch/course
- **Payload — pattern**
- **Notes:** the string `'Course.Migrate.AP'` is also reused, unrelated to this event, as a `$slug` value in the separate "RefundEligibleTag" activity-log system elsewhere in the same file — don't conflate the two uses

#### `Enrollment.Certified`
- **Producer (dead):** `triggerEnrollmentCertifyEvent()`, `Modules/Enrollment/Http/Traits/EnrollmentTrait.php:1097`
- **Trigger:** Bulk certification of enrollments
- **Payload — pattern**

#### `Enrollment.Updated.AP`
- **Producer (dead):** `triggerEnrollmentUpdateEvent()`, `Modules/Enrollment/Http/Controllers/EnrollmentController.php:1983`
- **Trigger:** An enrollment's status is changed by staff
- **Payload — pattern**

#### `Certificate.Request.AP`
- **Producer (dead):** `triggerCertificateRequestEvent()`, `Modules/StudentFrontendEnrollment/Http/Controllers/StudentFrontendEnrollmentController.php:733`
- **Trigger:** A student requests their completion certificate
- **Payload — ✅ verified:** `type: 'ap_enrollment'`, `actionType: 'Certificate Requested'`, `actionDescription` incl. course name, `student`, `enrollmentId`, `timestamp`, `display_json: {course_name}`

#### `Submit.Enrollmentform`
- **Producer (dead):** `triggerSubmitEnrollmentFormEvent()`, `Modules/LawSikho/Http/Traits/EnrollmentTrait.php:148`
- **Trigger:** Student submits the enrollment questionnaire
- **Payload — ✅ verified:** `type: 'ap_enrollment'`, `actionType: 'Enrollment Form Submitted'`, `student`, `enrollmentId: " "` (literal blank string, not null), `timestamp`, `display_json: {student_name}`

### Assessment context

#### `Assignment.Create.AP`
- **Producer (dead):** `triggerStudentAssignmentEvent()` (`StudentAssignmentController.php`, 4 dead call sites) and inline in `triggerWebhook()` (`AssignAssignmentsByFiltersJob.php:394` — this call itself is live code, but its *own* only caller, line 120, is commented out, so it's still unreachable)
- **Trigger:** An assignment is assigned to a student
- **Payload — ✅ verified (from `AssignAssignmentsByFiltersJob`):** `type: 'ap_assignment'`, `actionType: 'New Assignment Assigned'`, `actionDescription`, `student`, `enrollmentId`, `timestamp`, `display_json: {topic_name, type, exercise}`
- **Payload — ✅ verified (from `StudentAssignmentTrait.php:1289`):** same shape, `actionType` identical, minor wording differences in `actionDescription`

#### `Assignment.Updated.AP`
- **Producer (dead):** `triggerUpdateAssignmentEvent()`, `Modules/StudentAssignment/Http/Controllers/StudentAssignmentController.php:621`
- **Trigger:** An assigned assignment's details are updated
- **Payload — pattern**

#### `Assignment.Deleted.AP`
- **Producer (dead):** `triggerDeleteAssignmentEvent()`, `Modules/StudentAssignment/Http/Controllers/StudentAssignmentController.php:693`
- **Trigger:** A student assignment is deleted
- **Payload — pattern**

#### `Assignment.Submit.AP`
- **Producer (dead):** `triggerAssignmentSubmitEvent()`, `Modules/StudentAssignment/Http/Traits/StudentAssignmentTrait.php` (2 call sites)
- **Trigger:** A student submits an assignment
- **Payload — pattern**

#### `Assignment.Resubmit.AP`
- **Producer (dead):** `triggerAssignmentResubmitEvent()`, `Modules/StudentAssignment/Http/Traits/StudentAssignmentTrait.php` (2 call sites)
- **Trigger:** A student resubmits a previously-rejected/waived assignment
- **Payload — pattern**

#### `Student.Assignment.Submit.AP`
- **Producer (dead):** `triggerStudentAssignmentSubmitEvent()`, `Modules/StudentMyCourses/Http/Traits/StudentMyCoursesTrait.php` (2 call sites)
- **Trigger:** Submission tracked from the student's "my courses" surface
- **Payload — ✅ verified:** `type: 'ap_assignment'`, `actionType: 'Assignment Submitted By Admin'` *(note: name says "Student" but the actionType text says "By Admin" — an inconsistency worth resolving before ever re-enabling this)*, `actionDescription`, `student`, `enrollmentId`, `timestamp`, `display_json: {topic_name, type, exercise}`

#### `Admin.Assignment.Submit.AP`
- **Producer (dead):** `triggerAdminAssignmentSubmitEvent()`, `Modules/StudentMyCourses/Http/Traits/StudentMyCoursesTrait.php:1548`
- **Trigger:** Admin manually marks a submission on a student's behalf
- **Payload — pattern** (likely near-identical to `Student.Assignment.Submit.AP` given the naming overlap noted above)

#### `Result Evaluated` *(space-separated — the one name in this catalog that breaks the `Dot.Notation` convention used everywhere else)*
- **Producer (dead):** `triggerResultEvaluationEvent()`, `Modules/Result/Http/Traits/ResultTrait.php:712` (dispatch at line 737)
- **Trigger:** An evaluator grades a submission
- **Payload — ✅ verified:** `type: 'ap_result'`, `actionType: 'Result Evaluated'`, `actionDescription` (topic/course/batch/evaluator detail), `student`, `enrollmentId`, `display_json: {submitted_file, feedback_file, result_exercise_score, submitted_date}`, `timestamp`

### Identity context

#### `Profile.Update.AP`
- **Producer (dead):** `triggerProfileUpdateEvent()`, `Modules/StudentProfile/Http/Traits/StudentProfileTrait.php:869`
- **Trigger:** Student updates their own profile
- **Payload — ✅ verified:** `type: 'ap_profile_update'`, `actionType: 'Student Profile Updated'`, `actionDescription: "Student have updated their profile"` *(grammatical error in source, reproduced verbatim)*, `student`, `enrollmentId: " "`, `timestamp`, `display_json: []` (always empty)

#### `Profile.Update.By.Admin`
- **Producer (dead):** `triggerEventforUpdate()`, `Modules/Student/Http/Controllers/StudentController.php:302`
- **Trigger:** Admin edits a student's profile
- **Payload — pattern**

#### `Student.Profile.Updated`
- **Producer (dead):** `triggerEventforUpdate()`, `Modules/Student/Http/Traits/StudentTrait.php:1681`
- **Trigger:** A second, overlapping self-service profile-update path
- **Payload — pattern**

#### `Email.Updated`
- **Producer (dead):** inline in the same update flow, `Modules/Student/Http/Traits/StudentTrait.php:1913`
- **Trigger:** Student's email address is changed
- **Payload — ✅ verified:** `type: 'ap_profile_update'`, `actionType: 'Your email has been updated'`, `actionDescription`, `student`, **`newEmail`** (not `enrollmentId` — the one event in this catalog with a differently-shaped payload key), `display_json: {comment, description, commented_by, commented_at}`

#### `Student.Activate.AP`
- **Producer (dead):** `triggerStudentActivateEvent()`, `Modules/Student/Http/Traits/StudentTrait.php:1146`
- **Trigger:** Staff activates a student account
- **Payload — pattern**

#### `Student.Deactivate.AP`
- **Producer (dead):** `triggerStudentDeactivateEvent()`, `Modules/Student/Http/Traits/StudentTrait.php:1223` and (also dead) `Modules/AgenticSupportSystem/Http/Traits/AgenticSupportSystemTraitV2.php:3161`
- **Trigger:** Staff deactivates a student account
- **Payload — pattern**

#### `Password.Change`
- **Producer (dead):** `triggerEventForPasswordChange()`, `Modules/StudentAuth/Http/Controllers/NewPasswordController.php:168`
- **Trigger:** Student changes their password
- **Payload — pattern**

#### `Weekday.availability.AP`
- **Producer (dead):** `triggerWeekdayAvailabilityEvent()`, `Modules/StudentPerformanceCoach/Http/Controllers/StudentPerformanceCoachController.php:936` (dispatch at line 959)
- **Trigger:** Coaching availability slots are set
- **Payload — ✅ verified:** `type: 'ap_profile_update'`, `actionType: 'Mark Availability'`, `actionDescription`, `student`, `enrollmentId: " "`, `display_json: {student_name}`, `timestamp`
- **Notes:** doubly dead — the trigger call is commented out **and** the owning module (`StudentPerformanceCoach`) is confirmed not in active use

### Communication context

#### `NPS.Submitted.AP`
- **Producer (dead):** `triggerNPSSubmitEvent()`, `Modules/StudentFrontendEnrollment/Http/Controllers/NPSController.php:396` (dispatch at line 463)
- **Trigger:** Student submits an NPS survey
- **Payload — ✅ verified:** `type: 'ap_nps'`, `actionType: 'NPS Submitted'`, `actionDescription` incl. survey type, `student`, `enrollmentId: " "`, `timestamp`, `display_json: {survey_type}`

#### `assignment_csat_submitted` *(snake_case — inconsistent with the rest of the catalog)*
- **Producer (dead):** `triggerAssignmentCsatEvent()`, `Modules/StudentFrontendEnrollment/Http/Controllers/AssignmentCSATController.php:71` (dispatch at line 95)
- **Trigger:** Student submits an assignment CSAT survey
- **Payload — ✅ verified:** `type: 'ap_assignment'`, `actionType: 'Assignment CSAT Submitted'`, `actionDescription` incl. topic/course/batch, `student`, `enrollmentId`, `display_json: {comment, commented_by, commented_at, rating}`

#### `evaluator_csat_submitted` *(snake_case)*
- **Producer (dead):** `triggerResultEvaluationCsatEvent()`, `Modules/StudentFrontendEnrollment/Http/Controllers/EvaluatorCSATController.php:117` (dispatch at line 127)
- **Trigger:** Student submits an evaluator CSAT survey
- **Payload — ✅ verified:** `type: 'evaluator_csat'` *(note: differs from the `evaluator_csat_submitted` event name itself)*, `actionType: 'Evaluator CSAT Submitted'`, `actionDescription`, `student`, `enrollmentId`, `display_json: {submitted_file, feedback_file, submitted_date, comment, commented_by, commented_at}`

### Learning context

#### `Certificate.Generate`
- **Producer (dead):** `triggerEventForGenerateCertificate()`, `Modules/CourseCompletionMaster/Http/Traits/CourseCompletionMasterTrait.php:547` (dispatch at line 624)
- **Trigger:** A course-completion certificate is generated
- **Payload — ✅ verified:** `type: 'ap_enrollment'`, `actionType: 'Certificate Generated'`, `actionDescription` incl. course name, `student`, `enrollmentId`, `display_json: {course_name}` *(no `timestamp` key at this site, unlike most others — inconsistent)*

---

## 3. Live inbound webhook / external-callback endpoints

### `POST /api/v1/ai-assignments/webhook` (route name `ai-evaluation.webhook`)
- **Type:** Inbound HTTP webhook (external → this app)
- **Status:** 🟢 LIVE
- **Bounded context:** Assessment
- **Producer:** the external Auto-Evaluation AI API
- **Consumer:** `Modules\AIEvaluation\Http\Controllers\V1\AIEvaluationWebhookController::handle()` (163-line real implementation)
- **Auth:** `json.response` middleware only — **no authentication on this route**
- **Trigger:** External grading service posts back an AI evaluation result

### `POST /api/v1/ai-evaluation/webhook`
- **Type:** Inbound HTTP webhook
- **Status:** 🟢 LIVE
- **Bounded context:** Assessment
- **Consumer:** `AIEvaluationController::evaluationWebhook()`
- **Auth:** `auth:sanctum`, `json.response`
- **Notes:** A second, older webhook endpoint for the same external integration as above — confirm with the team which is current before relying on either

### `POST /v1/failed-api-responses`
- **Type:** Inbound HTTP intake
- **Status:** 🟢 LIVE
- **Bounded context:** Communication
- **Consumer:** `FailedApiResponseController::store()`
- **Auth:** `json.response` only, no auth

### `POST /v1/webhooks`, `POST /v1/webhook-events` (admin CRUD)
- **Type:** Admin management API, not itself an event
- **Status:** 🟢 LIVE (the CRUD works; what it manages, §2, does not fire)
- **Bounded context:** Communication
- **Auth:** `auth:sanctum`, `json.response`
- **Notes:** Configures subscriptions for a system that never dispatches — see `EVENT_LIST.md` §2

### `POST /v1/test-route`
- **Type:** Manual test trigger
- **Status:** 🟢 LIVE (route exists; behavior not further verified)
- **Bounded context:** Communication
- **Consumer:** `WebhookController::test()`
- **Notes:** No auth middleware specified on the route definition itself — verify before calling from any automated harness

---

## 4. Job-dispatched events (the real, live event mechanism)

Each entry's producer was individually grep-confirmed as live (uncommented) code for `EVENT_LIST.md` §4; entries marked "carried over" are drawn from the job/module pairing already verified in `DEVELOPER_DOCUMENTATION.md` §11 without a second per-line dispatch-site check.

### Enrollment activated
- **Status:** 🟢 LIVE — verified
- **Bounded context:** Enrollment
- **Producer:** `Modules/Enrollment/Http/Traits/EnrollmentTrait.php:901`
- **Consumer:** `EnrollmentActivatedJob` (queue `default_high`)
- **Payload:** collection of activated `Enrollment` models

### Enrollment deactivated
- **Status:** 🟢 LIVE — verified
- **Bounded context:** Enrollment
- **Producer:** `Modules/Enrollment/Http/Traits/EnrollmentTrait.php:1036` **and** `Modules/CourseBatch/Http/Controllers/CourseCalendarWebhookController.php:717` (two independent trigger paths)
- **Consumer:** `EnrollmentDeactivationJob` (queue `default_high`)
- **Payload:** collection of deactivated `Enrollment` models

### Enrollment batch added to Edmingle
- **Status:** 🟢 LIVE — verified
- **Bounded context:** Enrollment / Learning
- **Producer:** `Modules/Enrollment/Http/Traits/EnrollmentTrait.php:1653`
- **Consumer:** `CreateEdmingleBatch` (queue `default_medium`)

### Enrollment paused (missed-assignment handling)
- **Status:** 🟢 LIVE — verified
- **Bounded context:** Enrollment
- **Producer:** `Modules/Enrollment/Http/Controllers/EnrollmentController.php:2063`
- **Consumer:** `HandleMissedAssignments` (queue `default_medium`)

### Student activated (LMS batch sync)
- **Status:** 🟢 LIVE — verified
- **Bounded context:** Identity / Learning
- **Producer:** `Modules/Student/Http/Traits/StudentTrait.php:1163`
- **Consumer:** `ActivateStudentEdmingleBatches`

### Student deactivated (LMS batch sync)
- **Status:** 🟢 LIVE — verified
- **Bounded context:** Identity / Learning
- **Producer:** `Modules/Student/Http/Traits/StudentTrait.php:1243`, also `Modules/AgenticSupportSystem/Http/Traits/AgenticSupportSystemTraitV2.php:3181`
- **Consumer:** `DeactivateStudentEdmingleBatches`

### Package enrollment created
- **Status:** 🟢 LIVE — verified (3 independent trigger paths)
- **Bounded context:** Enrollment
- **Producer:** `Modules/Enrollment/Http/Traits/EnrollmentTrait.php:2203`, `Modules/Package/Jobs/PackageUpdateStudent.php:148`, `app/Console/Commands/PackageStudentUpdateEnrollment.php:138`
- **Consumer:** `PackageEnrollmentStudentAssignments`

### Package updated
- **Status:** 🟢 LIVE — verified
- **Bounded context:** Enrollment / Learning
- **Producer:** `Modules/Package/Jobs/PackageUpdateStudent.php`
- **Consumer:** the job itself, which on completion fires `PackageUpdateStudentCompleted` (see §1)

### Bulk enrollment CSV imported
- **Status:** carried over
- **Bounded context:** Enrollment
- **Consumer:** `EnrollmentCsvImport`

### Course/batch synced to calendar
- **Status:** carried over
- **Bounded context:** Learning
- **Consumer:** `SyncCourseWithCalendar`, `SyncEnrollmentWithCourseCalendarJob`

### Batch reschedule/cancel
- **Status:** carried over
- **Bounded context:** Learning
- **Consumer:** `CourseCalendarBulkBatchRescheduleJob`, `CourseCalendar*BatchJob`

### Student registered (LMS sync)
- **Status:** carried over
- **Bounded context:** Identity
- **Consumer:** `SyncUserWithLMS` (`Auth` module)

### Assignment assigned to student(s)
- **Status:** carried over
- **Bounded context:** Assessment
- **Consumer:** `AssignAssignmentsByFiltersJob`

### Assignment submitted (bulk)
- **Status:** carried over
- **Bounded context:** Assessment
- **Consumer:** `StudentAssignmentCsvImport`

### Assignment auto-graded
- **Status:** carried over
- **Bounded context:** Assessment
- **Consumer:** `EvaluateStudentAssignmentJob`, `BulkEvaluateStudentAssignmentsJob`

### Course material changed (AI sync)
- **Status:** carried over
- **Bounded context:** Assessment / Learning
- **Consumer:** `SyncCourseMaterialToAutoEvalJob`, `PropagateAIConfigToStudentAssignments`

### Notification broadcast requested
- **Status:** carried over
- **Bounded context:** Communication
- **Consumer:** `CreateNotificationForAll`, `CreateNotificationForSpecificStudents`, `CreateNotificationForAllForClass`

### Notification comment posted
- **Status:** carried over
- **Bounded context:** Communication
- **Consumer:** `CreateNotificationComment`, `CreateNotificationCommentStudent`

### Webhook dispatch requested
- **Status:** 🟡 reachable but never called live (only fires if §2 were re-enabled)
- **Bounded context:** Communication
- **Consumer:** `SendWebhookJob`

### Failed webhook response logged
- **Status:** carried over
- **Bounded context:** Communication
- **Consumer:** `LogFailedApiResponseJob`

### Installment payment received
- **Status:** carried over
- **Bounded context:** Enrollment
- **Producer:** `RevenueAPI` inbound controller
- **Consumer:** `ProcessInstallmentPaymentJob`

### FCM push token registered
- **Status:** carried over
- **Bounded context:** Identity
- **Consumer:** `SendUserSubscriberTokenToFCM`, `SendStudentSubscriberTokenToFCM`

### User synced to "other app"
- **Status:** carried over
- **Bounded context:** Identity / Integrations
- **Consumer:** `UpdateUserInOtherApp`, `SendUserDetailsToExternalApi`
- **Trigger:** User create/update with `ats=1` flag set

### Class roster changed *(deprecated feature)*
- **Status:** carried over — owning module not in active use
- **Bounded context:** Learning
- **Consumer:** `SyncClassParticipants`

### Project/task created *(deprecated feature)*
- **Status:** carried over — owning module not in active use
- **Bounded context:** Learning
- **Consumer:** `StudentTaskCreationJob`, `ProjectGroupStudentMappingJob`

### Coach allocated to student *(deprecated feature)*
- **Status:** carried over — owning module not in active use
- **Bounded context:** Learning
- **Consumer:** `PCAllocationJob`

### Any admin entity CSV export requested (pattern repeated across ~15 modules)
- **Status:** carried over
- **Bounded context:** cross-cutting
- **Consumer:** `*CSVDownloadStart` / `*CSVExport` job pairs

---

## 5. Related documents

- `documentation/EVENT_LIST.md` — the analysis and evidence behind every status/finding in this catalog
- `documentation/DEVELOPER_DOCUMENTATION.md` §11–12 — the full 128-job inventory this catalog's §4 draws from
- `documentation/DATABASE_SCHEMA.md` §6 — `webhooks`/`webhook_events`/`webhook_logs` table shapes referenced in §2–3
- `documentation/BOUNDED_CONTEXT_COMMUNICATION.md` — the context that owns the dead webhook-event mechanism
