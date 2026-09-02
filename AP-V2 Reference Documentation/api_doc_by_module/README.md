# API Documentation by Module

Per-module API contract reference for the Lawsikho Assignment Portal API, built as the **source of truth for AP-V3 migration parity testing**. Each file documents every live endpoint in one module — request params, validation, exact success/error response shapes, side effects, and known bugs/quirks — traced directly from route files, controllers, traits, FormRequests, and Resources, not inferred from naming.

**Read [`_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) first.** It covers the 4 response-envelope styles, standard error shapes, and pagination families shared across modules. Individual module files only call out where an endpoint *deviates* from those conventions.

## Scope

- **50 active modules**, one file each, covering ~700+ routes.
- **12 modules are confirmed deprecated (not in active production use)** and are intentionally omitted — see the exclusion list below. Cross-referenced against `../DEVELOPER_DOCUMENTATION.md` §4.
- Only `Routes/api.php` per module is covered. `Routes/web.php` files were sample-checked and confirmed to be non-functional Blade-view scaffolding with no real API surface.
- A route existing does not mean it works — several modules register `apiResource` (or explicit) routes with no backing controller method at all, which fail with an uncaught-error 500, not a clean 404/405. Each file calls these out explicitly per endpoint; don't assume a documented route is reachable without reading its Notes.

## Companion documents

- [`../DEVELOPER_DOCUMENTATION.md`](../DEVELOPER_DOCUMENTATION.md) — tech stack, module inventory, auth internals, full routes list, DB schema.
- [`../USER_WORKFLOWS.md`](../USER_WORKFLOWS.md) — traced end-to-end workflows, cross-cutting QA findings.
- [`../API_SPECIFICATIONS.md`](../API_SPECIFICATIONS.md) — original domain-grouped pass; superseded in depth here, kept for historical/cross-reference. Several of its claims were re-verified during this effort — corrections are noted inline in the relevant module file rather than collected separately.

## Module index

### Core enrollment & student lifecycle
| Module | Endpoints (raw routes) |
|---|---|
| [Enrollment](./Enrollment.md) | 56 routes / 60 endpoints |
| [LawSikho](./LawSikho.md) | 33 routes |
| [StudentFrontendEnrollment](./StudentFrontendEnrollment.md) | 73 |
| [StudentMyCourses](./StudentMyCourses.md) | 25 live + broken cluster |
| [StudentDashboard](./StudentDashboard.md) | 27 live + broken cluster |
| [StudentDashboardManagement](./StudentDashboardManagement.md) | 13 |
| [Student](./Student.md) | 29 routes / 24 actions |
| [StudentProfile](./StudentProfile.md) | 19 |
| [StudentBookACall](./StudentBookACall.md) | 70 (external proxy) |
| [StudentResults](./StudentResults.md) | 4 |

### Auth, identity & access
| Module | Endpoints |
|---|---|
| [Auth](./Auth.md) | 8 |
| [StudentAuth](./StudentAuth.md) | 13 |
| [User](./User.md) | 27 routes / 23 actions |
| [Role](./Role.md) | 13 registrations |
| [Permission](./Permission.md) | 3 |
| [InternalNotes](./InternalNotes.md) | 7 registrations |

### Courses & catalog
| Module | Endpoints |
|---|---|
| [Course](./Course.md) | ~24 |
| [CourseBatch](./CourseBatch.md) | ~23 |
| [CourseCategory](./CourseCategory.md) | 12 |
| [CourseCategoryCriteria](./CourseCategoryCriteria.md) | 2 |
| [CourseCriteria](./CourseCriteria.md) | 6 |
| [CourseFaq](./CourseFaq.md) | 5 |
| [CoursePlanType](./CoursePlanType.md) | 4 |
| [CourseCompletionMaster](./CourseCompletionMaster.md) | 6 |
| [Bootcamp](./Bootcamp.md) | 9 |
| [Package](./Package.md) | 11 |

### Assignments, grading & evaluation
| Module | Endpoints |
|---|---|
| [Assignment](./Assignment.md) | 10 |
| [AssignmentTag](./AssignmentTag.md) | 6 |
| [AssignmentCSAT](./AssignmentCSAT.md) | 8 |
| [AssignmentSendingLog](./AssignmentSendingLog.md) | 7 |
| [StudentAssignment](./StudentAssignment.md) | 20 |
| [Result](./Result.md) | 14 |
| [Evaluator](./Evaluator.md) | 7 |
| [EvaluatorCSAT](./EvaluatorCSAT.md) | 8 |
| [AIEvaluation](./AIEvaluation.md) | 12 |

### Notifications & engagement
| Module | Endpoints |
|---|---|
| [StudentNotifications](./StudentNotifications.md) | 7 live + broken cluster |
| [Notification](./Notification.md) | 12 live + broken/dead cluster |
| [NPS](./NPS.md) | 28 routes / 13 behaviors |

### Support & agentic systems
| Module | Endpoints |
|---|---|
| [AgenticSupportSystem](./AgenticSupportSystem.md) | 61 |

### External integrations & webhooks
| Module | Endpoints |
|---|---|
| [Webhook](./Webhook.md) | 17 registrations |
| [ReferralSystem](./ReferralSystem.md) | 6 (external proxy) |
| [AtsAPI](./AtsAPI.md) | 3 |
| [RevenueAPI](./RevenueAPI.md) | 2 |
| [EmailTemplate](./EmailTemplate.md) | 4 |

### Reference / lookup data
| Module | Endpoints |
|---|---|
| [Country](./Country.md) | 2 live + 4 broken |
| [State](./State.md) | 2 live + 4 broken |
| [JobRole](./JobRole.md) | 2 |
| [StudentDegree](./StudentDegree.md) | 2 live + 4 broken |
| [StudentUniversity](./StudentUniversity.md) | 2 live + 4 broken |
| [Topic](./Topic.md) | 8 live + 1 broken |

## Excluded — confirmed deprecated modules (12)

Not in active production use; omitted entirely rather than documented. See `../DEVELOPER_DOCUMENTATION.md` §4 for detail.

`BookMaster`, `BookDeliveryLog`, `Class`, `ClassCSAT`, `Forum`, `StudentForum`, `PerformanceCoach`, `PerformanceCoachCSAT`, `ProjectManagement`, `StudentClasses`, `StudentTasks`, `StudentPerformanceCoach`

## Verification

- Cross-checked `ls Modules/` (62 total) against this folder's file list: every one of the 50 active modules has exactly one corresponding `.md` file here, no gaps and no extras.
- A sample of each wave's most significant claims (broken routes, bug reports, auth-guard claims) was independently spot-checked against the live route/controller source rather than trusted from agent self-report — all spot-checks passed.
- Endpoint counts above are as reported by each module's file; a few files count "raw route registrations" vs. "distinct reachable behaviors" differently where `apiResource` macros produce broken stub actions — see the module file itself for the exact breakdown.
