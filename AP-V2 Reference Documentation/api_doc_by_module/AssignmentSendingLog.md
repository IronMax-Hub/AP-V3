# AssignmentSendingLog Module — API Documentation

The `AssignmentSendingLog` module is a **read-only reporting surface** over two tables, `assignment_log` and `assignment_log_mapping` — a batch/bulk assignment-distribution run and its per-student send-outcome rows, respectively. All 3 live routes in this module only ever read from these tables; nothing in this module's own code writes to them. See [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for app-wide envelope/error/pagination conventions.

**Module-wide auth:** every route in `Modules/AssignmentSendingLog/Routes/api.php` is `auth:sanctum` + `json.response`, prefix `v1`. No per-route deviation.

**Class layout:** single controller `AssignmentSendingLogController` (`index`/`show` directly on the class) `use`s `AssignmentSendingLogTrait` for `getStudentList()` and both cursor-range helper methods.

## ⚠️ Critical finding for parity testing: `assignment_log`/`assignment_log_mapping` are confirmed **dead tables — nothing in the current codebase writes to them**

Grepped every reference to `AssignmentLog::create()`, `new AssignmentLog()`, `AssignmentLogMapping::create()`, and `new AssignmentLogMapping()` across the entire `Modules/` tree. Every single call site found is **commented out**:
- `Modules/StudentAssignment/Http/Controllers/StudentAssignmentController.php` — 8 separate commented-out blocks (lines ~291–476) that would have created `AssignmentLog`/`AssignmentLogMapping` rows during what looks like the original bulk-assignment-with-per-student-outcome-tracking flow.
- `Modules/StudentAssignment/Jobs/StudentAssignmentCsvImport.php` and `Modules/StudentAssignment/Imports/StudentAssignmentImport.php` — commented-out `new AssignmentLogMapping()` in the CSV-import path.
- `Modules/Enrollment/Jobs/PackageEnrollmentStudentAssignments.php` — commented-out `AssignmentLog::create([...])`.

The only **live** writer found anywhere near this domain is `Modules\Enrollment\Jobs\BatchsAssignmentsJob::addFirstAssignmentLog()` — but despite the method's name, it writes to `Modules\StudentAssignment\Entities\FirstAssignmentSendLog` (a completely different table/model in the `StudentAssignment` module, documented in `StudentAssignment.md`), **not** to this module's `AssignmentLog`. The naming similarity (`addFirstAssignmentLog` vs. `AssignmentLog`) is coincidental/misleading, not a relationship.

**Conclusion for QA:** any `assignment_log`/`assignment_log_mapping` rows a tester finds in a real database are either historical (pre-dating the code that would have created them being commented out) or seeded by the module's own factories/seeders (`Modules/AssignmentSendingLog/Database/factories/`, `AssignmentSendingLogDatabaseSeeder.php`) — not something a fresh end-to-end workflow through this app's live code will ever populate today. A parity test that expects, e.g., submitting a bulk assignment via `StudentAssignment`'s `assign-by-filters` endpoint to produce a new row visible through this module's `index()`/`show()` **will fail**, because the write path that would connect them is dead code. Confirm with the team whether reviving that write path is in scope for AP-V3, or whether this module's read endpoints are themselves being retired.

---

## `GET /v1/assignment-log/get-student-list/{assignment_log_id}` — `getStudentList()` (trait method, route name `assignment-log.get-student-list`)
- Registered **before** the `apiResource` block, so this literal-prefixed path is matched ahead of the resource's `{assignment_log}` wildcard.
- Path param `assignment_log_id` — plain int, **not** route-model-bound; no existence check before querying — a nonexistent id simply yields an empty paginated result (`meta.total: 0`), not a 404.
- Query: `rows` (optional int, default 15); `search` (optional, `LIKE` against `student_name` and `student_email` on `assignment_log_mapping`); `cursor` (this module's standard base64-JSON cursor scheme).
- **Success response:** `AssignmentLogMappingListResources::collection(...)->additional(['meta' => ['total' => ..., 'range' => ...]])`. Resource excludes `id`/`assignment_log_id`/`assignment_id`/`enrollment_id`/`assignment_code`/`assignment_type`/`created_at`/`updated_by`/`updated_at` from the raw row and adds: `course` (`{course_name}`, via `enrollment.course` — **unguarded**, will throw if `enrollment` is null), `batch` (`{batch_date}` or `null`, via `enrollment.batch?`), `topic` (`{title}` or `null`, via `assignment?.topic?`).
- Malformed/tampered `cursor` → `abort(500, 'Cursor value tempered')`, per the module's own cursor helper (`calculateRangeForCursorStudent()`), consistent with the app-wide convention.

## `GET /v1/assignment-log` — `index()` (`apiResource`)
- Query: `rows` (optional int, default 15); `search` (optional, matches against `assignmentLogMapping.enrollment.course.course_name` OR `assignmentLogMapping.enrollment.batch.batch_date` via `whereRelation`/`orWhereRelation` — **searches through the child mapping rows' relations, not any column on `assignment_log` itself**); `cursor`.
- **Success response:** `AssignmentLogResources::collection(...)->additional(['meta' => ['total' => ..., 'total_record' => ..., 'range' => ...]])` — **note `total` and `total_record` are both present and always equal** (both computed via the same `AssignmentLogRepository::totalRecord()` call) — a redundant duplicate key pair, not two different counts; don't expect them to diverge.
- `AssignmentLogResources` fields: all raw columns except `updated_by`/`server_request`/`csv_file_location`/`updated_at`, plus `details` — `AssignmentLogMappingResources::collection($this->assignmentLogMapping)->unique('course_name')` — **the entire child-mapping collection is loaded and then de-duplicated client-response-side by `course_name`**, meaning `details` under-represents the true count of per-student mapping rows whenever multiple students share a course name (which is the common case) — do not use the length of `details` as a per-student count; use the dedicated `show()` endpoint's `total.successfull`/`total.unsuccessfull` counts instead.

## `GET /v1/assignment-log/{assignmentLog}` — `show()` (`apiResource`)
- Route-model-bound on `Modules\AssignmentSendingLog\Entities\AssignmentLog` — a binding miss produces the standard 404 `ModelNotFoundException` shape (see common conventions).
- **Success response:** `apiResponse(['general' => AssignmentLogDetailsResources::make($assignmentLog), 'total' => ['successfull' => ..., 'unsuccessfull' => ...]])` — note the **misspellings `successfull`/`unsuccessfull` (double "l", missing hyphenation) are literal key names in the live response**, not a typo in this doc; preserve exactly. Counts are `AssignmentLogMappingRepository::getSuccessfulStudentCount()`/`getUnsuccessfulStudentCount()`, each a `->where('sent_status', 'LIKE', 'Sent')` / `'Not Sent'` count against `assignment_log_mapping` scoped to this log id — these are the accurate per-student totals (unlike `index()`'s deduplicated `details` array above).
- `AssignmentLogDetailsResources` fields: all raw columns except `created_by`/`updated_by`/`updated_at`, plus `creator` (`{id,first_name,last_name}` — **unguarded `$this->creator->only(...)`**, will throw if `created_by` doesn't resolve to a real user).

## `POST /v1/assignment-log`, `PUT/PATCH /v1/assignment-log/{assignmentLog}`, `DELETE /v1/assignment-log/{assignmentLog}` — `apiResource`'s `store`/`update`/`destroy` — **confirmed broken, no method exists**
`Route::apiResource('assignment-log', 'AssignmentSendingLogController')` wires up all 5 CRUD routes, but the controller implements only `index`/`show` (plus the module-specific `getStudentList()`, outside the resource). No `store()`, `update()`, or `destroy()` method exists anywhere in the class or its trait — confirmed by reading both files in full. Calling any of these 3 routes triggers a PHP fatal `Error: Call to undefined method`, surfacing as an uncaught **500**, not a clean 404/405 — same failure pattern as `NPS`'s and `AssignmentTag`'s partially-wired `apiResource`s. Combined with the module-wide finding above (nothing writes to these tables from live code at all), this module is functionally **read-only end-to-end**: even if these 3 routes worked, nothing else in the app calls them or relies on their side effects — they're purely dead scaffolding from `apiResource`, not a gap in an otherwise-live write path.

---

## Summary of endpoints documented

**3 raw routes registered** (`getStudentList` + the 5-route `apiResource`, 7 total route entries, 3 distinct working actions):
- **3 working, all read-only:** `getStudentList`, `index`, `show`.
- **3 confirmed broken:** `store`, `update`, `destroy` (fatal 500, undefined method) — though moot given the whole table pair is unwritten by any live code path regardless.

**Notable findings for parity testing:**
- ⚠️ **The module's entire underlying data (`assignment_log`/`assignment_log_mapping`) is not produced by any live code path** — every writer site found in the codebase is commented out. This is the single most important fact for a QA author: don't design an end-to-end test expecting a live workflow (bulk-assign, CSV import) to populate these tables and then verify it through this module's endpoints — it structurally cannot happen today.
- `index()`'s `details` array is silently deduplicated by `course_name`, undercounting per-student rows — use `show()`'s `total.successfull`/`total.unsuccessfull` for accurate counts instead.
- `show()`'s response literally spells the keys `successfull`/`unsuccessfull` (double-L) — verbatim, not a doc typo.
- `store`/`update`/`destroy` are fatal-error dead routes on top of already-dead underlying tables.
- `BatchsAssignmentsJob::addFirstAssignmentLog()` in the `Enrollment` module is a same-domain-sounding but functionally unrelated method — it writes to `StudentAssignment`'s `FirstAssignmentSendLog`, not to this module's `AssignmentLog`. Don't conflate the two when tracing cross-module effects of a bulk-assignment call.

**Confidence:** High — the "nothing writes to this table" finding was verified by grepping for every constructor/`::create()` call site across the full `Modules/` tree and confirming each one is commented out, not merely inferred from the absence of an obvious caller.
