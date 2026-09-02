# StudentDegree Module API Documentation

The `StudentDegree` module has **no dedicated database table of its own**. It is a read-only view over `Modules\Enrollment\Entities\EnrollmentQuestionAnswer` rows, filtered to only the answers submitted for the fixed enrollment question text `"What are the educational degrees and diplomas that you hold?"` — used to build a degree-name typeahead/dropdown from students' free-text answers rather than from a normalized `degrees` table.

**Module-wide auth:** both routes in `Modules/StudentDegree/Routes/api.php` are `auth:sanctum` + `json.response`, mounted under `/api/v1/...`. No deviation.

See [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for the app-wide response envelope styles, standard error shapes, and pagination conventions referenced below instead of being repeated per endpoint.

`StudentDegreeController` implements only `index()` and `search()`, no traits. **This module has no `Database/Migrations` directory at all** — confirmed via filesystem search — because it owns no table; its repository (`StudentDegreeRepository`) is constructed against the `Enrollment` module's `EnrollmentQuestionAnswer` model, not a `StudentDegree` entity (no such entity class exists either).

## ⚠️ `apiResource('degrees', 'StudentDegreeController')` — only 2 of 5 wired actions exist (same landmine as `Country`/`State`)

```php
Route::get('/search/degrees', [StudentDegreeController::class, 'search'])->name('degrees.search');
Route::apiResource('degrees', 'StudentDegreeController');
```
`store`, `show`, `update`, `destroy` are registered by `apiResource` but **have no method on `StudentDegreeController`** (confirmed reading the complete 53-line controller). All four 500 with "Call to undefined method" when hit. This is architecturally consistent with the module having no underlying table to write to in the first place — there was never a sensible `store`/`update`/`destroy` to implement here, since the "degree" values are free-text answers owned by `Enrollment`, not first-class `StudentDegree` records.

---

## `GET /api/v1/degrees` (`index`, route name `degrees.index`)
- **Request params (all optional, no FormRequest, read via `request()` inside the repository):**
  - `search` — free text; applied as `WHERE answer LIKE %search%` (combined with the fixed question-text filter, always applied, see below).
  - `offset` — optional int, default `0`.
  - `limit` — optional int, default `10`.
- **Query logic (`getAllStudentDegree()`):** always filters to rows whose related `question.question` text `LIKE '%What are the educational degrees and diplomas that you hold?%'` (via `whereRelation`), selects only the `answer` column with `->distinct('answer')`, applies `offset`/`limit`, and returns the raw `answer` strings.
- **Response reshaping in the controller (not the Resource layer — no Resource class is used here at all):**
  ```php
  $data['data'] = $this->studentDegreeRepo->getAllStudentDegree()
      ->pluck('answer')->flatten()
      ->map(function ($answer) {
          $array = explode(',', $answer);
          foreach ($array as $data) {
              return ['Degree' => $data];
          }
      })
      ->unique('Degree')->values();
  $data['meta'] = ['total' => $this->studentDegreeRepo->searchDegreeCount()];
  return response($data);
  ```
  - **⚠️ Confirmed bug — the comma-split is a no-op beyond the first token.** The `foreach ($array as $data) { return [...]; }` loop **returns unconditionally on its first iteration**, regardless of how many comma-separated values `explode(',', $answer)` produced. If a student's free-text answer is `"B.Tech,MBA"`, only `{"Degree": "B.Tech"}` is emitted for that row — `"MBA"` is silently dropped, never surfacing as its own list entry. The variable name (`$array`) and the `explode(',', ...)` call strongly suggest the original intent was to flatten each multi-degree answer into multiple list entries (there's even a commented-out `Str::replace(', ', ',', $answer)` line hinting at an attempt to normalize `", "` vs `","` separators before this), but as written, **every answer effectively contributes at most its first comma-segment** to the final list. A parity test reproducing this exactly must NOT split multi-value answers into multiple `Degree` entries — only the substring before the first comma (or the whole string, if no comma) should appear.
  - **`explode(',', null)` on a `null` answer:** PHP 8.1+ raises a deprecation notice (not an error) for passing `null` where `string` is type-hinted, and treats it as `""`, so a `null`/empty answer yields `{"Degree": ""}` in the output rather than being skipped — confirm the app's error-reporting config swallows deprecation notices in the response (it does not affect the JSON body either way, just worth knowing a null answer is NOT filtered out, and DOES currently produce a literal empty-string degree entry that "distinct"/"unique" will de-duplicate down to at most one `{"Degree": ""}` row).
  - `->unique('Degree')` dedupes by the (already truncated) first-token value.
- **Success response shape:** `response($data)` where `$data = ['data' => [...], 'meta' => ['total' => N]]` — Laravel's `response()` helper auto-JSON-encodes a plain array (via `Illuminate\Http\Response::shouldBeJson()`), HTTP 200, `Content-Type: application/json`. **This is a hand-rolled shape with no `message`/`status` key at all** — matches the "resource-collection" pagination family's `{"data":[...], "meta":{"total":N}}` shell superficially, but is NOT built via a Resource class or either `apiResponse()` helper; it's assembled by hand in the controller.
- **⚠️ `meta.total` does not match `data.length`:** `searchDegreeCount()` counts **distinct raw `answer` rows** matching the question filter (and `search`, if present) — it counts the *pre-split* answers, not the post-processing `Degree` entries the buggy map/unique pipeline above actually produces. Given the first-token-only bug, `data.length` (deduped first-tokens) and `meta.total` (distinct full raw answers) will very likely diverge — **do not assume `meta.total == count(data)`** on this endpoint.

## `GET /v1/search/degrees` (`search`, route name `degrees.search`)
- **Request params:** same `search`/`offset`/`limit` semantics as `index`, applied inside `searchStudentDegree()` — same fixed question-text `whereRelation` filter, plus an additional optional `count` query param (`->limit(request('count'))` if present, which **overrides** rather than composes with the `offset`/`limit` pair used elsewhere — an inconsistent third pagination knob unique to this method).
- **Success response:** `$this->apiResponse($this->studentDegreeRepo->searchStudentDegree())` → `{"data": [...], "message": "Success", "status": "success"}`. **Not deduped, not reshaped, not a Resource** — raw `EnrollmentQuestionAnswer` model rows with the full default column set (`id`, `user_type`, `student_id`, `question_id`, `answer`, `is_other`), i.e. every matching raw answer row, including duplicates and multi-degree comma strings un-split.
- **Notes:** `search()`'s response shape (raw `EnrollmentQuestionAnswer` rows, `{Degree: ...}` never appears) is **entirely different** from `index()`'s (deduped, mis-split `{"Degree": "..."}` list) despite both querying the same underlying data with a very similar `search` filter — a parity test must treat these as two independent, non-interchangeable contracts, not two views of the same list.

---

## Summary

**Routes documented:** 2 `Route::` declarations (1 explicit `search` + 1 `apiResource` contributing 5 action bindings) → **7 total route registrations, only 2 reachable as real endpoints** (`index`, `search`); `store`/`show`/`update`/`destroy` 500 with "Call to undefined method."

**Notable findings for parity testing:**
- **Confirmed bug:** `index()`'s comma-split-then-`foreach`-return pattern only ever keeps the first comma-segment of a multi-value answer — not a real "split into multiple entries" as the code's shape suggests.
- **Confirmed bug/inconsistency:** `index()`'s `meta.total` is computed from a different (pre-split, not-mapped) query than what `data` actually contains — expect them to diverge whenever any answer contains a comma.
- `index()` and `search()` return structurally unrelated shapes over the same underlying `EnrollmentQuestionAnswer` rows — `index` is a hand-built, deduped, bug-truncated `{Degree: ...}` list; `search` is raw, undeduped model rows via the standard `apiResponse()` envelope.
- This module has no table, no entity, no migration of its own — it is entirely a filtered view into `Enrollment`'s `enrollment_question_answers` table, keyed off a hardcoded question-text string match (`WHERE question LIKE '%What are the educational degrees and diplomas that you hold?%'`) rather than a stable `question_id` — a change to that question's wording in the `Enrollment` module's seed/admin data would silently break this module's filter with no error, just an empty result set.
- `search()`'s extra `count` query param is a third, undocumented-elsewhere pagination knob (`->limit(request('count'))`) layered on top of the already-present `offset`/`limit`, unique to this repository method — not seen in the sibling `StudentUniversity` module's `search()`... actually it IS also present there (see `StudentUniversity.md`), but not in any other module documented so far in this wave.

**Confidence:** High — every behavior traced directly from the complete `StudentDegreeController.php`, `StudentDegreeRepository.php`, and its interface. The `foreach`-returns-on-first-iteration bug and the `meta.total`/`data.length` mismatch were independently re-verified by reading the exact map-callback body and comparing it against the separate `searchDegreeCount()` query, not inferred from variable naming.
