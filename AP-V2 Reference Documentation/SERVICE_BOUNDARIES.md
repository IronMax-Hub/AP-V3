# Service Boundaries

> **Generated:** 2026-08-29 · **Branch surveyed:** `New-Dummy-Prod-0605`
> **Method:** `config/database.php`, `config/queue.php`/`config/horizon.php`, every `DB::connection(...)` call site codebase-wide, `config/auth.php`, and the module coupling data already built for `CONTEXT_MAP.md`/`BOUNDED_CONTEXT_*.md`. Where this document's numbers overlap those documents, they're the same underlying data reframed around one question: **where are the real seams, and where do the module folders only look like seams?**
> **Companion documents:** `documentation/CONTEXT_MAP.md`, `documentation/BOUNDED_CONTEXT_{IDENTITY,LEARNING,ENROLLMENT,ASSESSMENT,COMMUNICATION,INTEGRATIONS}.md`, `documentation/DOMAIN_MODEL_DIAGRAM.md`, `documentation/EVENT_LIST.md`

## What "service boundary" means for this codebase

This is a **single Laravel application, one deployable, one process type (PHP-FPM behind nginx + Horizon workers), one database, one Redis instance**. There is no existing microservice split, no per-context database, no per-context deployment. `nwidart/laravel-modules` gives 62 folders the *look* of independent services, but a folder boundary is not a service boundary — a service boundary requires an independent deployment, an independent data store (or at least data ownership), and a contract (API/message) instead of direct in-process method/Eloquent-relationship calls.

This document covers two different things under that one heading:

1. **§1–2: Real boundaries that already exist** — the genuinely separate systems this application is a client or server to, and the two different client-facing API contracts (admin vs. student) it serves.
2. **§3–5: Internal seams** — whether the 6 bounded contexts already established in `BOUNDED_CONTEXT_*.md` could become real service boundaries with work, using the actual coupling numbers rather than the folder structure to judge readiness.

---

## 1. The deployment boundary today

| Dimension | Reality |
|---|---|
| Deployable units | 1 (this Laravel app). No module runs as a separate process |
| Database | 1 live connection (`DB_CONNECTION=mysql`) shared by all 62 modules — no schema-per-context, no database-per-context |
| Queue/cache/session infrastructure | 1 Redis instance; Horizon queues are priority-based (`default`, `default_high`, `default_medium`, `default_long`) — **not partitioned by bounded context**. A queue outage or Redis config change affects every context identically |
| Auth | 2 guards (`sanctum` for admin, `student` for students) — see §2 — but both are served by the same app instance and same codebase |
| Web server | 1 nginx + PHP-FPM container (`docker/`), or bare-metal `php artisan serve` |

Nothing here is a criticism — it's a correct description of "modular monolith," which is a legitimate architecture. The point of this document is to make explicit what would have to change if that ever stopped being true.

---

## 2. Real external service boundaries

These are the genuinely separate systems — different codebases, different teams (presumably), different failure domains — that this application already integrates with. Full env-var-level detail lives in `DEVELOPER_DOCUMENTATION.md` §14; this table adds the *protocol* and *contract type* dimension, which matters for a service-boundary discussion specifically.

| External system | Contract type | Direction | Owning bounded context | Notes |
|---|---|---|---|---|
| Edmingle (LMS) | HTTP API (implied — exact base URL not confirmed, see `DEVELOPER_DOCUMENTATION.md` §14) | Outbound | Enrollment / Learning / Identity (spans three — see `BOUNDED_CONTEXT_LEARNING.md` §8) | Batch/user sync |
| Course Calendar API | HTTP API | Bidirectional | Learning/Enrollment | Batch/class scheduling |
| ATS / Job Portal + Employer microservice | HTTP API | Outbound | Integrations | Two-step chained call (register on job portal, then employer microservice) |
| Revenue/Billing platform | HTTP API | **Inbound** — the one integration where this app is server, not client | Enrollment | `RevenueAPI` controller receives pushed data |
| Meeting/Book-a-Call API | HTTP API | Bidirectional | Learning (`StudentBookACall`) | A separate sub-project's own API, not a third party |
| Auto-Evaluation AI API | HTTP API + inbound webhook | Bidirectional | Assessment | See `EVENT_LIST.md` §3 for the live webhook receiver |
| Agentic Support System API | HTTP API, static-token auth | Bidirectional | Integrations | Non-Sanctum trust boundary |
| Zoho Desk | HTTP API (pull) | Outbound | Enrollment | Console command pulls ticket responses |
| Firebase Cloud Messaging | HTTP API | Outbound | Identity | Push tokens |
| Vanilla Forum | HTTP API | Bidirectional | Learning (deprecated `Forum`/`StudentForum`) | Dead feature, live integration code |
| Kanboard | HTTP API | Bidirectional | Learning (deprecated `ProjectManagement`) | Dead feature, live integration code |
| AWS S3 | Storage API | Outbound | (infrastructure, not a business context) | File storage |
| Pusher | Broadcast API | Outbound | (infrastructure) | Currently no-op — `BROADCAST_DRIVER=log` |

**All of the above go through an HTTP contract** — the correct shape for a service boundary, regardless of how well-designed the specific integration is. One exception exists, and it doesn't:

### ⚠️ The one real boundary violation: direct database access into another system

`config/database.php` defines **two additional MySQL connections beyond the primary `mysql` one that are actually wired to real credentials and actually used**: `staging` and `sql_migration`. Both are used exclusively from `app/Console/Commands` (10 files total, all one-off/historical scripts — none in `Modules/*` business logic):

| Connection | Points at (per `.env`) | Used by | Read or write | What it's for |
|---|---|---|---|---|
| `sql_migration` | `ls_ecomm_v3` database — LawSikho's main e-commerce/ordering system, tables `tbl_user`/`tbl_orders` | `PhoneNumberSyncWithLawsikho.php`, `CheckSqlPackageEnrollmentMigration.php` | **Read-only** (confirmed — no `insert`/`update` calls found against either connection anywhere) | Looks up phone numbers and legacy package-enrollment records directly from another system's live database, bypassing any API |
| `staging` | `ap_dec_2022` — an old snapshot of *this same application's own predecessor database* | The 10 `app/Console/Commands/LiveDbSeeding/*` one-time backfill scripts, plus `TopicMigration.php` | Read-only | Historical data migration source, not a live external service |

**`sql_migration` → `ls_ecomm_v3` is the one place in this codebase where a service boundary is crossed by querying another system's tables directly instead of calling an API.** It's low-risk today specifically because it's read-only and confined to two rarely-run console commands (one of which, `PhoneNumberSyncWithLawsikho`, has its own write-back to `students.phone` commented out — so today it reads external data and does nothing with it). But it means this app's code has hardcoded knowledge of another system's internal schema (`tbl_user.emailreg`, `tbl_orders.country_code`) with zero contract protecting either side from the other's schema changes. If this pattern is ever extended to a live, frequently-run path, that would be worth stopping and re-architecting as an API call first.

**Correction to `DEVELOPER_DOCUMENTATION.md` §7/§15/§16**, which describes "a second MySQL connection (`DB_MYSQL_LS_*`) alongside the primary" as something to "confirm with the team": **the `DB_MYSQL_LS_*` environment variables exist in `.env` but are not wired to any connection in `config/database.php`, and a codebase-wide search found zero references to them anywhere in application code.** They are dead configuration. The real second/third database connections are `staging` and `sql_migration`, neither of which was previously documented by that name.

---

## 3. Client-facing service boundaries: Admin API vs. Student API

Even though both are served by the same deployable, these function as two genuinely separate API contracts today, per `config/auth.php` and the route prefix convention (`v1/*` vs. `student/v1/*`):

| | Admin API | Student API |
|---|---|---|
| Guard | `sanctum` → `App\Models\User` | `student` → `Modules\Student\Entities\Student` |
| Route prefix | `v1/*` | `student/v1/*` |
| RBAC | `spatie/laravel-permission`, admin-only | None |
| Consumer | Internal back-office tooling | The public-facing student portal |

**This boundary is blurred in one place worth knowing about:** `StudentFrontendEnrollment` (Enrollment context) hosts CSAT, NPS, Notification, and Task controllers that appear to duplicate functionality that Learning's and Communication's own student-facing modules (`StudentMyCourses`, `StudentNotifications`, the CSAT modules) also expose — flagged independently in `BOUNDED_CONTEXT_ENROLLMENT.md` §8 and `DEVELOPER_DOCUMENTATION.md` §4. If both paths are genuinely live, the "student API" isn't one coherent contract but two overlapping ones under the same guard — worth resolving before treating either as the sole source of truth for a client integration.

---

## 4. Internal seams: could a bounded context become a real service?

All 6 contexts share the one database from §1 — **no context owns its own schema today**, and `DOMAIN_MODEL_DIAGRAM.md` shows Eloquent relationships (not API calls) crossing every context boundary. That's the first and biggest blocker to any extraction, common to all 6. Beyond that shared blocker, readiness differs sharply by context. The table below uses the exact cross-context edge counts from the `BOUNDED_CONTEXT_*.md` relationship tables:

| Context | In-degree (things that would break) | Out-degree (calls it would need to make outward) | Internal cohesion | Extraction verdict |
|---|---|---|---|---|
| **Integrations** | 2 | 29 | None (0 intra-context edges) | ✅ **Easiest** — almost nothing depends on it; it's already structured as an outbound gateway. Extracting it mainly means giving it its own outbound network egress and secrets, not renegotiating who depends on it |
| **Assessment** | 51 | 31 | High (near-complete mesh among 4 modules — a real pipeline) | 🟡 **Cleanest internally, but not easy** — would extract as one cohesive unit with a well-defined data ownership boundary (`assignments`/`student_assignments`/`results`), but 51 inbound edges from every other context mean a lot of call sites elsewhere need to switch from Eloquent joins to an API client first |
| **Communication** | 44 | 43 | Very low (2 intra-context edges across 9 modules) | 🟡 **Actually several small services wearing one label** — the 4 independent CSAT verticals, NPS, Notification, and Webhook don't depend on each other; each could be peeled off individually more easily than the context could be extracted as a whole |
| **Identity** | 48 | 31 | Low (13 edges, two disconnected stars: admin identity and student identity) | 🔴 **Hard** — `Student` and `User` are the shared-kernel entities nearly everything else joins against directly; extracting Identity means every other context needs an API/token-introspection call instead of a local FK, for authentication *and* for the dozens of denormalized reads of student/user attributes |
| **Enrollment** | 39 (context-level) / 39 modules system-wide depend on the `Enrollment` module alone | 49 | Minimal (2 intra-context edges — it's really one hub module plus 3 satellites) | 🔴 **Hardest alongside Learning** — `Enrollment` is the single most depended-upon module in the entire codebase (`CONTEXT_MAP.md` §4), and is in a near-symmetric dependency cycle with Learning (22↔20 edges) — neither can be extracted without the other |
| **Learning** | 82 | 83 | Mixed — cohesive within its "core catalog" sub-cluster, near-zero cohesion with its deprecated sub-cluster | 🔴 **Hardest** — the largest context (26 modules), the highest total coupling of any context in both directions, in a genuine dependency cycle with Enrollment, and 10 of its 26 modules are dead code that's still structurally load-bearing (`BOUNDED_CONTEXT_LEARNING.md` §6) |

**The practical reading of this table:** if a service extraction were ever attempted, **Integrations is the only context that could be pulled out today with modest effort**, because almost nothing in the monolith depends on it back. Every other context would require solving the shared-database problem first (§1), and Enrollment + Learning specifically cannot be separated from each other at all without first breaking their mutual cycle — they'd have to be extracted together as one large service, or not at all, regardless of which document files them as two contexts.

---

## 5. What would have to change before any real extraction

Not a roadmap — a checklist of the specific, verified blockers from this session's data, in the order they'd actually need to be tackled:

1. **Resolve the Enrollment↔Learning cycle first.** Nothing else about extraction is worth planning until this is a one-directional dependency (or the two are accepted as one extraction unit).
2. **Decide what "owns" `Student`, `User`, `Course`, and `Enrollment`.** These four entities are read directly (via Eloquent relationship, not API) from every other context (`DOMAIN_MODEL_DIAGRAM.md` §1). A real service boundary needs each of these to have exactly one owning service that others call, not join against.
3. **Replace direct Eloquent cross-context reads with an internal API or a shared read-model**, starting with whichever context is extracted first (Integrations, per §4) — even that low-risk case still has 29 outbound reads into other contexts today.
4. **Give `sql_migration` a real contract or retire it.** It's low-traffic today, but any live, direct, cross-system database read is the wrong pattern to carry forward into a service architecture, regardless of how rarely it's invoked.
5. **Decide on a real event/message mechanism.** `EVENT_LIST.md` found that the one mechanism in this codebase designed for exactly this purpose — `WebhookTriggered`, with a DB-backed subscription and retry model — is currently 100% disabled. A service split needs *something* to replace direct in-process calls with; reviving and hardening that mechanism (or picking a proper message queue) is a prerequisite, not a nice-to-have.
6. **Partition the queues.** Horizon's queues today are priority-tiers (`default_high`/`_medium`/`_long`), not per-context — any extracted service would need its own queue(s) or a different Redis instance to avoid one service's backlog starving another's.
7. **Untangle `StudentFrontendEnrollment`** (§3) before treating the student API as one contract belonging to one context — right now a client-facing extraction plan would need to know which of the two overlapping implementations is authoritative.

## 6. Related documents

- `documentation/CONTEXT_MAP.md` — the full 377-edge module coupling graph this document's context-level numbers are aggregated from
- `documentation/BOUNDED_CONTEXT_{IDENTITY,LEARNING,ENROLLMENT,ASSESSMENT,COMMUNICATION,INTEGRATIONS}.md` — per-context detail behind §4's verdicts
- `documentation/DOMAIN_MODEL_DIAGRAM.md` — the table-level evidence that every context shares one database with no ownership boundary
- `documentation/EVENT_LIST.md` — the disabled event mechanism referenced in §5.5
- `documentation/DEVELOPER_DOCUMENTATION.md` §7/§14/§15/§16 — original database-connection and external-integration inventory; §7/§16's `DB_MYSQL_LS_*` claim is corrected by this document's §2
