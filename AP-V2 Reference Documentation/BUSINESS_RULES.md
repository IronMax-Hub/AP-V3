# LawSikho Assignment Portal API — Business Rules

> **Generated:** 2026-08-29
> **Branch surveyed:** `New-Dummy-Prod-0605`
> **Companion documents:** [`documentation/DEVELOPER_DOCUMENTATION.md`](./DEVELOPER_DOCUMENTATION.md), [`documentation/USER_WORKFLOWS.md`](./USER_WORKFLOWS.md), [`documentation/API_SPECIFICATIONS.md`](./API_SPECIFICATIONS.md), [`documentation/DATABASE_SCHEMA.md`](./DATABASE_SCHEMA.md). This is the fifth and most policy-focused doc: not routes, not schema, not step-by-step flows — the actual **domain rules**: eligibility conditions, thresholds, formulas, and state-transition triggers, stated as testable "if X then the system does Y" statements with exact source locations.

## Method

The repo root has several `*_IMPACT_ANALYSIS.md` and `*_TASK_PLAN.md` files that read like authoritative specs (pause/refund/waiver, enrollment limits, KYC verification, installment automation, bootcamp title, resubmission reasons, AI evaluation). **These are planning documents, not records of what shipped.** Every rule below that touches one of these docs was verified directly against current code — grepping for the proposed classes/columns/methods, then reading the actual logic — rather than trusting the doc's prose. Where a proposal turned out unimplemented, partially implemented, or implemented differently, that's stated explicitly rather than silently repeating the plan as fact.

## Table of Contents

1. [Cross-Cutting Findings](#1-cross-cutting-findings)
2. [Enrollment Lifecycle Business Rules](#2-enrollment-lifecycle-business-rules)
3. [Course & Program Catalog Business Rules](#3-course--program-catalog-business-rules)
4. [Assignment & Grading Business Rules](#4-assignment--grading-business-rules)
5. [Student Engagement Business Rules](#5-student-engagement-business-rules)
6. [Admin Operations & External Integration Business Rules](#6-admin-operations--external-integration-business-rules)

---

## 1. Cross-Cutting Findings

### Three root-level feature proposals are entirely unimplemented — don't test for them

- **CR-10 Course Pause & Refund Waiver** (`CR10_COURSE_PAUSE_REFUND_WAIVER_*.md`) — the proposed 45-day refund window logic, `pauseWithRefundWaiver()` service method, and `refund_waiver_consent` audit event **do not exist in code** (verified via repo-wide grep, zero hits). Today's actual refund-eligibility check is a plain tag lookup (§2), and a refund-eligible student's only option is raising a support ticket — there is no self-service "waive refund and pause anyway" path yet.
- **Enrollment Limit / Batch Capacity** (`ENROLLMENT_LIMIT_*.md`) — **no batch capacity cap exists anywhere in the app.** No `enable_enrollment_limit`/`max_enrollment_count` columns, no capacity-checking service, zero code references. A batch can be enrolled into without limit today.
- **KYC Verification Gate** (`KYC_VERIFICATION_IMPACT_ANALYSIS.md`) — no KYC columns exist on `students`, no gate exists on certificate download. Independently confirmed the doc's own strongest finding is still true: certificate S3 URLs are permanent and already exposed in 5 listing resources *before* any download click, which would undermine a future click-time gate unless that leak is closed too.

### One bug-fix doc is accurate about the bug, inaccurate about the fix

`INSTALLMENT_AUTOMATION_MIGRATION_FIX.md` correctly describes a real double-reactivation bug — but the actual fix rides on a **pre-existing** `enrollments.deactivation_status` column (added by an unrelated migration) rather than the new `deactivated_by_migration` column the plan proposed. The proposed column doesn't exist; the bug is nonetheless genuinely fixed today (see §2).

### The resubmission-reason planning doc is now the stale one — its flagged bugs are fixed

`RESUBMISSION_REASON_IMPACT_ANALYSIS.md` flagged three bugs (a hardcoded string bypassing the reason-constant system, a reverse-mapping resource only handling 4 of 6 reasons, a mailable silently dropping the reason argument). **All three are now fixed in current code** — this is the opposite direction from most other findings in this session, where docs described unbuilt features. Don't apply that doc's bug list to current behavior; see §4.

### A recurring "unordered first row" pattern — three independent instances

The same class of bug shows up in three unrelated places: NPS's "earliest assignment" check uses `StudentAssignment::where(...)->first()` with no `ORDER BY` (§5); `EmailTemplate`'s role-scoped retrieval uses `auth()->user()->roles[0]` with no ordering on the underlying pivot (§6); and — while not itself buggy — `results.assignment_id`'s naming trap (documented in `documentation/DATABASE_SCHEMA.md` §1) reflects the same "assume the obvious thing without verifying" pattern at the schema level. None of these are guaranteed-correct without an explicit `ORDER BY`, even though they usually happen to return a plausible answer.

### A previously-undocumented, live integration: Employer Service registration

Staff `User` creation/update with `ats=1` triggers a two-step external registration chain (job-portal registration, then an employer-service record with **hardcoded placeholder company data**) via `SendUserDetailsToExternalApi` — confirmed live, matches `EMPLOYER_SERVICE_API_IMPLEMENTATION.md` accurately, but wasn't caught by any of the previous 4 docs' full-codebase audits. See §6. Worth adding to `DEVELOPER_DOCUMENTATION.md`'s external integrations list.

### AI evaluation shipped without three of its planned audit/safety rules

`AI_EVALUATION_TASK_BREAKDOWN.md`'s explicit "never overwrite `ai_score`/`ai_feedback`" audit requirement is violated by the live `edit-feedback` endpoint (it overwrites directly, `reviewer_edited_score`/`reviewer_edited_feedback` columns exist but are never written to). The planned "course materials must be synced before triggering evaluation" precondition was never implemented. The planned "re-sync on AI model change" trigger exists in code but is commented out. See §4.

### Several evaluator/notification/RBAC gaps between what a column/comment implies and what the code does

- `Course.default_written_evaluator_id` exists, is settable via the API, and is **never read** — written-assignment submissions get the same `default_evaluator_id` as subjective ones (§4).
- Role deactivation has an inline comment `// Deactivate Users` but the code only logs an activity — assigned users are never touched (§6).
- `create_notification_for_all` and `create_notification_for_specific_range` are byte-for-byte identical methods; neither populates the `notification_user` table that actually gates per-student visibility — the real delivery mechanism lives elsewhere, unaccounted for in this pass (§5).

---

## 2. Enrollment Lifecycle Business Rules

> Four repo-root planning docs cover this domain. **All four describe proposed/planned changes, not current behavior.** Three of the four (pause/refund waiver, enrollment limits, KYC gate) are **not implemented at all**. The fourth (installment automation) describes a real, now-fixed bug — fixed differently than proposed.

### Pause, Resume & Refund Eligibility (CR-10 proposal — mostly not implemented)

#### Rule: Refund-eligibility check is a pure tag lookup, not a date calculation
**Statement:** Whether a student can pause a course without triggering a refund-eligibility warning depends entirely on whether their `Enrollment` has a tag named exactly `Refund Eligible`. No date/window logic exists in this check today.
**Threshold/formula:** `$this->tags()->where('name', '{"en":"Refund Eligible"}')->exists()` — the tag name is matched against the **raw JSON-encoded multi-locale string**, not plain text (spatie/laravel-tags stores `name` as JSON). A fixture tagging with plain `"Refund Eligible"` will NOT satisfy this check.
**Source:** `Modules/Enrollment/Entities/Enrollment.php:384-387`.
**Implementation status:** confirmed live. The CR's proposed 45-day window logic (`isRefundWindowExpired()`) does not exist — proposed-not-found.
**QA implication:** Seed/remove the tag with the exact JSON-locale name shown above to test either branch — no date field exists to manipulate instead.

#### Rule: Pause is blocked by refund-eligibility tag OR an existing pause-adjacent status
**Statement:** `CoursePauseService::checkEligibility()` returns `eligible=false` if (a) no batch is assigned, (b) the enrollment is refund-eligible, or (c) status is already `PAUSED`/`RESUME_REQUESTED`/`PAUSE_REQUESTED`.
**Threshold/formula:** exact reason strings: `'No batch is assigned to this enrollment.'`, `'refund_eligible'`, `'already_paused_or_resume_requested'`.
**Source:** `Modules/Enrollment/Services/CoursePauseService.php:22-79`.
**Implementation status:** confirmed live.
**QA implication:** Use these exact reason strings as assertion targets.

#### Rule: "Raise Request" is the only student-facing path for a refund-eligible pause today
**Statement:** A refund-eligible enrollment cannot be paused directly by the student — the only action is `POST refund-eligible-pause/{enrollment}`, requiring a `ticket_id`, setting status to `PAUSE_REQUESTED` without actually pausing. No self-service "waive refund and pause anyway" endpoint exists.
**Source:** `Modules/Enrollment/Http/Controllers/EnrollmentController.php` (`refundEligiblePauseRequestStudent`).
**Implementation status:** confirmed live (pre-CR-10 baseline). The CR-10 waiver-pause endpoint, service method, and audit event — proposed-not-found (zero grep hits for `pauseWithRefundWaiver`, `isRefundWindowExpired`, `refund-waiver-pause`, `refund_waiver_consent`).
**QA implication:** Don't test for a self-service refund-waiver-and-pause action — it doesn't exist yet.

#### Rule: `enrollment_pause_log_new.accepted`/`.rejected` don't exist
**Statement:** `PauseResumeHistoryResource::getDisplayStatusLabel()` reads `$this->accepted`/`$this->rejected`, but the migration meant to add those columns has its `up()` entirely commented out (see `documentation/DATABASE_SCHEMA.md` §2). These fields will always read `null`.
**Implementation status:** confirmed broken/incomplete — a live schema gap, not a planning-doc discrepancy.
**QA implication:** Any test asserting on `accepted`/`rejected` in a pause-history response should expect `null`.

### Enrollment Limits / Batch Capacity (proposal — not implemented)

#### Rule: No batch capacity limit exists anywhere in the app today
**Statement:** There is no way to cap enrollments per batch — no `enable_enrollment_limit`/`max_enrollment_count` columns, no `BatchCapacityService`, no "batch full" error path anywhere.
**Source:** verified via repo-wide grep — zero hits for `enable_enrollment_limit`, `max_enrollment_count`, `BatchCapacityService`, `BatchCapacityExceeded`.
**Implementation status:** proposed-not-found — the entire proposal is unimplemented.
**QA implication:** Do not test for a "batch full" 422 on any enrollment-creation endpoint; a batch can be enrolled into without limit today.

#### Rule: The only existing "seats used" calculation is purely informational
**Statement:** `CourseCalenderAPITrait::getStudentCountInCourseAndBatch()` counts active enrollments per course+batch for external Course Calendar reporting — it enforces nothing.
**Source:** `Modules/AgenticSupportSystem/Http/Traits/CourseCalenderAPITrait.php:163+`.
**Implementation status:** confirmed live, zero enforcement effect.
**QA implication:** Safe to test as a read-only count; enrolling past this count is never blocked.

### KYC Verification Gate on Certificates (proposal — not implemented)

#### Rule: Certificate download has no KYC gate; the certificate URL is already public before any gate could apply
**Statement:** No NSDC/KYC columns exist on `students` (zero grep hits for `kyc_self_declaration`/`kyc_approved_by`/etc.). Even if a click-time gate were added, it would be bypassable today because the certificate's permanent, non-expiring S3 URL is already returned directly in 5 different enrollment-listing resources before any download click.
**Source:** `KYC_VERIFICATION_IMPACT_ANALYSIS.md` §1 (verified: `generateCertificate()` uses `Storage::disk('s3')->url()`, not `temporaryUrl()`; an unused `s3-private` disk is already configured in `config/filesystems.php`).
**Implementation status:** proposed-not-found. The S3-URL-leak is a real, currently-live fact any future gating design must account for.
**QA implication:** A future "unverified student can't download certificate" test must also confirm the URL isn't already retrievable from a listing endpoint — testing only the download-click endpoint gives a false sense of security.

### Installment Payment Automation — a real bug, fixed differently than planned

#### Rule: Reactivating a PENDING enrollment via installment payment excludes migration-deactivated enrollments
**Statement:** `ProcessInstallmentPaymentJob`'s `fetchPendingEnrollments()` only reactivates `PENDING` enrollments where `deactivation_status = Enrollment::NORMAL_DEACTIVATION` (0) — enrollments deactivated as the *source* of a batch/course/bootcamp migration are excluded.
**Threshold/formula:** `Enrollment::where('student_id', $id)->where('status', PENDING)->where('deactivation_status', NORMAL_DEACTIVATION)` plus a `type` filter.
**Source:** `Modules/RevenueAPI/Jobs/ProcessInstallmentPaymentJob.php:124-147`.
**Implementation status:** ⚠️ implemented differently than the plan describes. `INSTALLMENT_AUTOMATION_MIGRATION_FIX.md` proposes a new `deactivated_by_migration` column with a historical backfill — **none of that exists** (zero grep hits). Instead, the bug is fixed via the pre-existing `deactivation_status` column: every migration-deactivation call site now sets the matching constant, and the job filters on it.
**QA implication:** A regression test for "installment payment doesn't reactivate a migration-superseded enrollment" is valid and should pass today — write it against `deactivation_status`, not `deactivated_by_migration`. Reliable for enrollments deactivated after 2026-06-01 (when the column was introduced); see `documentation/DATABASE_SCHEMA.md` §1 for the historical-backfill caveat on older rows.

---

## 3. Course & Program Catalog Business Rules

### Rule: Bootcamp `title`/`name` split — partially implemented, and the implemented part differs from proposed
**Statement:** `BOOTCAMP_TITLE_IMPACT_ANALYSIS.md` proposes splitting `bootcamps.name` (batch-specific) from a new `title` (stable display name), with `title ?? name` fallback and no more denormalizing `bootcamp_name` onto new enrollments.
**Actual verified behavior:**
- ✅ Done as proposed: `title` column exists; `Bootcamp` model has `getDisplayNameAttribute()` returning `title ?? name`; `bootcamp_from_lawsikho` accepts/stores `title`; enrollment type-determination already uses `bootcamp_id` presence, not `bootcamp_name`.
- ⚠️ NOT as proposed: `Enrollment::getBootcampDisplayNameAttribute()` **concatenates** `"<name> - <title>"` when both exist, rather than preferring `title` alone. A second accessor, `getBootcampStudentNameAttribute()`, ignores `title` entirely and returns only `bootcamp_name ?? bootcamp?->name` — two overlapping accessors exist; confirm which resource actually calls which before asserting.
- ⚠️ NOT done at all: the core goal — stop denormalizing `bootcamp_name` onto new enrollments — was never implemented. `EnrollmentTrait` still writes `bootcamp_name` on every enrollment-creation path (now auto-resolved from `bootcamp_id` if not explicitly passed, but still written). The dependent P1 fixes in the proposal likely were never needed since their precondition never materialized.
**Source:** `Modules/Bootcamp/Entities/Bootcamp.php`; `Modules/Enrollment/Entities/Enrollment.php:200-215`; `Modules/Enrollment/Http/Traits/EnrollmentTrait.php:161-180`.
**QA implication:** Assert the `"name - title"` concatenation when both are set, not `title` alone. Don't assume `bootcamp_name` is ever null on new enrollments.

### Rule: Course completion pass/fail formula (non-bootcamp course)
**Statement:** A non-bootcamp enrollment completes only if it clears a per-category subjective-score threshold AND (if criteria defines written exercises) a written-score threshold AND an overall total-percent threshold.
**Threshold/formula (from `CourseCompletionMasterTrait::marksheetCalculation()`):**
1. Read `enrollment.passing_criteria` JSON — if null, `403 "No criteria found"`, stop.
2. Collect subjective `Result.obtain_marks` across all `student_assignments`, sort descending, take **top `minSubjectiveAssignment` scores only** — extra submissions beyond the minimum don't count. Exception: if `count(subjective) > totalWrittenAssignment` (⚠️ compares subjective count against the *written* threshold — looks like a copy-paste artifact, not intentional logic) it still takes the top-N; otherwise sums all unsliced.
3. If `totalWrittenAssignment` is truthy: same top-N-and-sum for written scores. Written pass check: `countWris >= minWri AND writtenTotalMarks != 0 AND (totalWriScore*100)/writtenTotalMarks >= wittenPassPercent` [sic, literal JSON key typo].
4. Subjective pass check: `countSubs >= minSub AND subjectiveTotalMark != 0 AND (totalSubScore*100)/subjectiveTotalMark >= subjectivePassPercent`.
5. `complete = 1` only if: written check passes (when applicable) AND subjective check passes AND `(totalScore*100)/totalMarks >= minTotalPassPercent`.
6. `completed_at` is set **once** (guarded by `is_null`) — a re-run after a regrade won't update it even if completion status changes; `current_percent`/`completed` themselves are overwritten every run.
**Exact `passing_criteria` JSON keys** (a translation layer, not a direct table-column copy): `minSubjectiveAssignment`, `minSubjectiveAssignmentPercent`, `totalWrittenAssignment`, `perWriMarkrs` [sic], `writtenTotalMarks`, `lms_mcq`, `minTotalPassPercent`, `wittenPassPercent` [sic], `subjectivePassPercent`, `pass_marks_needed`, `totalMarks`, `subTotalMarksForPass`, `subjectiveTotalMark`.
**Source:** `Modules/CourseCompletionMaster/Http/Traits/CourseCompletionMasterTrait.php:126-433`.
**QA implication:** Seed `passing_criteria` directly with the exact camelCase/typo'd keys — `course_criterias`' snake_case columns don't appear verbatim. Test the "extra submissions capped at top-N" behavior explicitly.

### Rule: Course completion pass/fail formula (bootcamp enrollment)
**Statement:** If `bootcamp_id` is set AND the course is `course_type = BOOTCAMP_COURSE` AND a `course_criterias` row exists, both subjective and written thresholds are checked (written read live from `course_criterias`, the one documented exception to "always from the snapshot"). Otherwise, only the subjective threshold applies, with **no total-percent gate at all**.
**Source:** same trait, lines 162-305.
**QA implication:** A bootcamp enrollment with no `course_criterias` row completes on subjective score alone, no overall percentage gate — don't apply the non-bootcamp path's total-percent rule here.

### Rule: Certificate letter-grade bands
**Statement:** Grade is a step function of `current_percent`, all lower bounds inclusive:

| current_percent | Grade |
|---|---|
| ≥ 90 | A+ |
| ≥ 80, < 90 | A |
| ≥ 70, < 80 | B+ |
| ≥ 60, < 70 | B |
| ≥ 50, < 60 | C+ |
| ≥ 40, < 50 | C |
| < 40 | `''` (empty string, not "F"/"D") |

**Source:** `Modules/CourseCompletionMaster/Http/Traits/CourseCompletionMasterTrait.php:461-474`.
**QA implication:** Test exact boundaries (89.99→A, 90.00→A+, 39.99→'', 40.00→C).

### Rule: Course-batch date uniqueness is global, not per-course
**Statement:** `course_batches.batch_date` has a plain global unique constraint — no course or Zoom-account scoping, confirmed identical at both DB and validation layers.
**Source:** migration + `StoreRequest.php:29-30` / `UpdateRequest.php:14-16`.
**QA implication:** Two different courses genuinely cannot share a batch date — a deterministic collision test.

### Rule: Category vs. course-level criteria precedence is resolved at enrollment-creation time
**Statement:** On enrollment creation, the system looks up `course_criterias` for the course FIRST; if none, falls back to `course_category_criterias` for the course's category; if neither, no snapshot is taken (later completion checks 403). No code auto-copies category criteria into a course-level row — the tables stay independent, resolved only at snapshot time.
**Threshold/formula:** `if (course_criterias exists) use it; elseif (course_category_id set) use category criteria; else no snapshot`.
**Source:** `Modules/Enrollment/Http/Traits/EnrollmentTrait.php` (~line 428-430).
**QA implication:** Seed only category criteria → enroll → expect a valid snapshot via fallback. Seed both → expect course-level values win. Seed neither → expect `passing_criteria` stays null.

### Rule: Course AI-config change propagates to NOT-yet-AI-enabled assignments (correction to earlier doc)
**Statement:** Updating a course's `ai_model_id`/`assignment_instruction_link`/`assignment_sample_feedback_link`/`is_ai_enabled` updates `Assignment`/`StudentAssignment` rows that currently have AI **disabled** — it does NOT touch already-AI-enabled assignments. **This corrects `documentation/USER_WORKFLOWS.md` §2.1**, which had the direction backwards.
**Threshold/formula:**
1. `Assignment::where('course_id', $id)->where('is_ai_enabled', 0)->update($propagateData)` — runs when any of the 4 fields changed (via `wasChanged()`).
2. `StudentAssignment::whereIn('enrollment_id', <course's enrollments>)->where('is_ai_enabled', 0)->where('status', '!=', EVALUATED)->update($propagateData)` — additionally excludes finalized assignments.
3. If `ai_model_id`/link fields (not a bare `is_ai_enabled` toggle) changed: also dispatches `PropagateAIConfigToStudentAssignments` (a deeper, separately-queued propagation, not traced further).
**Source:** `Modules/Course/Http/Traits/CourseTrait.php:355-416`.
**QA implication:** Create a course with one AI-enabled and one AI-disabled assignment, update the course's `ai_model_id` — expect only the disabled one to change synchronously; already-`EVALUATED` student assignments should never be touched.

---

## 4. Assignment & Grading Business Rules

> The resubmission-reason planning doc (`RESUBMISSION_REASON_IMPACT_ANALYSIS.md`) is the one root doc in this whole exercise whose flagged problems have since been **fixed** — don't apply its bug list to current behavior.

### Resubmission Gate

#### Rule: Subjective-only automatic resubmission gate, strictly `< 4`
**Statement:** When an evaluator saves scores, if the assignment is subjective AND at least one exercise score is below 4, the result bounces back for resubmission.
**Threshold/formula:** Per-exercise, **not an average** — breaks and flags resubmit on the first score where `obtain_marks < 4` (strictly less than; exactly `4` does not trigger it). Skipped entirely if `assignment_type != TYPE_SUBJECTIVE` — written assignments can never trigger this regardless of score.
**Source:** `Modules/Result/Http/Controllers/ResultController.php:266-289`.
**QA implication:** Test a subjective assignment where only exercise 2 of 3 scores <4 — expect resubmit despite exercises 1/3 passing. Same scenario on written — expect no resubmit regardless of scores.

#### Rule: Automatic resubmit reason is now a constant (fixed since the impact-analysis doc was written)
**Statement:** The auto-resubmit gate stores `reason = Result::REASON_NEW_4` ("Based on Evaluator Feedback").
**Implementation status:** the impact-analysis doc flagged a hardcoded raw string bypassing the constant system at this exact call site — **that's since been fixed**; current code uses the constant.
**Source:** `ResultController.php:282`.
**QA implication:** Assert `results.reason == "Based on Evaluator Feedback"` after auto-resubmit.

### Resubmission Reason Constants — live vs. dead sets

#### Rule: Two duplicated constant sets exist on both `Result` and `ResultView`; only `REASON_NEW_*` is live
**Statement:** Both entities define `REASON_ONE`–`FOUR` (plagiarism wording) and `REASON_NEW_1`–`NEW_6` (file-format/evaluator-feedback wording). Only `REASON_NEW_*` is referenced by the live student `re-submit` endpoint's integer 1–6 mapping; `REASON_ONE`–`FOUR` have no live call site.
**Implementation status:** implemented differently than the impact-analysis doc describes — that doc's framing is inverted relative to today's code (it called the file-format set "current, about to be replaced"; in reality it was renamed to `REASON_NEW_*` and remains live, while the plagiarism set was promoted into `Result.php` itself but stayed unused). The reconciliation the doc called for did not happen — duplication now exists in two files instead of one.
**Source:** `Modules/Result/Entities/Result.php:38-52`, `ResultView.php:40-53`, `Modules/StudentAssignment/Http/Traits/StudentAssignmentTrait.php:915-952`.
**QA implication:** Use `REASON_NEW_1`–`REASON_NEW_6` (int 1–6 via API) for all resubmission-reason fixtures — `REASON_ONE`–`FOUR` are inert.

#### Rule: Reverse-mapping (DB string → API integer) now covers all 6 reasons (fixed)
**Statement:** `AssignmentsDetailsResource::getReason()` checks all six `REASON_NEW_*` constants. The impact-analysis doc flagged this as only handling 4 values with reason 5 silently returning `null` — **that's been fixed**.
**Source:** `Modules/StudentMyCourses/Http/Resources/AssignmentsDetailsResource.php:89-115`.
**QA implication:** A round-trip test (submit reason=6 → read back → expect 6) should pass for all 6 values now.

#### Rule: Resubmission reason is now rendered in the student email (fixed)
**Statement:** `AssignmentResubmit` accepts a `$reason` argument and the blade template renders reason-specific text. The impact-analysis doc flagged the mailable as silently ignoring this — **fixed**, but note the two resubmission triggers (manual `re_submit()` vs. automatic score-gate) use **different mailables** with different constructor signatures.
**Source:** `Modules/StudentAssignment/Emails/AssignmentResubmit.php:20-25`; `resources/views/emails/student-assignments/resubmit.blade.php:80-88`.
**QA implication:** Confirm which trigger path a test is exercising — the manual `re_submit()` path is the one confirmed fixed.

### Submission Attempt Limit (`submit_counter`)

#### Rule: Counter starts at 4, decrements by 1, blocks at 0
**Statement:** `submit_counter` initializes to `4`, decrements unconditionally by 1 on every accepted submission (both staff-mediated and student-self-service endpoints), blocked with 403 once `<= 0`.
**Source:** `Modules/StudentAssignment/Http/Traits/StudentAssignmentTrait.php:550` (init), `:624` (gate), `:721,733,801` (decrement sites).
**QA implication:** 4 successful submit→auto-resubmit cycles should still allow a 5th attempt, since each resubmit restores the counter (see next rule).

#### Rule: Counter restoration has two DIFFERENT cap behaviors depending on the resubmit path
**Statement:** Both resubmission triggers restore `submit_counter +1`, but only one caps it.
**Threshold/formula:** Automatic score-gate path (`ResultController.php:287-289`) increments **unconditionally**, no upper bound. Manual `re_submit()` path (`StudentAssignmentTrait.php:978-980`) increments **only if `<= 3`** — explicitly won't push past 4.
**Implementation status:** confirmed live; a genuine inconsistency between the two paths, not documented elsewhere.
**QA implication:** A boundary worth an explicit regression test — the two code paths disagree on whether the counter can exceed its original starting value.

#### Rule: Manual `re_submit()`'s second eligibility branch is dead code
**Statement:** `re_submit()` proceeds if `status == SUBMITTED`, OR (`status == RESUBMITTED` AND `assignment.plagiarism == 1`) — but `STATUS_RESUBMITTED` is never actually set anywhere live (the plagiarism check that would set it is hardcoded off), so the second branch is unreachable.
**Source:** `StudentAssignmentTrait.php:952-957`.
**QA implication:** Treat `re_submit()` as gated purely on `STATUS_SUBMITTED`.

### AI-Assisted Evaluation — plan vs. reality

#### Rule: "Never overwrite ai_score/ai_feedback" audit rule — proposed, violated by the live edit endpoint
**Statement:** The FRD's TASK-21 requires reviewer edits to go into separate `reviewer_edited_score`/`reviewer_edited_feedback` columns, never overwriting the original AI output.
**Source (actual code):** `Modules/AIEvaluation/Http/Controllers/V1/AIModelBulkAssignmentController.php::editFeedback()` — writes directly into `ai_feedback`/`ai_score` on the same row; `reviewer_edited_*` columns exist in the DB but are never written to anywhere in the app (confirmed via grep).
**Implementation status:** proposed-not-found / implemented in violation of the plan's own audit requirement.
**QA implication:** A test expecting the pre-edit AI score to remain recoverable after `POST /api/v1/ai-assignments/edit-feedback` will fail — there is no way to recover it. Flag to the team as a real gap if audit/recoverability matters.

#### Rule: "Course materials must be synced before triggering evaluation" — proposed, not implemented
**Statement:** The FRD's TASK-17 specifies checking `ai_course_material_syncs.sync_status` before allowing an evaluation trigger, rejecting with 422 if not ready.
**Source (actual code):** no read of `sync_status` from any trigger/evaluate path (grepped `Modules/AIEvaluation`).
**Implementation status:** proposed-not-found.
**QA implication:** Triggering evaluation for a never-synced course will NOT be rejected — it proceeds and presumably fails downstream at the external service instead.

#### Rule: "Re-sync on AI model change" — proposed, present only as commented-out code
**Statement:** TASK-08 specifies that changing a course's `ai_model_id` should mark its sync row `pending`.
**Source:** `AIModelBulkAssignmentController.php:125` — the exact implementing line exists but is entirely commented out.
**Implementation status:** proposed-not-found (dead code).
**QA implication:** Changing a course's AI model via bulk-assignment will NOT auto-trigger a re-sync.

### Evaluator Assignment

#### Rule: Submission-time evaluator pre-fill always uses the subjective default
**Statement:** `Result.evaluator_id` is pre-filled from `enrollment.course.default_evaluator_id` unconditionally, regardless of whether the submitted assignment is subjective or written.
**Threshold/formula:** `Course.default_written_evaluator_id` — a distinct column that exists and is settable via the API — is **never read** at submission time (confirmed via grep, both `default_evaluator_id` reads hardcode the same column).
**Source:** `Modules/StudentAssignment/Http/Traits/StudentAssignmentTrait.php:708,789`.
**Implementation status:** confirmed live, likely-unintended gap.
**QA implication:** Set a course's `default_written_evaluator_id` different from `default_evaluator_id`, submit a WRITTEN assignment — expect `default_evaluator_id` to be assigned, not the written-specific one, despite the field name.

#### Rule: Round-robin evaluator distribution is deterministic and order-preserving
**Statement:** `assignEvaluatorRoundRobin` distributes via `resultIndex % totalEvaluators`, indexing directly into the `evaluator_id[]` array exactly as submitted (not re-sorted).
**Threshold/formula:** explicit `result_id[]` → `i` = position in the caller-submitted array order. `current_cond` (filtered view) branch → `i` = position in a query explicitly `ORDER BY id ASC`.
**Source:** `Modules/Result/Http/Traits/ResultTrait.php:458-535`; `ResultRepository.php:257-272`.
**QA implication:** For a deterministic test, predict assignment via `index % evaluatorCount` against the submitted array order (explicit list) or ascending `result.id` (filtered view) — reordering the evaluator array changes outcomes for the same result set.

---

## 5. Student Engagement Business Rules

### NPS Survey Triggers

#### Rule: NPS Survey Type 1 (mid-course pulse) trigger
**Statement:** Offered once the earliest assignment for an enrollment is more than 30 days old, and no Type-1 response exists yet.
**Threshold/formula:** `strtotime($earliestAssignment->created_at) < strtotime('-30 days')` AND zero existing `(enrollment_id, SURVEY_TYPE_1)` rows. "Earliest" is `StudentAssignment::where(...)->first()` with **no `ORDER BY`** — not a guaranteed chronological minimum (see §1).
**Source:** `Modules/StudentDashboard/Http/Traits/StudentDashboardTrait.php::getSurveyData()`, ~lines 220-247.
**QA implication:** Seed a single `student_assignments` row (to sidestep the ordering ambiguity) with `created_at` -31 days, zero Type-1 rows, and confirm the survey fires.

#### Rule: NPS Survey Type 2 (completion survey) trigger — two matching sub-conditions
**Statement:** Offered once `completed == 1` AND `mcq_completed` exactly matches whether the course's criteria requires MCQ.
**Threshold/formula:** `mcqValid` = `'Y'` if `passing_criteria.criteria[0].lms_mcq == 'Y'` (also defaults `'Y'` if `passing_criteria` unset), else `'N'`. Fires if: (`completed==1 AND mcq_completed==1 AND mcqValid=='Y'`) OR (`completed==1 AND mcq_completed==0 AND mcqValid=='N'`) — both also require zero existing Type-2 rows. A completed enrollment where `mcq_completed` **disagrees** with `mcqValid` never triggers the survey under either branch — a legitimate "stuck" state.
**Source:** same trait, ~lines 249-290.
**QA implication:** Test all four `(mcq_completed, mcqValid)` combinations — two should trigger, two (including the disagreement case) should not.

#### Rule: NPS rating-branch storage — identical thresholds in v1 and v2
**Statement:** `rating > 8` → `suggestions` only, `reason='N'`. `rating > 6` (7 or 8) → `experience` + `reason='N'`. `rating <= 6` → `experience` + `reason='Y'`.
**Implementation status:** confirmed identical in both `StudentDashboard`'s v1 and `NPS`'s v2 implementations — no discrepancy on this specific rule despite the two otherwise diverging schemas (`documentation/API_SPECIFICATIONS.md` §5).
**QA implication:** One shared boundary-value test suite (rating = 6, 7, 8, 9) validates both endpoints.

### CSAT Duplicate-Submission Rules — different key per CSAT type

| CSAT type | Dedup key | Status |
|---|---|---|
| AssignmentCSAT | `(student_id, assignment_id, enrollment_id)` OR `(student_id, assignment_id, package_id)` — whichever context field is present | live |
| EvaluatorCSAT | `(student_id, result_id)` | live |
| ClassCSAT | `(student_id, class_date_relation_id)` | ⚠️ module not in production use |
| PerformanceCoachCSAT | `(student_id, result_id)` | ⚠️ module not in production use |

**Notable:** On a duplicate, AssignmentCSAT/EvaluatorCSAT return HTTP **200** with `{"message": "Already Submitted"}` — not an error status. A QA test must check message text, not status code, to detect a rejected duplicate.
**Source:** each module's own `store()`/`checkIfDuplicate()`.

### StudentBookACall Cancellation / Reschedule / No-Show Policy

#### Rule: No minimum-notice restriction on cancel or reschedule
**Statement:** No time-based rule prevents cancelling/rescheduling close to (or after) a booking's start time — searched for `diffInHours`/`diffInMinutes`/notice-period logic; the only time-diff calculations found compute meeting *duration*, not a notice gate.
**Implementation status:** confirmed absent, not a research gap. If such a policy exists, it lives entirely in the external `BOOK_A_CALL_API` sub-project.
**QA implication:** A test can freely cancel/reschedule at any point relative to start time and should expect success from this app's side.

#### Rule: No-show marking has no local policy — pure external pass-through
**Statement:** No eligibility check, no consequence (no "N no-shows suspends booking" rule) exists locally — `noShowStudent()`/`noShowStudentDelete()` simply proxy to the external service.
**Notable bug:** on a failed external call, `noShowStudent()` returns HTTP 500 with the misleading message `"Data Added Successfully"` — a copy-paste artifact from the success path.
**Source:** `Modules/StudentBookACall/Http/Traits/StudentMeetingTrait.php`.
**QA implication:** Any "repeated no-shows affect eligibility" rule, if it exists, must be tested against the external sub-project directly.

### Notification Targeting Rule

#### Rule: "For all" and "specific range" are provably identical code; neither creates delivery rows
**Statement:** `create_notification_for_all` and `create_notification_for_specific_range` are **byte-for-byte identical** (differ only by one extra `Log::info()` call). Neither inserts into `notification_user` — the table that actually gates per-student visibility. Both only create the `notification` row plus tag/channel/course/batch/package pivots per whatever optional arrays were sent.
**Source:** `Modules/Notification/Http/Traits/NotificationTrait.php::create_notification_for_specific_range()` (lines 81-148) / `::create_notification_for_all()` (lines 163-233).
**Implementation status:** confirmed live and identical. The real per-student delivery mechanism (whatever populates `notification_user`) is not reachable from either creation endpoint — likely a separate scheduled job, not traced in this pass.
**QA implication:** Don't write separate test suites expecting different targeting behavior between the two endpoints — from the API's perspective they're the same action under two names. Verifying actual student-facing delivery requires finding and testing the separate dispatch mechanism.

---

## 6. Admin Operations & External Integration Business Rules

### RBAC

#### Rule: Role deactivation does NOT cascade to deactivate assigned users
**Statement:** `POST /v1/roles/status/change` with `status=deactivate` only flips `roles.status` and logs an activity — it never touches any `User` holding that role, despite an inline comment `// Deactivate Users` immediately above the logging call.
**Source:** `Modules/Role/Http/Controllers/RolesController.php:262-308` (misleading comments at 276, 297); `app/Traits/ActivationAndDeactivationProcess.php:22-52` (confirmed no `User::` query anywhere in the helper).
**Implementation status:** confirmed live — current, intentional-looking behavior, not a bug awaiting a fix in flight.
**QA implication:** After deactivating a role with assigned users, assert those users' status/login ability is **unchanged**.

### LawSikho Ingestion — Student Upsert Decision Table

#### Rule: `POST /v1/add-student` outcome depends on (email exists?, address present?)

| Email matches? | `address` present? | Outcome |
|---|---|---|
| No | n/a | **Create** — requires `full_name`/`phone`/`status` non-null (else 422). Auto-generates `reg_code`/password, dispatches `SendStudentDataToExternalAPI`. Returns 201. |
| Yes | Yes | **Update** 8 contact fields only, each falling back to current value if absent from request. Returns 201, `"Student Exist"`. |
| Yes | No | **No-op** — record unchanged. Still returns 201, `"Student Exist"` — indistinguishable from the update case in the response. |

**Threshold/formula:** lookup is `Student::where('email', ...)->first()` — DB-collation case sensitivity, no application-level email normalization.
**Source:** `Modules/LawSikho/Http/Traits/StudentTrait.php:43-93`.
**QA implication:** A fixture reusing an email from a prior test run silently hits update-or-no-op instead of create — assert on **which student id came back**, not just status code.

### AtsAPI

#### Rule: Each of AtsAPI's 3 endpoints has independently different auth; the root config doc describes a different scheme than what's live

| Endpoint | Inbound auth |
|---|---|
| `POST /v1/save-job-and-course-mapping` | none (gateway middleware registered, never attached) |
| `GET /v1/atsapi/get-all-courses` | none |
| `GET /v1/atsapi/get-all-jobs` | custom `ats-token: Bearer <token>` header — but this token is only **relayed onward** as the outbound `Authorization` header to the external ATS API, never validated locally. Any string starting with `Bearer ` passes this app's own check. |

**Implementation status:** `ATS_API_CONFIGURATION.md` reads as if `ATS_API_BEARER_TOKEN` authenticates inbound callers — it actually only configures this app as an **outbound** client to the external ATS search service. Treat that doc as describing the outbound integration only.
**Source:** `Modules/AtsAPI/Http/Traits/AtsApiTrait.php:77-89,91-109,156-234`; `config/app.php:267-272`.
**QA implication:** Test `get-all-jobs` with `Bearer garbage-token` — expect this app to accept and forward it, relaying whatever the external service returns, rather than a clean local 401.

#### Rule: Job-listing eligibility requires 4 conditions, one not previously documented
**Statement:** A `course_job_mappings` row appears in a listing only if: (1) its `course_id` matches a course the caller has an **ACTIVE** enrollment in, (2) `status='1'`, (3) `is_draft='1'`, (4) `expiry_date >= today`.
**Source:** `Modules/AtsAPI/Http/Traits/AtsApiTrait.php:91-109`.
**Implementation status:** condition (1) — the active-enrollment gate — wasn't previously documented in `documentation/API_SPECIFICATIONS.md` §6 (which only covered conditions 2-4).
**QA implication:** A mapping satisfying status/draft/expiry but where the caller's enrollment for that course is `PENDING`/`PAUSED` should be **excluded**.

### Employer Service Integration (found in code — undocumented elsewhere until now)

#### Rule: Staff `User` creation/update conditionally triggers a 2-step external registration chain
**Statement:** If `user.ats == 1` AND the user has no existing `user_details` row, `SendUserDetailsToExternalApi` dispatches: (1) job-portal registration (`user_type = EMPLOYER_TYPE`); (2) **only if step 1 succeeds** (`code === 200`), a second call creating an "employer" record using **entirely hardcoded placeholder company data** (`company_name: 'Lawsikho'`, fixed email/phone/address/city/state/country/industry/team_size — only the user's own email/name/phone vary).
**Threshold/formula:** idempotency guard is `!user.user_detail` — a user who already has a `user_details` row never re-triggers this job even if `ats` is toggled again.
**Notable:** the employer-creation step is explicitly non-critical — its failure is logged but doesn't throw, retry, or roll back the first registration.
**Source:** `Modules/User/Http/Controllers/UserController.php:227-235,429-437`; `Modules/User/Jobs/SendUserDetailsToExternalApi.php`; `Modules/User/Entities/UserDetail.php:15-16`.
**Implementation status:** confirmed live; matches `EMPLOYER_SERVICE_API_IMPLEMENTATION.md` accurately (unlike the ATS doc above). `EMPLOYER_SERVICE_API_URL` is unset in the current `.env` — running on the config default unless overridden elsewhere.
**QA implication:** A genuinely live, testable integration missing from the other 4 docs. Key edge case: mock the job-portal call to fail — expect `user_details` to stay empty and the employer-service call to never fire. Mock job-portal success + employer-service failure — expect the overall job to still report success, `user_details.third_party_id` saved despite the second failure.

### Email Templates

#### Rule: "Current user's role" for template retrieval is an unordered first-row pick, not a defined priority
**Statement:** `GET` template retrieval uses `auth()->user()->roles[0]->id` — neither the controller nor the default `spatie/laravel-permission` relationship impose any ordering on `model_has_roles`. `roles[0]` is whatever row the DB returns first absent an `ORDER BY` — typically insertion order on most InnoDB setups, but not a guaranteed contract anywhere in the codebase.
**Source:** `Modules/EmailTemplate/Http/Controllers/EmailTemplateController.php:40-49`.
**Implementation status:** confirmed live; adds to the storage/retrieval mismatch already flagged in `documentation/API_SPECIFICATIONS.md` §6 — even the role-scoping itself is non-deterministic for multi-role users.
**QA implication:** Don't assert which role's template comes back for a multi-role user based on assumed assignment order. If a test needs a deterministic result, assign the user exactly one role.

---

*End of business rules documentation. For request/response contracts see `documentation/API_SPECIFICATIONS.md`; for step-by-step workflows see `documentation/USER_WORKFLOWS.md`; for schema see `documentation/DATABASE_SCHEMA.md`; for module/route/auth ground truth see `documentation/DEVELOPER_DOCUMENTATION.md`.*
