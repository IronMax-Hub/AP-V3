# StudentUniversity Module API Documentation

The `StudentUniversity` module has **no dedicated database table of its own** — it is a near-identical sibling of `StudentDegree` (see [`./StudentDegree.md`](./StudentDegree.md) for the shared pattern in full detail). It is a read-only view over `Modules\Enrollment\Entities\EnrollmentQuestionAnswer` rows, filtered to answers for the fixed enrollment question `question_id = 78` ("Name of college/university where you obtained a degree from," per the inline comment in source) — used to build a university-name typeahead/dropdown from students' free-text answers.

**Module-wide auth:** both routes in `Modules/StudentUniversity/Routes/api.php` are `auth:sanctum` + `json.response`, mounted under `/api/v1/...`. No deviation.

See [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for the app-wide response envelope styles, standard error shapes, and pagination conventions.

`StudentUniversityController` implements only `index()` and `search()`, no traits. No `Database/Migrations` directory exists in this module (confirmed via filesystem search) — same "borrowed table" architecture as `StudentDegree`.

## ⚠️ `apiResource('universities', 'StudentUniversityController')` — only 2 of 5 wired actions exist (same landmine as `Country`/`State`/`StudentDegree`)

```php
Route::get('/search/universities', [StudentUniversityController::class, 'search'])->name('universities.search');
Route::apiResource('universities', 'StudentUniversityController');
```
`store`, `show`, `update`, `destroy` are registered by `apiResource` but have no method on `StudentUniversityController` (confirmed reading the complete 53-line controller). All four 500 with "Call to undefined method" when hit — this is now the **fourth** module in this wave (`Country`, `State`, `StudentDegree`, `StudentUniversity`) with the identical `apiResource(...)`-registers-5,-only-2-implemented pattern.

## ⚠️ Key difference from `StudentDegree`: filtered by `question_id = 78`, not by question-text `LIKE`

`StudentDegreeRepository` matches its target question via `WHERE question.question LIKE '%<full question text>%'` (a relation join + text match). `StudentUniversityRepository` instead filters directly by `WHERE question_id = 78` — a **hardcoded literal id**, with the human-readable question text only present as a source-code comment (`// 78= Name of college/university where you obtained a degree from`), not enforced or verified against the actual `questions` table at all. This is a real, more brittle variant of the same "coupling to Enrollment's `questions` table via a magic constant" pattern: if that question is ever deleted/re-seeded with a different id in `Enrollment`, this module's filter silently returns nothing (or, worse, silently starts returning answers to a *different*, unrelated question if id `78` gets reassigned) — with zero validation/error either way. **A parity test must confirm the seeded `questions` table's row for id `78` is indeed the "university" question before trusting this module's behavior transfers cleanly.**

---

## `GET /api/v1/universities` (`index`, route name `universities.index`)
- **Request params (all optional, no FormRequest, read via `request()` inside the repository):** `search` (`WHERE answer LIKE %search%`, combined with `question_id = 78`), `offset` (default `0`), `limit` (default `10`).
- **Response reshaping in the controller** — line-for-line the same pattern and the same bug as `StudentDegree::index()`, with only the output key name and repository target differing:
  ```php
  $data['data'] = $this->studentUniversityRepo->getAllStudentUniversity()
      ->pluck('answer')->flatten()
      ->map(function ($answer) {
          $array = explode(',', $answer);
          foreach ($array as $data) {
              return ['university' => $data];  // lowercase key here
          }
      })
      ->unique('university')->values();
  $data['meta'] = ['total' => $this->studentUniversityRepo->searchUniversityCount()];
  return response($data);
  ```
  - **⚠️ Same confirmed bug as `StudentDegree::index()`:** the `foreach`-then-unconditional-`return` only ever keeps the first comma-segment of a multi-value `answer` — a `"Delhi University,IIT Delhi"` answer yields only `{"university": "Delhi University"}`, silently dropping `"IIT Delhi"`.
  - **⚠️ Response-key casing inconsistency vs. `StudentDegree`, confirmed verbatim from source:** this module's key is lowercase `"university"`; `StudentDegree`'s equivalent key is capitalized `"Degree"`. **Not a typo to "correct" — both are load-bearing, real API surface** and must be reproduced with this exact casing per module in AP-V3.
  - Same `explode(',', null)` deprecation-notice-but-not-error behavior on a `null` answer as `StudentDegree`.
- **Success response shape:** `response($data)` → auto-JSON `{"data": [...], "meta": {"total": N}}`, no `message`/`status` key, same as `StudentDegree::index()`.
- **⚠️ Same `meta.total`/`data.length` mismatch risk as `StudentDegree`:** `searchUniversityCount()` counts distinct raw `answer` rows (pre-split), not the post-`map`/`unique` output — expect divergence whenever any answer contains a comma.

## `GET /v1/search/universities` (`search`, route name `universities.search`)
- **Request params:** `search`/`offset`/`limit` as above, plus the same extra `count` query param (`->limit(request('count'))`) seen in `StudentDegree::search()` — overrides rather than composes with `offset`/`limit`.
- **Success response:** `$this->apiResponse($this->studentUniversityRepo->searchStudentUniversity())` → `{"data": [...], "message": "Success", "status": "success"}`. Raw `EnrollmentQuestionAnswer` model rows, full default column set (`id`, `user_type`, `student_id`, `question_id`, `answer`, `is_other`), undeduped, comma strings un-split — not a Resource, not reshaped.
- **Notes:** exactly the same `index()`-vs-`search()` shape divergence documented for `StudentDegree` applies here — treat the two endpoints as non-interchangeable contracts.

---

## Summary

**Routes documented:** 2 `Route::` declarations (1 explicit `search` + 1 `apiResource` contributing 5 action bindings) → **7 total route registrations, only 2 reachable as real endpoints** (`index`, `search`); `store`/`show`/`update`/`destroy` 500 with "Call to undefined method."

**Notable findings for parity testing:**
- **Confirmed bug (shared with `StudentDegree`):** `index()`'s comma-split-then-`foreach`-return only keeps the first comma-segment of a multi-value answer.
- **Confirmed bug (shared with `StudentDegree`):** `index()`'s `meta.total` is computed from a query that doesn't match what `data` actually contains post-processing.
- **Confirmed, module-specific:** filters by hardcoded `question_id = 78` rather than a text match — more brittle than `StudentDegree`'s `LIKE` approach, with the mapping to "university question" documented only as a source comment, never verified at runtime.
- **Confirmed casing inconsistency vs. `StudentDegree`:** response key is lowercase `"university"` here vs. capitalized `"Degree"` there — both must be preserved exactly, not normalized, for parity.
- Like `StudentDegree`, this module owns no table/entity/migration of its own; it's entirely a filtered view into `Enrollment`'s `enrollment_question_answers` table.

**Confidence:** High — every behavior traced directly from the complete `StudentUniversityController.php`, `StudentUniversityRepository.php`, and its interface, and cross-checked line-by-line against the already-verified `StudentDegree` module to confirm which parts are truly identical (the bug pattern, the `count` param, the shape divergence) versus which parts genuinely differ (the `question_id=78` hardcoded filter vs. text-`LIKE`, and the key-casing).
