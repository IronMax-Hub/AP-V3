# LawSikho Assignment Portal API — Developer Documentation

> **Regenerated:** 2026-08-29
> **Framework:** Laravel 8.x (PHP ^8.1)
> **Architecture:** Modular Monolith (`nwidart/laravel-modules`, 62 modules)
> **Branch surveyed:** `New-Dummy-Prod-0605`

---

## Why this document exists

The repo previously carried a `DEVELOPER_DOCUMENTATION.md` at the project root. It was **untracked in git** (no commit history), self-dated "March 2026" while the repo had commits as recent as 2026-08-27, and undercounted modules (61 vs. the actual 62) — so it was drifting from reality with no process keeping it in sync.

This document was regenerated from scratch on 2026-08-29 by reading the current codebase directly: `composer.json`/`package.json`, every `Modules/*` directory, `config/*.php`, `.env` (variable names only — no values), live `php artisan route:list` output, and migration files. Anywhere the old document's claims didn't match what the code actually does, that's called out explicitly rather than silently repeated (e.g. the JWT/Edmingle SSO claim in §5, the module count in §4).

**This file will go stale the same way the old one did unless something keeps it current.** Treat it as a snapshot, not a live source — re-verify against the code before relying on specifics (route signatures, column names, env var lists) for anything load-bearing like writing automated tests.

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Tech Stack & Dependencies](#2-tech-stack--dependencies)
3. [Project Structure](#3-project-structure)
4. [Full Module Inventory (62 modules)](#4-full-module-inventory-62-modules)
5. [Authentication System](#5-authentication-system)
6. [API Routes Reference](#6-api-routes-reference)
7. [Database Schema](#7-database-schema)
8. [Local Development Setup](#8-local-development-setup)
9. [Known Issues Found During This Audit](#9-known-issues-found-during-this-audit)
10. [Middleware](#10-middleware)
11. [Jobs & Queues](#11-jobs--queues)
12. [Events & Listeners](#12-events--listeners)
13. [Console Commands](#13-console-commands)
14. [External Integrations](#14-external-integrations)
15. [Configuration Reference](#15-configuration-reference)
16. [Environment Variables](#16-environment-variables)

---

## 1. Project Overview

The LawSikho Assignment Portal API is a **Laravel-based, modular-monolith REST API** backing LawSikho's online legal education platform. It covers the student lifecycle (registration, enrollment, activation), the assignment workflow (assignment library, submissions, evaluator grading), course/batch/package management, live-class scheduling (with Edmingle/Zoom integration), performance coaching, CSAT/NPS feedback collection, referrals, forums, project management (Kanboard-style), and a large set of admin/back-office CRUD modules. Two user types exist: internal **Admin/Staff** (`App\Models\User`) and **Students** (`Modules\Student\Entities\Student`), each with separate auth flows.

## 2. Tech Stack & Dependencies

**Framework:** Laravel `^8.75`, PHP `^8.1`, modularized via `nwidart/laravel-modules` `8.2.*`.

| Package | Version | Purpose |
|---|---|---|
| `laravel/framework` | ^8.75 | Core framework |
| `nwidart/laravel-modules` | 8.2.* | Modular architecture (62 modules under `Modules/`) |
| `laravel/sanctum` | ^2.11 | API token auth (admin & student) |
| `tymon/jwt-auth` | * | JWT tokens (Edmingle SSO / external integrations) |
| `spatie/laravel-permission` | ^5.5 | Role-based access control |
| `spatie/laravel-activitylog` | ^4.4 | Audit/activity logging |
| `spatie/laravel-medialibrary` | ^9.0 | File/media attachments |
| `spatie/laravel-tags` | ^4.3 | Tagging (used by AssignmentTag module) |
| `laravel/horizon` | ^5.8 | Queue monitoring dashboard (Redis-backed) |
| `laravel/telescope` | ^4.7 | Request/debug introspection (dev tooling) |
| `predis/predis` | ^1.1 | Redis client |
| `league/flysystem-aws-s3-v3` | ^1.0 | S3-backed file storage |
| `maatwebsite/excel` | ^3.1 | Excel import/export (bulk enrollment, reports) |
| `carlos-meneses/laravel-mpdf` | ^2.1 | PDF generation |
| `macsidigital/laravel-zoom` | ^5.0 | Zoom meeting integration |
| `sentry/sentry-laravel` | ^3.1 | Error monitoring |
| `guzzlehttp/guzzle` + `oauth-subscriber` | ^7.0 / ^0.6 | Outbound HTTP + OAuth (external API integrations) |
| `propaganistas/laravel-phone` | ^4.0 | Phone number validation |
| `rap2hpoutre/laravel-log-viewer` | ^2.1 | Log viewer UI |
| `brainfoolong/cryptojs-aes-php` | ^2.1 | CryptoJS-compatible AES encryption (likely for cross-system payload signing) |
| `phpunit/phpunit` (dev) | ^9.5.10 | Testing |
| `laravel/breeze` (dev) | ^1.7 | Scaffolding (auth views) |
| `laravel-mix` (npm, dev) | ^6.0.6 | Frontend asset bundling |

No standalone frontend framework — `package.json` only carries Laravel Mix + Prettier for asset building, confirming this is API/backend-first.

## 3. Project Structure

| Path | Purpose |
|---|---|
| `app/` | Core Laravel app: base `User` model, global Helpers, Console Kernel overrides, Overrides for vendor package patches |
| `Modules/` | 62 self-contained feature modules (nwidart/laravel-modules), each with its own Controllers, Entities (Eloquent models), Routes, Migrations, Providers, Repositories, Transformers, Jobs, Tests |
| `routes/` | Root-level route files (loaded alongside each module's own `Routes/api.php` / `web.php`) |
| `database/` | Root migrations, factories, seeders (in addition to per-module migrations under `Modules/*/Database`) |
| `config/` | Laravel + package config (auth, sanctum, permission, queue, horizon, telescope, zoom, media-library, tags, sentry, etc.) |
| `resources/` | Blade views / mail templates (this is an API-first app, so this is thin) |
| `tests/` | PHPUnit test suite |
| `docker/` + `Dockerfile` + `docker-compose.yml` | Containerized local dev setup |
| `packages/` | Locally vendored/forked package (`laravel-pepipost-mailer`) |
| `storage/`, `bootstrap/`, `public/`, `server.php`, `artisan` | Standard Laravel scaffolding |

## 4. Full Module Inventory (62 modules)

No module currently defines a `description` field in its `module.json` (all checked came back empty), so purposes below are inferred from each module's controllers/entities/route files. Ambiguous ones are flagged.

| Module | Purpose (inferred) |
|---|---|
| AgenticSupportSystem | Backend for an AI-driven support/agent system (single `AgenticSupportSystemController`; likely wraps an external agentic API — see `AGENTIC_API_V2_CURL_REFERENCE.md` at repo root) |
| AIEvaluation | AI-assisted assignment evaluation — syncs course materials to an AI model and logs AI evaluation runs (`AICourseMaterialSyncs`, `AIModels`, `AIEvaluationAuditLogs`) |
| Assignment | Core assignment library management, including bootcamp-specific assignments |
| AssignmentCSAT | Post-assignment CSAT (satisfaction) survey forms and reason-code mappings |
| AssignmentSendingLog | Logs of when/how assignments were sent to students |
| AssignmentTag | Tagging system for assignments (via `spatie/laravel-tags`) |
| AtsAPI | Integration with an external Applicant Tracking System (ATS), mapping courses to job postings (`CourseJobMapping`) |
| Auth | Admin/staff authentication (Sanctum session controllers, password reset, email verification, registration) |
| BookDeliveryLog | ⚠️ **Not currently in use** (confirmed by team, 2026-08-29). Tracks physical/digital book delivery status to students |
| BookMaster | ⚠️ **Not currently in use** (confirmed by team, 2026-08-29). Master book catalog and its mapping to courses |
| Bootcamp | Bootcamp (bundled course) management and bootcamp-book associations. ⚠️ Note: the `Bootcamp` model has no create action on its own `BootcampController` — `bootcamps` rows are actually created via `LawSikho`'s `POST /v1/bootcamp_from_lawsikho` (see `documentation/API_SPECIFICATIONS.md` §7). Don't confuse this with "bootcamp courses," a separate concept (`courses` rows with `course_type = BOOTCAMP_COURSE`, created via `Modules/Course`). |
| Class | ⚠️ **Not currently in use** (confirmed by team, 2026-08-29). Live class scheduling: occurrences, hosts, experts, participants, Zoom user mapping, course/batch/topic linkage, class packages |
| ClassCSAT | ⚠️ **Not currently in use** (confirmed by team, 2026-08-29). Post-class CSAT survey forms and reason-code mappings |
| Country | Country reference/master data |
| Course | Core course catalog, mentor/instructor/evaluator mappings, mock question/answer bank |
| CourseBatch | Course batch (cohort) management, including Edmingle batch sync and a calendar webhook receiver |
| CourseCategory | Course category master data |
| CourseCategoryCriteria | Eligibility/criteria rules tied to course categories |
| CourseCompletionMaster | Master config for course completion rules (no dedicated entity found — likely reads/writes via other modules' models or config-only) |
| CourseCriteria | Course-level and bootcamp-course eligibility criteria |
| CourseFaq | FAQ content per course |
| CoursePlanType | Course plan/pricing type master data |
| EmailTemplate | Manages reusable email templates used across notification flows |
| Enrollment | Core student enrollment records, bulk enrollment (CSV) import/reporting, enrollment pause logs, enrollment questionnaires |
| Evaluator | Evaluator (grader) master records |
| EvaluatorCSAT | Post-evaluation CSAT survey forms for evaluators |
| Forum | ⚠️ **Not currently in use** (confirmed by team, 2026-08-29). Admin-side forum/discussion feature (entity-less — likely proxies to an external forum, see Vanilla Forum config in services) |
| InternalNotes | Internal staff notes on students, with edit history |
| JobRole | Job role master data (used by AtsAPI / User modules) |
| LawSikho | Miscellaneous LawSikho-branded integration; logs third-party API calls (`ThirdPartyLog`) — catch-all/legacy module |
| Notification | In-app notification system: batch sends, per-channel/category notifications, per-course/package targeting, comments |
| NPS | Net Promoter Score survey collection across courses, packages, and bootcamps (v1 and v2 form schemas) |
| Package | Bundled package (multi-course) catalog and course mapping |
| PerformanceCoach | ⚠️ **Not currently in use** (confirmed by team, 2026-08-29). Performance coaching: coach categories, call scheduling/slots, call outcomes, student assignment to coaches |
| PerformanceCoachCSAT | ⚠️ **Not currently in use** (confirmed by team, 2026-08-29). Post-coaching-call CSAT survey forms |
| Permission | Permission master data (spatie/laravel-permission integration) |
| ProjectManagement | ⚠️ **Not currently in use** (confirmed by team, 2026-08-29). Kanboard-style project/task tracking for student projects (columns, tasks, student file uploads) |
| ReferralSystem | Student referral program (entity-less — likely stores data on the `Student`/`Enrollment` models directly) |
| Result | Student results/scores, exercise scoring, featured assignment mapping |
| RevenueAPI | Inbound integration receiving enrollment/revenue data from LawSikho's revenue platform (entity-less — likely writes into `Enrollment`) |
| Role | Role master data + model-role pivot (spatie/laravel-permission) |
| State | State/province reference master data |
| Student | Core student profile, availability, and misc detail records |
| StudentAssignment | Student-side assignment submissions and view/reporting, first-assignment send tracking |
| StudentAuth | Student authentication (login, password reset) — separate from admin `Auth` module |
| StudentBookACall | ✅ **Confirmed live in production** (per team, 2026-08-29) — integrates with a separate sub-project's API (explains the `MEETING_API_BASE_URL`/`BOOK_A_CALL_API` external calls in §6 of USER_WORKFLOWS.md). Student-facing call/meeting booking: instructors, teams, events, availability (also the module with the previously-broken placeholder route in `Routes/web.php`, now fixed) |
| StudentClasses | ⚠️ **Not currently in use** (confirmed by team, 2026-08-29). Student-facing class listing/access (contains a stray `Untitled-1.sql` file in `Routes/` — likely accidental commit, worth cleanup) |
| StudentDashboard | Student dashboard/LMS landing data aggregation |
| StudentDashboardManagement | Admin-side management of the student "journey" steps shown on the dashboard, with comments |
| StudentDegree | Student academic degree records |
| StudentForum | ⚠️ **Not currently in use** (confirmed by team, 2026-08-29). Student-facing forum access |
| StudentFrontendEnrollment | Student-facing enrollment frontend; unusually also hosts several CSAT/NPS/Notification/Task/Filter controllers — appears to be a frontend aggregation layer re-exposing other modules' controllers for the student portal (worth confirming with the team whether this is intentional duplication) |
| StudentMyCourses | Student's enrolled-course listing and global search |
| StudentNotifications | Student-facing notification retrieval |
| StudentPerformanceCoach | ⚠️ **Not currently in use** (confirmed by team, 2026-08-29). Student-facing performance coaching data |
| StudentProfile | Student profile details, original registration snapshot, "how did you hear about LawSikho" survey |
| StudentResults | Student-facing results/scores view |
| StudentTasks | ⚠️ **Not currently in use** (confirmed by team, 2026-08-29). Student task management with file mapping |
| StudentUniversity | Student university/education background records |
| Topic | Course topic/curriculum management, topic documents, assignment-video mapping |
| User | Admin/staff user records, user details, user-to-job-role mapping |
| Webhook | Generic inbound webhook receiver/logger, including failed-response tracking |

**Modules whose purpose is genuinely ambiguous from names alone and should be confirmed with the team:** `CourseCompletionMaster`, `Forum`, `LawSikho`, `ReferralSystem`, `RevenueAPI` (no entities of their own — likely operate on other modules' data or are thin integration wrappers).
## 5. Authentication System

The API uses **three separate auth guards** defined in `config/auth.php`, backed by **Laravel Sanctum** (`laravel/sanctum` ^2.11) for token issuance:

| Guard | Driver | Provider | Model |
|---|---|---|---|
| `web` | session | `users` | `App\Models\User` |
| `sanctum` | sanctum | `users` | `App\Models\User` (admin/staff) |
| `student` | sanctum | `students` | `Modules\Student\Entities\Student` |

Sanctum config (`config/sanctum.php`): token `expiration` is `null` (personal access tokens **never expire** unless revoked manually). Stateful domains default to `localhost,localhost:3000,127.0.0.1,127.0.0.1:8000,::1` plus `APP_URL`/`FRONTEND_URL` hosts if set.

### Admin/Staff login flow (`Modules/Auth`, prefix `v1`, guard `sanctum`)
Routes (`Modules/Auth/Routes/api.php`), all wrapped in `json.response` middleware:
- `POST /v1/register` — `RegisteredUserController@store` (guest only)
- `POST /v1/login` — `AuthController@store` (guest only) — issues a Sanctum token for `App\Models\User`
- `POST /v1/forgot-password`, `POST /v1/reset-password` — standard Laravel password-reset controllers (guest only)
- Behind `auth:sanctum`: `POST /v1/logout` (`AuthController@destroy`), `POST /v1/email/verification-notification`, `GET /v1/verify-email/{id}/{hash}`, `POST /v1/update-password`

Note: `Modules/Auth/Routes/web.php` also has a scaffold placeholder route (`/auth` → `AuthController@index`) — same dead-scaffold pattern found in `StudentBookACall` (see routes section); low risk since it's under `web` not `api`, but worth auditing other modules for the same leftover.

### Student login flow (`Modules/StudentAuth`, prefix `student/v1`, guard `student`)
Routes (`Modules/StudentAuth/Routes/api.php`), wrapped in `json.response` + `last.login` middleware:
- Guest: `POST /student/v1/login/email-verification`, `POST /student/v1/login/password-verification` (`StudentAuthController`), forgot-password flow (email verification → OTP → create password, via `PasswordResetController`), plus SSO endpoints: `POST /student/v1/sso-validation` and `POST /student/v1/edmingle/sso-validation` (both on `Modules\Student\Http\Controllers\StudentController`, for admin-initiated and Edmingle-initiated SSO respectively)
- Behind `auth:student`: `GET /lms`, OTP send/verify/resend, email-verified check, `logout`, `update-password`, `change-password`

`Modules/StudentAuth/Routes/web.php` has the same dead-scaffold placeholder (`/studentauth` → `StudentAuthController@index`) pointing at a controller that likely doesn't exist under that exact name in this module — same class of issue as the `StudentBookACall` bug fixed earlier; not verified further here as it's a `web.php` route (out of scope for `api` clients).

### JWT (`tymon/jwt-auth`) — installed but NOT actually used
`tymon/jwt-auth` (`"*"`) is a composer dependency and the `DEVELOPER_DOCUMENTATION.md` (stale doc) describes it as being used "for Edmingle SSO." **This is not accurate today**: there is no `config/jwt.php` published, no `Tymon\JWTAuth` provider registered in `config/app.php`, and a repo-wide grep (excluding vendor/node_modules) for `JWTAuth`, `Tymon\JWTAuth`, and `JWTFactory` returns **zero matches** in application code. The actual Edmingle SSO flow goes through `StudentController::edmingleSsoValidation` using Sanctum's `student` guard, not JWT. Treat `tymon/jwt-auth` as an unused/vestigial dependency unless further grep turns up dynamic usage.

### RBAC — `spatie/laravel-permission`
Configured in `config/permission.php` with custom models (not the package's stock ones):
- Permission model: `Modules\Permission\Entities\Permission`
- Role model: `Modules\Role\Entities\Role`
- Standard tables: `roles`, `permissions`, `model_has_permissions`, `model_has_roles` (+ presumably `role_has_permissions`, not shown in the head of the config but standard for this package).
- `Modules/Role` and `Modules/Permission` provide the CRUD/management layer for roles and permissions used to gate admin/staff access; student guard does not appear to use spatie/permission (no student-side role model referenced in config).

---

## 6. API Routes Reference

> Generated from a live `php artisan route:list --json` run against the current codebase (post-fix of the dead `StudentBookACall` placeholder route). Total registered routes: **1143**.

- API routes (`api` middleware): **1028**
- Plain web routes (non-API): **4**
- Vendor/framework routes excluded from tables below (Telescope, Horizon, etc.): **67**
- Dead/unused `nwidart/laravel-modules` scaffold placeholders (e.g. `GET /assignment` → `AssignmentController@index`, one per module, left over from `module:make`, not part of the real API — **do not build QA tests against these**): **44**
- Real, purpose-built module route groups documented below: **64**

### 6.1 Scaffold placeholder routes (unused, exclude from testing)

These are leftover default routes auto-generated when each module was created via `php artisan module:make`. One existed for `StudentBookACall` pointing at a controller that was **never created**, which crashed `artisan route:list` until it was commented out. The rest point at real (but unused) `index()` methods. Treat all of these as dead code, not part of the supported API surface.

| Method | URI | Controller@Action |
|---|---|---|
| GET|HEAD | `/agenticsupportsystem` | `Modules\AgenticSupportSystem\Http\Controllers\AgenticSupportSystemController@index` |
| GET|HEAD | `/aievaluation` | `Modules\AIEvaluation\Http\Controllers\AIEvaluationController@index` |
| GET|HEAD | `/assignment` | `Modules\Assignment\Http\Controllers\AssignmentController@index` |
| GET|HEAD | `/assignmentcsat` | `Modules\AssignmentCSAT\Http\Controllers\AssignmentCSATController@index` |
| GET|HEAD | `/assignmentsendinglog` | `Modules\AssignmentSendingLog\Http\Controllers\AssignmentSendingLogController@index` |
| GET|HEAD | `/atsapi` | `Modules\AtsAPI\Http\Controllers\AtsAPIController@index` |
| GET|HEAD | `/bookdeliverylog` | `Modules\BookDeliveryLog\Http\Controllers\BookDeliveryLogController@index` |
| GET|HEAD | `/bookmaster` | `Modules\BookMaster\Http\Controllers\BookMasterController@index` |
| GET|HEAD | `/class` | `Modules\Class\Http\Controllers\ClassController@index` |
| GET|HEAD | `/classcsat` | `Modules\ClassCSAT\Http\Controllers\ClassCSATController@index` |
| GET|HEAD | `/country` | `Modules\Country\Http\Controllers\CountryController@index` |
| GET|HEAD | `/course` | `Modules\Course\Http\Controllers\CourseController@index` |
| GET|HEAD | `/coursecategorycriteria` | `Modules\CourseCategoryCriteria\Http\Controllers\CourseCategoryCriteriaController@index` |
| GET|HEAD | `/coursecompletionmaster` | `Modules\CourseCompletionMaster\Http\Controllers\CourseCompletionMasterController@index` |
| GET|HEAD | `/dump-autoload` | `Closure` |
| GET|HEAD | `/evaluator` | `Modules\Evaluator\Http\Controllers\EvaluatorController@index` |
| GET|HEAD | `/evaluatorcsat` | `Modules\EvaluatorCSAT\Http\Controllers\EvaluatorCSATController@index` |
| GET|HEAD | `/forum` | `Modules\Forum\Http\Controllers\ForumController@index` |
| GET|HEAD | `/jobrole` | `Modules\JobRole\Http\Controllers\JobRoleController@index` |
| GET|HEAD | `/lawsikho` | `Modules\LawSikho\Http\Controllers\LawSikhoController@index` |
| GET|HEAD | `/logs` | `Rap2hpoutre\LaravelLogViewer\LogViewerController@index` |
| GET|HEAD | `/notification` | `Modules\Notification\Http\Controllers\NotificationController@index` |
| GET|HEAD | `/performancecoach` | `Modules\PerformanceCoach\Http\Controllers\PerformanceCoachController@index` |
| GET|HEAD | `/performancecoachcsat` | `Modules\PerformanceCoachCSAT\Http\Controllers\PerformanceCoachCSATController@index` |
| GET|HEAD | `/projectmanagement` | `Modules\ProjectManagement\Http\Controllers\ProjectManagementController@index` |
| GET|HEAD | `/referralsystem` | `Modules\ReferralSystem\Http\Controllers\ReferralSystemController@index` |
| GET|HEAD | `/result` | `Modules\Result\Http\Controllers\ResultController@index` |
| GET|HEAD | `/revenueapi` | `Modules\RevenueAPI\Http\Controllers\RevenueAPIController@index` |
| GET|HEAD | `/state` | `Modules\State\Http\Controllers\StateController@index` |
| GET|HEAD | `/studentauth` | `Modules\StudentAuth\Http\Controllers\StudentAuthController@index` |
| GET|HEAD | `/studentclasses` | `Modules\StudentClasses\Http\Controllers\StudentClassesController@index` |
| GET|HEAD | `/studentdashboard` | `Modules\StudentDashboard\Http\Controllers\StudentDashboardController@index` |
| GET|HEAD | `/studentdashboardmanagement` | `Modules\StudentDashboardManagement\Http\Controllers\StudentDashboardManagementController@index` |
| GET|HEAD | `/studentdegree` | `Modules\StudentDegree\Http\Controllers\StudentDegreeController@index` |
| GET|HEAD | `/studentforum` | `Modules\StudentForum\Http\Controllers\StudentForumController@index` |
| GET|HEAD | `/studentfrontendenrollment` | `Modules\StudentFrontendEnrollment\Http\Controllers\StudentFrontendEnrollmentController@index` |
| GET|HEAD | `/studentmycourses` | `Modules\StudentMyCourses\Http\Controllers\StudentMyCoursesController@index` |
| GET|HEAD | `/studentnotifications` | `Modules\StudentNotifications\Http\Controllers\StudentNotificationsController@index` |
| GET|HEAD | `/studentperformancecoach` | `Modules\StudentPerformanceCoach\Http\Controllers\StudentPerformanceCoachController@index` |
| GET|HEAD | `/studentprofile` | `Modules\StudentProfile\Http\Controllers\StudentProfileController@index` |
| GET|HEAD | `/studentresults` | `Modules\StudentResults\Http\Controllers\StudentResultsController@index` |
| GET|HEAD | `/studenttasks` | `Modules\StudentTasks\Http\Controllers\StudentTasksController@index` |
| GET|HEAD | `/studentuniversity` | `Modules\StudentUniversity\Http\Controllers\StudentUniversityController@index` |
| GET|HEAD | `/webhook` | `Modules\Webhook\Http\Controllers\WebhookController@index` |

### 6.2 Routes by module

Grouped by the module namespace that owns the controller. Within each module, routes are sorted by URI. Route `name` is shown only when Laravel assigned one.

#### AIEvaluation (12 routes)

Common middleware: `App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| POST | `/api/v1/ai-assignments/bulk-assign` |  | `AIModelBulkAssignmentController@bulkAssign` |
| POST | `/api/v1/ai-assignments/bulk-evaluate` |  | `AIModelBulkAssignmentController@bulkEvaluate` |
| POST | `/api/v1/ai-assignments/edit-feedback` |  | `AIModelBulkAssignmentController@editFeedback` |
| POST | `/api/v1/ai-assignments/evaluate` |  | `AIModelBulkAssignmentController@singleEvaluate` |
| POST | `/api/v1/ai-assignments/webhook` | ai-evaluation.webhook | `AIEvaluationWebhookController@handle` |
| POST | `/api/v1/ai-evaluation/send-to-ai` |  | `AIEvaluationController@sendToAI` |
| POST | `/api/v1/ai-evaluation/webhook` |  | `AIEvaluationController@evaluationWebhook` |
| GET|HEAD | `/api/v1/ai-models` |  | `AIModelController@index` |
| POST | `/api/v1/ai-models` |  | `AIModelController@store` |
| PUT | `/api/v1/ai-models/{id}` |  | `AIModelController@update` |
| DELETE | `/api/v1/ai-models/{id}` |  | `AIModelController@destroy` |
| PATCH | `/api/v1/ai-models/{id}/set-default` |  | `AIModelController@setDefault` |

#### AgenticSupportSystem (61 routes)

Common middleware: `App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| POST | `/api/v1/batch/check-edmingle-mapping` | ass.check-edmingle-mapping | `AgenticSupportSystemController@checkEdmingleBatchMapping` |
| GET|HEAD | `/api/v1/batches/all` | ass.all-batches | `AgenticSupportSystemController@getAllBatches` |
| GET|HEAD | `/api/v1/bootcamps/all` | ass.all-bootcamps | `AgenticSupportSystemController@getAllBootcamps` |
| GET|HEAD | `/api/v1/course-calender/course-anchor-users-details/all` | course-calender.all-course-anchor-users-details | `AgenticSupportSystemController@getAllCourseAnchorUsersDetails` |
| GET|HEAD | `/api/v1/course-calender/course-category-details/all` | course-calender.all-course-category-details | `AgenticSupportSystemController@getAllCourseCategoryDetails` |
| GET|HEAD | `/api/v1/course-calender/course-details/all` | course-calender.all-course-details | `AgenticSupportSystemController@getAllCourseDetails` |
| GET|HEAD | `/api/v1/course-calender/evaluator-admin-users-details/all` | course-calender.all-evaluator-admin-users-details | `AgenticSupportSystemController@getAllEvaluatorAdminUsersDetails` |
| GET|HEAD | `/api/v1/course-calender/evaluator-users-details/all` | course-calender.all-evaluator-users-details | `AgenticSupportSystemController@getAllEvaluatorUsersDetails` |
| GET|HEAD | `/api/v1/course-calender/get-user-by-roles` | course-calender.get-user-by-roles | `AgenticSupportSystemController@getUserByRoles` |
| GET|HEAD | `/api/v1/course-calender/student-count-in-course-and-batch` | course-calender.student-count-in-course-and-batch | `AgenticSupportSystemController@getStudentCountInCourseAndBatch` |
| GET|HEAD | `/api/v1/courses/all` | ass.all-courses | `AgenticSupportSystemController@getAllCourses` |
| POST | `/api/v1/external/sanctum/validate-user` | ass.sanctum-token-validation | `AgenticSupportSystemController@sanctumTokenValidation` |
| GET|HEAD | `/api/v1/listing/batches-v2` | ass.batches-listing-v2 | `AgenticSupportSystemController@getBatchesListingV2` |
| GET|HEAD | `/api/v1/listing/bootcamps-v2` | ass.bootcamps-listing-v2 | `AgenticSupportSystemController@getBootcampsListingV2` |
| GET|HEAD | `/api/v1/listing/countries-v2` | ass.countries-listing-v2 | `AgenticSupportSystemController@getCountriesListingV2` |
| GET|HEAD | `/api/v1/listing/courses-v2` | ass.courses-listing-v2 | `AgenticSupportSystemController@getCoursesListingV2` |
| GET|HEAD | `/api/v1/packages/all` | ass.all-packages | `AgenticSupportSystemController@getAllPackages` |
| GET|HEAD | `/api/v1/students/all-data/{emailId}` | ass.all-data | `AgenticSupportSystemController@getStudentAllDataByEmailId` |
| POST | `/api/v1/students/assign-batch-v2` | ass.student-assign-batch-v2 | `AgenticSupportSystemController@assignBatchV2` |
| GET|HEAD | `/api/v1/students/assignments-v2` | ass.student-assignments-v2 | `AgenticSupportSystemController@getStudentAssignmentsV2` |
| GET|HEAD | `/api/v1/students/certificates-v2` | ass.student-certificates-v2 | `AgenticSupportSystemController@getStudentCertificatesV2` |
| GET|HEAD | `/api/v1/students/course-details-by-email` | ass.course-details-by-email | `AgenticSupportSystemController@getCourseDetailsByEmail` |
| POST | `/api/v1/students/create-bootcamp-additional-enrollment-by-course-name` | ass.student-create-bootcamp-additional-enrollment-by-course-name | `AgenticSupportSystemController@createBootcampAdditionalEnrollmentByCourseName` |
| POST | `/api/v1/students/create-enrollment-v2` | ass.student-create-enrollment-v2 | `AgenticSupportSystemController@createEnrollmentV2` |
| GET|HEAD | `/api/v1/students/details-by-name` | ass.students-details-by-name | `AgenticSupportSystemController@getStudentsDetailsFromName` |
| GET|HEAD | `/api/v1/students/details-v2` | ass.students-details-v2 | `AgenticSupportSystemController@getStudentsDetailsV2` |
| GET|HEAD | `/api/v1/students/details/for-transcript` | ass.students-details-for-transcript | `AgenticSupportSystemController@getStudentsDetailsForTranscript` |
| GET|HEAD | `/api/v1/students/enrollment-form-data-v2` | ass.student-enrollment-form-data-v2 | `AgenticSupportSystemController@getStudentEnrollmentFormDataV2` |
| GET|HEAD | `/api/v1/students/enrollments-v2` | ass.student-enrollments-v2 | `AgenticSupportSystemController@getStudentEnrollmentsV2` |
| GET|HEAD | `/api/v1/students/enrollments-v3` | ass.student-enrollments-v3 | `AgenticSupportSystemController@getStudentEnrollmentsV3` |
| GET|HEAD | `/api/v1/students/enrollments-v4` | ass.student-enrollments-v4 | `AgenticSupportSystemController@getStudentEnrollmentsV2` |
| POST | `/api/v1/students/get-student-registration-details` | ass.student-get-student-registration-details | `AgenticSupportSystemController@getStudentRegistrationDetails` |
| GET|HEAD | `/api/v1/students/hardcopy-v2` | ass.student-hardcopy-v2 | `AgenticSupportSystemController@getStudentHardCopyDeliveryV2` |
| GET|HEAD | `/api/v1/students/meetings-v2` | ass.student-meetings-v2 | `AgenticSupportSystemController@getStudentMeetingsV2` |
| POST | `/api/v1/students/migrate-batch-v2` | ass.migrate-batch-v2 | `AgenticSupportSystemController@migrateBatchV2` |
| POST | `/api/v1/students/migrate-batch-v3` | ass.migrate-batch-v3 | `AgenticSupportSystemController@migrateBatchV3` |
| POST | `/api/v1/students/migrate-bootcamp-v2` | ass.migrate-bootcamp-v2 | `AgenticSupportSystemController@migrateBootcampV2` |
| GET|HEAD | `/api/v1/students/results-v2` | ass.student-results-v2 | `AgenticSupportSystemController@getStudentResultsV2` |
| POST | `/api/v1/students/resume-enrollment-v2` | ass.student-resume-enrollment-v2 | `AgenticSupportSystemController@resumeEnrollmentV2` |
| POST | `/api/v1/students/update-enrollment-status-v2` | ass.student-update-enrollment-status-v2 | `AgenticSupportSystemController@updateEnrollmentStatusV2` |
| POST | `/api/v1/students/update-v2` | ass.student-update-v2 | `AgenticSupportSystemController@updateStudentV2` |
| GET|HEAD | `/api/v1/students/{email}/all-course-details-by-email` | ass.all-course-details-by-email | `AgenticSupportSystemController@getAllCourseDetailsByEmail` |
| GET|HEAD | `/api/v1/students/{email}/assignments/{enrollment_id}` | ass.student-assignments-by-enrollment-id | `AgenticSupportSystemController@getAssignmentsByEnrollmentId` |
| GET|HEAD | `/api/v1/students/{email}/certificates/{enrollment_id}` | ass.student-certificates | `AgenticSupportSystemController@getCertificates` |
| GET|HEAD | `/api/v1/students/{email}/course-details/{courseId}` | ass.course-details-by-email-and-course-id | `AgenticSupportSystemController@getCourseDetailsByEmailAndCourseId` |
| GET|HEAD | `/api/v1/students/{email}/enrolled-courses` | ass.student-enrolled-courses | `AgenticSupportSystemController@getEnrolledCoursesByStudentEmail` |
| GET|HEAD | `/api/v1/students/{email}/enrollments` | ass.student-enrollment-details | `AgenticSupportSystemController@getStudentEnrollmentDetails` |
| GET|HEAD | `/api/v1/students/{email}/get-course-details/{courseId}` | ass.student-enrollment-details-by-course-id | `AgenticSupportSystemController@getEnrollmentsByCourseId` |
| GET|HEAD | `/api/v1/students/{email}/meetings` | ass.student-meetings | `AgenticSupportSystemController@getMeetings` |
| GET|HEAD | `/api/v1/students/{email}/notifications` | ass.student-notifications | `AgenticSupportSystemController@getNotifications` |
| GET|HEAD | `/api/v1/students/{email}/results/{enrollment_id}` | ass.student-results-by-enrollment-id | `AgenticSupportSystemController@getResultsByEnrollmentId` |
| GET|HEAD | `/api/v1/students/{email}/student-details` | ass.student-details | `AgenticSupportSystemController@getStudentDetails` |
| GET|HEAD | `/api/v1/students/{email}/student-details-for-ai-support` | ass.student-details-for-ai-support | `AgenticSupportSystemController@getStdentDetailsForAISupport` |
| GET|HEAD | `/api/v1/support-hub/enrollments/details` | support-hub.enrollment-details | `AgenticSupportSystemController@getEnrollmentDetails` |
| GET|HEAD | `/api/v1/support-hub/enrollments/pause-requested` | support-hub.enrollments-pause-requested | `AgenticSupportSystemController@getPauseRequestedEnrollmentsForSupportHub` |
| GET|HEAD | `/api/v1/support-hub/get-upcoming-batches-for-specific-course` | support-hub.get-upcoming-batches-for-specific-course | `AgenticSupportSystemController@getUpcomingBatchesForSpecificCourse` |
| GET|HEAD | `/api/v1/support-hub/students/assignments-by-email` | support-hub.assignments-by-email | `AgenticSupportSystemController@getAssignmentsDetailsForSupportHub` |
| GET|HEAD | `/api/v1/support-hub/students/by-course-batch` | support-hub.students-by-course-batch | `AgenticSupportSystemController@getStudentsByCourseAndBatchForSupportHub` |
| POST | `/api/v1/support-hub/students/deactivate` | support-hub.students.deactivate | `AgenticSupportSystemController@deactivateStudentsAgenticAPI` |
| GET|HEAD | `/api/v1/support-hub/students/enrollment-list` | support-hub.student-enrollment-list | `AgenticSupportSystemController@getStudentEnrollmentListForSupportHub` |
| GET|HEAD | `/api/v1/support-hub/students/enrollments` | support-hub.student-enrollments | `AgenticSupportSystemController@getStudentEnrollmentsOverview` |

#### Assignment (11 routes)

Common middleware: `App\Http\Middleware\Authenticate:sanctum, App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/v1/assignment-library` | assignment-library.index | `AssignmentController@index` |
| POST | `/api/v1/assignment-library` | assignment-library.store | `AssignmentController@store` |
| GET|HEAD | `/api/v1/assignment-library/count` | assignment-library.count | `AssignmentController@getAssignmentCounts` |
| DELETE | `/api/v1/assignment-library/delete-multiple` | assignment-library.delete-multiple | `AssignmentController@deactivateMultiple` |
| POST | `/api/v1/assignment-library/status/change` | assignment-library.status.change | `AssignmentController@changeStatus` |
| PUT | `/api/v1/assignment-library/{assignment}` | assignment-library.update | `AssignmentController@update` |
| GET|HEAD | `/api/v1/assignment-library/{assignment}/logs` | bootcamp-course.logs | `AssignmentController@activityLogs` |
| GET|HEAD | `/api/v1/assignment-library/{course_id}/export` | assignment-library.export | `BootcampAssignmentController@export` |
| POST | `/api/v1/bootcamp-assignment-library` | bootcamp-assignment-library.store | `BootcampAssignmentController@store` |
| GET|HEAD | `/api/v1/bootcamp-assignment-library` | bootcamp-assignment-library.index | `BootcampAssignmentController@index` |
| PUT | `/api/v1/bootcamp-assignment-library/{assignment}` | bootcamp-assignment-library.update | `BootcampAssignmentController@update` |

#### AssignmentCSAT (11 routes)

Common middleware: `App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/student/v1/assignment-csat/{student_assignment}` | student.assignment-csat.questions | `AssignmentCSATController@getAssignmentCSATFormReason` |
| GET|HEAD | `/api/student/v1/student/assignment-csat-questions` | assignment-csat.questions | `AssignmentCSATController@getCSATFormReason` |
| GET|HEAD | `/api/v1/assignment-csat` | assignment-csat.index | `AssignmentCSATController@index` |
| POST | `/api/v1/assignment-csat` | assignment-csat.store | `AssignmentCSATController@store` |
| POST | `/api/v1/assignment-csat/check-available` | assignment-csat.check-available | `AssignmentCSATController@checkAvailable` |
| GET|HEAD | `/api/v1/assignment-csat/export` | assignment-csat.export | `AssignmentCSATController@export` |
| GET|HEAD | `/api/v1/assignment-csat/graph-index` | assignment-csat.graph_index | `AssignmentCSATController@graphIndex` |
| GET|HEAD | `/api/v1/assignment-csat/reasons` | assignment-csat.reasons | `AssignmentCSATController@getCSATFormReason` |
| GET|HEAD | `/api/v1/assignment-csat/{assignment_csat}` | assignment-csat.show | `AssignmentCSATController@show` |
| PUT|PATCH | `/api/v1/assignment-csat/{assignment_csat}` | assignment-csat.update | `AssignmentCSATController@update` |
| DELETE | `/api/v1/assignment-csat/{assignment_csat}` | assignment-csat.destroy | `AssignmentCSATController@destroy` |

#### AssignmentSendingLog (6 routes)

Common middleware: `App\Http\Middleware\Authenticate:sanctum, App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/v1/assignment-log` | assignment-log.index | `AssignmentSendingLogController@index` |
| POST | `/api/v1/assignment-log` | assignment-log.store | `AssignmentSendingLogController@store` |
| GET|HEAD | `/api/v1/assignment-log/get-student-list/{assignment_log_id}` | assignment-log.get-student-list | `AssignmentSendingLogController@getStudentList` |
| GET|HEAD | `/api/v1/assignment-log/{assignment_log}` | assignment-log.show | `AssignmentSendingLogController@show` |
| PUT|PATCH | `/api/v1/assignment-log/{assignment_log}` | assignment-log.update | `AssignmentSendingLogController@update` |
| DELETE | `/api/v1/assignment-log/{assignment_log}` | assignment-log.destroy | `AssignmentSendingLogController@destroy` |

#### AssignmentTag (6 routes)

Common middleware: `App\Http\Middleware\Authenticate:sanctum, App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/v1/search/tags` | tags.search | `TagController@search` |
| GET|HEAD | `/api/v1/tags` | tags.index | `TagController@index` |
| POST | `/api/v1/tags` | tags.store | `TagController@store` |
| GET|HEAD | `/api/v1/tags/{tag}` | tags.show | `TagController@show` |
| PUT|PATCH | `/api/v1/tags/{tag}` | tags.update | `TagController@update` |
| DELETE | `/api/v1/tags/{tag}` | tags.destroy | `TagController@destroy` |

#### AtsAPI (4 routes)

Common middleware: `App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/student/v1/atsapi/get-all-jobs` | get-all-jobs | `AtsAPIController@getAllJobs` |
| GET|HEAD | `/api/v1/atsapi/get-all-courses` | get-all-courses | `AtsAPIController@getAllCourses` |
| GET|HEAD | `/api/v1/atsapi/get-all-jobs` | get-all-jobs | `AtsAPIController@getAllJobs` |
| POST | `/api/v1/save-job-and-course-mapping` | save-job-and-course-mapping | `AtsAPIController@saveJobAndCourseMapping` |

#### Auth (8 routes)

Common middleware: `App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| POST | `/api/v1/email/verification-notification` | verification.send | `EmailVerificationNotificationController@store` |
| POST | `/api/v1/forgot-password` | password.email | `PasswordResetLinkController@store` |
| POST | `/api/v1/login` |  | `AuthController@store` |
| POST | `/api/v1/logout` | logout | `AuthController@destroy` |
| POST | `/api/v1/register` |  | `RegisteredUserController@store` |
| POST | `/api/v1/reset-password` | password.update | `NewPasswordController@store` |
| POST | `/api/v1/update-password` | update-password | `NewPasswordController@update_password` |
| GET|HEAD | `/api/v1/verify-email/{id}/{hash}` | verification.verify | `VerifyEmailController@__invoke` |

#### BookDeliveryLog (3 routes)

Common middleware: `App\Http\Middleware\Authenticate:sanctum, App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/v1/book_delivery_log` |  | `BookDeliveryLogController@index` |
| GET|HEAD | `/api/v1/book_delivery_log/export/csv` |  | `BookDeliveryLogController@export` |
| PUT | `/api/v1/book_delivery_log/manual-order` |  | `BookDeliveryLogController@manualOrder` |

#### BookMaster (8 routes)

Common middleware: `App\Http\Middleware\Authenticate:sanctum, App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/v1/book_master` | book_master.index | `BookMasterController@index` |
| POST | `/api/v1/book_master` | book_master.store | `BookMasterController@store` |
| GET|HEAD | `/api/v1/book_master/export` |  | `BookMasterController@export` |
| GET|HEAD | `/api/v1/book_master/search` |  | `BookMasterController@search` |
| GET|HEAD | `/api/v1/book_master/{book_master_id}/activity` | book_master.activity | `BookMasterController@activity` |
| GET|HEAD | `/api/v1/book_master/{book_master}` | book_master.show | `BookMasterController@show` |
| PUT|PATCH | `/api/v1/book_master/{book_master}` | book_master.update | `BookMasterController@update` |
| DELETE | `/api/v1/book_master/{book_master}` | book_master.destroy | `BookMasterController@destroy` |

#### Bootcamp (9 routes)

Common middleware: `App\Http\Middleware\Authenticate:sanctum, App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/v1/bootcamps` |  | `BootcampController@index` |
| GET|HEAD | `/api/v1/bootcamps/book_master/export` |  | `BootcampController@export` |
| POST | `/api/v1/bootcamps/books` |  | `BootcampController@storeBootcampBooks` |
| GET|HEAD | `/api/v1/bootcamps/search` |  | `BootcampController@search` |
| GET|HEAD | `/api/v1/bootcamps/{bootcamp_id}/activity` | bootcamps.activity | `BootcampController@activity` |
| PUT | `/api/v1/bootcamps/{bootcamp}/books` |  | `BootcampController@updateBootcampBooks` |
| GET|HEAD | `/api/v1/search/all_bootcamp` |  | `BootcampController@all_bootcamps` |
| GET|HEAD | `/api/v1/search/specific-bootcamp-list` |  | `BootcampController@specific_bootcamp_list` |
| GET|HEAD | `/api/v1/student_specific_bootcamps` |  | `BootcampController@student_specific_bootcamps` |

#### Class (15 routes)

Common middleware: `(varies per route — see individual entries if needed)`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/v1/class` | class.index | `ClassController@index` |
| POST | `/api/v1/class` | class.store | `ClassController@store` |
| GET|HEAD | `/api/v1/class/details/export/{class}` | class.details.export | `ClassController@exportDetails` |
| GET|HEAD | `/api/v1/class/export` | class.export | `ClassController@export` |
| GET|HEAD | `/api/v1/class/get-occurrence-date/{class}` | class.getOccurrenceDate | `ClassController@getOccurrenceDate` |
| GET|HEAD | `/api/v1/class/get-zoom-user` | class.get-zoom-user | `ClassController@getZoomUser` |
| GET|HEAD | `/api/v1/class/index/participants-count` | class.index.counts | `ClassController@indexMetaParticipantsCount` |
| GET|HEAD | `/api/v1/class/sync-zoom-user` | class.sync-zoom-user | `ClassController@syncUser` |
| GET|HEAD | `/api/v1/class/{class_occurrance_date}/manual-sync` | class.manual-sync | `ClassController@manualSync` |
| POST | `/api/v1/class/{class}` | class.update | `ClassController@update` |
| GET|HEAD | `/api/v1/class/{class}` | class.show | `ClassController@show` |
| PUT|PATCH | `/api/v1/class/{class}` | class.update | `ClassController@update` |
| DELETE | `/api/v1/class/{class}` | class.destroy | `ClassController@destroy` |
| GET|HEAD | `/api/v1/search/specific-class` | class.specific.search | `ClassController@searchClassesWithArray` |
| GET|HEAD | `/class/zoom` |  | `ClassController@syncUser` |

#### ClassCSAT (10 routes)

Common middleware: `App\Http\Middleware\Authenticate:sanctum, App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/v1/class-csat` | class-csat.index | `ClassCSATController@index` |
| POST | `/api/v1/class-csat` | class-csat.store | `ClassCSATController@store` |
| GET|HEAD | `/api/v1/class-csat-graph-index` | class-csat.graph_index | `ClassCSATController@graph_index` |
| GET|HEAD | `/api/v1/class-csat-questions` | class-csat.questions | `ClassCSATController@questions` |
| POST | `/api/v1/class-csat/check-available` | class-csat.check-available | `ClassCSATController@checkAvailable` |
| POST | `/api/v1/class-csat/export` | class-csat.export | `ClassCSATController@export` |
| GET|HEAD | `/api/v1/class-csat/{class_csat}` | class-csat.show | `ClassCSATController@show` |
| PUT|PATCH | `/api/v1/class-csat/{class_csat}` | class-csat.update | `ClassCSATController@update` |
| DELETE | `/api/v1/class-csat/{class_csat}` | class-csat.destroy | `ClassCSATController@destroy` |
| GET|HEAD | `/api/v1/class-list` | class-csat.class-list | `ClassCSATController@class_list` |

#### Closure/Anonymous (4 routes)

Common middleware: `(varies per route — see individual entries if needed)`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/api/debug-enrollments` |  | `Closure` |
| POST | `/api/packageStudentUpdate` |  | `Closure` |
| POST | `/api/v1/ai-assignments/reevaluate` |  | `Closure` |
| GET|HEAD | `/api/webhook` |  | `Closure` |

#### Country (6 routes)

Common middleware: `App\Http\Middleware\Authenticate:sanctum, App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/v1/countries` | countries.index | `CountryController@index` |
| POST | `/api/v1/countries` | countries.store | `CountryController@store` |
| GET|HEAD | `/api/v1/countries/{country}` | countries.show | `CountryController@show` |
| PUT|PATCH | `/api/v1/countries/{country}` | countries.update | `CountryController@update` |
| DELETE | `/api/v1/countries/{country}` | countries.destroy | `CountryController@destroy` |
| GET|HEAD | `/api/v1/search/countries` | countries.search | `CountryController@search` |

#### Course (27 routes)

Common middleware: `App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| POST | `/api/v1/add-course` | lawsikho.add_course | `CourseController@store` |
| POST | `/api/v1/bootcamp-course` | bootcamp-course.store | `BootcampCourseController@store` |
| GET|HEAD | `/api/v1/bootcamp-course` | bootcamp-course.index | `BootcampCourseController@index` |
| GET|HEAD | `/api/v1/bootcamp-course/export` | bootcamp-course.export | `BootcampCourseController@exportBootcampCourse` |
| POST | `/api/v1/bootcamp-course/status/change` | bootcamp-course.change.status | `BootcampCourseController@changeStatus` |
| PUT | `/api/v1/bootcamp-course/{course}` | bootcamp-course.update | `BootcampCourseController@update` |
| GET|HEAD | `/api/v1/bootcamp-course/{course}/logs` | bootcamp-course.logs | `BootcampCourseController@activityLogs` |
| GET|HEAD | `/api/v1/course` | course.index | `CourseController@index` |
| POST | `/api/v1/course` | course.store | `CourseController@store` |
| POST | `/api/v1/course/bulk-ai-config` | course.bulk-ai-config | `CourseController@bulkAIConfig` |
| GET|HEAD | `/api/v1/course/for/assignment-library` | course.index-for-assignment-library | `CourseController@courseIndexForAssignmentLibrary` |
| POST | `/api/v1/course/transfer-to-other` | course.transfer-to-other | `CourseController@transferToOther` |
| GET|HEAD | `/api/v1/course/{course}` | course.show | `CourseController@show` |
| PUT|PATCH | `/api/v1/course/{course}` | course.update | `CourseController@update` |
| DELETE | `/api/v1/course/{course}` | course.destroy | `CourseController@destroy` |
| GET|HEAD | `/api/v1/course/{course}/ai-config` | course.ai-config | `CourseController@getAIConfig` |
| GET|HEAD | `/api/v1/course/{course}/batches/performance` | course.batches.performance | `CourseController@batchesPerformance` |
| GET|HEAD | `/api/v1/course/{course}/batches/performance/total` | course.batches.performance.total | `CourseController@batchesPerformanceTotal` |
| GET|HEAD | `/api/v1/course/{course}/mentors` | course.mentors.index | `CourseController@courseMentors` |
| GET|HEAD | `/api/v1/courses/assignment-library/export` |  | `CourseController@exportAssignmentLibrary` |
| GET|HEAD | `/api/v1/courses/except_bootcamp` |  | `CourseController@courses_except_bootcamp` |
| GET|HEAD | `/api/v1/courses/export` |  | `CourseController@export` |
| GET|HEAD | `/api/v1/courses/student-assignments/dashboard/list` | course.student-assignments.dashboard.list | `CourseController@courseStudentAssignmentsDashboardData` |
| GET|HEAD | `/api/v1/courses/{course_id}/activity` | courses.activity | `CourseController@activity` |
| GET|HEAD | `/api/v1/search/courses` | course.search | `CourseController@search` |
| GET|HEAD | `/api/v1/search/specific-courses` | course.specific.search | `CourseController@searchCoursesWithArray` |
| GET|HEAD | `/api/v1/{course}/faqs` | course.faqs | `CourseController@courseFaqs` |

#### CourseBatch (26 routes)

Common middleware: `App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/v1/compare-batch-course-calendar` | course-calendar.compare-batch | `CourseCalendarWebhookController@compareBatchCourseCalender` |
| GET|HEAD | `/api/v1/course-batches` | course-batches.index | `CourseBatchController@index` |
| POST | `/api/v1/course-batches` | course-batches.store | `CourseBatchController@store` |
| POST | `/api/v1/course-batches/status/change` | course-batches.status.change | `CourseBatchController@changeStatus` |
| GET|HEAD | `/api/v1/course-batches/{courseBatch}/logs` | course-batches.logs | `CourseBatchController@activityLogs` |
| GET|HEAD | `/api/v1/course-batches/{course_batch}` | course-batches.show | `CourseBatchController@show` |
| PUT|PATCH | `/api/v1/course-batches/{course_batch}` | course-batches.update | `CourseBatchController@update` |
| DELETE | `/api/v1/course-batches/{course_batch}` | course-batches.destroy | `CourseBatchController@destroy` |
| POST | `/api/v1/course-calendar/batch-cancel` | course-calendar.batch-cancel | `CourseCalendarWebhookController@batchCancel` |
| POST | `/api/v1/course-calendar/batch-created` | course-calendar.batch-created | `CourseCalendarWebhookController@batchCreated` |
| POST | `/api/v1/course-calendar/batch-reschedule` | course-calendar.batch-reschedule | `CourseCalendarWebhookController@batchReschedule` |
| POST | `/api/v1/course-calendar/batch-sync` | course-calendar.batch-sync | `CourseCalendarWebhookController@handle` |
| POST | `/api/v1/course-calendar/batch-updated` | course-calendar.batch-updated | `CourseCalendarWebhookController@batchUpdated` |
| GET|HEAD | `/api/v1/course-calendar/bootcamps` | course-calendar.bootcamps | `CourseCalendarWebhookController@getBootcamps` |
| GET|HEAD | `/api/v1/course-calendar/bootcamps-with-title` | course-calendar.bootcamps-with-title | `CourseCalendarWebhookController@getBootcampsWithTitle` |
| GET|HEAD | `/api/v1/course-calendar/edmingle-tutors` | course-calendar.edmingle-tutors | `CourseCalendarWebhookController@getEdmingleTutors` |
| GET|HEAD | `/api/v1/coursebatch/export` |  | `CourseBatchController@export` |
| GET|HEAD | `/api/v1/edmingle-batches` | edmingle-batches.index | `EdmingleBatchController@index` |
| POST | `/api/v1/edmingle-batches` | edmingle-batches.store | `EdmingleBatchController@store` |
| GET|HEAD | `/api/v1/edmingle-batches/{edmingleBatch}/activity` | edmingleBatch.activity | `EdmingleBatchController@activity` |
| GET|HEAD | `/api/v1/edmingle-batches/{edmingle_batch}` | edmingle-batches.show | `EdmingleBatchController@show` |
| PUT|PATCH | `/api/v1/edmingle-batches/{edmingle_batch}` | edmingle-batches.update | `EdmingleBatchController@update` |
| DELETE | `/api/v1/edmingle-batches/{edmingle_batch}` | edmingle-batches.destroy | `EdmingleBatchController@destroy` |
| GET|HEAD | `/api/v1/search/course-batches` | course-batches.search | `CourseBatchController@search` |
| GET|HEAD | `/api/v1/search/course-batches-course-calender` | course-batches.search | `CourseCalendarWebhookController@searchCourseBatchesWithCourseCalender` |
| GET|HEAD | `/api/v1/search/specific-course-batches` | course-batches.specific.search | `CourseBatchController@searchBatchesWithArray` |

#### CourseCategory (14 routes)

Common middleware: `App\Http\Middleware\Authenticate:sanctum, App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/v1/course-categories` | course-categories.index | `CourseCategoryController@index` |
| POST | `/api/v1/course-categories` | course-categories.store | `CourseCategoryController@store` |
| GET|HEAD | `/api/v1/course-categories-for-package-creation` | course-categories.list-for-package-creation | `CourseCategoryController@listForPackageCreation` |
| GET|HEAD | `/api/v1/course-categories/export` |  | `CourseCategoryController@export` |
| POST | `/api/v1/course-categories/status/change` | roles.status.change | `CourseCategoryController@changeStatus` |
| POST | `/api/v1/course-categories/transfer-to-other` | course-categories.transfer-to-other | `CourseCategoryController@transferToOther` |
| GET|HEAD | `/api/v1/course-categories/{category_id}/activity` | course-categories.activity | `CourseCategoryController@activity` |
| GET|HEAD | `/api/v1/course-categories/{courseCategory}/courses/performance` | course-categories.courses.performance | `CourseCategoryController@coursesPerformance` |
| GET|HEAD | `/api/v1/course-categories/{courseCategory}/courses/performance/total` | course-categories.courses.performance.total | `CourseCategoryController@coursesPerformanceTotal` |
| GET|HEAD | `/api/v1/course-categories/{course_category}` | course-categories.show | `CourseCategoryController@show` |
| PUT|PATCH | `/api/v1/course-categories/{course_category}` | course-categories.update | `CourseCategoryController@update` |
| DELETE | `/api/v1/course-categories/{course_category}` | course-categories.destroy | `CourseCategoryController@destroy` |
| GET|HEAD | `/api/v1/search/course-categories` | course-categories.search | `CourseCategoryController@search` |
| GET|HEAD | `/api/v1/search/specific-course-categories` | course-categories.specific.search | `CourseCategoryController@searchCourseCategoriesWithArray` |

#### CourseCategoryCriteria (2 routes)

Common middleware: `App\Http\Middleware\Authenticate:sanctum, App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| POST | `/api/v1/course-category-criteria` | course-category-criteria.store | `CourseCategoryCriteriaController@store` |
| PUT | `/api/v1/course-category-criteria/{course_category_criteria}` | course-category-criteria.update | `CourseCategoryCriteriaController@update` |

#### CourseCompletionMaster (10 routes)

Common middleware: `App\Http\Middleware\Authenticate:sanctum, App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/v1/course-completion-master` | course-completion-master.index | `CourseCompletionMasterController@index` |
| POST | `/api/v1/course-completion-master` | course-completion-master.store | `CourseCompletionMasterController@store` |
| GET|HEAD | `/api/v1/course-completion-master/export` | course-completion-master.export | `CourseCompletionMasterController@export` |
| GET|HEAD | `/api/v1/course-completion-master/generate-certificate/{enrollment}` | course-completion-master.generate-certificate | `CourseCompletionMasterController@generateCertificate` |
| GET|HEAD | `/api/v1/course-completion-master/marksheet_calculation/{enrollment}` | course-completion-master.marksheet_calculation | `CourseCompletionMasterController@marksheetCalculation` |
| GET|HEAD | `/api/v1/course-completion-master/remove-certificate/{enrollment}` | course-completion-master.remove-certificate | `CourseCompletionMasterController@removeCertificate` |
| GET|HEAD | `/api/v1/course-completion-master/{course_completion_master}` | course-completion-master.show | `CourseCompletionMasterController@show` |
| PUT|PATCH | `/api/v1/course-completion-master/{course_completion_master}` | course-completion-master.update | `CourseCompletionMasterController@update` |
| DELETE | `/api/v1/course-completion-master/{course_completion_master}` | course-completion-master.destroy | `CourseCompletionMasterController@destroy` |
| POST | `/api/v1/course-completion-master/{enrollment}/send/email` | course-completion-master.send-email | `CourseCompletionMasterController@sendEmail` |

#### CourseCriteria (6 routes)

Common middleware: `App\Http\Middleware\Authenticate:sanctum, App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| POST | `/api/v1/bootcamp-course-criteria` | bootcamp-course-criteria.store | `BootcampCourseCriteriaController@store` |
| PUT|PATCH | `/api/v1/bootcamp-course-criteria/{bootcamp_course_criterion}` | bootcamp-course-criteria.update | `BootcampCourseCriteriaController@update` |
| DELETE | `/api/v1/bootcamp-course-criteria/{bootcamp_course_criterion}` | bootcamp-course-criteria.destroy | `BootcampCourseCriteriaController@destroy` |
| POST | `/api/v1/course-criteria` | course-criteria.store | `CourseCriteriaController@store` |
| PUT|PATCH | `/api/v1/course-criteria/{course_criterion}` | course-criteria.update | `CourseCriteriaController@update` |
| DELETE | `/api/v1/course-criteria/{course_criterion}` | course-criteria.destroy | `CourseCriteriaController@destroy` |

#### CourseFaq (6 routes)

Common middleware: `App\Http\Middleware\Authenticate:sanctum, App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/v1/course-faqs` | course-faqs.index | `CourseFaqController@index` |
| POST | `/api/v1/course-faqs` | course-faqs.store | `CourseFaqController@store` |
| GET|HEAD | `/api/v1/course-faqs/{course_faq}` | course-faqs.show | `CourseFaqController@show` |
| PUT|PATCH | `/api/v1/course-faqs/{course_faq}` | course-faqs.update | `CourseFaqController@update` |
| DELETE | `/api/v1/course-faqs/{course_faq}` | course-faqs.destroy | `CourseFaqController@destroy` |
| GET|HEAD | `/api/v1/search/faqs/with-specific-course` | course-faqs.with-specific-course.search | `CourseFaqController@searchSpecificCourseFaqs` |

#### CoursePlanType (5 routes)

Common middleware: `App\Http\Middleware\Authenticate:sanctum, App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/v1/course-plan-types` | course-plan-types.index | `CoursePlanTypeController@index` |
| POST | `/api/v1/course-plan-types` | course-plan-types.store | `CoursePlanTypeController@store` |
| GET|HEAD | `/api/v1/course-plan-types/{course_plan_type}` | course-plan-types.show | `CoursePlanTypeController@show` |
| PUT|PATCH | `/api/v1/course-plan-types/{course_plan_type}` | course-plan-types.update | `CoursePlanTypeController@update` |
| DELETE | `/api/v1/course-plan-types/{course_plan_type}` | course-plan-types.destroy | `CoursePlanTypeController@destroy` |

#### EmailTemplate (4 routes)

Common middleware: `App\Http\Middleware\Authenticate:sanctum, App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/v1/email-templates` | email-templates.index | `EmailTemplateController@index` |
| POST | `/api/v1/email-templates` | email-templates.store | `EmailTemplateController@store` |
| GET|HEAD | `/api/v1/email-templates/show` | email-templates.show | `EmailTemplateController@show` |
| PUT|PATCH | `/api/v1/email-templates/{email_template}` | email-templates.update | `EmailTemplateController@update` |

#### Enrollment (61 routes)

Common middleware: `App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| POST | `/api/student/v1/student-my-courses/pause-bundle` | student.enrollments.pause-bundle | `EnrollmentController@pauseBundleEnrollmentStudent` |
| GET|HEAD | `/api/student/v1/student-my-courses/pause-log/{enrollment}` | student.enrollments.pause-log | `EnrollmentController@studentPauseLog` |
| GET|HEAD | `/api/student/v1/student-my-courses/pause-status/{enrollment}` | student.enrollments.pause-eligibility | `EnrollmentController@pauseEligibility` |
| POST | `/api/student/v1/student-my-courses/pause/{enrollment}` | student.enrollments.pause | `EnrollmentController@pauseSingleEnrollmentStudent` |
| POST | `/api/student/v1/student-my-courses/refund-eligible-pause/{enrollment}` | student.enrollments.refund-eligible-pause | `EnrollmentController@refundEligiblePauseRequestStudent` |
| POST | `/api/student/v1/student-my-courses/resume/{enrollment}` | student.enrollments.resume-request | `EnrollmentController@resumeRequestStudent` |
| POST | `/api/v1/bootcamp-course-enrollment` | lawsikho.bootcamp_course_enrollment | `EnrollmentController@store_from_lawsikho` |
| POST | `/api/v1/bootcamp-course-enrollment-from-revenue` | lawsikho.bootcamp_course_enrollment | `EnrollmentController@store_from_revenue` |
| GET|HEAD | `/api/v1/check-refund-eligible/{enrollment}` | enrollments.check-refund-eligible | `EnrollmentController@checkRefundEligibleInBootcampAndPackage` |
| GET|HEAD | `/api/v1/compare-batch` |  | `EnrollmentController@compareBatch` |
| GET|HEAD | `/api/v1/edmingle-tutors` |  | `EnrollmentController@getTutors` |
| GET|HEAD | `/api/v1/enrollment-csv-report` | enrollment-csv-report | `EnrollmentCSVReportController@enrollment_csv_report` |
| POST | `/api/v1/enrollment-csv-report` | enrollment-csv-report | `EnrollmentCSVReportController@enrollment_csv_store` |
| GET|HEAD | `/api/v1/enrollment-csv-report-export/{enrollment_csv_report}` | enrollment-csv-report-export | `EnrollmentCSVReportController@enrollment_csv_report_export` |
| GET|HEAD | `/api/v1/enrollments` | enrollments.index | `EnrollmentController@index` |
| POST | `/api/v1/enrollments` | enrollments.store | `EnrollmentController@store` |
| POST | `/api/v1/enrollments/add/batch` | enrollments.add.batch | `EnrollmentController@addBatch` |
| GET|HEAD | `/api/v1/enrollments/batch-tracker` | enrollments.batch-tracker | `EnrollmentController@batchTracker` |
| GET|HEAD | `/api/v1/enrollments/books/export/csv` | enrollments.books.export.csv | `EnrollmentController@exportBooksList` |
| POST | `/api/v1/enrollments/bootcamp` | enrollments.bootcamp.store | `EnrollmentController@storeBootcampEnrollment` |
| POST | `/api/v1/enrollments/bootcamp/additional` | enrollments.bootcamp.additional-course.store | `EnrollmentController@storeBootcampAdditionalEnrollment` |
| POST | `/api/v1/enrollments/bulk-additional` | enrollments.bulk.additional-course.store | `EnrollmentController@storeBulkAdditionalEnrollment` |
| PUT | `/api/v1/enrollments/certificate/status/update` | enrollments.status.update | `EnrollmentController@updateCertifiedStatus` |
| POST | `/api/v1/enrollments/certify` | enrollments.certify | `EnrollmentController@certify` |
| GET|HEAD | `/api/v1/enrollments/dashboard/list` | enrollments.dashboard.list | `EnrollmentController@enrollmentsDashboardData` |
| GET|HEAD | `/api/v1/enrollments/export/csv` | enrollment.export.csv | `EnrollmentController@export` |
| POST | `/api/v1/enrollments/import` | enrollments.import | `EnrollmentController@importFile` |
| POST | `/api/v1/enrollments/make/active` | enrollments.make.active | `EnrollmentController@activate` |
| POST | `/api/v1/enrollments/make/deactive` | enrollments.make.deactive | `EnrollmentController@deactivate` |
| POST | `/api/v1/enrollments/make/pause` | enrollments.make.pause | `EnrollmentController@pauseEnrollment` |
| POST | `/api/v1/enrollments/make/resume` | enrollments.make.resume | `EnrollmentController@resumeEnrollment` |
| POST | `/api/v1/enrollments/migrate_batch/{enrollment}` | enrollments.migrate-batch | `EnrollmentController@migrateBatch` |
| POST | `/api/v1/enrollments/migrate_bootcamp/{enrollment}` | enrollments.migrate-bootcamp | `EnrollmentController@migrateBootcamp` |
| POST | `/api/v1/enrollments/migrate_course/{enrollment}` | enrollments.migrate-course | `EnrollmentController@migrateCourse` |
| POST | `/api/v1/enrollments/package` | enrollments.package.store | `EnrollmentController@storePackageEnrollment` |
| GET|HEAD | `/api/v1/enrollments/pause-log/{enrollment}` | enrollments.pause-log | `EnrollmentController@pauseLog` |
| GET|HEAD | `/api/v1/enrollments/pause-resume/export-templates` | enrollments.pause-resume.export-templates.index | `EnrollmentController@listCsvExportTemplates` |
| POST | `/api/v1/enrollments/pause-resume/export-templates` | enrollments.pause-resume.export-templates.store | `EnrollmentController@saveCsvExportTemplate` |
| DELETE | `/api/v1/enrollments/pause-resume/export-templates/{template}` | enrollments.pause-resume.export-templates.destroy | `EnrollmentController@deleteCsvExportTemplate` |
| GET|HEAD | `/api/v1/enrollments/pause-resume/history` | enrollments.pause-resume.history | `EnrollmentController@pauseResumeHistory` |
| GET|HEAD | `/api/v1/enrollments/pause-resume/history/export` | enrollments.pause-resume.history.export | `EnrollmentController@pauseResumeHistoryCSVExport` |
| GET|HEAD | `/api/v1/enrollments/pause-status/{enrollment}` | enrollments.pause-status | `EnrollmentController@pauseStatus` |
| POST | `/api/v1/enrollments/pause/{enrollment}` | enrollments.pause | `EnrollmentController@pause` |
| POST | `/api/v1/enrollments/reject-pause/{enrollment}` | enrollments.reject-pause | `EnrollmentController@rejectPauseRequest` |
| POST | `/api/v1/enrollments/resume/{enrollment}` | enrollments.resume | `EnrollmentController@resume` |
| GET|HEAD | `/api/v1/enrollments/total` | enrollments.total | `EnrollmentController@total` |
| POST | `/api/v1/enrollments/un-certify` | enrollments.un-certify | `EnrollmentController@unCertify` |
| GET|HEAD | `/api/v1/enrollments/{enrollment_id}/activity` | enrollment.activity | `EnrollmentController@activity` |
| GET|HEAD | `/api/v1/enrollments/{enrollment}` | enrollments.show | `EnrollmentController@show` |
| PUT|PATCH | `/api/v1/enrollments/{enrollment}` | enrollments.update | `EnrollmentController@update` |
| DELETE | `/api/v1/enrollments/{enrollment}` | enrollments.destroy | `EnrollmentController@destroy` |
| PATCH | `/api/v1/enrollments/{enrollment}/refund-eligibility-foregone` | enrollments.refund-eligibility-foregone.update | `EnrollmentController@updateRefundEligibilityForegone` |
| PATCH | `/api/v1/enrollments/{enrollment}/refund-eligible/{tag}` | enrollments.refund-eligible.edit | `EnrollmentController@editRefundEligibleTag` |
| PUT | `/api/v1/enrollments/{enrollment}/update/mcq` | enrollments.update.mcq | `EnrollmentController@updateMcq` |
| POST | `/api/v1/multiple_migrate_batch` |  | `EnrollmentController@multipleMigrateBatch` |
| POST | `/api/v1/package-enrollment-lawsikho` | lawsikho.package_enrollment_lawsikho | `EnrollmentController@store_package_enrollment_from_lawsikho` |
| GET|HEAD | `/api/v1/search/bootcamp` | enrollments.getBootcamp | `EnrollmentController@search_bootcamp` |
| GET|HEAD | `/api/v1/search/enrollments` | enrollments.search | `EnrollmentController@search` |
| GET|HEAD | `/api/v1/search/specific-bootcamp` | enrollments.specific.search | `EnrollmentController@searchBootcampWithArray` |
| GET|HEAD | `/api/v1/search/specific-enrollments` | enrollments.specific.search | `EnrollmentController@searchEnrollmentsWithArray` |
| POST | `/api/v1/single-course-enrollment` | lawsikho.single_course_enrollment | `EnrollmentController@store_from_lawsikho` |

#### Evaluator (7 routes)

Common middleware: `App\Http\Middleware\Authenticate:sanctum, App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/v1/evaluator` | evaluator.index | `EvaluatorController@index` |
| POST | `/api/v1/evaluator` | evaluator.store | `EvaluatorController@store` |
| GET|HEAD | `/api/v1/evaluator/export` | evaluator.export | `EvaluatorController@export` |
| GET|HEAD | `/api/v1/evaluator/results/dashboard/list` | evaluator.results.dashboard.list | `EvaluatorController@evaluatorsResultsDashboardData` |
| GET|HEAD | `/api/v1/evaluator/{evaluator}` | evaluator.show | `EvaluatorController@show` |
| PUT|PATCH | `/api/v1/evaluator/{evaluator}` | evaluator.update | `EvaluatorController@update` |
| DELETE | `/api/v1/evaluator/{evaluator}` | evaluator.destroy | `EvaluatorController@destroy` |

#### EvaluatorCSAT (9 routes)

Common middleware: `App\Http\Middleware\Authenticate:sanctum, App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/v1/evaluator-csat` | evaluator-csat.index | `EvaluatorCSATController@index` |
| POST | `/api/v1/evaluator-csat` | evaluator-csat.store | `EvaluatorCSATController@store` |
| GET|HEAD | `/api/v1/evaluator-csat-graph-index` | evaluator-csat.graph_index | `EvaluatorCSATController@graph_index` |
| POST | `/api/v1/evaluator-csat/check-available` | evaluator-csat.check-available | `EvaluatorCSATController@checkAvailable` |
| GET|HEAD | `/api/v1/evaluator-csat/export` | evaluator-csat.export | `EvaluatorCSATController@export` |
| GET|HEAD | `/api/v1/evaluator-csat/questions` | evaluator-csat.questions | `EvaluatorCSATController@getCSATFormReason` |
| GET|HEAD | `/api/v1/evaluator-csat/{evaluator_csat}` | evaluator-csat.show | `EvaluatorCSATController@show` |
| PUT|PATCH | `/api/v1/evaluator-csat/{evaluator_csat}` | evaluator-csat.update | `EvaluatorCSATController@update` |
| DELETE | `/api/v1/evaluator-csat/{evaluator_csat}` | evaluator-csat.destroy | `EvaluatorCSATController@destroy` |

#### Forum (48 routes)

Common middleware: `App\Http\Middleware\Authenticate:student, App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/student/v1/activity` | activity | `ForumController@showActivity` |
| POST | `/api/student/v1/discussion` | discussions.store | `ForumController@storeDiscussion` |
| DELETE | `/api/student/v1/discussion/comment/{commentId}` | comment.delete | `ForumController@commentDelete` |
| GET|HEAD | `/api/student/v1/discussion/search` | discussions.search | `ForumController@discussionSearch` |
| POST | `/api/student/v1/discussion/{discussionId}/comment` | comments.store | `ForumController@commentStore` |
| POST | `/api/student/v1/discussion/{discussion_id}` | discussions.update | `ForumController@discussionUpdate` |
| GET|HEAD | `/api/student/v1/discussion/{discussion_id}/details` | forum.discussions.details.show | `ForumController@discussionDetails` |
| GET|HEAD | `/api/student/v1/draft` | drafts.index | `ForumController@draft_list` |
| POST | `/api/student/v1/draft-comment/{discussion_id}` | drafts.comments.store | `ForumController@draftCommentStore` |
| PATCH | `/api/student/v1/draft-comment/{draftId}` | drafts.comments.store | `ForumController@draftCommentUpdate` |
| POST | `/api/student/v1/draft/discussion` | forum.discussions.drafts.store | `ForumController@draftDiscussionStore` |
| GET|HEAD | `/api/student/v1/draft/{draftId}/details` | draft.details | `ForumController@draft_details` |
| DELETE | `/api/student/v1/remove-draft/{draftId}` | draft.remove | `ForumController@draft_remove` |
| POST | `/api/v1/forum/auto-complete-search` | forum.auto-complete-search | `ForumController@autoCompleteSearchDiscussions` |
| GET|HEAD | `/api/v1/forum/bread_crumbs/{category_id}` | forum.bread_crumbs | `ForumController@breadCrubms` |
| GET|HEAD | `/api/v1/forum/categories` | forum.categories.index | `ForumController@indexCategories` |
| GET|HEAD | `/api/v1/forum/categories/sub/{id}` | forum.categories.sub.index | `ForumController@showSubCategories` |
| GET|HEAD | `/api/v1/forum/categories/{id}` | forum.categories.show | `ForumController@showCategory` |
| POST | `/api/v1/forum/category_id/get-by-name` | forum.get_id_of_category_by_name | `ForumController@getIdOfCategoryByName` |
| GET|HEAD | `/api/v1/forum/child_category` | forum.child_category | `ForumController@childCategory` |
| POST | `/api/v1/forum/create-user/{username}/{pass}/{name}/{token}` | forum.createUser | `ForumController@createUser` |
| GET|HEAD | `/api/v1/forum/discussion-by-tag/{discussion_id}` | forum.discussions_by_tag | `ForumController@discussions` |
| GET|HEAD | `/api/v1/forum/discussion/{category_id}` | form.get_discussion_by_category | `ForumController@discussionByCategory` |
| POST | `/api/v1/forum/discussions` | forum.discussions.store | `ForumController@storeDiscussions` |
| POST | `/api/v1/forum/discussions/bookmark` | forum.discussions.bookmark | `ForumController@indexBookmarkDiscussions` |
| GET|HEAD | `/api/v1/forum/discussions/bookmarks/list` | forum.discussions.bookmarked.list | `ForumController@listBookmarkedDiscussions` |
| POST | `/api/v1/forum/discussions/comments` | forum.discussions.comments.store | `ForumController@storeComment` |
| POST | `/api/v1/forum/discussions/comments/delete/{comment_id}` | forum.discussions.comments.destroy | `ForumController@destroyComment` |
| POST | `/api/v1/forum/discussions/comments/drafts` | forum.discussions.comments.drafts.store | `ForumController@storeDraftComment` |
| POST | `/api/v1/forum/discussions/comments/update` | forum.discussions.comments.update | `ForumController@updateComment` |
| GET|HEAD | `/api/v1/forum/discussions/delete/{id}` | forum.discussions.update | `ForumController@destroyDiscussion` |
| GET|HEAD | `/api/v1/forum/discussions/details/{id}` | forum.discussions.details.show | `ForumController@showDiscussionDetails` |
| POST | `/api/v1/forum/discussions/drafts` | forum.discussions.drafts.store | `ForumController@storeDraftDiscussion` |
| GET|HEAD | `/api/v1/forum/discussions/featured` | forum.discussions.featured.index | `ForumController@indexFeatureDiscussions` |
| GET|HEAD | `/api/v1/forum/discussions/lists/{pageNum?}` | forum.discussions.index | `ForumController@indexDiscussions` |
| GET|HEAD | `/api/v1/forum/discussions/search` | forum.discussions.search | `ForumController@listSearchDiscussions` |
| POST | `/api/v1/forum/discussions/update` | forum.discussions.update | `ForumController@updateDiscussion` |
| GET|HEAD | `/api/v1/forum/discussions/{id}` | forum.discussions.show | `ForumController@showDiscussion` |
| GET|HEAD | `/api/v1/forum/drafts` | forum.drafts.index | `ForumController@indexDrafts` |
| GET|HEAD | `/api/v1/forum/drafts/{id}` | forum.drafts.destroy | `ForumController@removeDrafts` |
| GET|HEAD | `/api/v1/forum/get_match_tags/{discussion_id}` | forum.match_tags | `ForumController@match_tags` |
| GET|HEAD | `/api/v1/forum/get_tags_by_id/{discussion_id}` | forum.getTagById | `ForumController@getTagById` |
| GET|HEAD | `/api/v1/forum/student/id` | forum.student.id | `ForumController@showMyForumId` |
| GET|HEAD | `/api/v1/forum/tags` | forum.tags.index | `ForumController@indexTags` |
| GET|HEAD | `/api/v1/forum/tags/{id}` | forum.tags.show | `ForumController@showTag` |
| GET|HEAD | `/api/v1/forum/user-discussions` | forum.users.discussions.index | `ForumController@indexUserDiscussions` |
| GET|HEAD | `/api/v1/forum/users/me` | forum.users.me | `ForumController@showMyProfile` |
| GET|HEAD | `/api/v1/forum/users/my/activity` | forum.users.my.activity | `ForumController@showMyActivity` |

#### InternalNotes (5 routes)

Common middleware: `App\Http\Middleware\Authenticate:sanctum, App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/v1/internal_notes` | internal_notes.index | `InternalNotesController@index` |
| POST | `/api/v1/internal_notes` | internal_notes.store | `InternalNotesController@store` |
| GET|HEAD | `/api/v1/internal_notes/{internal_note}` | internal_notes.show | `InternalNotesController@show` |
| PUT|PATCH | `/api/v1/internal_notes/{internal_note}` | internal_notes.update | `InternalNotesController@update` |
| DELETE | `/api/v1/internal_notes/{internal_note}` | internal_notes.destroy | `InternalNotesController@destroy` |

#### JobRole (2 routes)

Common middleware: `App\Http\Middleware\Authenticate:sanctum, App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/v1/search/job-roles` | job-roles.search | `JobRoleController@search` |
| GET|HEAD | `/api/v1/search/specific-job-roles` | job-role.specific.search | `JobRoleController@searchJobRolesWithArray` |

#### LawSikho (27 routes)

Common middleware: `App\Http\Middleware\ForceJsonResponse, App\Http\Middleware\LogThirdPartyRequestResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| POST | `/api/v1/active-access` | active_access | `LawSikhoController@active_access` |
| POST | `/api/v1/add-student` | lawsikho.add_student | `LawSikhoController@add_student` |
| GET|HEAD | `/api/v1/all-enrollments` | lawsikho.all-enrollments | `LawSikhoController@getAllEnrollmentNames` |
| POST | `/api/v1/bootcamp_from_lawsikho` |  | `LawSikhoController@bootcamp_from_lawsikho` |
| GET|HEAD | `/api/v1/check-enrollment` | lawsikho.check-enrollment | `LawSikhoController@check_enrollment` |
| GET|HEAD | `/api/v1/check-lawsikho-student` | lawsikho.check-lawsikho-student | `LawSikhoController@showEnrollmentNames` |
| GET|HEAD | `/api/v1/check-lms` | lawsikho.check_lms | `LawSikhoController@check_lms` |
| GET|HEAD | `/api/v1/check-student` | lawsikho.check_student | `LawSikhoController@check_student` |
| GET|HEAD | `/api/v1/course-category` | lawsikho.course_category | `LawSikhoController@course_category` |
| GET|HEAD | `/api/v1/course_batch` | lawsikho.course_batch | `LawSikhoController@course_batches` |
| GET|HEAD | `/api/v1/course_batches` | lawsikho.course_batches | `LawSikhoController@course_batches` |
| POST | `/api/v1/course_update` | lawsikho.update_course | `LawSikhoController@update_course` |
| GET|HEAD | `/api/v1/generate-enrollment-code` | lawsikho.generate_enrollment_code | `LawSikhoController@generate_enrollment_code` |
| GET|HEAD | `/api/v1/get-student-address` | lawsikho.get_student_address | `LawSikhoController@get_student_address` |
| GET|HEAD | `/api/v1/lawsikho/student-details/{id}` | student.Details | `LawSikhoController@studentDetails` |
| GET|HEAD | `/api/v1/lms` | lawsikho.students.lms.show | `LawSikhoController@getStudentLmsId` |
| PATCH | `/api/v1/lms` | lawsikho.students.lms.update | `LawSikhoController@updateStudentLmsId` |
| POST | `/api/v1/revoke-access` | revoke_access | `LawSikhoController@revoke_access` |
| POST | `/api/v1/store-cv` | lawsikho.store_cv | `LawSikhoController@store_cv` |
| POST | `/api/v1/store-enrollment-form` | lawsikho.store_enrollment_form | `LawSikhoController@store_enrollment_form` |
| POST | `/api/v1/store-enrollment-form-v2` | lawsikho.store_enrollment_form_v2 | `LawSikhoController@store_enrollment_form_v2` |
| POST | `/api/v1/store-id-proof` | lawsikho.store_id_proof | `LawSikhoController@store_id_proof` |
| POST | `/api/v1/store-photo` | lawsikho.store_photo | `LawSikhoController@store_photo` |
| GET|HEAD | `/api/v1/student-enrollment-check` | lawsikho.check_if_student_filled_enrollment_form | `LawSikhoController@check_if_student_filled_enrollment_form` |
| POST | `/api/v1/update-lms` | lawsikho.update_lms | `LawSikhoController@update_lms` |
| POST | `/api/v1/update-student-address` | lawsikho.update_student_address | `LawSikhoController@update_student_address` |
| GET|HEAD | `/api/v1/written-assignment-course` | lawsikho.written_assignment_course | `LawSikhoController@written_assignment_course` |

#### NPS (30 routes)

Common middleware: `App\Http\Middleware\Authenticate:sanctum, App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/v1/graph-index` | nps.graph_index | `NPSController@graph_index1` |
| GET|HEAD | `/api/v1/nps` | nps.index1 | `NPSController@index1` |
| GET|HEAD | `/api/v1/nps-charts/{value}` | nps.reports | `NPSController@npsReports` |
| GET|HEAD | `/api/v1/nps-filter-options` | nps.options | `NPSController@searchNPSReasons` |
| GET|HEAD | `/api/v1/nps-filter-search` | search.options | `NPSController@searchOptions` |
| GET|HEAD | `/api/v1/nps/bootcamps` | nps.bootcamps | `NPSController@npsBootcampData` |
| GET|HEAD | `/api/v1/nps/courses` | nps.courses | `NPSController@npsCoureseData` |
| GET|HEAD | `/api/v1/nps/dashboard` | nps.dashboard | `NPSController@graph_index` |
| GET|HEAD | `/api/v1/nps/exports` | nps.exports | `NPSController@export` |
| GET|HEAD | `/api/v1/nps/library` | nps.packages | `NPSController@npsPackageData` |
| GET|HEAD | `/api/v1/nps/method-calls` | nps.method-calls | `NPSController@npsMethodCalls` |
| GET|HEAD | `/api/v1/nps/reasons` | nps.reasons | `NPSController@getNPSFormReason` |
| GET|HEAD | `/api/v1/nps/survey-data/{id}` | nps.survey-data | `NPSController@getSurveyData` |
| GET|HEAD | `/api/v1/search/nps-type-filter` | nps.type.filter | `NPSController@npsTypeFilter` |
| GET|HEAD | `/api/v1/search/specific-nps-reason` | course.specific.nps-search | `NPSController@searchNPSReasonsWithArray` |
| GET|HEAD | `/api/v1/search/specific-nps-type-filter` | search.nps.type.filter | `NPSController@searchnpsTypeFilter` |
| GET|HEAD | `/api/v2/graph-index` | nps.graph_index | `NPSController@graph_index` |
| GET|HEAD | `/api/v2/nps` | nps.index | `NPSController@index` |
| POST | `/api/v2/nps` | nps.store | `NPSController@store` |
| GET|HEAD | `/api/v2/nps-filter-options` | nps.options | `NPSController@searchNPSReasons` |
| GET|HEAD | `/api/v2/nps-filter-search` | search.options | `NPSController@searchOptions` |
| GET|HEAD | `/api/v2/nps/exports` | nps.exports | `NPSController@export` |
| GET|HEAD | `/api/v2/nps/reasons` | nps.reasons | `NPSController@getNPSFormReason` |
| GET|HEAD | `/api/v2/nps/survey-data/{id}` | nps.survey-data | `NPSController@getSurveyData` |
| GET|HEAD | `/api/v2/nps/{np}` | nps.show | `NPSController@show` |
| PUT|PATCH | `/api/v2/nps/{np}` | nps.update | `NPSController@update` |
| DELETE | `/api/v2/nps/{np}` | nps.destroy | `NPSController@destroy` |
| GET|HEAD | `/api/v2/search/nps-type-filter` | nps.type.filter | `NPSController@npsTypeFilter` |
| GET|HEAD | `/api/v2/search/specific-nps-reason` | course.specific.nps-search | `NPSController@searchNPSReasonsWithArray` |
| GET|HEAD | `/api/v2/search/specific-nps-type-filter` | search.nps.type.filter | `NPSController@searchnpsTypeFilter` |

#### Notification (19 routes)

Common middleware: `App\Http\Middleware\Authenticate:sanctum, App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| POST | `/api/v1/create-notification-for-all` | notification.create_notification_for_all | `NotificationController@create_notification_for_all` |
| POST | `/api/v1/create-notification-for-specific-range` | notification.create_notification_for_specific_range | `NotificationController@create_notification_for_specific_range` |
| DELETE | `/api/v1/delete-comment` | notification-comments.delete | `NotificationController@delete_comment` |
| GET|HEAD | `/api/v1/notification` | notification.index | `NotificationController@index` |
| POST | `/api/v1/notification` | notification.store | `NotificationController@store` |
| PUT | `/api/v1/notification-edit/{notification}` | notification.update | `NotificationController@update` |
| PUT | `/api/v1/notification-status/{notification_id}` | notification.change.status | `NotificationController@changeNotificationStatus` |
| GET|HEAD | `/api/v1/notification/comments/{notification_id}` | notification.comments.get | `NotificationController@comments_get` |
| POST | `/api/v1/notification/comments/{notification_id}` | notification.comments.post | `NotificationController@comments_post` |
| GET|HEAD | `/api/v1/notification/students` | notification.students | `NotificationController@students` |
| GET|HEAD | `/api/v1/notification/tags` | notification.tags | `NotificationController@tags` |
| GET|HEAD | `/api/v1/notification/{id}` | notification.show | `NotificationController@show` |
| PUT | `/api/v1/notification/{id}` | notification.update | `NotificationController@update` |
| GET|HEAD | `/api/v1/notification/{notification}` | notification.show | `NotificationController@show` |
| PUT|PATCH | `/api/v1/notification/{notification}` | notification.update | `NotificationController@update` |
| DELETE | `/api/v1/notification/{notification}` | notification.destroy | `NotificationController@destroy` |
| GET|HEAD | `/api/v1/search/category` | notification.search.category | `NotificationController@search_category` |
| GET|HEAD | `/api/v1/search/specific-categories` | notification.specific.search-category | `NotificationController@searchCategoriesWithArray` |
| POST | `/api/v1/text_editor/image_upload` | text_editor.image_upload | `NotificationController@image_upload` |

#### Other (3 routes)

Common middleware: `(varies per route — see individual entries if needed)`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/oauth2/{integration}/authorise` | oauth2.authorise | `AuthorisationController@create` |
| GET|HEAD | `/oauth2/{integration}/authorize` | oauth2.authorize | `AuthorisationController@create` |
| GET|HEAD | `/oauth2/{integration}/callback` | oauth2.callback | `AuthorisationController@store` |

#### Package (11 routes)

Common middleware: `App\Http\Middleware\Authenticate:sanctum, App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/v1/export/package` |  | `PackageController@export` |
| GET|HEAD | `/api/v1/get-packages` | dashboard-management.packages | `PackageController@search` |
| GET|HEAD | `/api/v1/packages` | packages.index | `PackageController@index` |
| POST | `/api/v1/packages` | packages.store | `PackageController@store` |
| GET|HEAD | `/api/v1/packages/{package_id}/activity` | packages.activity | `PackageController@activity` |
| GET|HEAD | `/api/v1/packages/{package}` | packages.show | `PackageController@show` |
| PUT|PATCH | `/api/v1/packages/{package}` | packages.update | `PackageController@update` |
| DELETE | `/api/v1/packages/{package}` | packages.destroy | `PackageController@destroy` |
| GET|HEAD | `/api/v1/search/packages` | packages.search | `PackageController@search` |
| GET|HEAD | `/api/v1/search/packages-with-courses` | packages.with-courses.search | `PackageController@searchPackagesWithCourses` |
| GET|HEAD | `/api/v1/search/specific-packages` | packages.specific.search | `PackageController@searchPackagesWithArray` |

#### PerformanceCoach (25 routes)

Common middleware: `App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/student/v1/date-range-slots` |  | `PerformanceCoachController@getSlotsAndRanges` |
| PATCH | `/api/v1/book-slot/{pc_call_schedule_id}` |  | `PerformanceCoachCallScheduleController@updateBookSlot` |
| GET|HEAD | `/api/v1/call-analytics` | performance-coaching.call-analytics | `PerformanceCoachCallScheduleController@callAnalytics` |
| GET|HEAD | `/api/v1/call-history/{student}/{callType}` |  | `PerformanceCoachCallScheduleController@studentCallHistory` |
| POST | `/api/v1/check-conflict-schedule` |  | `PerformanceCoachCallScheduleController@checkConflictSchedule` |
| GET|HEAD | `/api/v1/date-range-slots/{startDate?}/{endDate?}` |  | `PerformanceCoachController@getSlotsAndRanges` |
| PATCH | `/api/v1/mark-availablity/{slot}` |  | `PerformanceCoachCallScheduleController@markAvailable` |
| POST | `/api/v1/mark-unavailablity` |  | `PerformanceCoachCallScheduleController@markUnavailable` |
| POST | `/api/v1/pc-allocate` | performance_coach.pc_allocate | `PerformanceCoachController@pcAllocate` |
| GET|HEAD | `/api/v1/pc-allocation` | performance-coach.allocation | `PerformanceCoachStudentsController@index` |
| GET|HEAD | `/api/v1/pc-allocation/coach-select` | performance_coach.coach_list | `PerformanceCoachController@coach_list` |
| GET|HEAD | `/api/v1/pc-dashboard/allocation` | pc_dashboard_allocation | `PerformanceCoachController@pcDashboardAllocation` |
| GET|HEAD | `/api/v1/pc-dashboard/callSchedule/{callType}` | pc_dashboard_call_schedule | `PerformanceCoachController@pc_dashboard_call_schedule` |
| GET|HEAD | `/api/v1/pc-details/{user}/allocation` | pc-details.user.allocation | `PerformanceCoachStudentsController@show` |
| GET|HEAD | `/api/v1/pc-details/{user}/callSchedule` | pc-details.user.callSchedule | `PerformanceCoachCallScheduleController@show` |
| GET|HEAD | `/api/v1/pc-master` | performance_coach.coach_list_details | `PerformanceCoachController@coach_list_details` |
| GET|HEAD | `/api/v1/pc-master/export` | performance-coach.export | `PerformanceCoachController@export` |
| GET|HEAD | `/api/v1/pc/export/active-allocation` |  | `PerformanceCoachStudentsController@export` |
| GET|HEAD | `/api/v1/performance-coach/slots/booked/dates` | performance-coach.slots.booked.dates | `PerformanceCoachController@bookedSlotsDates` |
| PATCH | `/api/v1/performance-coaching/update/status/{student}` | admin.performance-coaching.update.status | `PerformanceCoachStudentsController@performanceCoachingUpdateStatus` |
| GET|HEAD | `/api/v1/schedule-slots-date` |  | `PerformanceCoachCallScheduleController@scheduleSlotsDates` |
| GET|HEAD | `/api/v1/search/pc-allocation/coach-select/with-array-of-id` |  | `PerformanceCoachController@coach_list_with_array_of_id` |
| GET|HEAD | `/api/v1/slots/{date}` |  | `PerformanceCoachController@slotsIndex` |
| PATCH | `/api/v1/update-call-link/{callId}` |  | `PerformanceCoachController@updateCallLink` |
| PATCH | `/api/v1/update-call/{callId}` |  | `PerformanceCoachController@updateCall` |

#### PerformanceCoachCSAT (9 routes)

Common middleware: `App\Http\Middleware\Authenticate:sanctum, App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/v1/pc-csat` | pc-csat.index | `PerformanceCoachCSATController@index` |
| POST | `/api/v1/pc-csat` | pc-csat.store | `PerformanceCoachCSATController@store` |
| GET|HEAD | `/api/v1/pc-csat-graph-index` | pc-csat.graph_index | `PerformanceCoachCSATController@graph_index` |
| POST | `/api/v1/pc-csat/check-available` | pc-csat.check-available | `PerformanceCoachCSATController@checkAvailable` |
| GET|HEAD | `/api/v1/pc-csat/export` | pc-csat.export | `PerformanceCoachCSATController@export` |
| GET|HEAD | `/api/v1/pc-csat/questions` | pc-csat.questions | `PerformanceCoachCSATController@getCSATFormReason` |
| GET|HEAD | `/api/v1/pc-csat/{pc_csat}` | pc-csat.show | `PerformanceCoachCSATController@show` |
| PUT|PATCH | `/api/v1/pc-csat/{pc_csat}` | pc-csat.update | `PerformanceCoachCSATController@update` |
| DELETE | `/api/v1/pc-csat/{pc_csat}` | pc-csat.destroy | `PerformanceCoachCSATController@destroy` |

#### Permission (3 routes)

Common middleware: `App\Http\Middleware\Authenticate:sanctum, App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/v1/permissions` | permissions.index | `PermissionsController@index` |
| GET|HEAD | `/api/v1/permissions-for-role-creation` | permissions.list-for-role-creation | `PermissionsController@listForRoleCreation` |
| GET|HEAD | `/api/v1/permissions/users/{user?}` | permissions.user.index | `PermissionsController@userPermissions` |

#### ProjectManagement (27 routes)

Common middleware: `App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/v1/projects` | projects.index | `ProjectManagementController@index` |
| POST | `/api/v1/projects` | projects.store | `ProjectManagementController@store` |
| POST | `/api/v1/projects/check-name-duplicacy` | projects.check-name-duplicacy | `ProjectManagementController@checkProjectNameDuplecacy` |
| POST | `/api/v1/projects/course-completion-master/{enrollment}/tasks` | projects.course-completion-master.tasks.store | `ProjectTaskController@storeCourseCompletionTask` |
| GET|HEAD | `/api/v1/projects/tasks/files/{fileId}` | projects.tasks.files.download | `ProjectTaskController@downloadTaskFiles` |
| DELETE | `/api/v1/projects/tasks/{id}/files/{fileId}` | projects.tasks.files.destroy | `ProjectTaskController@deleteTaskFile` |
| GET|HEAD | `/api/v1/projects/{project}` | projects.show | `ProjectManagementController@show` |
| PUT|PATCH | `/api/v1/projects/{project}` | projects.update | `ProjectManagementController@update` |
| DELETE | `/api/v1/projects/{project}` | projects.destroy | `ProjectManagementController@destroy` |
| GET|HEAD | `/api/v1/projects/{project}/categories` | projects.categories.index | `ProjectManagementController@categoriesIndex` |
| GET|HEAD | `/api/v1/projects/{project}/columns` | projects.columns.index | `ProjectColumnsController@index` |
| POST | `/api/v1/projects/{project}/columns` | projects.columns.store | `ProjectColumnsController@store` |
| PUT | `/api/v1/projects/{project}/columns/{id}` | projects.columns.update | `ProjectColumnsController@update` |
| DELETE | `/api/v1/projects/{project}/columns/{id}` | projects.columns.destroy | `ProjectColumnsController@destroy` |
| PUT | `/api/v1/projects/{project}/columns/{id}/change-position` | projects.columns.changePosition | `ProjectColumnsController@changePosition` |
| GET|HEAD | `/api/v1/projects/{project}/group/students` | projects.group.students.index | `ProjectManagementController@groupStudentsIndex` |
| GET|HEAD | `/api/v1/projects/{project}/search_categories_array` | projects.categories.array | `ProjectManagementController@categoriesArray` |
| GET|HEAD | `/api/v1/projects/{project}/search_columns_array` | projects.columns.array | `ProjectColumnsController@columnsArray` |
| GET|HEAD | `/api/v1/projects/{project}/search_students_array` | projects.group.students.array | `ProjectManagementController@studentsArray` |
| GET|HEAD | `/api/v1/projects/{project}/tasks` | projects.tasks.index | `ProjectTaskController@index` |
| POST | `/api/v1/projects/{project}/tasks` | projects.tasks.store | `ProjectTaskController@store` |
| GET|HEAD | `/api/v1/projects/{project}/tasks/{id}` | projects.tasks.show | `ProjectTaskController@show` |
| POST | `/api/v1/projects/{project}/tasks/{id}` | projects.tasks.update | `ProjectTaskController@update` |
| POST | `/api/v1/projects/{project}/tasks/{id}/change-column` | projects.tasks.change-column | `ProjectTaskController@changeTaskColumn` |
| GET|HEAD | `/api/v1/projects/{project}/tasks/{id}/comments` | projects.tasks.comments.index | `ProjectTaskController@indexComment` |
| POST | `/api/v1/projects/{project}/tasks/{id}/comments` | projects.tasks.comments.store | `ProjectTaskController@storeComment` |
| POST | `/api/v1/projects/{project}/tasks/{id}/files` | projects.tasks.files.store | `ProjectTaskController@storeTaskFile` |

#### ReferralSystem (6 routes)

Common middleware: `App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/student/v1/referral-system/courseInfo` | student.courseInfo | `ReferralSystemController@courseInfo` |
| GET|HEAD | `/api/student/v1/referral-system/courseSpecific` | student.courseSpecific | `ReferralSystemController@courseSpecific` |
| GET|HEAD | `/api/student/v1/referral-system/generalCode` | student.generalCode | `ReferralSystemController@generalCode` |
| POST | `/api/student/v1/referral-system/mailSend` | student.SendMail | `ReferralSystemController@studentMailSend` |
| GET|HEAD | `/api/student/v1/referral-system/studentEarningDetail` | student.studentEarningDetail | `ReferralSystemController@studentEarningDetail` |
| GET|HEAD | `/api/v1/referral-system/students` | student.referral | `ReferralSystemController@referralSystem` |

#### Result (16 routes)

Common middleware: `(varies per route — see individual entries if needed)`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/v1/results` | results.index | `ResultController@index` |
| POST | `/api/v1/results` | results.store | `ResultController@store` |
| GET|HEAD | `/api/v1/results/add-featured-assignment/{result}` | results.add-featured-assignment | `ResultController@addToFeatureList` |
| POST | `/api/v1/results/assign-evaluator-round-robin` | results.assign-evaluator-round-robin | `ResultController@assignEvaluatorRoundRobin` |
| POST | `/api/v1/results/assign-evaluator-single/{result_id}` | results.assign-evaluator-single | `ResultController@assignEvaluatorSingle` |
| GET|HEAD | `/api/v1/results/download/zip` | results.download.zip | `ResultController@download` |
| GET|HEAD | `/api/v1/results/export/csv` | results.export.csv | `ResultController@export` |
| GET|HEAD | `/api/v1/results/file/download/{result}` | results.file.download | `ResultController@downloadFile` |
| GET|HEAD | `/api/v1/results/get-all-evaluator-details/{course}` | results.get-all-evaluator-details | `ResultController@getAllEvaluatorDetails` |
| GET|HEAD | `/api/v1/results/get-evaluator-pending-details/{evaluator_id}` | results.get-evaluator-pending-details | `ResultController@getEvaluatorPendingDetails` |
| GET|HEAD | `/api/v1/results/remove-featured-assignment/{result}` | results.remove-featured-assignment | `ResultController@removeFromFeatureList` |
| GET|HEAD | `/api/v1/results/send-email/{result}` | results.send-email | `ResultController@sendMail` |
| GET|HEAD | `/api/v1/results/{result}` | results.show | `ResultController@show` |
| PUT|PATCH | `/api/v1/results/{result}` | results.update | `ResultController@update` |
| DELETE | `/api/v1/results/{result}` | results.destroy | `ResultController@destroy` |
| GET|HEAD | `/api/v1/results/{result}/activity` | results.activity | `ResultController@activity` |

#### RevenueAPI (2 routes)

Common middleware: `App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/v1/get-student-details` |  | `RevenueAPIController@get_student_details` |
| POST | `/api/v1/installment-payment` |  | `RevenueAPIController@handleInstallmentPayment` |

#### Role (10 routes)

Common middleware: `App\Http\Middleware\Authenticate:sanctum, App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/v1/roles` | roles.index | `RolesController@index` |
| POST | `/api/v1/roles` | roles.store | `RolesController@store` |
| POST | `/api/v1/roles/export` | roles.export | `RolesController@export` |
| POST | `/api/v1/roles/status/change` | roles.status.change | `RolesController@changeStatus` |
| POST | `/api/v1/roles/transfer-to-other` | roles.transfer-to-other | `RolesController@transferToOther` |
| GET|HEAD | `/api/v1/roles/{role_id}/activity` | roles.activity | `RolesController@activity` |
| GET|HEAD | `/api/v1/roles/{role}` | roles.show | `RolesController@show` |
| PUT|PATCH | `/api/v1/roles/{role}` | roles.update | `RolesController@update` |
| DELETE | `/api/v1/roles/{role}` | roles.destroy | `RolesController@destroy` |
| GET|HEAD | `/api/v1/search/specific-roles` | roles.specific.search | `RolesController@searchRolesWithArray` |

#### State (6 routes)

Common middleware: `App\Http\Middleware\Authenticate:sanctum, App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/v1/search/states` | states.search | `StateController@search` |
| GET|HEAD | `/api/v1/states` | states.index | `StateController@index` |
| POST | `/api/v1/states` | states.store | `StateController@store` |
| GET|HEAD | `/api/v1/states/{state}` | states.show | `StateController@show` |
| PUT|PATCH | `/api/v1/states/{state}` | states.update | `StateController@update` |
| DELETE | `/api/v1/states/{state}` | states.destroy | `StateController@destroy` |

#### Student (32 routes)

Common middleware: `App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| POST | `/api/student/v1/edmingle/sso-validation` | students.login-from-edmingle.sso-validation | `StudentController@edmingleSsoValidation` |
| POST | `/api/student/v1/sso-validation` | students.login-from-admin.sso-validation | `StudentController@ssoValidation` |
| GET|HEAD | `/api/v1/lawsikho/students-listing` | students.Listing | `StudentController@activeStudents` |
| GET|HEAD | `/api/v1/search/city` | students.city | `StudentController@searchCity` |
| GET|HEAD | `/api/v1/search/custom/students` | students.custom.search | `StudentController@searchCustom` |
| GET|HEAD | `/api/v1/search/specific-students` | students..specific.search | `StudentController@searchStudentsWithArray` |
| GET|HEAD | `/api/v1/search/students` | students.search | `StudentController@search` |
| GET|HEAD | `/api/v1/students` | students.index | `StudentController@index` |
| POST | `/api/v1/students` | students.store | `StudentController@store` |
| POST | `/api/v1/students/activate` | students.active | `StudentController@activeStudent` |
| GET|HEAD | `/api/v1/students/bootcamp/{bootcamp}/enrollments/{student}` | students.bootcamp.enrollments | `StudentController@showBootcampEnrollments` |
| POST | `/api/v1/students/count` | students.count | `StudentController@getStudentCounts` |
| GET|HEAD | `/api/v1/students/dashboard/list` | students.dashboard.list | `StudentController@studentsDashboardData` |
| POST | `/api/v1/students/deactivate` | students.deactive | `StudentController@deactivateStudent` |
| GET|HEAD | `/api/v1/students/enrollment-form-data/{student}` | students.enrollment-form-data | `StudentController@showEnrollmentFormData` |
| GET|HEAD | `/api/v1/students/enrollments/{enrollment}/assignments` | students.enrollments.assignments | `StudentController@showStudentEnrollmentAssignments` |
| GET|HEAD | `/api/v1/students/enrollments/{student}` | students.enrollments | `StudentController@showEnrollments` |
| POST | `/api/v1/students/export` | students.export | `StudentController@export` |
| POST | `/api/v1/students/export-with-enrollment-form` | students.export-with-enrollment-form | `StudentController@exportWithEnrollmentForm` |
| POST | `/api/v1/students/get-reg-code` | students.get-reg-code | `StudentController@getRegCode` |
| POST | `/api/v1/students/international/books/export` | students.international.books.export | `StudentController@exportBooksForInternationalStudents` |
| GET|HEAD | `/api/v1/students/login-from-admin/{student}` | students.login-from-admin | `StudentController@loginAsStudent` |
| GET|HEAD | `/api/v1/students/package/{package}/enrollments/{student}` | students.package.enrollments | `StudentController@showPackageEnrollments` |
| GET|HEAD | `/api/v1/students/profile/{student}` | students.profile.show | `StudentController@showProfile` |
| POST | `/api/v1/students/search/index` | students.filters.index | `StudentController@index` |
| GET|HEAD | `/api/v1/students/{student_id}/activity` | students.activity | `StudentController@activity` |
| GET|HEAD | `/api/v1/students/{student}` | students.show | `StudentController@show` |
| PUT|PATCH | `/api/v1/students/{student}` | students.update | `StudentController@update` |
| DELETE | `/api/v1/students/{student}` | students.destroy | `StudentController@destroy` |
| GET|HEAD | `/api/v1/students/{student}/availability` | students.availability | `StudentController@getStudentAvailability` |
| GET|HEAD | `/api/v1/students/{student}/bootcamps` | students.bootcamps | `StudentController@bootcamps` |
| PUT | `/api/v1/students/{student}/email/update` | students.email.update | `StudentController@updateEmail` |

#### StudentAssignment (20 routes)

Common middleware: `App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| POST | `/api/student/v1/student-assignments/{student_assignment}/send-link-email` | student-assignments.send-link-email | `StudentAssignmentController@sendLinkEmail` |
| POST | `/api/v1/request-large-csv-set` | bypass.large.csv.set | `StudentAssignmentController@bypass_large_csv_set` |
| GET|HEAD | `/api/v1/student-assignment/meta-data` | student-assignments.medatData | `StudentAssignmentController@getMetaData` |
| GET|HEAD | `/api/v1/student-assignments` | student-assignments.index | `StudentAssignmentController@index` |
| POST | `/api/v1/student-assignments` | student-assignments.store | `StudentAssignmentController@store` |
| POST | `/api/v1/student-assignments/assign-by-filters` | student-assignments.assign-by-filters | `StudentAssignmentController@assignByFilters` |
| GET|HEAD | `/api/v1/student-assignments/dashboard/list` | student-assignments.dashboard.list | `StudentAssignmentController@studentAssignmentsDashboardData` |
| DELETE | `/api/v1/student-assignments/delete-multiple` | student-assignments.delete-multiple | `StudentAssignmentController@destroyMultiple` |
| GET|HEAD | `/api/v1/student-assignments/export/csv` | student-assignments.export.csv | `StudentAssignmentController@export` |
| GET|HEAD | `/api/v1/student-assignments/get-resubmit-data/{student_assignment_id}/{student_id}` | student-assignments.resubmit-data | `StudentAssignmentController@getStudentAssignmentResubmissionList` |
| POST | `/api/v1/student-assignments/import` | student-assignments.import | `StudentAssignmentController@import` |
| PUT | `/api/v1/student-assignments/update-multiple` | student-assignments.update-multiple | `StudentAssignmentController@updateMultiple` |
| PUT | `/api/v1/student-assignments/update-multiple-ai-data` | student-assignments.update-multiple-ai-data | `StudentAssignmentController@bulkEvaluateEdit` |
| GET|HEAD | `/api/v1/student-assignments/validate-enrollments` | student-assignments.validate-enrollments | `StudentAssignmentController@validateEnrollments` |
| GET|HEAD | `/api/v1/student-assignments/{student_assignment_id}/activity` | student_assignment.activity | `StudentAssignmentController@activity` |
| GET|HEAD | `/api/v1/student-assignments/{student_assignment}` | student-assignments.show | `StudentAssignmentController@show` |
| PUT|PATCH | `/api/v1/student-assignments/{student_assignment}` | student-assignments.update | `StudentAssignmentController@update` |
| DELETE | `/api/v1/student-assignments/{student_assignment}` | student-assignments.destroy | `StudentAssignmentController@destroy` |
| POST | `/api/v1/student-assignments/{student_assignment}/re-submit` | student-assignments.re-submit | `StudentAssignmentController@re_submit` |
| POST | `/api/v1/student-assignments/{student_assignment}/submit` | student-assignments.submit | `StudentAssignmentController@submit` |

#### StudentAuth (13 routes)

Common middleware: `App\Http\Middleware\ForceJsonResponse, App\Http\Middleware\StudentActivity`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| POST | `/api/student/v1/change-password` | student.change-password | `NewPasswordController@change_password` |
| POST | `/api/student/v1/forgot-password/create-password` | student.forget-password.create-password | `PasswordResetController@createPassword` |
| POST | `/api/student/v1/forgot-password/email-verification` | student.forget-password.email.verification | `PasswordResetController@emailVerification` |
| POST | `/api/student/v1/forgot-password/otp-verification` | student.forget-password.otp.verification | `PasswordResetController@otpVerification` |
| GET|HEAD | `/api/student/v1/lms` | student.lms | `StudentAuthController@lms` |
| POST | `/api/student/v1/login/email-verification` | student.login.email.verification | `StudentAuthController@emailVerification` |
| POST | `/api/student/v1/login/password-verification` | student.login.password.verification | `StudentAuthController@passwordVerification` |
| GET|HEAD | `/api/student/v1/student/is-email-verified` | student.is-email-verified | `StudentAuthController@checkifEmailVerified` |
| POST | `/api/student/v1/student/logout` | student.logout | `StudentAuthController@destroy` |
| POST | `/api/student/v1/student/resend-otp` | student.resend-otp | `StudentAuthController@resendOtp` |
| POST | `/api/student/v1/student/send-otp` | student.send-otp | `StudentAuthController@sendOtp` |
| POST | `/api/student/v1/student/update-password` | student.update-password | `NewPasswordController@update_password` |
| POST | `/api/student/v1/student/verify-otp` | student.verify-otp | `StudentAuthController@verifyOtp` |

#### StudentBookACall (70 routes)

Common middleware: `(varies per route — see individual entries if needed)`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| POST | `/api/check-email` |  | `EventController@checkStudentEmail` |
| GET|HEAD | `/api/feedback-from-email/{studentEmail}` | feedback.from.email | `StudentMeetingController@feedBackFromEmail` |
| GET|HEAD | `/api/get-bookACall-roles` |  | `EventController@getBookACallRole` |
| GET|HEAD | `/api/get-bookACall-user-role/{meetingId}` |  | `EventController@getBookACallUserRole` |
| GET|HEAD | `/api/member-list` |  | `InstructorController@memberList` |
| GET|HEAD | `/api/remove-meetingId/{meetingId}` |  | `StudentMeetingController@removeMeetingId` |
| POST | `/api/student/v1/booking/create` |  | `MeetingBookingController@createBooking` |
| PUT | `/api/student/v1/booking/edit/{bookingId}` |  | `MeetingBookingController@editBooking` |
| GET|HEAD | `/api/student/v1/booking/reschedule/{id}` |  | `MeetingBookingController@rescheduleShow` |
| POST | `/api/student/v1/booking/{bookingId}/cancel` |  | `MeetingBookingController@cancelBooking` |
| GET|HEAD | `/api/student/v1/courses/instructor/{courseId}` |  | `BookACallCourseController@getInstructorsOfCourse` |
| GET|HEAD | `/api/student/v1/event/{eventId}` |  | `EventController@getEventUser` |
| GET|HEAD | `/api/student/v1/events/{userId}` |  | `EventController@index` |
| GET|HEAD | `/api/student/v1/get-teamMember/{teamId}` |  | `TeamController@getTeamMember` |
| POST | `/api/student/v1/mark-as-complete/{bookingId}` |  | `StudentMeetingController@markAsComplete` |
| PUT | `/api/student/v1/meeting/add-rating/{meeting_id}` |  | `StudentMeetingController@addMeetingRating` |
| GET|HEAD | `/api/student/v1/no-show-history/{meetingId}` |  | `StudentMeetingController@getNoShowHistory` |
| DELETE | `/api/student/v1/no-show-student-delete/{bookingId}` |  | `StudentMeetingController@noShowStudentDelete` |
| POST | `/api/student/v1/no-show-student/{bookingId}` |  | `StudentMeetingController@noShowStudent` |
| GET|HEAD | `/api/student/v1/reschedule-history/{meetingId}` |  | `StudentMeetingController@getRescheduleHistory` |
| GET|HEAD | `/api/student/v1/slots` |  | `StudentMeetingController@getSlots` |
| GET|HEAD | `/api/student/v1/student-dashboard-meetings` |  | `StudentMeetingController@studentDashboardMeetings` |
| GET|HEAD | `/api/student/v1/student-meetings` |  | `StudentMeetingController@studentMeetings` |
| GET|HEAD | `/api/student/v1/student/courses` |  | `BookACallCourseController@getCoursesForStudent` |
| GET|HEAD | `/api/student/v1/student/packages/name` |  | `BookACallCourseController@getPackageNameForStudent` |
| POST | `/api/student/v1/student/review` |  | `StudentMeetingController@storeStudentReview` |
| POST | `/api/student/v1/team-booking` |  | `TeamController@createTeamBooking` |
| GET|HEAD | `/api/student/v1/team-event/{teamId}` |  | `EventController@teamEvents` |
| GET|HEAD | `/api/student/v1/team-slots` |  | `StudentMeetingController@getTeamSlots` |
| POST | `/api/student/v1/team/reschedule` |  | `MeetingBookingController@teamReschedule` |
| GET|HEAD | `/api/student/v1/teams` |  | `TeamController@index` |
| GET|HEAD | `/api/student/v1/timezones` |  | `MeetingBookingController@timezones` |
| POST | `/api/update-recording-url` |  | `MeetingBookingController@updateRecordingUrl` |
| POST | `/api/users/has-event-update` |  | `EventController@updateHasEvent` |
| GET|HEAD | `/api/v1/admin/events/{userId}` |  | `EventController@adminIndex` |
| GET|HEAD | `/api/v1/booking-calls/default-team` |  | `TeamController@getDefaultTeam` |
| PUT | `/api/v1/booking/edit/{bookingId}` |  | `MeetingBookingController@editBookingInstructor` |
| GET|HEAD | `/api/v1/booking/reschedule/{id}` |  | `MeetingBookingController@rescheduleShow` |
| POST | `/api/v1/booking/{bookingId}/cancel` |  | `MeetingBookingController@cancelBooking` |
| POST | `/api/v1/default-team` |  | `TeamController@storeDefaultTeam` |
| GET|HEAD | `/api/v1/defaultTeamById` |  | `TeamController@getDefaultTeamById` |
| POST | `/api/v1/delete-default-team` |  | `TeamController@deleteDefaultTeam` |
| DELETE | `/api/v1/event/delete/{eventId}` |  | `EventController@deleteEvent` |
| GET|HEAD | `/api/v1/events/{userId}` |  | `EventController@index` |
| GET|HEAD | `/api/v1/export/meetings/{userId}` |  | `MeetingBookingController@export` |
| GET|HEAD | `/api/v1/get-token` |  | `TeamController@getToken` |
| POST | `/api/v1/import-csv` | users.importCsv | `BookACAllUtilityController@importUserCsv` |
| POST | `/api/v1/instructor/review/{instructorId}` |  | `InstructorController@storeInstructorReview` |
| GET|HEAD | `/api/v1/instructors` |  | `InstructorController@index` |
| GET|HEAD | `/api/v1/instructors/export` |  | `InstructorController@export` |
| GET|HEAD | `/api/v1/login-bookcall/{user}` |  | `EventController@loginToBookACall` |
| GET|HEAD | `/api/v1/meetings/{userId}` |  | `MeetingBookingController@myMeetings` |
| GET|HEAD | `/api/v1/member-list` |  | `InstructorController@memberList` |
| GET|HEAD | `/api/v1/my-team` |  | `TeamController@myTeam` |
| GET|HEAD | `/api/v1/new-teams` |  | `TeamController@newTeamindex` |
| GET|HEAD | `/api/v1/personal-meetings` |  | `MeetingBookingController@personalMeetings` |
| GET|HEAD | `/api/v1/personal-meetings/slots` |  | `MeetingBookingController@personalMeetingsSlots` |
| GET|HEAD | `/api/v1/resend/register/email/{userId}` |  | `InstructorController@resendRegisterEmail` |
| POST | `/api/v1/resend/register/email/{userId}` |  | `InstructorController@resendRegisterEmail` |
| GET|HEAD | `/api/v1/slots` |  | `StudentMeetingController@getSlots` |
| POST | `/api/v1/team-event` |  | `EventController@createTeamEvent` |
| GET|HEAD | `/api/v1/team-event/{teamId}` |  | `EventController@teamEvents` |
| GET|HEAD | `/api/v1/team-filter` |  | `TeamController@teamFilterList` |
| POST | `/api/v1/team-members` |  | `TeamController@AddTeamMember` |
| GET|HEAD | `/api/v1/team-slots` |  | `StudentMeetingController@getTeamSlots` |
| GET|HEAD | `/api/v1/team/instructors` |  | `InstructorController@TeamIndex` |
| POST | `/api/v1/team/reschedule` |  | `MeetingBookingController@teamReschedule` |
| GET|HEAD | `/api/v1/teams` |  | `TeamController@index` |
| PUT | `/api/v1/teams/{id}` |  | `TeamController@update` |
| GET|HEAD | `/api/v1/timeZone` |  | `EventController@getTimeZone` |

#### StudentClasses (12 routes)

Common middleware: `App\Http\Middleware\Authenticate:student, App\Http\Middleware\ForceJsonResponse, App\Http\Middleware\StudentActivity`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/student/v1/class` | student.class.index | `StudentClassesController@index` |
| GET|HEAD | `/api/student/v1/class/schedule-date` | student.class.show | `StudentClassesController@scheduleDate` |
| GET|HEAD | `/api/student/v1/class/{classOccurranceDate}/details` | student.class.show | `StudentClassesController@show` |
| GET|HEAD | `/api/student/v1/student-classes` | student-classes.index | `StudentClassesController@index` |
| POST | `/api/student/v1/student-classes` | student-classes.store | `StudentClassesController@store` |
| GET|HEAD | `/api/student/v1/student-classes/get-all-classes-by-course/{course_id}` | student-classes.get-all-classes-by-course | `StudentClassesController@getAllClassByCourse` |
| GET|HEAD | `/api/student/v1/student-classes/get-all-classes-by-date/{date}` | student-classes.get-all-classes-by-date | `StudentClassesController@getAllClassByDate` |
| GET|HEAD | `/api/student/v1/student-classes/getAllClass/{param}/{date?}` | student-classes.getAllClass | `StudentClassesController@getAllClass` |
| GET|HEAD | `/api/student/v1/student-classes/getClassDetails/{param}` | student-classes.getClassDetails | `StudentClassesController@getClassDetails` |
| GET|HEAD | `/api/student/v1/student-classes/{student_class}` | student-classes.show | `StudentClassesController@show` |
| PUT|PATCH | `/api/student/v1/student-classes/{student_class}` | student-classes.update | `StudentClassesController@update` |
| DELETE | `/api/student/v1/student-classes/{student_class}` | student-classes.destroy | `StudentClassesController@destroy` |

#### StudentDashboard (34 routes)

Common middleware: `App\Http\Middleware\Authenticate:student, App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/student/v1/internal-get-curl` | Internal.get.curl | `StudentLmsController@InternalCurlGetRequest` |
| POST | `/api/student/v1/internal-post-curl` | Internal.post.curl | `StudentLmsController@InternalCurlPostRequest` |
| GET|HEAD | `/api/student/v1/join-class` | join.class | `StudentLmsController@joinClass` |
| POST | `/api/student/v1/read-announcement` | announcement | `StudentLmsController@readAnnouncement` |
| GET|HEAD | `/api/student/v1/student-classes/get-courses` | student-classes.get-courses | `StudentDashboardController@coursesForClass` |
| PATCH | `/api/student/v1/student-dashboard/add-rating/{stepId}` | student-dashboard.add-rating | `StudentDashboardController@addRating` |
| PATCH | `/api/student/v1/student-dashboard/add-update-feedback/{stepId}` | student-dashboard.update-feedback | `StudentDashboardController@addUpdateFeedback` |
| GET|HEAD | `/api/student/v1/student-dashboard/announcements` | studentAnnouncements | `StudentLmsController@getStudentAnnouncements` |
| GET|HEAD | `/api/student/v1/student-dashboard/calendar` | studentCalendar | `StudentLmsController@getStudentCalendar` |
| GET|HEAD | `/api/student/v1/student-dashboard/class-updates` | classUpdate | `StudentLmsController@getClassUpdate` |
| PATCH | `/api/student/v1/student-dashboard/delete-feedback/{stepId}` | student-dashboard.delete-feedback | `StudentDashboardController@deleteFeedback` |
| GET|HEAD | `/api/student/v1/student-dashboard/get-opportunities` | student-dashboard.get-opportunities | `StudentDashboardController@getOpportunities` |
| PATCH | `/api/student/v1/student-dashboard/mark-completed/{stepId}` | student-dashboard.mark-completed | `StudentDashboardController@markCompleted` |
| PATCH | `/api/student/v1/student-dashboard/mark-unCompleted/{stepId}` | student-dashboard.mark-unCompleted | `StudentDashboardController@markUnCompleted` |
| POST | `/api/student/v1/student-dashboard/read-annouscement` | updateStatus | `StudentLmsController@readStudentAnnouscement` |
| GET|HEAD | `/api/student/v1/student-dashboard/student-enrollments` | student-dashboard.student-enrollments | `StudentDashboardController@studentEnrollments` |
| GET|HEAD | `/api/student/v1/student-dashboard/student-joureny-steps` | student-dashboard.student-joureny-stpes | `StudentDashboardController@studentJourneyStpes` |
| GET|HEAD | `/api/student/v1/student-dashboard/today-classes` | todayClass | `StudentLmsController@getTodayClass` |
| GET|HEAD | `/api/student/v1/student-dashboard/unread-count` | getCount | `StudentLmsController@getUnreadCount` |
| POST | `/api/v1/add-nps` | storeNPS | `StudentDashboardController@storeNPS` |
| GET|HEAD | `/api/v1/check-enrollment/{enrollment}` | check_enrollment | `StudentDashboardController@check_enrollment` |
| GET|HEAD | `/api/v1/student-dashboard` | student-dashboard.index | `StudentDashboardController@index` |
| POST | `/api/v1/student-dashboard` | student-dashboard.store | `StudentDashboardController@store` |
| GET|HEAD | `/api/v1/student-dashboard/get-courses-for-assignment-submission` | student-dashboard.get-courses-for-assignment-submission | `StudentDashboardController@coursesForAssignmentSubmission` |
| GET|HEAD | `/api/v1/student-dashboard/get-courses-list-for-dropdown` | student-dashboard.get-courses-list-for-dropdown | `StudentDashboardController@getCoursesListForDropdown` |
| GET|HEAD | `/api/v1/student-dashboard/get-latest-class/dashboard` | student-dashboard.get-latest-class.dashboard | `StudentDashboardController@getLatestThreeClass` |
| GET|HEAD | `/api/v1/student-dashboard/get-latest-pending-assignments` | student-dashboard.get-latest-pending-assignments | `StudentDashboardController@getLatestFivePendingAssignment` |
| GET|HEAD | `/api/v1/student-dashboard/get-package-name-with-course-count` | student-dashboard.get-package-name-with-course-count | `StudentDashboardController@getPackageNameWithCourseCount` |
| GET|HEAD | `/api/v1/student-dashboard/nps-survey-data/{enrollment}` | student-dashboard.nps-survey-data | `StudentDashboardController@getSurveyData` |
| GET|HEAD | `/api/v1/student-dashboard/{student_dashboard}` | student-dashboard.show | `StudentDashboardController@show` |
| PUT|PATCH | `/api/v1/student-dashboard/{student_dashboard}` | student-dashboard.update | `StudentDashboardController@update` |
| DELETE | `/api/v1/student-dashboard/{student_dashboard}` | student-dashboard.destroy | `StudentDashboardController@destroy` |
| GET|HEAD | `/api/v1/student-topperlist-dashboard` | student_topperlist.logged_in_user | `StudentDashboardController@topperlist_logged_student` |
| GET|HEAD | `/api/v1/student-topperlist-dashboard/{enrollment}` | student_topperlist | `StudentDashboardController@topperlist` |

#### StudentDashboardManagement (15 routes)

Common middleware: `App\Http\Middleware\Authenticate:sanctum, App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/v1/category-courses` | dashboard-management.courses | `StudentDashboardManagementController@getCourses` |
| GET|HEAD | `/api/v1/dashboard-management/course-categories` | dashboard-management.course-categories | `StudentDashboardManagementController@getCategoriesWithAll` |
| POST | `/api/v1/dashboard-management/delete-drafted` | dashboard-management.delete-drafted | `StudentDashboardManagementController@deleteDraftedSteps` |
| GET|HEAD | `/api/v1/dashboard-management/get-journey-details` | dashboard-management.get-journey-details | `StudentDashboardManagementController@getJourneyDetails` |
| GET|HEAD | `/api/v1/dashboard-management/get-journey-steps` | dashboard-management.get-journey-steps | `StudentDashboardManagementController@getJourneySteps` |
| GET|HEAD | `/api/v1/dashboard-management/get-parent-steps` | dashboard-management.get-parent-steps | `StudentDashboardManagementController@getParentSteps` |
| POST | `/api/v1/dashboard-management/save-journey-steps` | dashboard-management.save-journey-steps | `StudentDashboardManagementController@saveJourneySteps` |
| GET|HEAD | `/api/v1/dashboard-management/{stepId}/activity` | dashboard-management.step-activity-log | `StudentDashboardManagementController@stepActivityLog` |
| GET|HEAD | `/api/v1/get-bootcamps` | dashboard-management.bootcamps | `StudentDashboardManagementController@all_bootcamps_with_serch` |
| GET|HEAD | `/api/v1/studentdashboardmanagements` | studentdashboardmanagements.index | `StudentDashboardManagementController@index` |
| POST | `/api/v1/studentdashboardmanagements` | studentdashboardmanagements.store | `StudentDashboardManagementController@store` |
| GET|HEAD | `/api/v1/studentdashboardmanagements/export/csv` | studentdashboardmanagements.export.csv | `StudentDashboardManagementController@export` |
| GET|HEAD | `/api/v1/studentdashboardmanagements/{studentdashboardmanagement}` | studentdashboardmanagements.show | `StudentDashboardManagementController@show` |
| PUT|PATCH | `/api/v1/studentdashboardmanagements/{studentdashboardmanagement}` | studentdashboardmanagements.update | `StudentDashboardManagementController@update` |
| DELETE | `/api/v1/studentdashboardmanagements/{studentdashboardmanagement}` | studentdashboardmanagements.destroy | `StudentDashboardManagementController@destroy` |

#### StudentDegree (6 routes)

Common middleware: `App\Http\Middleware\Authenticate:sanctum, App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/v1/degrees` | degrees.index | `StudentDegreeController@index` |
| POST | `/api/v1/degrees` | degrees.store | `StudentDegreeController@store` |
| GET|HEAD | `/api/v1/degrees/{degree}` | degrees.show | `StudentDegreeController@show` |
| PUT|PATCH | `/api/v1/degrees/{degree}` | degrees.update | `StudentDegreeController@update` |
| DELETE | `/api/v1/degrees/{degree}` | degrees.destroy | `StudentDegreeController@destroy` |
| GET|HEAD | `/api/v1/search/degrees` | degrees.search | `StudentDegreeController@search` |

#### StudentForum (15 routes)

Common middleware: `App\Http\Middleware\Authenticate:student, App\Http\Middleware\ForceJsonResponse, App\Http\Middleware\StudentActivity`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/student/v1/bookmark` | student.forum.discussion.bookmarked.index | `StudentForumController@indexBookmarkedDiscussions` |
| GET|HEAD | `/api/student/v1/category-bread-crumbs` | student.forum.category.index | `StudentForumController@indexBreadCrumbs` |
| GET|HEAD | `/api/student/v1/discussion/category` | student.forum.category.index | `StudentForumController@indexCategory` |
| GET|HEAD | `/api/student/v1/discussion/feature-discussion` | student.forum.discussion.feature.index | `StudentForumController@indexFeatureDiscussion` |
| GET|HEAD | `/api/student/v1/discussion/my-discussion` | student.forum.my.discussion.index | `StudentForumController@indexStudentDiscussion` |
| GET|HEAD | `/api/student/v1/discussion/tags` | student.forum.discussion.tags.index | `StudentForumController@indexDiscussionsTags` |
| GET|HEAD | `/api/student/v1/discussion/users` | student.forum.discussion.users.index | `StudentForumController@discussionUsers` |
| PATCH | `/api/student/v1/discussion/{discussionId}` | student.forum.discussion.update | `StudentForumController@updateDiscussion` |
| PATCH | `/api/student/v1/discussion/{discussionId}/bookmark` | student.forum.discussion.bookmark.store | `StudentForumController@storeDiscussionBookmark` |
| PATCH | `/api/student/v1/discussion/{discussionId}/comment/{commentId}` | student.forum.discussion.comment.update | `StudentForumController@updateDiscussionComment` |
| DELETE | `/api/student/v1/discussion/{discussionId}/remove-discussion` | student.forum.discussion.destroy | `StudentForumController@removeDiscussion` |
| GET|HEAD | `/api/student/v1/discussions` | student.forum.discussion.index | `StudentForumController@indexDiscussion` |
| POST | `/api/student/v1/draft-discussion` | student.forum.discussion.draft.store | `StudentForumController@storeDraftDiscussion` |
| PATCH | `/api/student/v1/draft-discussion/{draftId}` | student.forum.discussion.draft.update | `StudentForumController@updateDraftDiscussion` |
| GET|HEAD | `/api/student/v1/recursive-category` | student.forum.discussion.category.recursive.index | `StudentForumController@recursiveCategory` |

#### StudentFrontendEnrollment (70 routes)

Common middleware: `App\Http\Middleware\ForceJsonResponse, App\Http\Middleware\StudentActivity`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| POST | `/api/student/v1/assignment-csat/{student_assignment}/submit` | student.assignment-csat.submit | `AssignmentCSATController@submit` |
| GET|HEAD | `/api/student/v1/bootcamp` | student.enrollment.bootcamp.name | `StudentFrontendEnrollmentController@enrollmentBootcampNames` |
| GET|HEAD | `/api/student/v1/bootcamp/{id}/enrollments` | student.bootcamp.enrollments | `StudentFrontendEnrollmentController@bootcampEnrollments` |
| GET|HEAD | `/api/student/v1/call-csat/{pc_call_schedule_id}` | student.pc-csat.questions | `PerformanceCoachCSATController@performanceCoachCSATFormReason` |
| POST | `/api/student/v1/call-csat/{pc_call_schedule_id}/submit` | student.pc-csat.submit | `PerformanceCoachCSATController@submit` |
| GET|HEAD | `/api/student/v1/check-eligibility-class-csat/{class_occurance_date_id}` |  | `ClassCSATController@check_eligibilty` |
| GET|HEAD | `/api/student/v1/class-csat/{classCode}` | student.class-csat.questions | `ClassCSATController@classCSATFormReason` |
| POST | `/api/student/v1/class-csat/{classCode}/submit` | student.class-csat.submit | `ClassCSATController@submit` |
| GET|HEAD | `/api/student/v1/course-faqs-student/{course_id}` | course_faqs | `StudentFrontendEnrollmentController@course_faqs` |
| GET|HEAD | `/api/student/v1/email-verify-status` | student.email-verify-status | `StudentFrontendEnrollmentController@getIfEmailVerified` |
| GET|HEAD | `/api/student/v1/enrollment-form-status` | student.enrollment.status | `StudentFrontendEnrollmentController@getStudentEnrollmentStatus` |
| POST | `/api/student/v1/enrollment/{enrollment}/request-for-certificate` | student.enrollment.request.certificate | `StudentFrontendEnrollmentController@enrollmentRequestForCertificate` |
| POST | `/api/student/v1/enrollment/{enrollment}/send-certificate` | student.enrollment.send.certificate | `StudentFrontendEnrollmentController@sendCertificate` |
| GET|HEAD | `/api/student/v1/enrollments/{enrollment}/calendy` | student.getcalendyData | `StudentFrontendEnrollmentController@getcalendyData` |
| GET|HEAD | `/api/student/v1/enrollments/{enrollment}/faq` | enrollment_faqs | `StudentFrontendEnrollmentController@enrollment_faqs` |
| GET|HEAD | `/api/student/v1/enrollments/{enrollment}/progress-status` | student.progress-status | `StudentFrontendEnrollmentController@progress_status` |
| GET|HEAD | `/api/student/v1/enrollments/{enrollment}/results` | enrollment_result | `StudentFrontendEnrollmentController@enrollment_result` |
| GET|HEAD | `/api/student/v1/enrollments/{enrollment}/task` | student.enrollment.tasks.index | `StudentFrontendEnrollmentController@enrollmentTasks` |
| GET|HEAD | `/api/student/v1/enrollments/{enrollment}/toppers` | toppers_list | `StudentFrontendEnrollmentController@toppers_list` |
| GET|HEAD | `/api/student/v1/evaluation-csat/{result}` | student.evaluation-csat.questions | `EvaluatorCSATController@evaluatorCSATFormReason` |
| POST | `/api/student/v1/evaluation-csat/{result}/submit` | student.evaluation-csat.submit | `EvaluatorCSATController@submit` |
| GET|HEAD | `/api/student/v1/filter/package` | student.package.filter | `FiltersController@package` |
| GET|HEAD | `/api/student/v1/filter/project/{course}` |  | `TaskController@getProjectByCourse` |
| GET|HEAD | `/api/student/v1/notification` | student.notification.index | `NotificationController@index` |
| POST | `/api/student/v1/notification/all/read` | student.notification.read.all | `NotificationController@readAll` |
| GET|HEAD | `/api/student/v1/notification/bell` | student.notification.bell | `NotificationController@bell` |
| POST | `/api/student/v1/notification/{notificationUser}/comment` | student.notification.comment.store | `NotificationController@storeComment` |
| GET|HEAD | `/api/student/v1/notification/{notificationUser}/details` | student.notification.show | `NotificationController@show` |
| GET|HEAD | `/api/student/v1/nps/{enrollment}` | student.nps.show | `NPSController@show` |
| POST | `/api/student/v1/nps/{enrollment}/submit` | student.nps.submit | `NPSController@submit` |
| GET|HEAD | `/api/student/v1/package` | student.enrollment.package.name | `StudentFrontendEnrollmentController@enrollmentPackageNames` |
| GET|HEAD | `/api/student/v1/package/{package}/enrollments` | student.package.enrollments | `StudentFrontendEnrollmentController@packageEnrollments` |
| GET|HEAD | `/api/student/v1/result-listing/{enrollment}` | result_listing | `StudentFrontendEnrollmentController@result_listing` |
| GET|HEAD | `/api/student/v1/set-last-login-for-verify-later` | student.set-last-login-for-verify-later | `StudentFrontendEnrollmentController@setLastLogingForVerifyLater` |
| GET|HEAD | `/api/student/v1/student-support` | student.support.index | `StudentSupportController@index` |
| POST | `/api/student/v1/student-support` | student.support.store | `StudentSupportController@store` |
| GET|HEAD | `/api/student/v1/student-support/admin-reply-attachment/{ticketId}/thread/{threadId}/attachments/{attachmentId}/download` | student.support.attachment.download | `StudentSupportController@downloadAdminsideAttachment` |
| GET|HEAD | `/api/student/v1/student-support/ticket-counts` |  | `StudentSupportController@getTicketCounts` |
| GET|HEAD | `/api/student/v1/student-support/{ticketId}` | student.support.show | `StudentSupportController@show` |
| GET|HEAD | `/api/student/v1/student-support/{ticketId}/attachments/{attachmentId}/download` | student.support.attachment.download | `StudentSupportController@download` |
| PATCH | `/api/student/v1/student-support/{ticketId}/close` | student.support.close | `StudentSupportController@close` |
| GET|HEAD | `/api/student/v1/student-support/{ticketId}/conversations` | student.support.conversations | `StudentSupportController@conversations` |
| PATCH | `/api/student/v1/student-support/{ticketId}/reopen` | student.support.reopen | `StudentSupportController@reopen` |
| POST | `/api/student/v1/student-support/{ticketId}/reply` | student.support.reply | `StudentSupportController@reply` |
| GET|HEAD | `/api/student/v1/student-support/{ticketId}/thread/{threadId}` |  | `StudentSupportController@getFullThreadContent` |
| POST | `/api/student/v1/student/campaign_stat` | students.campaign_stat | `StudentFrontendEnrollmentController@updateCampaignStat` |
| GET|HEAD | `/api/student/v1/student/class-csat-questions/{parent_id}` | class-csat.questions | `ClassCSATController@questions` |
| GET|HEAD | `/api/student/v1/student/getStudentCourseBatch` | student.getStudentCourseBatch | `StudentFrontendEnrollmentController@getStudentCourseBatch` |
| GET|HEAD | `/api/student/v1/student/getcalendy/{course}` | student.getcalendy | `StudentFrontendEnrollmentController@getcalendy` |
| GET|HEAD | `/api/student/v1/student/notification` | notification.index | `NotificationController@index` |
| GET|HEAD | `/api/student/v1/student/notification/latest_five` | notification.latest_five | `NotificationController@latest_five` |
| GET|HEAD | `/api/student/v1/student/nps-questions` | nps.questions | `NPSController@getNPSReason` |
| GET|HEAD | `/api/student/v1/student/projects/{project}/tasks/{id}` | student.projects.tasks.show | `TaskController@show` |
| POST | `/api/student/v1/student/projects/{project}/tasks/{id}` | student.projects.tasks.attachment.update | `TaskController@update` |
| POST | `/api/student/v1/student/projects/{project}/tasks/{id}/change-column` | student.tasks.change-column | `TaskController@changeTaskColumn` |
| GET|HEAD | `/api/student/v1/student/projects/{project}/tasks/{id}/comments` | student.tasks.comments.index | `TaskController@indexComment` |
| POST | `/api/student/v1/student/projects/{project}/tasks/{id}/comments` | student.tasks.comments.store | `TaskController@storeComment` |
| POST | `/api/student/v1/student/token_save` | students.token_save | `StudentFrontendEnrollmentController@saveStudentToken` |
| GET|HEAD | `/api/student/v1/students/tasks/{course_id}/{batch_id}` | students.enrollment.tasks.index | `TaskController@index` |
| POST | `/api/student/v1/submit-assignment-csat` | assignment.submit_evaluation | `AssignmentCSATController@submit_assignment_csat` |
| POST | `/api/student/v1/submit-class-csat` | submit_evaluation | `ClassCSATController@submit_class_csat` |
| POST | `/api/student/v1/submit-evaluation` | submit_evaluation | `StudentFrontendEnrollmentController@submit_evaluation` |
| POST | `/api/student/v1/submit-nps` | nps.submit | `NPSController@submit_nps` |
| GET|HEAD | `/api/student/v1/task/{fileId}/download_attachment` | student.projects.tasks.download_attachment | `TaskController@download_attachment` |
| POST | `/api/student/v1/task/{taskId}/comment` | student.projects.tasks.show | `TaskController@add_task_comment_student` |
| GET|HEAD | `/api/student/v1/task/{taskId}/details` | student.projects.tasks.show | `TaskController@show_task` |
| POST | `/api/student/v1/task/{task}/column-change` | student.change-task-column | `TaskController@taskColumnChange` |
| GET|HEAD | `/api/student/v1/topper-list-student/{course}/{batch}` | topper_list | `StudentFrontendEnrollmentController@topper_list` |
| GET|HEAD | `/api/student/v2/nps-questions` | student.nps.show | `NPSController@checkNpsDue` |
| POST | `/api/student/v2/nps/submit` |  | `NPSController@submitNps` |

#### StudentMyCourses (28 routes)

Common middleware: `App\Http\Middleware\Authenticate:student, App\Http\Middleware\ForceJsonResponse, App\Http\Middleware\StudentActivity`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| POST | `/api/student/v1/assignment/{student_assignment}/rate-note/{topicDocDetail}` | assignment.rate-note | `StudentMyCoursesController@rate_note` |
| GET|HEAD | `/api/student/v1/enrollments` |  | `StudentMyCoursesController@allEnrollments` |
| GET|HEAD | `/api/student/v1/enrollments/course` |  | `StudentMyCoursesController@get_all_enrollments` |
| POST | `/api/student/v1/enrollments/submit-assignment/{studentAssignment}` | submit-assignment | `StudentMyCoursesController@assignmentSubmit` |
| GET|HEAD | `/api/student/v1/enrollments/{enrollment}/assignments` | enrollments.assignments.enrollment | `StudentMyCoursesController@get_assignments_related_to_enrollment` |
| GET|HEAD | `/api/student/v1/enrollments/{enrollment}/get_question` | enrollments.assignments.question | `StudentMyCoursesController@getQuestionRelatedToEnrollment` |
| GET|HEAD | `/api/student/v1/filter/course` | student.course.filter | `StudentMyCoursesController@courseListForFilter` |
| GET|HEAD | `/api/student/v1/search` | student.global.search | `StudentGlobalSearchController@__invoke` |
| GET|HEAD | `/api/student/v1/student-my-courses` | student-my-courses.index | `StudentMyCoursesController@index` |
| POST | `/api/student/v1/student-my-courses` | student-my-courses.store | `StudentMyCoursesController@store` |
| POST | `/api/student/v1/student-my-courses/add-result-video-rating` | student-my-courses.add-result-video-rating | `StudentMyCoursesController@addResultVideoRating` |
| POST | `/api/student/v1/student-my-courses/add-video-rating` | student-my-courses.add-video-rating | `StudentMyCoursesController@addVideoRating` |
| GET|HEAD | `/api/student/v1/student-my-courses/evaluator-csat/reasons/{parent_id}` | student-my-courses.evaluator-csat.reasons | `StudentMyCoursesController@getEvaluatorCSATFormReason` |
| GET|HEAD | `/api/student/v1/student-my-courses/get-all-enrollments` | student-my-courses.get-all-enrollments | `StudentMyCoursesController@getAllEnrollments` |
| GET|HEAD | `/api/student/v1/student-my-courses/get-all-package-enrollments` | student-my-courses.get-all-package-enrollments | `StudentMyCoursesController@getEnrollmentRelatedToPackage` |
| GET|HEAD | `/api/student/v1/student-my-courses/get-assignments/{enrollment}` | student-my-courses.get-assignments | `StudentMyCoursesController@getAssignmentsRelatedToEnrollment` |
| GET|HEAD | `/api/student/v1/student-my-courses/get-course-by-id/{enrollment}` | student-my-courses.get-course-by-id | `StudentMyCoursesController@getCourseById` |
| GET|HEAD | `/api/student/v1/student-my-courses/get-course-criteria/{enrollment}` | student-my-courses.get-course-criteria | `StudentMyCoursesController@getCourseCriteria` |
| GET|HEAD | `/api/student/v1/student-my-courses/get-course-name-by-id/{course}` | student-my-courses.get-course-name-by-id | `StudentMyCoursesController@getCourseNameById` |
| GET|HEAD | `/api/student/v1/student-my-courses/get-package-enrollments/{package_id}` | student-my-courses.get-package-enrollments | `StudentMyCoursesController@getPackageEnrollments` |
| GET|HEAD | `/api/student/v1/student-my-courses/get-result-preview/{assignment_id}` | student-my-courses.get-result-preview | `StudentMyCoursesController@getResultPreview` |
| GET|HEAD | `/api/student/v1/student-my-courses/reasons/{parent_id}` | student-my-courses.reasons | `StudentMyCoursesController@getCSATFormReason` |
| POST | `/api/student/v1/student-my-courses/requestForCertificate` | student-my-courses.requestForCertificate | `StudentMyCoursesController@requestForCertificate` |
| POST | `/api/student/v1/student-my-courses/submit-assignment/{studentAssignment}` | student-my-courses.submit-assignment | `StudentMyCoursesController@submitAssignment` |
| GET|HEAD | `/api/student/v1/student-my-courses/{student_my_course}` | student-my-courses.show | `StudentMyCoursesController@show` |
| PUT|PATCH | `/api/student/v1/student-my-courses/{student_my_course}` | student-my-courses.update | `StudentMyCoursesController@update` |
| DELETE | `/api/student/v1/student-my-courses/{student_my_course}` | student-my-courses.destroy | `StudentMyCoursesController@destroy` |
| POST | `/api/student/v1/students/question_answer` | students.questionanswer | `StudentMyCoursesController@storeQuestionAnswer` |

#### StudentNotifications (12 routes)

Common middleware: `App\Http\Middleware\Authenticate:student, App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/v1/bellNotification/unread` | student.getUnreadDetails | `StudentNotificationsController@getUnreadDetails` |
| GET|HEAD | `/api/v1/getALlNotificationTags` | student.getTags | `StudentNotificationsController@getTags` |
| GET|HEAD | `/api/v1/getAllNotification` | student.getAllNotification | `StudentNotificationsController@getAllNotification` |
| GET|HEAD | `/api/v1/getAllNotificationCount/unread` | student.getUnreadNotification | `StudentNotificationsController@getUnread` |
| GET|HEAD | `/api/v1/student/notifications` | notifications.index | `StudentNotificationsController@index` |
| POST | `/api/v1/student/notifications` | notifications.store | `StudentNotificationsController@store` |
| GET|HEAD | `/api/v1/student/notifications/get-all-comment/{notification_id}` | student.notifications.get-all-comment | `StudentNotificationsController@getAllComments` |
| POST | `/api/v1/student/notifications/mark-as-read` | student/notifications | `StudentNotificationsController@markAsRead` |
| POST | `/api/v1/student/notifications/store-comment` | student/notifications/store-comment | `StudentNotificationsController@storeComment` |
| GET|HEAD | `/api/v1/student/notifications/{notification}` | notifications.show | `StudentNotificationsController@show` |
| PUT|PATCH | `/api/v1/student/notifications/{notification}` | notifications.update | `StudentNotificationsController@update` |
| DELETE | `/api/v1/student/notifications/{notification}` | notifications.destroy | `StudentNotificationsController@destroy` |

#### StudentPerformanceCoach (16 routes)

Common middleware: `App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| POST | `/api/student/v1/book-slot` |  | `StudentPerformanceCoachController@bookSlot` |
| PATCH | `/api/student/v1/book-slot/{pc_call_schedule_id}` |  | `StudentPerformanceCoachController@updateBookSlot` |
| GET|HEAD | `/api/student/v1/general-range-slots` |  | `StudentPerformanceCoachController@generalRangeSlots` |
| GET|HEAD | `/api/student/v1/get-call-date` |  | `StudentPerformanceCoachController@getCallDate` |
| POST | `/api/student/v1/issue-report` |  | `StudentPerformanceCoachController@issuePerformanceCoachNotAllocated` |
| PATCH | `/api/student/v1/issue-report/{callId}` |  | `StudentPerformanceCoachController@issueReport` |
| GET|HEAD | `/api/student/v1/pc-call-schedule/{callType}` |  | `StudentPerformanceCoachController@studentCallHistory` |
| POST | `/api/student/v1/performance-coaching/update/status` |  | `StudentPerformanceCoachController@performanceCoachingUpdateStatus` |
| GET|HEAD | `/api/student/v1/schedule-log/{call_id}` |  | `StudentPerformanceCoachController@schedule_log` |
| GET|HEAD | `/api/student/v1/schedule-slots-date` |  | `StudentPerformanceCoachController@scheduleSlotsDates` |
| PATCH | `/api/student/v1/share-feedback/{callId}` |  | `StudentPerformanceCoachController@shareFeedback` |
| GET|HEAD | `/api/student/v1/slots/{date}` |  | `StudentPerformanceCoachController@slotsIndex` |
| POST | `/api/student/v1/student-availability` |  | `StudentPerformanceCoachController@studentWeekdayAvailability` |
| GET|HEAD | `/api/student/v1/timezones-for-availability` |  | `StudentPerformanceCoachController@timezonesForAvailability` |
| GET|HEAD | `/api/v1/performance-coach/slots/booked` | performance-coach.slots.booked | `StudentPerformanceCoachController@bookedSlots` |
| GET|HEAD | `/api/v1/schedule-log/{call_id}` |  | `StudentPerformanceCoachController@schedule_log` |

#### StudentProfile (18 routes)

Common middleware: `App\Http\Middleware\Authenticate:student, App\Http\Middleware\ForceJsonResponse, App\Http\Middleware\StudentActivity`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| POST | `/api/student/v1/address` | student_profile.addressSave | `StudentProfileController@addressSave` |
| GET|HEAD | `/api/student/v1/filter/country` | student_profile.get_countries | `StudentProfileController@getCountries` |
| GET|HEAD | `/api/student/v1/filter/country_code` | student_profile.get_country_code | `StudentProfileController@getCountryCode` |
| GET|HEAD | `/api/student/v1/filter/state` | student_profile.get_states | `StudentProfileController@getStates` |
| GET|HEAD | `/api/student/v1/getAllCountry` | student_profile.getAllCountry | `StudentProfileController@getAllCountry` |
| GET|HEAD | `/api/student/v1/getAllState` | student_profile.getAllState | `StudentProfileController@getAllState` |
| GET|HEAD | `/api/student/v1/getEnrollFormData` | student_profile.getEnrollFormData | `StudentProfileController@getEnrollFormData` |
| GET|HEAD | `/api/student/v1/getIfAddress` | student_profile.getIfAddress | `StudentProfileController@getIfAddress` |
| GET|HEAD | `/api/student/v1/getOriginalRegistrationDetails` | student_profile.getOriginalRegistrationDetails | `StudentProfileController@getStudentOriginalRegistrationDetails` |
| GET|HEAD | `/api/student/v1/getProfile` | student_profile.getProfile | `StudentProfileController@getProfile` |
| GET|HEAD | `/api/student/v1/getUserForEnrollApi` | student_profile.getUserForEnrollApi | `StudentProfileController@getUserForEnrollApi` |
| PATCH | `/api/student/v1/personal-information` | savePersonalInformation | `StudentProfileController@savePersonalInformation` |
| POST | `/api/student/v1/profile/cv/email` | student_profile.emailCv | `StudentProfileController@emailCv` |
| GET|HEAD | `/api/student/v1/profile/enrollment-form-details` | student_profile.enrollment_form_details | `StudentProfileController@enrollmentFormDetails` |
| POST | `/api/student/v1/profile/id-proof/email` | student_profile.emailIdProof | `StudentProfileController@emailIdProof` |
| GET|HEAD | `/api/student/v1/profile/personal-info` | student_profile.personal_info | `StudentProfileController@personal_info` |
| POST | `/api/student/v1/saveAddress` | stduent_profile.saveAddress | `StudentProfileController@saveAddress` |
| GET|HEAD | `/api/student/v1/student-profile` | student_profile.index | `StudentProfileController@index` |

#### StudentResults (4 routes)

Common middleware: `App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| POST | `/api/student/v1/result/{result}/email-feedback-file` | student.results.email.feedback_file | `StudentResultsController@emailFeedbackFile` |
| POST | `/api/student/v1/result/{result}/rate-evaluation-video` | student.results.rate.evaluation_video | `StudentResultsController@rateEvaluationVideo` |
| GET|HEAD | `/api/student/v1/student-results/index/{enrollment}` | student-results.index | `StudentResultsController@index` |
| GET|HEAD | `/api/v1/student-results/index/{enrollment}` | student-results.index | `StudentResultsController@index` |

#### StudentTasks (13 routes)

Common middleware: `App\Http\Middleware\Authenticate:student, App\Http\Middleware\ForceJsonResponse, App\Http\Middleware\StudentActivity`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/student/v1/default-course-project` | student.tasks.index | `StudentTasksController@defaultCourseProject` |
| GET|HEAD | `/api/student/v1/student/tasks` | tasks.index | `StudentTasksController@index` |
| POST | `/api/student/v1/student/tasks` | tasks.store | `StudentTasksController@store` |
| POST | `/api/student/v1/student/tasks/add-attachments/{task_id}` | student.add-attachments | `StudentTasksController@addAttachments` |
| POST | `/api/student/v1/student/tasks/add-comment` | student.add-comment | `StudentTasksController@addComment` |
| GET|HEAD | `/api/student/v1/student/tasks/get-attachments/{task_id}` | student.get-attachments | `StudentTasksController@getAllTaskFiles` |
| GET|HEAD | `/api/student/v1/student/tasks/get-comments/{task_id}` | student.get-comments | `StudentTasksController@getAllComments` |
| POST | `/api/student/v1/student/tasks/moveTaskPosition` | student.moveTaskPosition | `StudentTasksController@moveTaskPosition` |
| GET|HEAD | `/api/student/v1/student/tasks/{task}` | tasks.show | `StudentTasksController@show` |
| PUT|PATCH | `/api/student/v1/student/tasks/{task}` | tasks.update | `StudentTasksController@update` |
| DELETE | `/api/student/v1/student/tasks/{task}` | tasks.destroy | `StudentTasksController@destroy` |
| POST | `/api/student/v1/task/attachment/{task_id}` | student.add-attachments-student | `StudentTasksController@addAttachmentsStudent` |
| GET|HEAD | `/api/student/v1/task/{course}/{project}` | student.tasks.index | `StudentTasksController@index` |

#### StudentUniversity (6 routes)

Common middleware: `App\Http\Middleware\Authenticate:sanctum, App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/v1/search/universities` | universities.search | `StudentUniversityController@search` |
| GET|HEAD | `/api/v1/universities` | universities.index | `StudentUniversityController@index` |
| POST | `/api/v1/universities` | universities.store | `StudentUniversityController@store` |
| GET|HEAD | `/api/v1/universities/{university}` | universities.show | `StudentUniversityController@show` |
| PUT|PATCH | `/api/v1/universities/{university}` | universities.update | `StudentUniversityController@update` |
| DELETE | `/api/v1/universities/{university}` | universities.destroy | `StudentUniversityController@destroy` |

#### Topic (9 routes)

Common middleware: `App\Http\Middleware\Authenticate:sanctum, App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/v1/search/specific-topics` | topic.specific.search | `TopicController@searchTopicsWithArray` |
| GET|HEAD | `/api/v1/search/topics` | topics.search | `TopicController@search` |
| GET|HEAD | `/api/v1/topic-doc-details` | topic-doc-details.index | `TopicDocDetailsController@index` |
| POST | `/api/v1/topic-doc-details` | topic-doc-details.store | `TopicDocDetailsController@store` |
| GET|HEAD | `/api/v1/topic-doc-details/{topic_doc_detail}` | topic-doc-details.show | `TopicDocDetailsController@show` |
| PUT|PATCH | `/api/v1/topic-doc-details/{topic_doc_detail}` | topic-doc-details.update | `TopicDocDetailsController@update` |
| DELETE | `/api/v1/topic-doc-details/{topic_doc_detail}` | topic-doc-details.destroy | `TopicDocDetailsController@destroy` |
| GET|HEAD | `/api/v1/topics` | topics.index | `TopicController@index` |
| GET|HEAD | `/api/v1/topics/export` | topics.export | `TopicController@export` |

#### User (27 routes)

Common middleware: `App\Http\Middleware\ForceJsonResponse`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| GET|HEAD | `/api/v1/get-lms` | get-lms | `UserController@get_lms` |
| GET|HEAD | `/api/v1/search/roles` |  | `UserController@search_roles` |
| GET|HEAD | `/api/v1/search/specific-users` | users.specific.search | `UserController@searchUsersWithArray` |
| GET|HEAD | `/api/v1/search/users` | users.search | `UserController@search` |
| GET|HEAD | `/api/v1/user-profile` | user.profile | `UserController@userProfile` |
| PATCH | `/api/v1/user-profile` | user.profile-store | `UserController@storeUserProfile` |
| POST | `/api/v1/user/campaign_stat` | user.campaign_stat | `UserController@updateCampaignStat` |
| GET|HEAD | `/api/v1/user/permissions` | permissions.user.index | `UserController@permissions` |
| POST | `/api/v1/user/token_save` | user.token_save | `UserController@saveUserToken` |
| GET|HEAD | `/api/v1/users` | users.index | `UserController@index` |
| POST | `/api/v1/users` | users.store | `UserController@store` |
| GET|HEAD | `/api/v1/users/export` | users.export | `UserController@export` |
| POST | `/api/v1/users/meeting-details` | user.meeting-details | `UserController@getUserMeetingDetails` |
| POST | `/api/v1/users/meeting-id-update-from-other-app` | user.meeting-id-update-from-other-app | `UserController@meetingIdUpdateFromOtherApp` |
| POST | `/api/v1/users/meeting-status-update` | user.meeting-status-update | `UserController@meetingStatusUpdate` |
| POST | `/api/v1/users/meeting-status-update-from-other-app` | user.meeting-status-update-from-other-app | `UserController@meetingStatusUpdateFromOtherApp` |
| GET|HEAD | `/api/v1/users/notifications` | users.notifications.index | `UserController@notifications` |
| GET|HEAD | `/api/v1/users/notifications/mark/read` | users.notifications.mark-all-as-read | `UserController@markAsReadAll` |
| GET|HEAD | `/api/v1/users/notifications/un-read` | users.notifications.un-read | `UserController@undReadNotifications` |
| GET|HEAD | `/api/v1/users/notifications/{id}/mark/read` | users.notifications.mark-single-as-read | `UserController@markSingleAsRead` |
| POST | `/api/v1/users/remove-link` | user.remove-link | `UserController@removeLinkWithAlternateEmail` |
| POST | `/api/v1/users/status/change` | user.status.change | `UserController@changeStatus` |
| POST | `/api/v1/users/update/alternate-email` | user.update.alternate-email | `UserController@updateWithAlternateEmail` |
| GET|HEAD | `/api/v1/users/{user}` | users.show | `UserController@show` |
| PUT|PATCH | `/api/v1/users/{user}` | users.update | `UserController@update` |
| DELETE | `/api/v1/users/{user}` | users.destroy | `UserController@destroy` |
| GET|HEAD | `/api/v1/users/{user}/activity` | users.activity | `UserController@activity` |

#### Webhook (12 routes)

Common middleware: `(varies per route — see individual entries if needed)`

| Method | URI | Name | Controller@Action |
|---|---|---|---|
| POST | `/api/test-route` | test | `WebhookController@test` |
| POST | `/api/v1/failed-api-responses` | failed-api-responses.store | `FailedApiResponseController@store` |
| GET|HEAD | `/api/v1/webhook-events` | webhook-events.index | `EventController@index` |
| POST | `/api/v1/webhook-events` | webhook-events.store | `EventController@store` |
| GET|HEAD | `/api/v1/webhook-events/{webhook_event}` | webhook-events.show | `EventController@show` |
| PUT|PATCH | `/api/v1/webhook-events/{webhook_event}` | webhook-events.update | `EventController@update` |
| DELETE | `/api/v1/webhook-events/{webhook_event}` | webhook-events.destroy | `EventController@destroy` |
| GET|HEAD | `/api/v1/webhooks` | webhooks.index | `WebhookController@index` |
| POST | `/api/v1/webhooks` | webhooks.store | `WebhookController@store` |
| GET|HEAD | `/api/v1/webhooks/{webhook}` | webhooks.show | `WebhookController@show` |
| PUT|PATCH | `/api/v1/webhooks/{webhook}` | webhooks.update | `WebhookController@update` |
| DELETE | `/api/v1/webhooks/{webhook}` | webhooks.destroy | `WebhookController@destroy` |
## 7. Database Schema

> Verified directly against migration files on the `New-Dummy-Prod-0605` branch as of 2026-08-29 (135 `Schema::create` migrations found across root `database/migrations/` and 43 of the 62 `Modules/*/Database/Migrations/` directories; the remaining ~19 modules add columns/indexes to existing tables only, or have no migrations of their own).

### 7.1 Schema Overview by Domain

| Domain / Module | Tables |
|---|---|
| **Core (root `database/migrations`)** | `users`, `password_resets`, `personal_access_tokens`, `failed_jobs`, `job_batches`, `notifications` (Laravel's polymorphic notifications table), `media` (spatie media-library), `activity_log` (spatie activitylog), `permission_tables` (spatie/laravel-permission: `roles`, `permissions`, `model_has_roles`, etc.), `user_emails`, `week_days`, `deactivating_comments`, `edmingle_countries`, `fcm_tokens` |
| **Student** | `students`, `student_other_details`, `student_week_day_availabilities` |
| **StudentProfile** | `know_about_lawsikho_question`, `know_about_lawsikho_student_answer`, `student_original_registration_details` |
| **StudentAssignment** | `student_assignments`, `first_assignment_send_log` |
| **Assignment / AssignmentTag / AssignmentSendingLog / AssignmentCSAT** | `assignments`, `tags`, `assignment_log`, `assignment_log_mapping`, `assignment_csat_form(_reasons[_mapping])` |
| **Enrollment** | `enrollments`, `enrollment_questions`, `enrollment_question_answers`, `enrollment_csv_report`, `bulk_enrollment_reports`, `bulk_enrollment_details`, `csv_export_templates`, `enrollment_pause_log_new` |
| **Course / CourseBatch / CourseCategory / CourseCriteria / CourseCategoryCriteria / CourseFaq / CoursePlanType** | `courses`, `course_evaluator_mappings`, `course_mentor_mappings`, `course_optional_questions`, `course_optional_question_answers`, `course_batches`, `edmingle_batches`, `course_categories`, `course_category_criterias`, `course_criterias`, `course_faqs`, `course_plan_types` |
| **Package** | `packages`, `package_course_mappings` |
| **Bootcamp** | `bootcamps`, `bootcamp_books` |
| **Result** | `results`, `result_exercise_scores`, `course_featured_assignment_mapping`, `student_result_video_mapping` |
| **Evaluator / EvaluatorCSAT** | *(no own table — evaluators are `users` rows via role/permission)*; `evaluator_csat_form(_reason[_maping])` |
| **Class / ClassCSAT** | `classes`, `class_course_batch`, `class_course_mapping`, `class_expert`, `class_host`, `class_occurrance_date`, `class_package`, `class_participants`, `class_topic_and_type`, `zoom_users`, `class_csat_form`, `class_csat_form_reason`, `class_csat_form_reason_maping` |
| **Topic** | `topics`, `topic_doc_details`, `student_assignment_video_mapping` |
| **PerformanceCoach / PerformanceCoachCSAT** | `performance_coach_call_categories`, `performance_coach_call_schedules`, `performance_coach_call_schedule_slots`, `performance_coach_call_outcomes`, `performance_coach_call_suspended_categories`, `performance_coach_students`, `performance_coach_student_reports`, `performance_coach_slots`, `performance_coach_ranges`, `performance_coach_block_slots`, `performance_coach_start_and_pauses`, `performance_coach_csat_form(_reason[_mapping])` |
| **Notification** | `notification`, `notification_category`, `notification_channel`, `notification_tag(s)`, `notification_user`, `notification_comments`, `batch_notification`, `channel_notification`, `course_notification`, `package_notification` *(distinct from the root `notifications` table used by Laravel's DB notification driver)* |
| **NPS** | `nps_form` / `nps_form_v2`, `nps_form_reason`, `nps_form_reason_maping` / `_v2`, `nps_course_data`, `nps_bootcamp_data`, `nps_package_data` |
| **ProjectManagement / StudentTasks** | `projects`, `project_categories`, `project_mentors`, `projects_tasks_student_files`, `student_task_file_mapping` |
| **AIEvaluation** | `ai_models`, `ai_evaluation_audit_logs`, `ai_course_material_syncs` |
| **StudentDashboardManagement** | `student_dashboard_journey_steps`, `student_dashboard_journey_steps_mapping`, `student_dashboard_journey_journey_comments` |
| **StudentBookACall** | `course_instructor_mappings` |
| **Webhook** | `webhooks` *(created twice — 2025-01-07 and again 2025-02-19, likely a schema-rebuild; verify only one is live in prod before relying on it)*, `webhook_events`, `webhook_logs` |
| **BookMaster / BookDeliveryLog** | `books`, `course_books`, `book_delivery_log` |
| **InternalNotes** | `students_internal_notes`, `internal_notes_history` |
| **User / JobRole** | `user_details`, `user_job_role_mappings`, `job_roles` |
| **Misc single-table modules** | `tags` (AssignmentTag), `course_job_mappings` (AtsAPI), `countries` (Country), `states` (State), `third_party_logs` (LawSikho), `email_templates` (EmailTemplate) |

### 7.2 Key Tables — Column Reference

**`users`** (Admin/Staff — `App\Models\User`)
- `id`, `title`, `first_name`, `last_name`, `full_name`, `email` (unique), `calendly_link`
- `country_id` → FK `countries.id`
- `phone`, `status` (tinyint), `edmingle_id`, `kanboard_id`, `forum_text`, `forum_token_time`
- `email_verified_at`, `last_login`, `password`, `remember_token`
- `created_by` / `updated_by` → self-referencing FK `users.id`
- `timestamps`, `soft_deletes`

**`students`** (`Modules\Student\Entities\Student`)
- `id`, `reg_code` (unique), `full_name`, `email` (unique), `phone`, `date_of_birth`, `gender`
- `father_name`, `address`, `pin_code`, `city`, `state`, `country` (plain strings, not FKs)
- `cv_title`, `id_image`, `image`, `password`, `status` (indexed), `kanboard_id`, `lms_id`, `forum_id`, `forum_pass`, `forum_access_token`
- `tmp_verification_token` (unique), `tmp_verification_token_expire_at`, `verification_otp`, `enrollment_form_filled_at`
- `created_by` / `updated_by` → FK `users.id`
- `timestamps` (no soft deletes)

**`courses`**
- `id`, `status`, `course_name`, `duration_days`
- `course_category_id` → FK `course_categories.id`
- `default_evaluator_id`, `default_written_evaluator_id`, `student_coach_id`, `student_writing_coach_id`, `freelance_id`, `placement_id` → all FK `users.id`
- `course_type` (tinyint)
- `created_by` / `updated_by` → FK `users.id`
- `timestamps`, `soft_deletes`

**`course_batches`**
- `id`, `batch_date` (unique), `start_date`, `date_of_compilation`
- `added_by` / `updated_by` → FK `users.id`
- `status`, `timestamps`, `soft_deletes`
- (later migration adds Edmingle sync columns — see `2026_06_03_..._add_edmingle_sync_columns_to_course_batches_table.php`)

**`packages`**
- `id`, `name`, `duration_days`, `created_by`/`updated_by` → FK `users.id`, `timestamps`, `soft_deletes`

**`bootcamps`**
- `id`, `name`, `timestamps` (minimal — most bootcamp logic lives in `enrollments.bootcamp_id`/`bootcamp_name` as loose integer/string, not an FK)

**`enrollments`** (central transactional table)
- `id`, `enrollment_code` (unique)
- `course_id` → FK `courses.id`
- `batch_id` → FK `course_batches.id`
- `status`, `batch_assigning_eligibility`, `type`, `bootcamp_id` (int, not FK), `bootcamp_name`, `course_activated`
- `enrollment_code_created_at`, `enrollment_expire_at`
- `batch_assigned_by` → FK `users.id`
- `course_expiry_date`
- `course_plan_type_id` → FK `course_plan_types.id`
- `student_id` → FK `students.id`
- `package_id` → FK `packages.id`
- `is_certified`, `certified_by` → FK `users.id`
- `reference_package` → FK `packages.id`
- `certified_datetime`, `certificate_file`, `passing_criteria` (json), `is_passing_condition_added`, `request_for_certificate`
- `current_percent`, `subjective_passing_percent`, `written_passing_percent` (decimals)
- `completed`, `completed_at`, `mcq_completed`, `mcq_score`, `ls_order_id`
- `created_by`/`updated_by` → FK `users.id`
- `timestamps`, `soft_deletes`

**`assignments`**
- `id`, `course_id` → FK `courses.id`, `topic_id` → FK `topics.id`
- `assignment_code`, `assignment_type`, `number_of_exercises`, `assignment_download_file`
- `plagiarism`, `word_count`, `ref_assignment_no`, `status` (default `Assignment::STATUS_ACTIVE`), `is_bootcamp_written`
- `package_id` → FK `packages.id`
- `created_by`/`updated_by` → FK `users.id`
- `timestamps`

**`student_assignments`** (per-student assignment instance — the thing students actually submit against)
- `id`, `enrollment_id` → FK `enrollments.id`, `assignment_id` → FK `assignments.id`
- `submission_last_date`, `submit_counter` (default 4), `status` (indexed, default `STATUS_ACTIVE`)
- `number_of_exercises`, `mandatory` (bool, default true)
- `created_by`/`updated_by` → FK `users.id`
- `timestamps`

**`results`** (evaluation/grading record)
- `id`, `student_id` → FK `students.id`
- `assignment_id` → FK **`student_assignments.id`** (name is misleading — it references the per-student assignment, not `assignments`)
- `evaluator_id` → FK `users.id`
- `status`, `plagiarism_result`, `plagiarism_result_file`
- `submitted_date`, `submitted_file`, `feedback_file`, `feedback_file_original_name`, `feedback_link`
- `evaluation_date`, `evaluation_due_date`, `is_email_sent`, `feedback_to_student`, `is_review_done`
- `waive_marks`, `feature_assignment`, `reason`, `resubmission_feedback`, `bootcamp_id`
- `timestamps` (no soft deletes)

**`projects`**
- `id`, `name`, `status`, `course_id` → FK `courses.id`, `batch_id` → FK `course_batches.id`
- `kan_project_id`, `kan_group_id` (Kanboard integration IDs)
- `created_by`/`updated_by` → FK `users.id`, `timestamps`

**`performance_coach_call_schedules`**
- `id`, `student_id` → FK `students.id`, `performance_coach_id` → FK `users.id`
- `category_id` → FK `performance_coach_call_categories.id`
- `type`, `is_old_pc`, `status`, `due_on`, `overdue_on`, `call_initiated_on`, `call_duration`, `timestamps`

**`notifications`** (root, Laravel's native notifications table — distinct from the `Notification` module's own `notification` table)
- `id` (uuid, primary), `type`, polymorphic `notifiable_type`/`notifiable_id`, `data` (text/json), `read_at`, `timestamps`

### 7.3 Key Relationships (inferred from FKs above)

- `students` 1—N `enrollments` (`enrollments.student_id`)
- `courses` 1—N `enrollments`, and `courses` 1—N `assignments`
- `course_batches` 1—N `enrollments` (`batch_id`), and 1—N `projects`
- `packages` 1—N `enrollments` (both `package_id` and `reference_package`), 1—N `assignments`, N—N `courses` via `package_course_mappings`
- `enrollments` 1—N `student_assignments` — this is the join between a student's specific course enrollment and the assignments they must submit
- `assignments` 1—N `student_assignments`
- `student_assignments` 1—N `results` — a result belongs to one per-student assignment instance, not directly to the `assignments` catalog table
- `students` 1—N `results` (redundant with the path through `student_assignments`, but the FK exists directly on `results.student_id` too)
- `users` is the universal actor table — nearly every domain table's `created_by`/`updated_by`, and role-specific FKs (`courses.default_evaluator_id`, `performance_coach_call_schedules.performance_coach_id`, `enrollments.certified_by`) all point at `users`, confirming staff/evaluators/coaches are just `users` rows differentiated by `spatie/laravel-permission` roles, not separate tables
- `course_categories` 1—N `courses`; `course_plan_types` 1—N `enrollments`
- `topics` 1—N `assignments`

### 7.4 Anomalies Worth Flagging to the Team

- Two separate `webhooks` create-table migrations exist (`2025_01_07_172031` and `2025_02_19_164706`) — likely one superseded the other; confirm which is authoritative before writing tests against it.
- Two parallel notification systems exist: the root `notifications` table (Laravel's built-in, uuid-keyed, polymorphic) and the `Notification` module's own `notification`/`notification_user`/`notification_channel` tables. Don't conflate them when testing notification features.
- `results.assignment_id` is a foreign key to `student_assignments.id`, not `assignments.id` — the column name is misleading for anyone (or any QA script) inferring schema from names alone.
- `students.country`/`state`/`city` are free-text strings while `users.country_id` is a proper FK to `countries` — inconsistent modeling between the two user types.
## 8. Local Development Setup

**Docker (recommended — `docker-compose.yml` + `Dockerfile` at repo root):**
```bash
cp .env.example .env   # if present; otherwise configure .env manually — see §16 for the full variable list
docker compose up -d          # app (PHP-FPM), nginx (port 8000), redis
docker compose up horizon     # optional: only needed if QUEUE_CONNECTION=redis and you want async job processing
```
The app is served through nginx on **http://localhost:8000** (`docker/nginx/default.conf` proxies to the `app` container). The `app` container keeps its own `vendor/` (mounted as an anonymous volume over the host mount) so `composer install` inside the container doesn't fight the host's `vendor/`.

**Bare-metal / non-Docker:**
```bash
composer install
npm install && npm run dev     # only needed for the thin resources/ Blade assets — this is an API-first app
php artisan key:generate
php artisan migrate            # runs both database/migrations and every Modules/*/Database/Migrations
php artisan module:enable      # modules_statuses.json already lists all 62 as enabled; only needed if you disabled one
php artisan serve
```

**Local env quirks observed (as of this audit):**
- `QUEUE_CONNECTION=sync` locally — jobs run inline, not through Horizon/Redis. Don't expect async behavior when testing jobs locally unless you switch this to `redis` and run the `horizon` container/process.
- `CACHE_DRIVER=file`, `SESSION_DRIVER=file`, `BROADCAST_DRIVER=log` — none of the Redis/Pusher-backed features are live in this environment by default.
- A second MySQL connection (`DB_MYSQL_LS_*`) exists alongside the primary `DB_CONNECTION=mysql` — confirm with the team what it's used for (see §7) before assuming a single-database setup is sufficient for full integration testing.

**Testing:** `phpunit.xml` is configured; run with `php artisan test` or `vendor/bin/phpunit`. `Modules/*/Tests` holds per-module PHPUnit tests (e.g. `Modules/AtsAPI/Tests/Unit/AtsAPIControllerTest.php`).

## 9. Known Issues Found During This Audit

These were discovered while regenerating this document and are worth the team's attention — none were fixed as part of writing the docs except the first, which blocked route inspection entirely:

1. **[Fixed during this audit]** `Modules/StudentBookACall/Routes/web.php` had a dead placeholder route (`Route::get('/', 'StudentBookACallController@index')`) pointing at a controller that was never created, which made `php artisan route:list` fail with a fatal `BindingResolutionException` for the *entire application* — not just that module. It's now commented out.
2. **44 other dead scaffold routes** of the same kind exist across other modules (one per module, auto-generated by `module:make`, e.g. `GET /assignment → AssignmentController@index`) — none currently crash the app because their target controllers happen to exist, but they're unused surface area. Full list in §6.1.
3. **Hardcoded secret-shaped fallback value** in `config/services.php`: `EXTERNAL_PORTAL_UPDATE_API_KEY` has a real-looking API key as its `env()` default, committed to a tracked file. Should be rotated and removed from source.
4. **`tymon/jwt-auth` is an unused dependency.** The old documentation claimed it's used for Edmingle SSO; a full grep for `JWTAuth`/`Tymon\JWTAuth`/`JWTFactory` across application code returns nothing. Edmingle SSO actually goes through Sanctum's `student` guard (`StudentController::edmingleSsoValidation`). Confirm before ripping it out, but don't build anything new assuming JWT is active.
5. **Two `webhooks` table migrations** (`2025_01_07_172031` and `2025_02_19_164706`) — likely one superseded the other. Confirm which is authoritative before writing tests against the webhook feature.
6. **`AtsGateWay` middleware logic bug — confirmed real in code, but currently unreachable:** for any `channel` param other than `Lawsikho` or `SkillArbitrage`, it both proxies the request to an external endpoint *and* calls `$next($request)`, double-processing the request. **Correction (2026-08-29, see `documentation/API_SPECIFICATIONS.md` §7):** this middleware is registered as an alias but is never attached to any live route — `save-job-and-course-mapping` only carries `json.response`, so this code path does not run in production today. Don't build a regression test expecting to reproduce it; confirm with the team whether it was recently unwired or always dead.
7. **`StudentClasses/Routes/` contains a stray `Untitled-1.sql` file** — looks like an accidental commit, not a route file.
8. **`results.assignment_id` is a foreign key to `student_assignments.id`, not `assignments.id`** — easy to get wrong if inferring schema from column names alone (relevant if your Python QA project seeds/verifies data directly against the DB).
9. **`StudentFrontendEnrollment` module hosts controllers that look like duplicates of other modules'** (CSAT/NPS/Notification/Task/Filter functionality) — confirm with the team whether this is an intentional student-facing aggregation layer or accidental duplication before treating both as independently authoritative endpoints in test coverage.

## 10. Middleware

### Global middleware (`app/Http/Kernel.php` → `$middleware`, runs on every request)
- `TrustProxies`
- `Fruitcake\Cors\HandleCors` — CORS handling
- `PreventRequestsDuringMaintenance`
- `ValidatePostSize`
- `TrimStrings`
- `ConvertEmptyStringsToNull`
- `ForceJsonResponse` — forces `Accept: application/json` semantics globally (also separately aliased as `json.response`, see below)

### Middleware groups
- **`web`**: `EncryptCookies`, `AddQueuedCookiesToResponse`, `StartSession`, `ShareErrorsFromSession`, `VerifyCsrfToken`, `SubstituteBindings`
- **`api`**: `Laravel\Sanctum\Http\Middleware\EnsureFrontendRequestsAreStateful`, `throttle:api`, `SubstituteBindings`, `ApiPerformanceLogger` (custom — logs API request performance/timing)

### Named route middleware (aliases, `$routeMiddleware`)
| Alias | Class | Purpose |
|---|---|---|
| `auth` | `App\Http\Middleware\Authenticate` | Standard Laravel auth guard check |
| `auth.basic` | `Illuminate\Auth\Middleware\AuthenticateWithBasicAuth` | HTTP basic auth |
| `cache.headers` | `Illuminate\Http\Middleware\SetCacheHeaders` | Sets cache headers on response |
| `can` | `Illuminate\Auth\Middleware\Authorize` | Policy/gate authorization |
| `guest` | `App\Http\Middleware\RedirectIfAuthenticated` | Blocks already-authenticated users from guest-only routes |
| `password.confirm` | `Illuminate\Auth\Middleware\RequirePassword` | Requires recent password confirmation |
| `signed` | `Illuminate\Routing\Middleware\ValidateSignature` | Validates signed URLs (used on email verification link) |
| `throttle` | `Illuminate\Routing\Middleware\ThrottleRequests` | Rate limiting |
| `verified` | `App\Http\Middleware\EnsureEmailIsVerified` | Requires verified email |
| `json.response` | `App\Http\Middleware\ForceJsonResponse` | Forces JSON responses (applied per-route-group across most API modules) |
| `last.login` | `App\Http\Middleware\StudentActivity` | Tracks/updates student last-activity timestamp on request |
| `check_ip` | `App\Http\Middleware\CheckIpMiddleware` | IP allowlist/restriction check |
| `log.third.party` | `App\Http\Middleware\LogThirdPartyRequestResponse` | Logs outgoing/incoming third-party API request-response pairs |

### Module-local middleware (not registered in Kernel — applied directly in module route files via `Route::middleware(SomeMiddleware::class)`)
| Middleware | Module | Purpose |
|---|---|---|
| `StaticTokenAuth` | `AgenticSupportSystem` | Validates a static bearer token (`config('agenticsupportsystem.static_token')`) from `X-API-Token` or `Authorization` header; aborts 401/500 if missing/unconfigured |
| `ListingStaticTokenAuth` | `AgenticSupportSystem` | Same pattern as above but for a separate `listing_static_token` config value — gates a distinct listing endpoint with its own static token |
| `CheckLawSikhoApiToken` | `LawSikho` | Validates `X-Auth-Token` header against `config('lawsikho.api_token')`; simple shared-secret gate for LawSikho-side integration calls |
| `AtsGateWay` | `AtsAPI` | ⚠️ **Registered but not attached to any route** (confirmed 2026-08-29, see `documentation/API_SPECIFICATIONS.md` §7) — `AtsAPIServiceProvider` aliases it as `ats.gateway` but no `Routes/*.php` file anywhere in the app actually applies it. The class itself would route/proxy requests based on a `channel` request param (`Lawsikho` passes through; `SkillArbitrage` and any other value proxy to an external `skillarbitra-portal-api-development.lawsikho.dev` endpoint via `Http::post`), and its "else" branch has a real double-processing bug (fires the external POST *and* still calls `$next($request)`) — but since no route uses this middleware, none of that logic currently executes in production. The live `save-job-and-course-mapping` route only carries `json.response`. |

Total distinct middleware classes found: **14** app-level (`app/Http/Middleware`) + **4** module-local = 18, plus stock Laravel/Sanctum/Fruitcake middleware used directly by class reference.
## 11. Jobs & Queues

The application makes heavy use of queued jobs, primarily for two purposes: **long-running CSV export/import/download workflows** (the majority of jobs — pattern `*CSVDownload`, `*CSVExport`, `*CsvImport`) and **syncing data to/from external systems** (LMS, FCM, meeting APIs, other internal apps).

**Queue configuration (as currently set):**
- `.env`: `QUEUE_CONNECTION=sync` in this local environment — jobs run synchronously inline, not actually queued. This is almost certainly `redis` in staging/production, since `config/horizon.php` defines dedicated Redis-backed Horizon queues/connections (`redis`, `redis-long-running`, `redis-high`, `redis-medium`) — Horizon is installed and configured but only meaningful once `QUEUE_CONNECTION=redis`.
- `.env`: `REDIS_HOST`/`REDIS_PORT`/`REDIS_PASSWORD` are configured (values not shown here for security).

**Jobs by module** (128 total job classes found under `Modules/*/Jobs` and `Modules/*/Http/Jobs`; none under `app/Jobs` except one legacy event listener pairing):

| Module | Notable jobs | Purpose |
|---|---|---|
| Enrollment | `EnrollmentCsvImport`, `EnrollmentCsvDownload`, `RegularEnrollmentBookCSVDownload`, `InternationalEnrollmentBookCSVDownload`, `AutomatedEnrollmentStatusSyncJob`, `EnrollmentDeactivationJob`, `EnrollmentActivatedJob`, `HandleMissedAssignments`/`ResumeEnrollmentHandleMissedAssignments`, `CreateEdmingleBatch`/`RetryEdmingleAssignmentJob`, `CourseCalendar*BatchJob` (reschedule/cancel/create), `BatchMigrationSummaryJob`, `MultipleEnrollmentBatchMigration`, `StorePackageEnrollmentJob`, `StudentAddJob`/`StudentRemoveJob` | By far the largest job surface (37 jobs) — enrollment lifecycle (activate/pause/resume/deactivate), CSV import/export of enrollment data, and syncing enrollments/batches with Edmingle & the course calendar system |
| Student | `StudentCsvDownload`, `EnrollmentFormCSVDownload`, `SendStudentDataToExternalAPI`, `SendStudentSubscriberTokenToFCM`/`...ToScheduleApp`, `ActivateStudentEdmingleBatches`/`DeactivateStudentEdmingleBatches`, `InternationalStudentsBookCsvJob` | Student data export, pushing student data/tokens to external systems, Edmingle batch activation |
| Class | `ClassCSVDownload`/`ClassDetailsCSVDownload`, `ClassMailJob`, `SyncClassParticipants` | Class roster export and participant sync |
| Course | `SyncCourseWithCalendar`, `DeleteCourseSync`, `AssignmentLibraryCSVDownload`, `BootcampCSVDownloadStart`, `PropagateAIConfigToStudentAssignments`, `SendCourseCSVEmail` | Course/calendar sync, CSV exports, propagating AI evaluation config to assignments |
| StudentAssignment | `StudentAssignmentCsvImport`, `AssignmentCSVDownload`, `AssignAssignmentsByFiltersJob` | Bulk assignment CSV import/export and filtered bulk assignment |
| AIEvaluation | `EvaluateStudentAssignmentJob`, `BulkEvaluateStudentAssignmentsJob`, `SyncCourseMaterialToAutoEvalJob` | Dispatches assignment submissions to the external auto-evaluation API (single + bulk) |
| Result / Evaluator / EvaluatorCSAT / AssignmentCSAT / ClassCSAT / PerformanceCoachCSAT / NPS | `*CSVDownload`, `*CSVExport`, `*CSVExportStarted` | Each of these "reporting" modules follows the same CSV export pattern (start job → export job → notify-user-of-completion job) |
| StudentDashboardManagement / StudentDashboard | `UpdateStepsForOldStudents`, `UpdateSequenceId`, `StudentDashboardManagementCsvDownloadStart` | Student dashboard step/sequence maintenance |
| ProjectManagement | `StudentTaskCreationJob`, `ProjectGroupStudentMappingJob`, `SendEmailsTo{Students,Mentors}On{ProjectUpdate,TaskCreation,TaskCommentAdded}` | Kanboard-integrated project/task workflow (task creation, group mapping, notification emails) |
| StudentBookACall | `CheckStudentInSA`, `AddUserToMeetingsAPI`, `InsertBookACallUserEventJob`, `StudentFeedBackJob`, `ImportUsersFromCsv` | Meeting-booking sync with the external meetings API |
| User | `UpdateUserInOtherApp`, `SendUserDetailsToExternalApi`, `SendUserSubscriberTokenToFCM`/`...ToScheduleApp`, `UnlinkUserConnection`, `OtherAppMeetingIdUpdate`/`...StatusUpdate` | Keeps admin/staff user records in sync with "the other app" (LawSikho main platform) and FCM push tokens |
| Auth | `SyncUserWithLMS`, `LogUserActivity` | Syncs users with the LMS (Edmingle) on auth events; activity logging |
| RevenueAPI | `ProcessInstallmentPaymentJob` | Processes installment payment events coming in from the revenue platform |
| Webhook | `SendWebhookJob`, `LogFailedApiResponseJob` | Outbound webhook dispatch + failure logging |
| Package | `PackageUpdateStudent`, `PackageEnrollmentStudentAssignments`, `PackageCSVDownload` | Bundled package enrollment processing |
| AgenticSupportSystem | `AgenticBatchMigrationSyncJob` | Batch migration sync for the agentic support system integration |
| StudentAuth | `SendEmailOtpToStudent` | OTP delivery for student auth |
| PerformanceCoach | `PCAllocationJob`, `PerformanceCoachAllocationsCsvExportJob`, `PerformanceCoachCsvExportJob` | Coach-to-student allocation processing |
| BookMaster / BookDeliveryLog / Bootcamp | `BookMasterCSVDownloadStart`, `BookDeliveryLogCsvDownload`, `BootcampBookMasterCSVDownload` | Book allocation/delivery CSV exports |
| Role / Topic / CourseCategory / CourseCompletionMaster | `RolesCSVDownloadStart`, `TopicCSVDownloadStart`, `CourseCategoryCSVDownloadStart`, `CourseCompletionMaster*` | Standard CSV export jobs per admin entity |
| Notification | `CreateNotificationForAll`, `CreateNotificationForSpecificStudents`, `CreateNotificationForAllForClass`, `CreateNotificationComment`/`...CommentStudent` | Fan-out notification creation |
| CourseBatch | `SyncEnrollmentWithCourseCalendarJob`, `CourseCalendarBulkBatchRescheduleJob`, `BatchCSVDownload` | Batch/calendar sync |

## 12. Events & Listeners

Event/listener usage is minimal compared to the job-heavy architecture above — most cross-cutting workflows are done via direct job dispatch rather than the Laravel event system.

| Location | Event | Listener | Purpose |
|---|---|---|---|
| `app/Events`, `app/Listeners` | `BootcampAdditionalEnrollmentAdded` | `AddBootcampAdditionalEnrollmentToBookDelivery` | When an additional bootcamp enrollment is added, queues it into the book delivery workflow |
| `Modules/Webhook` | `WebhookTriggered` | `HandleWebhook` | Generic inbound/outbound webhook dispatch handling |
| `Modules/Package` | `PackageEnrollmentStudentAssignmentsCompleted`, `PackageUpdateStudentCompleted` | `SendPackageUpdateEmailNotification`, `SendEmailWhenJobsCompleted` | Notifies via email once package enrollment/update background jobs finish |

## 13. Console Commands

Custom artisan commands live almost entirely in `app/Console/Commands` (one exception in `Modules/Enrollment/Console`). Grouped by purpose:

**Sync / integration commands**
- `PhoneNumberSyncWithLawsikho` — syncs phone numbers with the main LawSikho app
- `SyncDashboardApiData` — pulls/pushes student dashboard data
- `SyncClassParticipants` — syncs class participant rosters
- `UpdateStudentForumToken` — refreshes Vanilla Forum tokens for students
- `PerformanceCoachBlockedSlotDataSync` — syncs coach calendar blocked slots
- `RetryFailedEdmingleSyncCommand` — retries failed Edmingle sync jobs
- `Modules/Enrollment/Console/SyncZohoSupportResponses` — pulls Zoho Desk support ticket responses into enrollment records

**Notification commands**
- `ClassNotificationToStudentsTwoHoursBeforeCommand`, `ClassNotificationToStudentsAtNightCommand` — scheduled class reminder notifications
- `NotificationCommand` — generic notification dispatch, likely scheduler-invoked

**Data fix / migration one-offs** (mostly hotfix/backfill scripts, valuable as historical record of past data issues)
- `AssignmentDeletedFix`, `AssignmentDeletedFixNPS`, `FirstAssignmentSendLogDataMissing`
- `CheckSqlPackageEnrollmentMigration`, `PackageStudentUpdateEnrollment`, `ShiftBootcampWritingAssignmentsInWritingAssignmentCourse`
- `BootcampCourseMigrationCommand`
- `SingleEnrollmentAddManually`, `EnrollmentsBooksDispatch`, `ExportLargeEnrollmentsCsv`
- `FeedUserData`
- `app/Console/Commands/LiveDbSeeding/*` (10 commands) — one-time live-database migration/seeding scripts (`LiveDataMigrate`, `MigrateLiveEnrollmentsData`, `MigrateLiveNotificationUsersData`, `MigrateLiveClassParticipantsData`, `MigrateTheNewAddedEnrollmentsAndStudents`, `UpdateLMSForStudent`, `UpdateDefaultEvaluatorForCourses`, `UpdateCourseCompletionMaster`, `UpdateEnrollmentTypeAfterMigration`, `EnrollmentExpiry`, `migrateVideoMappingAndFirstAssignmentLog`) — these look like they were run once during a historical data migration and are likely safe to archive/remove if confirmed no longer needed

**Framework/maintenance**
- `PruneExpiredTokens` — standard Sanctum token cleanup command

## 14. External Integrations

| Integration | Purpose | Where implemented | Key env vars (names only) |
|---|---|---|---|
| **Edmingle (LMS)** | Live-class/LMS platform. Students & batches are synced to Edmingle for live classes; enrollment activation/deactivation triggers Edmingle batch add/remove | `Modules/Enrollment/Jobs/CreateEdmingleBatch.php`, `RetryEdmingleAssignmentJob.php`, `Modules/Student/Jobs/{Activate,Deactivate}StudentEdmingleBatches.php`, `Modules/Auth/Jobs/SyncUserWithLMS.php`, `Modules/Course/Entities/Course.php` (edmingle_id/curriculum_id columns) | none named `EDMINGLE_*` found directly in `.env`; likely proxied through `COURSE_CALENDAR_API_URL`/`COURSE_ANCHOR_API_KEY` — **verify with team**, this is the one integration whose credentials weren't clearly identifiable from env var names alone |
| **Course Calendar API** | External scheduling system batches/classes are synced against | `config/services.php` (`course_calendar.url`), `Modules/Enrollment/Jobs/CourseCalendar*Job.php`, `Modules/CourseBatch/Jobs/*` | `COURSE_CALENDAR_API_URL` (referenced as `COURSE_CALENDER_API_URL` in `.env` — note the misspelling "Calender" vs the code's "Calendar", confirm this isn't a live bug), `EXTERNAL_PORTAL_UPDATE_API_KEY` |
| **Kanboard (Project Management)** | Backs the `ProjectManagement` module — student/mentor project & task tracking | `Modules/ProjectManagement/Http/Traits/{Project,ProjectTask}Trait.php`, `Modules/ProjectManagement/Jobs/*` | not exposed as a distinct `.env` key with "kanboard" in the name — check `Modules/ProjectManagement` config or trait for a hardcoded/other-named URL |
| **AtsAPI (Applicant Tracking System)** | Dedicated module exposing/consuming ATS data (e.g. job applicant/placement tracking) | `Modules/AtsAPI/Http/Controllers/AtsAPIController.php` | `ATS_API_BASE_URL`, `ATS_API_KEY`, `ATS_API_SECRET`, `ATS_API_URL` |
| **RevenueAPI** | Receives enrollment/installment-payment data pushed from LawSikho's revenue/billing platform | `Modules/RevenueAPI/Http/Controllers/RevenueAPIController.php`, `Modules/RevenueAPI/Jobs/ProcessInstallmentPaymentJob.php` | `MAIN_APP_API_KEY`, `MAIN_APP_API_SECRET`, `MAIN_APP_URL` (shared with "other app" sync, see User module) |
| **Webhook module** | Generic inbound webhook receiver + outbound webhook dispatcher/retry with failure logging | `Modules/Webhook/Http/Controllers/{Webhook,Event,FailedApiResponse}Controller.php`, `Modules/Webhook/Events/WebhookTriggered.php`, `Modules/Webhook/Jobs/{SendWebhookJob,LogFailedApiResponseJob}.php` | `API_KEY` (generic) |
| **AgenticSupportSystem** | AI-driven support/chat system integration (has its own API routes and a batch migration sync job) | `Modules/AgenticSupportSystem/Routes/api.php`, `Jobs/AgenticBatchMigrationSyncJob.php` | `AGENTIC_SUPPORT_SYSTEM_LISTING_TOKEN`, `AGENTIC_SUPPORT_SYSTEM_TOKEN`, `AGENTIC_USER_ID` |
| **AIEvaluation (Auto-Evaluation API)** | Sends student assignment submissions to an external AI grading service | `Modules/AIEvaluation/Jobs/{Evaluate,BulkEvaluate}StudentAssignmentJob.php`, `config/services.php` (`auto_evaluation.base_url`) | `AUTO_EVALUATION_API_URL` |
| **Vanilla Forum** | Powers `Forum`/`StudentForum` modules — SSO token exchange + discussion data | `Modules/Forum/Http/Traits/VanillaForumTrait.php`, `app/Console/Commands/UpdateStudentForumToken.php` | `VANILLA_ADMIN_USERNAME`, `VANILLA_ADMIN_PASSWORD`, `VANILLA_FORUM_TOKEN_URL`, `VANILLA_FORUM_URL` |
| **Zoho Desk** | Support ticketing — pulls support responses into enrollment records | `Modules/Enrollment/Console/SyncZohoSupportResponses.php`, `Modules/Enrollment/Jobs/AutomatedEnrollmentStatusSyncJob.php`, `students.zoho_contact_id` column | `ZOHO_DESK_AUTH_URL`, `ZOHO_DESK_BASE_URL`, `ZOHO_DESK_CLIENT_ID` |
| **Firebase Cloud Messaging (FCM)** | Push notifications to admin/student mobile or web clients | `Modules/{User,Student}/Jobs/Send*SubscriberTokenToFCM.php` | `FCM_API_URL`, `LS_AP_FCM_CHANNEL_ID` |
| **Zoom** | Video call/meeting integration (JWT auth method configured) | `config/zoom.php`, `config/services.php` (`zoom.client_key/secret`) | `ZOOM_CLIENT_KEY`, `ZOOM_CLIENT_SECRET` (not currently seen in the `.env` key list reviewed — confirm they exist where zoom features are actually used) |
| **Meeting/Book-a-Call API** | Backs `StudentBookACall` module's external meeting scheduling | `config/services.php` (`meeting_api.*`), `Modules/StudentBookACall/Jobs/AddUserToMeetingsAPI.php` | `MEETING_API_BASE_URL`, `BOOK_A_CALL_API`, `MEETING_TIMEZONE` |
| **AWS S3** | File storage (assignment files, CSV exports, book media, etc.) | `config/filesystems.php` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`, `AWS_BUCKET`, `AWS_USE_PATH_STYLE_ENDPOINT` |
| **Pusher / Laravel Echo** | Real-time broadcasting (currently `BROADCAST_DRIVER=log` locally, i.e. disabled/no-op) | `config/broadcasting.php` | `PUSHER_APP_ID`, `PUSHER_APP_KEY`, `PUSHER_APP_SECRET`, `PUSHER_APP_CLUSTER`, `MIX_PUSHER_APP_KEY`, `MIX_PUSHER_APP_CLUSTER` |
| **Course Anchor / Student Journey APIs** | Referenced but not traced to a specific controller in this pass — likely course-progress/journey tracking services | not confirmed — grep further if needed | `COURSE_ANCHOR_API_KEY`, `STUDENT_JOURNEY_API` |
| **Employer Service (job-portal + employer microservice)** | ⚠️ Discovered 2026-08-29 (see `documentation/BUSINESS_RULES.md` §6) — missed by the original module-by-module audit. When a staff `User` has `ats=1` and no `user_details` row, dispatches a 2-step chain: registers the user on an external job-portal API, then (only on success) creates an "employer" record on a separate employer microservice using hardcoded placeholder company data | `Modules/User/Http/Controllers/UserController.php:227-235,429-437`, `Modules/User/Jobs/SendUserDetailsToExternalApi.php` | `EMPLOYER_SERVICE_API_URL` (unset in current `.env` — runs on `config/services.php`'s default URL), plus the job-portal's own base URL config |

> ⚠️ **Security note (not for the docs, flag to the user directly):** `config/services.php` has a hardcoded fallback secret for `EXTERNAL_PORTAL_UPDATE_API_KEY` (`env('EXTERNAL_PORTAL_UPDATE_API_KEY', 'CC_API_SK_...')`) — a real-looking API key committed as a default value in a tracked config file. This should be rotated and removed from source, not just left as a fallback.

## 15. Configuration Reference (`config/*.php`)

| File | Purpose |
|---|---|
| `activitylog.php` | `spatie/laravel-activitylog` — audit log table/model config |
| `app.php` | Core app config (name, env, timezone, providers, aliases) |
| `auth.php` | Auth guards/providers (admin `User` + student `Student`, Sanctum) |
| `broadcasting.php` | Pusher/Echo broadcast driver config |
| `cache.php` | Cache store config (file locally; Redis available) |
| `cors.php` | CORS allowed origins/headers for the API |
| `database.php` | DB connections — default `mysql` plus a secondary LS (LawSikho/LMS) MySQL connection (`DB_MYSQL_LS_*`) and Redis |
| `excel.php` | `maatwebsite/excel` package config — used by the many CSV/Excel export jobs |
| `filesystems.php` | Local + S3 disk definitions |
| `hashing.php` | Password hashing driver (bcrypt/argon) |
| `horizon.php` | Laravel Horizon queue dashboard/worker config — Redis queues: `default`, `default_long`, `default_high`, `default_medium` |
| `logging.php` | Log channels (`stack` default per `.env`) |
| `mail.php` | Mail driver/from-address config |
| `media-library.php` | `spatie/laravel-medialibrary` — file/media attachment config (used for assignment/book/media uploads) |
| `modules.php` | `nwidart/laravel-modules` package config — module namespace, paths, generator stubs |
| `permission.php` | `spatie/laravel-permission` — RBAC table/guard config |
| `queue.php` | Queue connections (sync, redis, redis-long-running, etc.) |
| `sanctum.php` | Sanctum stateful domains + token expiration |
| `sentry.php` | Sentry error-tracking DSN/release config |
| `services.php` | Third-party service credentials (Mailgun, Postmark, SES, Zoom, LawSikho main app, auto-evaluation, meeting API, course calendar) |
| `session.php` | Session driver/lifetime (file locally) |
| `tags.php` | `spatie/laravel-tags` — tagging config, likely used by Assignment/AssignmentTag module |
| `telescope.php` | Laravel Telescope debug/monitoring dashboard config |
| `view.php` | Blade view paths |
| `zoom.php` | Zoom API base URL, JWT auth method, rate limiting |

## 16. Environment Variables

*(names only — never values)*

**App**
`APP_NAME`, `APP_ENV`, `APP_KEY`, `APP_DEBUG`, `APP_URL`, `APP_PASS_PHRASE`

**Database**
`DB_CONNECTION`, `DB_HOST`, `DB_PORT`, `DB_DATABASE`, `DB_USERNAME`, `DB_PASSWORD`, `DB_MYSQL_LS_CONNECTION`, `DB_MYSQL_LS_HOST`, `DB_MYSQL_LS_PORT`, `DB_MYSQL_LS_DATABASE`, `DB_MYSQL_LS_USERNAME`, `DB_MYSQL_LS_PASSWORD`

**Auth / Security**
`API_KEY`, `MAIN_APP_API_KEY`, `MAIN_APP_API_SECRET`

**AWS / Storage**
`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`, `AWS_BUCKET`, `AWS_USE_PATH_STYLE_ENDPOINT`, `FILESYSTEM_DRIVER`

**Mail**
`MAIL_MAILER`, `MAIL_HOST`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_ENCRYPTION`, `MAIL_FROM_ADDRESS`, `MAIL_FROM_NAME`

**Queue / Cache / Redis / Session**
`QUEUE_CONNECTION`, `CACHE_DRIVER`, `SESSION_DRIVER`, `SESSION_LIFETIME`, `REDIS_HOST`, `REDIS_PASSWORD`, `REDIS_PORT`, `MEMCACHED_HOST`

**Broadcasting**
`BROADCAST_DRIVER`, `PUSHER_APP_ID`, `PUSHER_APP_KEY`, `PUSHER_APP_SECRET`, `PUSHER_APP_CLUSTER`, `MIX_PUSHER_APP_KEY`, `MIX_PUSHER_APP_CLUSTER`

**External APIs / Integrations**
`AGENTIC_SUPPORT_SYSTEM_LISTING_TOKEN`, `AGENTIC_SUPPORT_SYSTEM_TOKEN`, `AGENTIC_USER_ID`, `ATS_API_BASE_URL`, `ATS_API_KEY`, `ATS_API_SECRET`, `ATS_API_URL`, `AUTO_EVALUATION_API_URL`, `BOOK_A_CALL_API`, `COURSE_ANCHOR_API_KEY`, `COURSE_CALENDER_API_URL`, `FCM_API_URL`, `LS_AP_FCM_CHANNEL_ID`, `MEETING_API_BASE_URL`, `MEETING_TIMEZONE`, `OTHER_APP_DOMAIN_NAME`, `OTHER_APP_URL`, `STUDENT_JOURNEY_API`, `VANILLA_ADMIN_USERNAME`, `VANILLA_ADMIN_PASSWORD`, `VANILLA_FORUM_TOKEN_URL`, `VANILLA_FORUM_URL`, `ZOHO_DESK_AUTH_URL`, `ZOHO_DESK_BASE_URL`, `ZOHO_DESK_CLIENT_ID`

**Misc / Dev**
`LOG_CHANNEL`, `LOG_DEPRECATIONS_CHANNEL`, `LOG_LEVEL`, `PHP_CS_FIXER_IGNORE_ENV`
