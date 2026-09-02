# AP-V3 Task Assignments

> **Update this file before every commit.** If you start, hand off, or finish a piece of work,
> reflect it here — this is how the other person knows what's claimed without asking. Pairs with
> [`PROGRESS.md`](PROGRESS.md) (what's done) and [`MIGRATION_PLAN.md`](MIGRATION_PLAN.md) §12
> (the reasoning behind how phases split between two people).

**Last updated:** 2026-09-02 · **Team:** Mayukh, Chhandak — both pairing with Claude Code

---

## 1. Right now

| Person | Working on | Started | Status |
|---|---|---|---|
| Mayukh | — | — | Unclaimed |
| Chhandak | — | — | Unclaimed |

*Keep this table current — it's the first thing to check before picking up new work, so you don't
duplicate what the other person already has in flight.*

## 2. How to claim work

1. Check `PROGRESS.md` for an unclaimed, unblocked checklist item.
2. Put your name and what you're taking on in the table above, with today's date.
3. Work it. Check the item off in `PROGRESS.md` as you finish sub-pieces, not just at the end.
4. Before you commit: update `PROGRESS.md` (what changed) and this file (clear your row, or move
   to the next thing).
5. If you get blocked, say so in `PROGRESS.md` §5 (Backlog) rather than leaving your row stale in
   this file — a stale "in progress" row is worse than an honest "blocked, see backlog" note.

## 3. Phase ownership plan

Not a rigid assignment — a starting split based on the coupling/parallelization analysis in
`MIGRATION_PLAN.md` §12. Adjust as you actually start working; update this section when you do,
so it stays true rather than aspirational.

| Phase | Suggested split | Why |
|---|---|---|
| 0 — Foundations | Done (Claude Code pairing session, both) | N/A |
| 1 — Identity | **Both, together, at least for the first slice.** Hard serialization point — nothing else can be built until real auth + `Student`/`User` exist. Do the CryptoJS-AES spike and the token scheme as a single-threaded piece before splitting. Once that's solid, can split: one person on Auth/StudentAuth/RBAC, the other on Student/StudentProfile/Country/State/InternalNotes. | MIGRATION_PLAN.md §12 |
| 2 — Catalog & Enrollment | **Split.** One person on the catalog side (Course/CourseBatch/Package/Bootcamp/Topic/Evaluator), the other on the enrollment side (Enrollment/RevenueAPI/ReferralSystem/the StudentFrontendEnrollment reorg). Sync frequently — this is a real dependency cycle, not two independent halves. | MIGRATION_PLAN.md §5 Phase 2, §12 |
| 3 — Assessment | Single owner + the other as reviewer (small, cohesive pipeline — splitting it adds coordination overhead for little parallelism gain) | MIGRATION_PLAN.md §5 Phase 3 |
| 4 — Communication | **Split.** Independent verticals (each CSAT type, NPS, Notification, EmailTemplate, Webhook) — genuinely parallelizable, near-zero internal coupling. | MIGRATION_PLAN.md §12 |
| 5 — Student Portal (BFF) | Single owner | Aggregation layer, low ambiguity once Phase 1–4 are stable |
| 6 — Integrations | Whoever has slack — **client scaffolding (httpx/authlib wrappers) can start anytime**, real wiring waits on the data it reads | MIGRATION_PLAN.md §5 Phase 6, §12 |

## 4. Decisions/preferences specific to each person

Freeform notes — tooling preferences, areas someone already knows well from AP-V2, availability
constraints. Fill in as it comes up; don't leave this section performative.

### Mayukh
*(nothing recorded yet)*

### Chhandak
*(nothing recorded yet)*

---

## 5. Update log

Append a line each time this file changes — newest first.

- **2026-09-02** — File created, phase-ownership plan drafted from `MIGRATION_PLAN.md` §12. No
  work claimed yet — Phase 1 is next up.
