# Domain Model Diagram

> **Generated:** 2026-08-29 · **Branch surveyed:** `New-Dummy-Prod-0605`
> **Source of truth:** traced from actual migration files (create + every subsequent alter) and Eloquent entity relationships — cross-checked against `documentation/DATABASE_SCHEMA.md` (the full column-level reference this document diagrams). Where the two disagree, trust `DATABASE_SCHEMA.md`; this doc is a visual distillation of it, not an independent source.
> **Companion documents:** `documentation/CONTEXT_MAP.md` (module coupling), `documentation/BOUNDED_CONTEXT_{IDENTITY,LEARNING,ENROLLMENT,ASSESSMENT,COMMUNICATION,INTEGRATIONS}.md` (business-capability ownership), `documentation/DATABASE_SCHEMA.md` (full column listing per table)

## How to read these diagrams

Diagrams use Mermaid `erDiagram` notation, one section per bounded context (same 6-context split as the `BOUNDED_CONTEXT_*.md` docs) plus one system-wide overview. Entities show **only the columns that matter for understanding the shape of the model** — PKs, FKs, and the handful of business-critical attributes — not the full column list (that's `DATABASE_SCHEMA.md`'s job).

- `PK` = primary key
- `FK` = a real, DB-enforced foreign key (`ON DELETE CASCADE`/`SET NULL` as noted in prose)
- A plain quoted comment with no `FK`/`PK` tag on an id-shaped column means **it looks like a foreign key but has no DB-level constraint** — the referential integrity, if any, is enforced only in application code, not the database. This codebase has an unusually high number of these; each one is a real place where an orphaned or garbage value can exist in the database undetected. They're marked deliberately, not omitted, because "the domain model as it actually is" includes where it's weaker than it looks.
- `||--o{` reads "one required, related to zero-or-many" (a standard 1:N with the child FK nullable-in-practice or not depending on the FK's own nullability, noted in prose). `}o--o{` marks a genuine pivot-backed many-to-many, shown via the pivot table as its own entity rather than a direct line, because that's what actually exists in the schema.

---

## 1. System-wide core domain model

The backbone that every bounded context ultimately connects through:

```mermaid
erDiagram
    COUNTRIES ||--o{ STUDENTS : "country_id (unconstrained)"
    COUNTRIES ||--o{ USERS : "country_id FK"
    USERS ||--o{ COURSES : "default_evaluator_id / mentor / coach FK (multiple roles)"
    COURSE_CATEGORIES ||--o{ COURSES : "course_category_id FK, nullable"
    COURSES ||--o{ ENROLLMENTS : "course_id FK, cascade"
    COURSE_BATCHES ||--o{ ENROLLMENTS : "batch_id FK, cascade, nullable"
    PACKAGES ||--o{ ENROLLMENTS : "package_id FK, nullable (x2: package_id, reference_package)"
    STUDENTS ||--o{ ENROLLMENTS : "student_id FK, cascade"
    ENROLLMENTS ||--o{ STUDENT_ASSIGNMENTS : "enrollment_id FK, cascade"
    ASSIGNMENTS ||--o{ STUDENT_ASSIGNMENTS : "assignment_id FK, cascade"
    COURSES ||--o{ ASSIGNMENTS : "course_id FK, cascade"
    TOPICS ||--o{ ASSIGNMENTS : "topic_id FK, cascade"
    STUDENT_ASSIGNMENTS ||--o{ RESULTS : "assignment_id FK -> student_assignments.id (naming trap, see §7)"
    STUDENTS ||--o{ RESULTS : "student_id FK, cascade"
    USERS ||--o{ RESULTS : "evaluator_id FK, nullable"

    USERS {
        bigint id PK
        string email UK
        string full_name
        tinyint status
        int edmingle_id
        enum ats "ATS module flag"
    }
    STUDENTS {
        bigint id PK
        string reg_code UK
        string email UK
        tinyint status "PENDING/ACTIVE/DISABLED"
        int country_id "unconstrained despite name"
        bigint lms_id "Edmingle student id"
    }
    COUNTRIES {
        bigint id PK
        string short
        string name
        string iso3
    }
    COURSE_CATEGORIES {
        bigint id PK
        int parent_id "unconstrained self-reference"
        string category_name UK
    }
    COURSES {
        bigint id PK
        string course_name
        tinyint course_type "SIMPLE_COURSE / BOOTCAMP_COURSE"
        boolean status
        bigint ai_model_id FK
    }
    COURSE_BATCHES {
        bigint id PK
        string batch_date UK "unique across ALL courses"
        boolean status
    }
    PACKAGES {
        bigint id PK
        string name
        int duration_days
    }
    ENROLLMENTS {
        bigint id PK
        string enrollment_code UK
        int status "PENDING/ACTIVE/PAUSED/RESUME_REQUESTED/PAUSE_REQUESTED"
        int bootcamp_id "unconstrained, no FK to bootcamps"
        json passing_criteria "point-in-time snapshot"
        int ls_order_id "revenue-side idempotency key"
    }
    ASSIGNMENTS {
        bigint id PK
        string assignment_code
        int assignment_type "SUBJECTIVE / WRITTEN"
        int status
        bigint package_id FK "nullable"
    }
    TOPICS {
        bigint id PK
        string title
    }
    STUDENT_ASSIGNMENTS {
        bigint id PK
        int status "indexed, see BUSINESS_RULES.md"
        int submit_counter "default 4"
        date submission_last_date
    }
    RESULTS {
        bigint id PK
        int status
        boolean is_evaluated
        tinyint latest "flags current result among a student_assignment's history"
        int bootcamp_id "unconstrained"
    }
```

**Immediately visible structural fact:** `course_batches` has **no `course_id` column at all** — a batch is a global, date-keyed cohort concept, not intrinsically owned by one course at the DB level. The course↔batch association only exists per-enrollment (`enrollments` carries both `course_id` and `batch_id` independently) or via the separate `edmingle_batches` table (which does carry both). Don't draw — or assume the code enforces — a direct `Course 1—N Batch` relationship; it isn't there.

**Second structural fact:** `bootcamps` has no DB relationship to `courses` at all. `enrollments.bootcamp_id` is a plain unconstrained integer, and `bootcamp_books` links bootcamps to `books` (deprecated), not to courses. A "bootcamp" and its associated "bootcamp course" are two independently-tracked concepts joined only in application logic, if at all — see `BOUNDED_CONTEXT_LEARNING.md` §3 for the same finding from the code side.

---

## 2. Identity context

```mermaid
erDiagram
    USERS ||--o{ USER_DETAILS : "user_id FK"
    USERS ||--o{ USER_JOB_ROLE_MAPPINGS : "user_id FK, cascade"
    JOB_ROLES ||--o{ USER_JOB_ROLE_MAPPINGS : "job_role_id FK, cascade"
    USERS ||--o{ USERS : "created_by / updated_by (self-FK)"
    STUDENTS ||--o{ STUDENT_OTHER_DETAILS : "student_id FK"
    STUDENTS ||--o{ STUDENT_ORIGINAL_REGISTRATION_DETAILS : "student_id FK, nullable"
    STUDENTS ||--o{ STUDENTS_INTERNAL_NOTES : "student_id FK, cascade"
    STUDENTS_INTERNAL_NOTES ||--o{ INTERNAL_NOTES_HISTORY : "history_tab_id (no DB FK, app-level only)"
    STUDENTS ||--o{ STUDENT_WEEK_DAY_AVAILABILITIES : "student_id FK, cascade"
    COUNTRIES ||--o{ STATES : "country_id FK, cascade"
    KNOW_ABOUT_LAWSIKHO_QUESTION ||--o{ KNOW_ABOUT_LAWSIKHO_STUDENT_ANSWER : "answer_id FK"
    STUDENTS ||--o{ KNOW_ABOUT_LAWSIKHO_STUDENT_ANSWER : "student_id FK"
    ROLES }o--o{ PERMISSIONS : "role_has_permissions (pivot)"
    ROLES ||--o{ MODEL_HAS_ROLES : "polymorphic model_type/model_id"
    PERMISSIONS ||--o{ MODEL_HAS_PERMISSIONS : "polymorphic model_type/model_id"

    USER_DETAILS {
        bigint id PK
        bigint user_id FK
        string third_party_id "nullable"
    }
    JOB_ROLES {
        bigint id PK
        string title
    }
    STUDENT_OTHER_DETAILS {
        bigint id PK
        bigint student_id FK
    }
    STUDENT_ORIGINAL_REGISTRATION_DETAILS {
        bigint id PK
        text original_registration_details_json
    }
    STUDENTS_INTERNAL_NOTES {
        bigint id PK
        bigint student_id FK
        text notes
        boolean is_edited
    }
    INTERNAL_NOTES_HISTORY {
        bigint id PK
        int internal_note_id "no DB FK, immutable append-only"
        text notes
    }
    STUDENT_WEEK_DAY_AVAILABILITIES {
        bigint id PK
        bigint student_id FK
        bigint range_id "FK -> performance_coach_ranges.id (deprecated module!)"
        bigint weekday_id FK
    }
    STATES {
        bigint id PK
        string name
        bigint country_id FK
    }
    KNOW_ABOUT_LAWSIKHO_QUESTION {
        bigint id PK
        string question
    }
    KNOW_ABOUT_LAWSIKHO_STUDENT_ANSWER {
        bigint id PK
        bigint student_id FK
        bigint answer_id FK
    }
    ROLES {
        bigint id PK
        string name
        string guard_name
    }
    PERMISSIONS {
        bigint id PK
        int parent_id "self-ref, unconstrained"
        string name
    }
```

**Notable anomaly worth flagging in the domain model itself:** `student_week_day_availabilities` — a **live, Identity-context table** — has a real, DB-enforced foreign key into `performance_coach_ranges`, a table owned entirely by the deprecated `PerformanceCoach` module. This is the schema-level twin of the code-level finding in `BOUNDED_CONTEXT_IDENTITY.md`/`CONTEXT_MAP.md` §5: the live/deprecated boundary is not clean, at either the code layer or the data layer.

`students.country_id` has no DB FK despite the name (added later, 2023-06-27, as a plain integer) — don't assume referential integrity here even though `countries.id: 99` is hardcoded app-wide to mean India.

---

## 3. Learning context

Split into the same three sub-clusters as `BOUNDED_CONTEXT_LEARNING.md` — core catalog is the load-bearing part; the deprecated cluster is shown separately because it's genuinely a different reliability tier.

### 3a. Core catalog — live

```mermaid
erDiagram
    COURSE_CATEGORIES ||--o{ COURSES : "course_category_id, nullable"
    COURSES ||--o{ COURSE_EVALUATOR_MAPPINGS : "course_id, cascade"
    USERS ||--o{ COURSE_EVALUATOR_MAPPINGS : "evaluator_id, cascade"
    COURSES ||--o{ COURSE_MENTOR_MAPPINGS : "course_id, cascade"
    USERS ||--o{ COURSE_MENTOR_MAPPINGS : "mentor_id, cascade"
    COURSES ||--o{ COURSE_CRITERIAS : "course_id, cascade"
    COURSE_CATEGORIES ||--o{ COURSE_CATEGORY_CRITERIAS : "category_id, cascade"
    COURSES ||--o{ COURSE_FAQS : "course_id, cascade"
    PACKAGES }o--o{ COURSES : "package_course_mappings (pivot)"
    COURSES ||--o{ COURSE_OPTIONAL_QUESTIONS : "course_id"
    COURSE_OPTIONAL_QUESTIONS ||--o{ COURSE_OPTIONAL_QUESTION_ANSWERS : "question denormalized as text, not FK"
    TOPICS ||--o{ TOPIC_DOC_DETAILS : "topic_id, cascade"

    COURSES {
        bigint id PK
        string course_name
        tinyint course_type
    }
    COURSE_CRITERIAS {
        bigint id PK
        bigint course_id FK
        int pass_marks_needed_percent
        int total_marks
    }
    COURSE_CATEGORY_CRITERIAS {
        bigint id PK
        bigint category_id FK
    }
    COURSE_FAQS {
        bigint id PK
        bigint course_id FK
        longtext question
    }
    PACKAGES {
        bigint id PK
        string name
    }
    COURSE_OPTIONAL_QUESTIONS {
        bigint id PK
        bigint course_id FK
        boolean is_mandatory
    }
    COURSE_OPTIONAL_QUESTION_ANSWERS {
        bigint id PK
        bigint enrollment_id FK
        text question "redundant copy, not FK'd back"
    }
    TOPIC_DOC_DETAILS {
        bigint id PK
        bigint topic_id FK
        string link "nullable"
    }
```

Two identically-shaped "criteria" tables exist (`course_criterias`, `course_category_criterias`) — only `course_criterias` is confirmed live at completion-check time (`USER_WORKFLOWS.md` §2.3); treat `course_category_criterias` as a secondary/legacy source unless told otherwise.

### 3b. Student journey / BFF layer — live

```mermaid
erDiagram
    STUDENTS ||--o{ STUDENT_DASHBOARD_JOURNEY_STEPS_MAPPING : "student_id, cascade"
    STUDENT_DASHBOARD_JOURNEY_STEPS ||--o{ STUDENT_DASHBOARD_JOURNEY_STEPS_MAPPING : "step_id, cascade"
    STUDENT_DASHBOARD_JOURNEY_STEPS_MAPPING ||--o{ STUDENT_DASHBOARD_JOURNEY_COMMENTS : "step_mapping_id, cascade, nullable"
    STUDENT_DASHBOARD_JOURNEY_STEPS ||--o{ STUDENT_DASHBOARD_JOURNEY_STEPS : "reference_id (self-ref, is_parent_step)"
    USERS ||--o{ COURSE_INSTRUCTOR_MAPPINGS : "instructor_id, cascade"
    COURSES ||--o{ COURSE_INSTRUCTOR_MAPPINGS : "course_id, cascade"

    STUDENT_DASHBOARD_JOURNEY_STEPS {
        bigint id PK
        int reference_id "self-ref"
        boolean is_parent_step
        boolean is_for_new
        boolean is_for_old
    }
    STUDENT_DASHBOARD_JOURNEY_STEPS_MAPPING {
        bigint id PK
        bigint student_id FK
        bigint step_id FK
        int enrollment_id "NOT a real FK despite the name"
        string subject_type "polymorphic"
        bigint subject_id "polymorphic"
    }
    STUDENT_DASHBOARD_JOURNEY_COMMENTS {
        bigint id PK
        text feedback
    }
    COURSE_INSTRUCTOR_MAPPINGS {
        bigint id PK
        bigint course_id FK
        bigint instructor_id FK
    }
```

`StudentBookACall`'s actual booking/meeting records are **not stored locally at all** — they live entirely in the external sub-project behind `MEETING_API_BASE_URL`/`BOOK_A_CALL_API`. `course_instructor_mappings` is the only local table this feature owns.

### 3c. Deprecated delivery/support cluster — confirmed not in active use

```mermaid
erDiagram
    BOOKS ||--o{ COURSE_BOOKS : "book_id, cascade"
    COURSES ||--o{ COURSE_BOOKS : "course_id, cascade"
    BOOKS ||--o{ BOOK_DELIVERY_LOG : "book_id, cascade"
    STUDENTS ||--o{ BOOK_DELIVERY_LOG : "student_id, cascade (snapshot copy, not live-joined)"
    BOOKS ||--o{ BOOTCAMP_BOOKS : "book_id, cascade"
    CLASSES ||--o{ CLASS_PARTICIPANTS : "class_id"
    CLASSES ||--o{ CLASS_OCCURRANCE_DATE : "class_id"
    PACKAGES ||--o{ CLASS_PACKAGE : "still-active FK, cascades if package deleted"
    COURSES ||--o{ CLASS_COURSE_MAPPING : "still-active FK"
    COURSE_BATCHES ||--o{ CLASS_COURSE_BATCH : "still-active FK"
    PROJECTS ||--o{ PROJECT_MENTORS : "project_id, cascade"
    COURSES ||--o{ PROJECTS : "course_id, cascade"
    COURSE_BATCHES ||--o{ PROJECTS : "batch_id, cascade"

    BOOKS {
        bigint id PK
        string sku
    }
    BOOK_DELIVERY_LOG {
        bigint id PK
        bigint enrollment_id FK
        string student_name "point-in-time snapshot"
        boolean is_sent
    }
    CLASSES {
        bigint id PK
        string zoom_id
        int zoom_account "no real FK despite intent"
    }
    CLASS_PARTICIPANTS {
        bigint id PK
        string zoom_meetng_id "literal typo in column name"
        string join_time "string, not timestamp"
    }
    PROJECTS {
        bigint id PK
        string kan_project_id "external Kanboard id"
    }
    PROJECT_CATEGORIES {
        bigint id PK
        string _remark "no FK to projects - project-independent"
    }
```

Even though the *features* are dead, several of these tables carry **live, still-enforced** foreign keys into active tables (`packages`, `courses`, `course_batches`) — deleting a package or course row would cascade-delete rows in `class_package`/`class_course_mapping` even though nothing reads them. This is the DB-level version of the "deprecated but not disconnected" finding — see `CONTEXT_MAP.md` §5 and `BOUNDED_CONTEXT_LEARNING.md` §6 for the code-level counterpart.

---

## 4. Enrollment context

```mermaid
erDiagram
    COURSES ||--o{ ENROLLMENTS : "course_id, cascade"
    COURSE_BATCHES ||--o{ ENROLLMENTS : "batch_id, cascade, nullable"
    COURSE_PLAN_TYPES ||--o{ ENROLLMENTS : "course_plan_type_id, nullable"
    STUDENTS ||--o{ ENROLLMENTS : "student_id, cascade"
    PACKAGES ||--o{ ENROLLMENTS : "package_id AND reference_package (two FKs to same table)"
    USERS ||--o{ ENROLLMENTS : "batch_assigning_eligibility / certified_by / created_by / updated_by"
    ENROLLMENTS ||--o{ ENROLLMENT_PAUSE_LOG_NEW : "enrollment_id, cascade"
    STUDENTS ||--o{ ENROLLMENT_PAUSE_LOG_NEW : "paused_by_student_id, nullable"
    USERS ||--o{ ENROLLMENT_PAUSE_LOG_NEW : "resumed_by_admin_id, set null"
    ENROLLMENT_QUESTIONS ||--o{ ENROLLMENT_QUESTION_ANSWERS : "question_id"
    STUDENTS ||--o{ ENROLLMENT_QUESTION_ANSWERS : "student_id"
    USERS ||--o{ BULK_ENROLLMENT_REPORTS : "user_id"
    BOOTCAMPS ||--o{ BULK_ENROLLMENT_REPORTS : "bootcamp_id, SET NULL"
    BULK_ENROLLMENT_REPORTS ||--o{ BULK_ENROLLMENT_DETAILS : "bulk_enrollment_report_id, cascade"
    ENROLLMENTS ||--o{ BULK_ENROLLMENT_DETAILS : "enrollment_id, nullable, set null"

    ENROLLMENTS {
        bigint id PK
        string enrollment_code UK
        int status
        int bootcamp_id "unconstrained, no FK"
        bigint edmingle_batch_id "FK-shaped, not constrained"
        int deactivation_status "backfill gap for pre-2026-06-01 rows"
        int original_enrollment_id "links migrated/paused enrollment to its origin"
        string pause_reason
        string paused_reason
        string _remark "two similarly-named text columns - confirm which is written to"
    }
    ENROLLMENT_PAUSE_LOG_NEW {
        bigint id PK
        bigint enrollment_id FK
        string status "required, NO default"
        string support_ticket_id "Zoho ticket ID"
    }
    ENROLLMENT_QUESTIONS {
        bigint id PK
        longtext question
    }
    ENROLLMENT_QUESTION_ANSWERS {
        bigint id PK
        string user_type
        json answer
    }
    BULK_ENROLLMENT_REPORTS {
        bigint id PK
        bigint bootcamp_id FK "set null - one of the few real FKs to bootcamps"
        json course_ids
        string status
    }
    BULK_ENROLLMENT_DETAILS {
        bigint id PK
        bigint bulk_enrollment_report_id FK
        bigint student_id "nullable, set null"
        bigint enrollment_id "nullable, set null"
    }
```

`enrollments.bootcamp_id` (the field you'd expect to link to a bootcamp) is **unconstrained**, while `bulk_enrollment_reports.bootcamp_id` **is** a real, DB-enforced FK — an inconsistency worth knowing before assuming either field behaves like the other. `RevenueAPI` and `ReferralSystem` (both part of this context per `BOUNDED_CONTEXT_ENROLLMENT.md`) own no tables of their own — confirmed entity-less; their writes land on `enrollments`/`students` columns already shown above.

---

## 5. Assessment context

```mermaid
erDiagram
    COURSES ||--o{ ASSIGNMENTS : "course_id, cascade"
    TOPICS ||--o{ ASSIGNMENTS : "topic_id, cascade"
    PACKAGES ||--o{ ASSIGNMENTS : "package_id, nullable"
    AI_MODELS ||--o{ ASSIGNMENTS : "ai_model_id, nullOnDelete"
    ASSIGNMENTS }o--o{ TAGS : "taggables (polymorphic pivot)"
    ENROLLMENTS ||--o{ STUDENT_ASSIGNMENTS : "enrollment_id, cascade"
    ASSIGNMENTS ||--o{ STUDENT_ASSIGNMENTS : "assignment_id, cascade (correctly named!)"
    AI_MODELS ||--o{ STUDENT_ASSIGNMENTS : "ai_model_id, nullOnDelete"
    STUDENT_ASSIGNMENTS ||--o{ RESULTS : "assignment_id FK -> student_assignments.id"
    STUDENTS ||--o{ RESULTS : "student_id, cascade"
    USERS ||--o{ RESULTS : "evaluator_id, cascade, nullable"
    AI_MODELS ||--o{ RESULTS : "ai_model_id, nullOnDelete"
    RESULTS ||--o{ RESULT_EXERCISE_SCORES : "result_id, cascade"
    RESULTS ||--o{ AI_EVALUATION_AUDIT_LOGS : "result_id, nullOnDelete"
    COURSES ||--o{ AI_COURSE_MATERIAL_SYNCS : "course_id, nullable, UNIQUE (one row per course)"
    STUDENT_ASSIGNMENTS ||--o{ ASSIGNMENT_CSAT_FORM : "assignment_id FK -> student_assignments"
    STUDENT_ASSIGNMENTS ||--o{ FIRST_ASSIGNMENT_SEND_LOG : "assignment_id FK -> student_assignments"

    ASSIGNMENTS {
        bigint id PK
        string assignment_code
        int assignment_type "SUBJECTIVE / WRITTEN"
        int plagiarism "inert at submission time"
    }
    TAGS {
        bigint id PK
        json name "multi-locale"
        string type "ASSIGNMENT_TAG / USER_TAG / STUDENT_TAG"
    }
    STUDENT_ASSIGNMENTS {
        bigint id PK
        bigint enrollment_id FK
        bigint assignment_id FK
        int submit_counter "default 4"
        int status "indexed"
    }
    RESULTS {
        bigint id PK
        bigint assignment_id FK "-> student_assignments.id, NOT assignments.id"
        int status
        tinyint latest "flags the current active result"
        int waive_marks "stored as literal 3 when truthy"
    }
    RESULT_EXERCISE_SCORES {
        bigint id PK
        bigint result_id FK
        float obtain_marks "sentinel 101 clears to null"
    }
    AI_MODELS {
        bigint id PK
        string model_name
        boolean is_default
    }
    AI_EVALUATION_AUDIT_LOGS {
        bigint id PK
        bigint result_id FK
        json metadata
        string _remark "append-only, created_at only, no updated_at"
    }
    AI_COURSE_MATERIAL_SYNCS {
        bigint id PK
        bigint course_id FK "unique - one sync row per course"
        string instruction_link_hash "change-detection"
    }
```

**The single most important structural fact in the whole domain model:** every `assignment_id` column in this diagram except `student_assignments.assignment_id` itself and `assignment_log_mapping.assignment_id` actually **foreign-keys to `student_assignments.id`, not `assignments.id`**, despite the column name in every case. This is systemic, not a one-off typo — `results`, `assignment_csat_form`, `first_assignment_send_log`, `course_featured_assignment_mapping`, `student_result_video_mapping`, and `student_assignment_video_mapping` (Learning context) all follow this pattern. Anyone writing raw SQL, seeding fixtures, or building an external QA harness against this schema needs to know this before writing a single join.

---

## 6. Communication context

```mermaid
erDiagram
    NOTIFICATION_CATEGORY ||--o{ NOTIFICATION : "category_id"
    NOTIFICATION ||--o{ BATCH_NOTIFICATION : "notification_id, cascade"
    COURSE_BATCHES ||--o{ BATCH_NOTIFICATION : "cascade"
    NOTIFICATION ||--o{ COURSE_NOTIFICATION : "notification_id, cascade"
    COURSES ||--o{ COURSE_NOTIFICATION : "cascade"
    NOTIFICATION ||--o{ PACKAGE_NOTIFICATION : "notification_id, cascade"
    PACKAGES ||--o{ PACKAGE_NOTIFICATION : "cascade"
    NOTIFICATION ||--o{ NOTIFICATION_USER : "notification_id, cascade"
    STUDENTS ||--o{ NOTIFICATION_USER : "column literally named user_id, FK's to students.id"
    NOTIFICATION ||--o{ NOTIFICATION_COMMENTS : "notification_id"
    WEBHOOK_EVENTS ||--o{ WEBHOOKS : "event_id, NOT NULL at DB level"
    WEBHOOKS ||--o{ WEBHOOK_LOGS : "webhook_id, cascade"
    STUDENTS ||--o{ ASSIGNMENT_CSAT_FORM : "student_id"
    STUDENTS ||--o{ EVALUATOR_CSAT_FORM : "student_id"
    RESULTS ||--o{ EVALUATOR_CSAT_FORM : "result_id"
    USERS ||--o{ EVALUATOR_CSAT_FORM : "evaluator_id"
    STUDENTS ||--o{ NPS_FORM : "student_id, REQUIRED"
    ENROLLMENTS ||--o{ NPS_FORM : "enrollment_id, REQUIRED"
    STUDENTS ||--o{ NPS_FORM_V2 : "student_id ONLY - no enrollment/course/batch FK"
    NPS_FORM_REASON ||--o{ NPS_FORM_REASON_MAPING : "reason_id"
    NPS_FORM_REASON ||--o{ NPS_FORM_REASON_MAPPING_V2 : "reason_id, plus reason_parent_id for 2-level hierarchy"

    NOTIFICATION {
        bigint id PK
        string title
        datetime sent_at "widened from date via separate alter"
        int status "0=pending,1=sent"
    }
    NOTIFICATION_USER {
        bigint id PK
        bigint user_id "misleading name, actually students.id"
        timestamp read_at
    }
    NOTIFICATION_COMMENTS {
        bigint id PK
        int parent_id "unconstrained, threaded"
        int created_by "either users.id or students.id depending on user_type enum"
    }
    WEBHOOKS {
        bigint id PK
        string webhook_secret
        int failure_count
        string _remark "two identical CREATE migrations exist - see DATABASE_SCHEMA.md §1"
    }
    WEBHOOK_LOGS {
        bigint id PK
        bigint webhook_id FK
        string status_code "string, not integer"
        json payload "required, no live writer observed"
    }
    NPS_FORM {
        bigint id PK
        bigint student_id FK
        bigint enrollment_id FK
        string survey_type "default SURVEY_TYPE_1"
    }
    NPS_FORM_V2 {
        bigint id PK
        bigint student_id FK
        string survey_type "required, NO default"
        text experience "text not string - longer answers"
    }
    NPS_FORM_REASON {
        bigint id PK
        string question
        int parent_id "unconstrained"
    }
    ASSIGNMENT_CSAT_FORM {
        bigint id PK
        bigint assignment_id "FK -> student_assignments, not assignments"
        int rating
    }
    EVALUATOR_CSAT_FORM {
        bigint id PK
        bigint result_id FK
        bigint evaluator_id FK
    }
```

Two structurally unrelated tables share near-identical names: **`notification`** (this module's custom entity, singular) vs. **`notifications`** (Laravel's own built-in queued-notification table, plural, UUID PK, unrelated data model). Don't confuse them when writing queries or fixtures. `nps_form` (v1) and `nps_form_v2` are genuinely different schemas, not a superset relationship — v2 dropped the enrollment/course/batch FKs entirely and widened text fields; v1 is not deprecated by v2's existence, both may need independent test coverage. `class_csat_form`/`_reason`/`_reason_maping` and `performance_coach_csat_form`/`_reason`/`_reason_mapping` (both deprecated, tied to Learning's dead `Class`/`PerformanceCoach` modules) follow the same three-table shape as `assignment_csat_form` and `evaluator_csat_form` above but are omitted from this diagram — see `DATABASE_SCHEMA.md` §3/§5 for their columns if needed.

---

## 7. Integrations context

```mermaid
erDiagram
    COURSES ||--o{ COURSE_JOB_MAPPINGS : "course_id, plain integer, NO FK constraint"
    USERS ||--o{ COURSE_JOB_MAPPINGS : "user_id, cascade, nullable"

    COURSE_JOB_MAPPINGS {
        bigint id PK
        string job_id "external id, not a local FK"
        enum channel "DB-level enum('Lawsikho','SkillArbitrage') - stricter than the app layer"
        enum status
        enum is_draft
        date expiry_date
    }
    THIRD_PARTY_LOGS {
        bigint id PK
        string service_name
        string request_url
        json request_body "nullable"
        int response_status
        string _remark "no FK columns at all - not tied to any specific student/enrollment row"
    }
```

This is by far the smallest schema footprint of the 6 contexts — consistent with the coupling finding in `BOUNDED_CONTEXT_INTEGRATIONS.md` that this context is an outbound-facing gateway layer, not a data owner. `AgenticSupportSystem` owns **no local tables at all** — it reads across every other context's tables live rather than maintaining its own copy. `third_party_logs` is what actually backs `LawSikho`'s near-universal request logging, including on unauthenticated endpoints, per `API_SPECIFICATIONS.md`.

---

## 8. Domain-model anomalies worth designing around

Collected here because they're properties of the model itself, not any one context — a QA harness, a new feature, or a migration plan needs to account for all of them regardless of which context it touches:

| Anomaly | Where | Why it matters |
|---|---|---|
| **Systemic `assignment_id` naming trap** | `results`, `assignment_csat_form`, `first_assignment_send_log`, `course_featured_assignment_mapping`, `student_result_video_mapping`, `student_assignment_video_mapping` | Every one of these FKs to `student_assignments.id`, not `assignments.id`, despite the column name. Only `student_assignments.assignment_id` and `assignment_log_mapping.assignment_id` point at the real `assignments` table |
| **`course_batches` has no `course_id`** | Learning §3a | A batch is not intrinsically course-scoped at the DB level; the association only exists via `enrollments` or `edmingle_batches` |
| **`bootcamps` has no DB relationship to `courses`** | System overview §1 | "Bootcamp" and "bootcamp course" are independently tracked; `enrollments.bootcamp_id` is unconstrained |
| **Two identical `webhooks` CREATE migrations** | Communication §6 | Confirm which is authoritative before trusting the schema for this table |
| **Two similarly-named enrollment pause columns** (`pause_reason`, `paused_reason`) | Enrollment §4 | Confirm which one the app actually writes to before asserting on either |
| **Dual OTP mechanism on `students`** (`verification_otp` vs. `otp`/`otp_expire_at`, added 8 months apart) | Identity | Two independent OTP systems coexist — see `DATABASE_SCHEMA.md` §1 |
| **`notification` vs. `notifications`** | Communication §6 | Two unrelated tables with near-identical names and different owners (custom module vs. Laravel core) |
| **NPS v1/v2 are different schemas, not a migration path** | Communication §6 | v2 dropped enrollment/course/batch FKs and widened text fields; both may be independently live |
| **`student_week_day_availabilities.range_id` FKs into a deprecated module's table** | Identity §2 | A live Identity table has a hard, DB-enforced dependency on `performance_coach_ranges` |
| **Deprecated-cluster tables retain live FKs into active tables** (`class_package` → `packages`, `class_course_mapping` → `courses`, `class_course_batch` → `course_batches`) | Learning §3c | Deleting a live package/course/batch row cascades into dead-feature tables that nothing reads |
| **A large number of FK-shaped, DB-unconstrained columns** (`students.country_id`, `enrollments.bootcamp_id`, `enrollments.edmingle_batch_id`, `results.bootcamp_id`, `course_job_mappings.course_id`, `student_dashboard_journey_steps_mapping.enrollment_id`, and others) | Throughout | The database will not catch an orphaned reference in any of these; application-level validation is the only guard, if one exists at all |

## 9. Related documents

- `documentation/DATABASE_SCHEMA.md` — the full column-level reference this document diagrams; consult it for exact types, defaults, and nullability
- `documentation/CONTEXT_MAP.md` — module-level (code) coupling, the counterpart to this document's table-level (data) coupling
- `documentation/BOUNDED_CONTEXT_{IDENTITY,LEARNING,ENROLLMENT,ASSESSMENT,COMMUNICATION,INTEGRATIONS}.md` — business-capability ownership and module relationships per context
- `documentation/BUSINESS_RULES.md` / `USER_WORKFLOWS.md` — the behavioral rules and end-to-end flows that operate on this data model
