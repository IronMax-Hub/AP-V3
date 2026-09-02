# StudentNotifications

Student-facing surface for reading/interacting with notifications — marking read, commenting, unread counts/bell dropdown, tag list, and the full listing feed. It reads/writes the **same underlying tables** as the admin-facing `Notification` module (`notification`, `notification_user`, `notification_comments`, `notification_tag`, etc.) — these two modules are two front-ends onto one shared data store, not independent systems. See [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md) for shared envelope/error/pagination conventions.

**Module-wide auth:** all 8 route registrations are under `Route::middleware(['auth:student', 'json.response'])->prefix('v1')`. Per Laravel's base `Authenticate` middleware, a successful `auth:student` check calls `Auth::shouldUse('student')`, which rebinds the *default* guard for the remainder of the request — so the plain `auth()->user()` calls used throughout this module's trait (as opposed to the explicit `auth('student')->user()` used in a few methods) correctly resolve to the authenticated `Student`, not to the app's actual configured default guard (`web`). Confirmed by reading `config/auth.php` (`defaults.guard => 'web'`) and Laravel's `Illuminate\Auth\Middleware\Authenticate::authenticate()` (`$this->auth->shouldUse($guard)` on success) — not a bug, just worth knowing why the shorthand works here.

The controller (`StudentNotificationsController`) is a pure shell — `use StudentNotificationsTrait;` and nothing else; every method documented below physically lives in `Modules/StudentNotifications/Http/Traits/StudentNotificationsTrait.php`.

---

## `POST /v1/student/notifications/mark-as-read` (route name `student/notifications`)
- **Trait method:** `markAsRead()`. **No FormRequest, no `Request` parameter at all** — reads `json_decode(file_get_contents('php://input'), true)` directly.
- **Request params (body):** `id` (optional) — a single notification id. If present, marks only that notification read for the caller; if absent, marks **all** of the caller's notifications read.
- **Behavior:** `id` present → `StudentNotificationsRepository::markSingleAsRead(auth()->user()->id, $input['id'])` → `NotificationUser::where('user_id', $studentId)->where('notification_id', $id)->update(['read_at' => now, 'new_comments' => 0])`. `id` absent → `markAllAsRead()` → same update but scoped only by `user_id` (every notification row for this student).
- **Response — identical regardless of outcome:** `{"status": 1, "data": [], "error": null}`, HTTP 200. ⚠️ The `if ($update) {...} else {...}` branch in source produces the **exact same array in both branches** — there is no way to distinguish "a row was actually updated" from "the update query matched zero rows" (e.g. a non-existent `id`) from this response alone. Per `_COMMON_CONVENTIONS.md`'s cross-cutting caution: a 2xx here is not proof anything was actually marked read.
- **Authorization note:** no ownership check beyond the `user_id` scoping on the query — but since the query itself filters by `auth()->user()->id`, a caller cannot mark a different student's notification directly through this parameter (the filter uses the caller's own id, not a caller-supplied student id). No cross-student leakage here.
- **Side effects:** none beyond the DB update.

## `POST /v1/student/notifications/store-comment` (route name `student/notifications/store-comment`)
- **Trait method:** `storeComment()`. **No FormRequest** — same raw `php://input` JSON decode pattern.
- **Request params (body):** `notification_id` (required, used as FK), `parent_id` (required — pass `null` explicitly for a top-level comment, since the code does `$notificationComment->parent_id = $input['parent_id']` unconditionally with no `isset` guard — a request body missing the `parent_id` key entirely throws an undefined-array-key warning, not a clean validation error), `comment` (required string).
- **Behavior**, inside `DB::transaction`:
  1. Creates a `NotificationComment` row (`user_type = NotificationComment::USER_TYPE_2` = `'student'`, `created_by = auth()->user()->id`).
  2. Re-reads the notification's own `new_comments` count and **writes that same unchanged value back** to `notification.new_comments` — a no-op update (`$comment_count['new_comments']` is never incremented before being re-saved).
  3. ⚠️ **Confirmed bug** (matches `API_SPECIFICATIONS.md`'s flag): updates `NotificationUser` via `->where('notification_id', $input['notification_id'])->where('user_id', $input['notification_id'])` — the **second `where` reuses the notification id as if it were the user id**, not `auth()->user()->id`. In practice this only touches a `NotificationUser` row where `user_id` happens to numerically equal the notification's id (coincidental, not intentional) — for any other case this update matches zero rows and silently no-ops. The comment mail badge / "new_comments" reset for the actual recipient(s) is effectively never applied by this line.
  4. Dispatches `CreateNotificationCommentStudent::dispatch($notification_id, $data, auth()->user())` (queued job — presumably notifies admin(s) of the new student comment; not traced further here, out of this module's own files).
  5. The mail-to-thread-participants block (looping `NotificationComment::where('notification_id', ...)->groupBy('created_by')->get()` and emailing each via `CreateNotificationCommentMail`) is **fully commented out in source** — dead/disabled code, not a live side effect despite the imported `Mail`/`CreateNotificationCommentMail` classes.
- **Success:** `{"data": <new comment's id>, "error": null, "status": 1}`, HTTP 200.
- **Notes:** no validation at all on any field — a request missing `comment` will fail with a PHP undefined-array-key notice at `$data['comment']` inside the transaction (not a clean 422).

## `GET /v1/student/notifications/get-all-comment/{notification_id}` (route name `student.notifications.get-all-comment`)
- **Trait method:** `getAllComments($notification_id, $parent_id = null)` — `$parent_id` has no way to be supplied by this route (the URI only captures `{notification_id}`), so it is always `null` in practice, meaning this endpoint only ever returns **top-level** comments for the notification (see `getSubComments()` below for how nested replies actually get attached).
- **Request params (path):** `notification_id`.
- **Behavior:** fetches `NotificationComment` rows via the repository (`where notification_id = ..., where parent_id = null, where deleted_at = null` — the `deleted_at` check is redundant with the model's own `SoftDeletes` global scope, but harmless), wrapped in `NotificationCommentsResource::collection(...)`. **Side effect:** also calls `markSingleAsRead(auth()->user()->id, $notification_id)` — viewing a notification's comment thread implicitly marks that notification read for the caller.
- **`NotificationCommentsResource` shape** (all raw `notification_comments` columns except `created_at`/`updated_at`, which are recomputed): `created_at` (`Y-m-d H:i:s`), `updated_at` (always `null`, hardcoded — not the real timestamp), `admin_id`/`admin_name` (populated only when `user_type !== 'student'`, i.e. an admin-authored comment, via the `user` relation), `student_id`/`student_name` (populated for any `user_type` **other than** `'admin'` — so both a genuine student comment and any future non-admin/non-student `user_type` value would fall into this branch; via the `student` relation), `sub_comments` — **recursively** resolved via `app(StudentNotificationsController::class)->getSubComments($this->notification_id, $this->id)`, i.e. every comment's replies are fetched with a fresh query per comment (N+1 pattern, one extra query per comment in the thread).
- **Empty result:** `{"status": 1, "data": [], "error": null}` (explicit branch, though functionally identical to what an empty Resource collection would already serialize to).
- **Non-empty result:** `{"status": 1, "error": null, "data": <NotificationCommentsResource collection>}` — note the key order differs (`error` before `data`) from the empty-result branch; both parse identically as JSON, but exact byte-order-sensitive snapshot tests would see a difference.

## `GET /v1/getAllNotificationCount/unread` (route name `student.getUnreadNotification`)
- **Trait method:** `getUnread()`. No params.
- **Behavior:** `Notification::whereRelation('user_notification', fn($q) => $q->where('user_id', auth('student')->user()->id)->where('read_at', null))->get()`, then returns the **count** of matching notifications.
- **Response:** `{"data": <int count>, "error": null, "status": 1}`, HTTP 200. Note `data` is a bare integer, not an object/array.

## `GET /v1/bellNotification/unread` (route name `student.getUnreadDetails`)
- **Trait method:** `getUnreadDetails()`. No params. Same base query as `getUnread()` (unread notifications for the caller via the `user_notification` relation), then per row: looks up `NotificationCategory` for `colour`, counts `NotificationComment` rows for `new_comments`, looks up the `NotificationUser` row for `read_at` (redundant re-fetch — the outer query already filtered on `read_at = null`, so this will always be `null`), and the first `NotificationTag`/`NotificationTags` pair for `tagTitle`.
- **Response (non-empty):** `{"data": [{"id","title","content","colour","new_comments","read_at","sent_at","tagTitle"}, ...], "error": null, "status": 1}`. **Empty:** `{"data": [], "error": null, "status": 1}`.
- **Notes:** N+1 query pattern (4 extra queries per notification row); `tagTitle` is `null` if the notification has no tag row at all (`$not_tag = ''` fallback then `?->title` — actually resolves to `null` since `''` has no `->title` property access via null-safe operator... more precisely: `$not_tag` is the *string* `''` when no tag exists, and `$not_tag->title ?? null` on a string triggers a warning and evaluates to `null` via the `??` coalesce, since accessing a property on a non-object emits a warning but returns `null`).

## `GET /v1/getALlNotificationTags` (route name `student.getTags`, note the route URI's literal mixed-case typo `getALlNotificationTags` — preserved verbatim, it is the real path)
- **Trait method:** `getTags()`. No params.
- **Behavior:** `NotificationTags::all()`, mapped to a flat array of just the `title` strings (no `id`).
- **Response:** `{"data": ["<title>", ...], "error": null, "status": 1}` (or `{"data": [], ...}` if none exist — both branches are functionally identical here, unlike some of this module's other "empty" branches).

## `GET /v1/getAllNotification` (route name `student.getAllNotification`)
- **Trait method:** `getAllNotification()`. **No FormRequest** — all params read via the `request()` helper.
- **Request params (query):** `pagenum` (optional int, 1-based; page size is a **hardcoded constant `20`**, not the `rows`/`cursor` convention used elsewhere in this app — this endpoint has its own bespoke offset-based pagination), `tagVal` (optional, comma-separated list of tag **titles**, not ids — filtered via a `whereRelation('tags.notificationTag', whereIn('title', ...))` chain), `searchVal` (optional, `LIKE '<value>%'` prefix match against `title` only).
- **Behavior:** scopes to notifications where the caller (`auth('student')->user()->id`) has a `user_notification` row (no `read_at`/status filter — this returns read and unread alike), applies the optional tag/search filters, orders by `id DESC`, then manually paginates via `offset()`/`limit()` (two near-identical queries run — one for the page of rows, one uncapped `count()` for the total). Per matched row: resolves `category` (for `colour`, but only if the row is **unread** — `$read_at->read_at` null-check controls whether `colour` is populated or forced to `''`), tag title, package/batch/course names (each a separate lookup keyed off the first matching `PackageNotification`/`BatchNotification`/`CourseNotification` row — a notification associated with multiple courses/batches/packages only ever surfaces the *first* one here).
- **Success (rows found):** `{"data": {"noOfPage": <ceil(count/20)>, "paginations": null, "records": [{"id","title","content","categoryTitle","category_id","colour","batch_id","course_id","created_at","created_by","new_comments","package_id","read_at","scheduled_time","sent_at","start_date": null (hardcoded, never populated from a real column), "tagTitle","updated_at"}], "total_count": <int>}, "error": null, "status": 1}`.
- **No rows:** `{"data": [], "error": null, "status": 1}` — note `data` changes shape entirely (bare empty array vs. the `{noOfPage, paginations, records, total_count}` object on the success path) — a client must not assume a stable `data` shape across both branches.
- **`noOfPage`** is computed from `count($data)` (the **current page's** row count, capped at 20 by the query's own `limit()`), not from the separate `$count_query` total — so `noOfPage` is only ever `1` (`ceil(≤20/20)`) regardless of how many total pages actually exist. This looks like a real bug: the intended `ceil($count_query / 20)` was very likely swapped for `ceil(count($data) / 20)`. Worth a dedicated regression test with >20 matching notifications.

---

## `apiResource('student/notifications', StudentNotificationsController)` — **broken scaffolding, not dead-but-harmless**

Per Laravel's actual `Route::apiResource()` behavior (verified in `vendor/laravel/framework/src/Illuminate/Routing/Router.php`), this registers exactly 5 routes — `index`, `store`, `show`, `update`, `destroy` (apiResource never registers `create`/`edit`, unlike `Route::resource()`):

| Method | URI | Action |
|---|---|---|
| GET | `/v1/student/notifications` | `index` |
| POST | `/v1/student/notifications` | `store` |
| GET | `/v1/student/notifications/{student_notification}` | `show` |
| PUT/PATCH | `/v1/student/notifications/{student_notification}` | `update` |
| DELETE | `/v1/student/notifications/{student_notification}` | `destroy` |

**None of these 5 methods exist anywhere** — not on `StudentNotificationsController` itself, and not on `StudentNotificationsTrait` (confirmed by reading both files in full; the trait only defines `markAsRead`, `storeComment`, `getAllComments`, `getSubComments`, `getUnread`, `getUnreadDetails`, `getTags`, `getAllNotification`). Calling any of these 5 routes throws a PHP `Error` ("Call to undefined method ...StudentNotificationsController::index()", etc.) — an uncaught fatal error, which (depending on `APP_DEBUG` and the exception handler's default rendering for a non-`HttpException` `\Error`) most likely surfaces as an unstyled HTTP 500, **not** any of this app's normal `apiResponse()`/`response()->json()` error shapes. **This is not the same as the "dead scaffolding" pattern seen elsewhere in this codebase** (a Blade `view()` call or an empty-but-callable method body) — it is scaffolding that was never actually implemented, and the routes are only reachable/broken, not silently harmless. Flag all 5 for an explicit "confirm this 500s" boundary test rather than skipping them as inert.

---

## Summary

- **Endpoint count:** 8 route registrations — 7 explicit named routes (all live/functioning) + 1 `apiResource` line contributing 5 further routes, all 5 of which are broken (undefined-method fatal error) rather than functional. Net **7 working endpoints, 5 broken**.
- **Notable bugs/quirks for parity testing:**
  1. `mark-as-read` returns an identical success body whether or not any row was actually updated.
  2. `store-comment`'s `NotificationUser` read-tracking update filters `user_id` by the **notification's own id**, not the calling student's id — confirmed real bug, effectively dead code for read-tracking purposes in the overwhelming majority of cases.
  3. `getAllNotification`'s `noOfPage` is computed from the current page's (max-20) row count rather than the true total — always reports `1` regardless of actual total pages.
  4. The `apiResource('student/notifications', ...)` registration is entirely non-functional — all 5 REST actions are undefined methods, not implemented-but-trivial stubs.
  5. Two of the "empty result" branches (`get-all-comment`, `getAllNotification`) return a **different `data` shape** than their corresponding non-empty branch, not just an empty version of the same shape.
- **Confidence:** High — every endpoint traced directly from `StudentNotificationsController`, the full `StudentNotificationsTrait`, `StudentNotificationsRepository`/its interface, and `NotificationCommentsResource`. The apiResource-is-broken finding was independently confirmed by reading Laravel's own `Router::apiResource()` source (only registers `index`/`show`/`store`/`update`/`destroy`) and grepping both the controller and trait for `store`/`show`/`update`/`destroy`/`index` method definitions (none found).

---

*Companion documents: [`./_COMMON_CONVENTIONS.md`](./_COMMON_CONVENTIONS.md), [`./Notification.md`](./Notification.md) (the admin-facing side of the same underlying tables), [`../API_SPECIFICATIONS.md`](../API_SPECIFICATIONS.md) §5 (original pass, cross-referenced above).*
