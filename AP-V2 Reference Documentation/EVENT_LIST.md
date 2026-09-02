# Event List

> **Generated:** 2026-08-29 · **Branch surveyed:** `New-Dummy-Prod-0605`
> **Method:** every event/listener pair traced from `app/Providers/EventServiceProvider.php` plus every `Modules/*/Events` and `Modules/*/Listeners` directory; every dispatch call site (`event(new ...)`, `::dispatch(`) verified individually for whether it is live code or commented out — not inferred from the existence of the class. This document corrects and supersedes any impression from root-level `*.md` files or even this session's own earlier `DEVELOPER_DOCUMENTATION.md` §12 that this codebase has a working event-driven layer beyond what's proven live below.
> **Companion documents:** `documentation/CONTEXT_MAP.md`, `documentation/BOUNDED_CONTEXT_*.md`, `documentation/DOMAIN_MODEL_DIAGRAM.md`, `documentation/DEVELOPER_DOCUMENTATION.md` §11–12 (Jobs & Queues, Events & Listeners — this document goes deeper on both and corrects one item)

## Headline finding

This codebase has three layers that could each be called "the event system," and their actual liveness is very different from what their code footprint suggests:

| Layer | What it looks like | What it actually is |
|---|---|---|
| **Formal Laravel Events** (`app/Events`, `Modules/*/Events`, `EventServiceProvider`) | 4 custom events + 1 framework event, all registered | Only **2 of 5** are ever actually dispatched. One registered event (`BootcampAdditionalEnrollmentAdded`) has its only dispatch call commented out. One event class (`PackageEnrollmentStudentAssignmentsCompleted`) isn't even registered in `$listen` and is also never dispatched live |
| **Business webhook events** (`Modules\Webhook\Events\WebhookTriggered`, dispatched with a string event name like `'Course.Enrollment.AP'`) | ~30 distinct named business events, a full DB-backed subscription/dispatch/retry pipeline, admin CRUD UI for managing subscriptions | **100% dead.** Every single one of the 53 call sites that would fire one of these events is commented out, codebase-wide, with zero exceptions. The dispatch machinery works and would fire correctly if uncommented — it's the trigger points that were disabled |
| **Job-dispatched "pseudo-events"** (direct `Job::dispatch()` calls from controllers/traits, no Event class involved) | 128 job classes across `Modules/*/Jobs` | **This is the real, live event mechanism of the application.** Business occurrences (enrollment activated, batch created, student registered) trigger jobs directly, bypassing Laravel's Event system entirely |

If you're building anything that needs to react to "something happened" in this system — a QA harness, a new integration, a webhook consumer — **the job-dispatch layer (§4) is where the real signal is**, not the Events layer (§1) or the webhook-event catalog (§2), despite the latter looking, from its class structure alone, like the more "proper" implementation.

---

## 1. Formal Laravel Events

`app/Providers/EventServiceProvider.php` registers exactly 4 mappings:

```php
protected $listen = [
    Registered::class => [SendEmailVerificationNotification::class],
    BootcampAdditionalEnrollmentAdded::class => [AddBootcampAdditionalEnrollmentToBookDelivery::class],
    PackageUpdateStudentCompleted::class => [SendPackageUpdateEmailNotification::class],
    WebhookTriggered::class => [HandleWebhook::class],
];
```

| Event | Listener(s) | Dispatch site | Status | Notes |
|---|---|---|---|---|
| `Illuminate\Auth\Events\Registered` (framework) | `SendEmailVerificationNotification` (framework) | `Modules/Auth/Http/Controllers/RegisteredUserController.php:36` — `event(new Registered($user))` | ✅ **LIVE** | Standard Laravel registration flow, uncommented |
| `App\Events\BootcampAdditionalEnrollmentAdded` | `App\Listeners\AddBootcampAdditionalEnrollmentToBookDelivery` | `Modules/Enrollment/Http/Traits/EnrollmentTrait.php:3576` — `// event(new BootcampAdditionalEnrollmentAdded($courseEnrollment));` | ❌ **DEAD** | The only dispatch call in the entire codebase is commented out. `DEVELOPER_DOCUMENTATION.md` §12 (written the same day as this document) describes this as if live — it isn't; that was an oversight in that document, corrected here |
| `Modules\Package\Events\PackageUpdateStudentCompleted` | `Modules\Package\Listeners\SendPackageUpdateEmailNotification` | `Modules/Package/Jobs/PackageUpdateStudent.php:86` — `event(new PackageUpdateStudentCompleted($this->userEmail));` | ✅ **LIVE** | Fires at the end of the package-update job, triggers a confirmation email |
| `Modules\Webhook\Events\WebhookTriggered` | `Modules\Webhook\Listeners\HandleWebhook` | Many (see §2) | ⚠️ **Plumbing live, never actually fires** | The class, listener, and dispatch infrastructure all work; every business call site that would construct one is commented out (§2) |
| `Modules\Package\Events\PackageEnrollmentStudentAssignmentsCompleted` | *(none — not in `$listen` at all)* | `Modules/Enrollment/Jobs/PackageEnrollmentStudentAssignments.php:88` — `// event(new PackageEnrollmentStudentAssignmentsCompleted());` | ❌ **DEAD, twice over** | Not registered in `EventServiceProvider`, and its one dispatch site is commented out. Its intended listener, `Modules\Package\Listeners\SendEmailWhenJobsCompleted`, type-hints **both** this event and `PackageUpdateStudentCompleted` as two separate parameters on one `handle()` method — a signature Laravel's event dispatcher cannot satisfy from a single-event `$listen` entry (each event type calls `handle()` with only its own instance). This listener is also unreferenced by any `$listen` entry, so it never runs at all |

**Net result: of 5 registered/intended event-listener pairs, exactly 2 are live** (`Registered`, `PackageUpdateStudentCompleted`).

---

## 2. Business webhook-event catalog — designed, wired, and entirely dead

`Modules\Webhook\Events\WebhookTriggered` takes a free-form string `$eventName` and payload, so in principle it can represent any business event without a new class per event. A generic listener (`HandleWebhook` → `WebhookTrait::processWebhook()`) looks up `WebhookEvent::where('event_name', $event)`, finds any `Webhook` subscription rows configured for that event with `status = ACTIVE`, and dispatches `SendWebhookJob` (outbound `POST` with a shared secret, 5-attempt retry, logged to `webhook_logs`) for each one. This is a real, working, generically-designed event bus — see `Modules/Webhook/Http/Traits/WebhookTrait.php` and `Modules/Webhook/Jobs/SendWebhookJob.php`.

**But every single place in the business logic that would actually construct a `WebhookTriggered` with a meaningful event name is commented out.** A full-codebase search for `$this->trigger*Event(` (the wrapper-method convention this app uses to fire these) found **53 call sites, all 53 commented out, zero live**. The 30 distinct event names below were designed, given wrapper methods, and payload shapes — none of them fire today.

| Event name | Bounded context | Intended trigger | Wrapper method (dead) | Location |
|---|---|---|---|---|
| `Course.Enrollment.AP` | Enrollment | Staff manually enrolls a student in a course via the Assignment Portal | `triggerCourseEnrollmentEvent` | `EnrollmentController.php` |
| `Course.Enrollment.Lawsikho` | Enrollment | Student purchases a course via the main LawSikho site | `triggerCourseEnrollmentEvent` | `EnrollmentController.php` |
| `Bootcamp.Enrollment.AP` | Enrollment | Staff manually enrolls a student in a bootcamp | `triggerBootcampEnrollmentEvent` | `Enrollment/Http/Traits/EnrollmentTrait.php` |
| `Bootcamp.Enrollment.Lawsikho` | Enrollment | Student purchases a bootcamp via LawSikho | `triggerBootcampEnrollmentEvent` | `EnrollmentController.php` |
| `Package.Enrollment.Lawsikho` | Enrollment | Student purchases a package via LawSikho | `triggerPackageEnrollmentEvent` | `Enrollment/Http/Traits/EnrollmentTrait.php` |
| `Course.Migrate.AP` | Enrollment/Learning | An enrollment is migrated to a different batch/course | `triggerCourseMigrateEvent` | `Enrollment/Http/Traits/EnrollmentTrait.php` |
| `Enrollment.Certified` | Enrollment | Bulk certification of enrollments | `triggerEnrollmentCertifyEvent` | `Enrollment/Http/Traits/EnrollmentTrait.php` |
| `Enrollment.Updated.AP` | Enrollment | An enrollment's status is changed by staff | `triggerEnrollmentUpdateEvent` | `EnrollmentController.php` |
| `Certificate.Generate` | Learning | A completion certificate is generated | `triggerEventForGenerateCertificate` | `CourseCompletionMaster/Http/Traits/CourseCompletionMasterTrait.php` |
| `Certificate.Request.AP` | Enrollment | A student requests their certificate | `triggerCertificateRequestEvent` | `StudentFrontendEnrollment/Http/Controllers/StudentFrontendEnrollmentController.php` |
| `Assignment.Create.AP` | Assessment | An assignment is assigned to a student | `triggerStudentAssignmentEvent` / inline in `triggerWebhook()` | `StudentAssignmentController.php`, `StudentAssignment/Jobs/AssignAssignmentsByFiltersJob.php` — note even the job's own `triggerWebhook()` call (line 120) is itself commented out |
| `Assignment.Updated.AP` | Assessment | An assigned assignment's details are updated | `triggerUpdateAssignmentEvent` | `StudentAssignmentController.php` |
| `Assignment.Deleted.AP` | Assessment | A student assignment is deleted | `triggerDeleteAssignmentEvent` | `StudentAssignmentController.php` |
| `Assignment.Submit.AP` | Assessment | A student submits an assignment | `triggerAssignmentSubmitEvent` | `StudentAssignment/Http/Traits/StudentAssignmentTrait.php` |
| `Assignment.Resubmit.AP` | Assessment | A student resubmits an assignment | `triggerAssignmentResubmitEvent` | `StudentAssignment/Http/Traits/StudentAssignmentTrait.php` |
| `Student.Assignment.Submit.AP` | Assessment | Submission tracked from the student's "my courses" surface | `triggerStudentAssignmentSubmitEvent` | `StudentMyCourses/Http/Traits/StudentMyCoursesTrait.php` |
| `Admin.Assignment.Submit.AP` | Assessment | Admin manually marks a submission | `triggerAdminAssignmentSubmitEvent` | `StudentMyCourses/Http/Traits/StudentMyCoursesTrait.php` |
| `Result Evaluated` *(space, not dot-notation — inconsistent with every other name in this catalog)* | Assessment | An evaluator grades a submission | `triggerResultEvaluationEvent` | `Result/Http/Traits/ResultTrait.php` |
| `evaluator_csat_submitted` *(snake_case — also inconsistent)* | Communication | Student submits an evaluator CSAT survey | `triggerResultEvaluationCsatEvent` | `StudentFrontendEnrollment/Http/Controllers/EvaluatorCSATController.php` |
| `assignment_csat_submitted` *(snake_case)* | Communication | Student submits an assignment CSAT survey | `triggerAssignmentCsatEvent` | `StudentFrontendEnrollment/Http/Controllers/AssignmentCSATController.php` |
| `NPS.Submitted.AP` | Communication | Student submits an NPS survey | `triggerNPSSubmitEvent` | `StudentFrontendEnrollment/Http/Controllers/NPSController.php` |
| `Profile.Update.AP` | Identity | Student updates their own profile | `triggerProfileUpdateEvent` | `StudentProfile/Http/Traits/StudentProfileTrait.php` |
| `Profile.Update.By.Admin` | Identity | Admin edits a student's profile | `triggerEventforUpdate` | `Student/Http/Controllers/StudentController.php` |
| `Student.Profile.Updated` | Identity | Student self-service profile update (a second, overlapping path with `Profile.Update.AP`) | `triggerEventforUpdate` | `Student/Http/Traits/StudentTrait.php` |
| `Email.Updated` | Identity | Student's email address is changed | *(inline, same update flow)* | `Student/Http/Traits/StudentTrait.php` |
| `Student.Activate.AP` | Identity | Staff activates a student account | `triggerStudentActivateEvent` | `Student/Http/Traits/StudentTrait.php` |
| `Student.Deactivate.AP` | Identity | Staff deactivates a student account | `triggerStudentDeactivateEvent` | `Student/Http/Traits/StudentTrait.php`, also referenced (also dead) from `AgenticSupportSystem/Http/Traits/AgenticSupportSystemTraitV2.php` |
| `Weekday.availability.AP` | Learning (deprecated) | Coaching availability is set | `triggerWeekdayAvailabilityEvent` | `StudentPerformanceCoach/Http/Controllers/StudentPerformanceCoachController.php` — doubly dead: the trigger is commented out **and** the owning module is confirmed not in active use |
| `Password.Change` | Identity | Student changes their password | `triggerEventForPasswordChange` | `StudentAuth/Http/Controllers/NewPasswordController.php` |
| `Submit.Enrollmentform` | Enrollment | Student submits the enrollment questionnaire | `triggerSubmitEnrollmentFormEvent` | `LawSikho/Http/Traits/EnrollmentTrait.php` |

**Confirmed live receiving logic exists for only 3 of these 30 names** — `WebhookTrait::getActionDescription()` has a real `switch` case (with a `'no event found'` default) for `Course.Enrollment.AP`, `Course.Enrollment.Lawsikho`, and `Bootcamp.Enrollment.Lawsikho` only, suggesting these three were the most fully-built-out before the mechanism was disabled. That helper method itself, however, has **zero callers anywhere in the codebase** — it's dead code on the receiving side too.

**What would need to happen to revive this system:** uncomment the relevant `$this->trigger*Event(...)` call, ensure a matching row exists in `webhook_events` (`event_name` column) and at least one active row in `webhooks` pointing at a real subscriber URL, per `DATABASE_SCHEMA.md` §6. The naming inconsistency (`Result Evaluated` vs. dot-notation vs. `snake_case`) should probably be cleaned up before re-enabling, since `WebhookEvent::where('event_name', $event)` is an exact string match with no normalization.

---

## 3. Live inbound webhook / external-callback endpoints

Separate from the dead outbound business-event catalog above, these are **real, currently-reachable** endpoints that receive events *from* external systems:

| Endpoint | Purpose | Auth | Notes |
|---|---|---|---|
| `POST /api/v1/ai-assignments/webhook` (route name `ai-evaluation.webhook`) | Receives AI grading results from the external Auto-Evaluation API | `json.response` only — **no auth middleware on this route** | `AIEvaluationWebhookController::handle()`, a substantive 163-line implementation, confirmed real (not a stub) |
| `POST /api/v1/ai-evaluation/webhook` | A second, older AI evaluation webhook endpoint | `auth:sanctum`, `json.response` | `AIEvaluationController::evaluationWebhook()` — two webhook endpoints for the same integration exist; confirm with the team which is current before building test coverage against either |
| `POST /v1/failed-api-responses` | Generic failure-logging intake | `json.response` only, no auth | `FailedApiResponseController::store()` |
| `POST /v1/webhooks`, `POST /v1/webhook-events` (admin CRUD) | Manage outbound webhook subscriptions and the event catalog itself | `auth:sanctum`, `json.response` | This is the admin UI for the dead system in §2 — subscriptions can be configured here, but nothing will ever populate them since no event is ever dispatched |
| `POST /v1/test-route` | Manual webhook test trigger (`WebhookController::test`) | none specified in the route definition itself | Worth checking what this actually does before assuming it's safe to call from a QA harness |

The unauthenticated `ai-assignments/webhook` endpoint is worth flagging to the team directly if not already known — a public POST endpoint accepting grading results with no visible signature/secret check at the route-middleware layer (any header-based verification, if present, would be inside the controller body, not verified further here).

---

## 4. Job-dispatched events — the real event bus

This is what actually drives cross-cutting behavior in this application: a controller or trait detects a business occurrence and directly dispatches a job, with no Event class in between. Rows marked **✅ verified** had their dispatch call site individually grep-confirmed live (not commented) for this document; the rest are carried over from the job inventory in `DEVELOPER_DOCUMENTATION.md` §11 (itself derived from real job/module pairing) without a second per-line trigger-site check — treat those as high-confidence but not individually re-verified here.

| Business event | Context | Job(s) dispatched | Trigger site | Confidence |
|---|---|---|---|---|
| Enrollment activated | Enrollment | `EnrollmentActivatedJob` | `Enrollment/Http/Traits/EnrollmentTrait.php:901`, queue `default_high` | ✅ verified |
| Enrollment deactivated | Enrollment | `EnrollmentDeactivationJob` | `Enrollment/Http/Traits/EnrollmentTrait.php:1036` **and** `CourseBatch/Http/Controllers/CourseCalendarWebhookController.php:717` (two independent trigger paths) | ✅ verified |
| Enrollment batch-added to Edmingle | Enrollment/Learning | `CreateEdmingleBatch` | `Enrollment/Http/Traits/EnrollmentTrait.php:1653`, queue `default_medium` | ✅ verified |
| Enrollment paused (missed-assignment handling) | Enrollment | `HandleMissedAssignments` | `Enrollment/Http/Controllers/EnrollmentController.php:2063`, queue `default_medium` | ✅ verified |
| Student activated (LMS batch sync) | Identity/Learning | `ActivateStudentEdmingleBatches` | `Student/Http/Traits/StudentTrait.php:1163` | ✅ verified |
| Student deactivated (LMS batch sync) | Identity/Learning | `DeactivateStudentEdmingleBatches` | `Student/Http/Traits/StudentTrait.php:1243`, also from `AgenticSupportSystem/Http/Traits/AgenticSupportSystemTraitV2.php:3181` | ✅ verified |
| Package enrollment created | Enrollment | `PackageEnrollmentStudentAssignments` | `Enrollment/Http/Traits/EnrollmentTrait.php:2203`, `Package/Jobs/PackageUpdateStudent.php:148`, `app/Console/Commands/PackageStudentUpdateEnrollment.php:138` (three independent trigger paths) | ✅ verified |
| Package updated | Enrollment/Learning | `PackageUpdateStudent` → (on completion) fires `PackageUpdateStudentCompleted` event (§1) | `Package/Jobs/PackageUpdateStudent.php` | ✅ verified |
| Bulk enrollment CSV imported | Enrollment | `EnrollmentCsvImport` | Enrollment bulk-import endpoint | carried over |
| Course/batch synced to calendar | Learning | `SyncCourseWithCalendar`, `SyncEnrollmentWithCourseCalendarJob` | Course/batch save paths | carried over |
| Batch reschedule/cancel | Learning | `CourseCalendarBulkBatchRescheduleJob`, `CourseCalendar*BatchJob` | Batch admin actions | carried over |
| Student registered (LMS sync) | Identity | `SyncUserWithLMS` | `Auth` module, on registration | carried over |
| Assignment assigned to student(s) | Assessment | `AssignAssignmentsByFiltersJob` | Bulk assignment-by-filter admin action | carried over |
| Assignment submitted (bulk) | Assessment | `StudentAssignmentCsvImport` | Bulk assignment CSV import | carried over |
| Assignment auto-graded | Assessment | `EvaluateStudentAssignmentJob`, `BulkEvaluateStudentAssignmentsJob` | Submission → AI Evaluation dispatch | carried over |
| Course material changed (AI sync) | Assessment/Learning | `SyncCourseMaterialToAutoEvalJob`, `PropagateAIConfigToStudentAssignments` | Course AI-config update | carried over |
| Class roster changed *(deprecated feature)* | Learning | `SyncClassParticipants` | Zoom participant sync | carried over |
| Notification broadcast requested | Communication | `CreateNotificationForAll`, `CreateNotificationForSpecificStudents`, `CreateNotificationForAllForClass` | Admin notification composer | carried over |
| Notification comment posted | Communication | `CreateNotificationComment`/`CreateNotificationCommentStudent` | Notification comment endpoints | carried over |
| Webhook dispatch requested *(only reachable if §2 were re-enabled)* | Communication | `SendWebhookJob` | `WebhookTrait::processWebhook()` | ✅ verified reachable, but never called live (§2) |
| Failed webhook response logged | Communication | `LogFailedApiResponseJob` | `FailedApiResponseController::store()` (§3) | carried over |
| Project/task created *(deprecated feature)* | Learning | `StudentTaskCreationJob`, `ProjectGroupStudentMappingJob` | Project management actions | carried over |
| Coach allocated to student *(deprecated feature)* | Learning | `PCAllocationJob` | Coaching allocation admin action | carried over |
| Installment payment received | Enrollment | `ProcessInstallmentPaymentJob` | `RevenueAPI` inbound controller | carried over |
| Book delivery batch generated *(deprecated feature)* | Learning | `BookMasterCSVDownloadStart`, `BootcampBookMasterCSVDownload` | Book delivery admin export | carried over |
| Any admin entity CSV export requested | (cross-cutting) | `*CSVDownloadStart` / `*CSVExport` (pattern repeated across ~15 modules) | Respective module's export endpoint | carried over |
| FCM push token registered | Identity | `SendUserSubscriberTokenToFCM`, `SendStudentSubscriberTokenToFCM` | Login/device-registration flow | carried over |
| User synced to "other app" | Identity/Integrations | `UpdateUserInOtherApp`, `SendUserDetailsToExternalApi` | User create/update, ATS `ats=1` flag set | carried over |

For the full 128-job inventory (including every CSV export/import pattern not individually broken out above), see `DEVELOPER_DOCUMENTATION.md` §11 — this table re-frames a subset of the same data around "what business thing happened" rather than "which module owns the job," and adds file:line verification for the highest-traffic lifecycle events.

---

## 5. Notes for anyone building against this event surface

1. **Don't build a QA test or integration expecting the webhook-event catalog (§2) to fire.** Every trigger is commented out; testing "does enrolling a student produce a `Course.Enrollment.AP` webhook" will always fail, correctly, because the code doesn't do that today. This is a legitimate target for a "re-enable and test" ticket, not a bug to chase in current behavior.
2. **The job-dispatch layer (§4) is the reliable signal for "did X happen."** If you need to assert that enrollment activation had a side effect, look for the dispatched job (e.g., `EnrollmentActivatedJob` on the `default_high` queue) rather than any event.
3. **`QUEUE_CONNECTION=sync` locally** (per `DEVELOPER_DOCUMENTATION.md` §8) means every job in §4 runs inline during the request in local dev — there's no async delay to account for when testing locally, but staging/production (Redis + Horizon) will behave differently.
4. **The two unauthenticated inbound webhook endpoints** in §3 (`ai-assignments/webhook`, `failed-api-responses`) are real attack surface worth a deliberate look if this app's security posture is ever reviewed — flagged here, not assessed further.
5. **If the team ever decides to revive the §2 system**, the naming inconsistency (`Result Evaluated` vs. `snake_case` vs. `Dot.Notation.AP`) and the exact-match lookup in `WebhookTrait::processWebhook()` are worth fixing at the same time, not after.

## 6. Related documents

- `documentation/EVENT_CATALOG.md` — the reference lookup companion to this document: one structured entry per event (producer, consumer, payload, status), for looking up a specific event rather than reading the full analysis
- `documentation/DEVELOPER_DOCUMENTATION.md` §11–12 — the full 128-job inventory and the (now-corrected) formal events section
- `documentation/DATABASE_SCHEMA.md` §6 — `webhooks`/`webhook_events`/`webhook_logs` table shapes, including the two-identical-migrations finding for `webhooks`
- `documentation/BOUNDED_CONTEXT_COMMUNICATION.md` — the Communication context that owns the webhook mechanism
- `documentation/USER_WORKFLOWS.md` — end-to-end flows that this document's events are extracted from
