"""The endpoint manifest — one Endpoint entry per operation to compare.

HOW TO ADD AN ENDPOINT (do this as each one lands per docs/PROGRESS.md):
    1. Look up the documented request/response shape in
       AP-V3/AP-V2 Reference Documentation/API_SPECIFICATIONS.md.
    2. Add an Endpoint(...) below. legacy_path/v3_path are almost always identical —
       the compatibility mandate (CLAUDE.md, MIGRATION_PLAN.md §2 principle 5) means a
       genuine path difference here is itself a finding worth a diff, not something to
       paper over.
    3. If a field is legitimately non-deterministic across the two systems/runs
       (timestamps, request IDs, independently-minted surrogate keys), list its dotted
       path in ignore_fields rather than skipping the endpoint's body diff entirely.
    4. Run: python -m scripts.api_parity_check.cli --endpoint <name>

NOTE on /health: AP-V3's `/health` is operational infrastructure with no route on the
legacy Laravel side at all (checked: no `health` route in either `routes/` or `Modules/`)
— so it has nothing to compare against and does not belong in this manifest. Use
`--ping` (see cli.py) to just check both UAT deployments are reachable at all before
running real comparisons; that's a separate, cruder check than what's below.

The one seeded entry is `countries` — a real ported endpoint documented in
API_SPECIFICATIONS.md §2 ("Reference/Lookup Data"). It requires an admin (`auth:sanctum`)
token and, per docs/PROGRESS.md, AP-V3 hasn't built Phase 1 (Identity/Auth) yet — so
running this today is *expected* to fail on the v3 side (no route/no auth). That's the
harness working correctly, not a bug: it's here as a worked template to copy once each
endpoint actually lands, not as a claim that parity already holds.
"""

from __future__ import annotations

from .models import Endpoint

ENDPOINTS: list[Endpoint] = [
    Endpoint(
        name="countries",
        method="GET",
        legacy_path="/v1/search/countries",
        v3_path="/v1/search/countries",
        description=(
            "Reference/lookup data (API_SPECIFICATIONS.md §2). Legacy always prepends a "
            "hardcoded India row (id:99) and filters any real id:99 row — if v3 ever diffs "
            "only on that one row, that's the known landmine, not a new bug."
        ),
        auth="admin",
        # 'meta.total' can legitimately differ if the two DBs aren't seeded identically;
        # uncomment once you've confirmed the UAT seed data actually matches row-for-row.
        # ignore_fields=("meta.total",),
    ),
]


def get_endpoint(name: str) -> Endpoint:
    for ep in ENDPOINTS:
        if ep.name == name:
            return ep
    known = ", ".join(ep.name for ep in ENDPOINTS)
    raise KeyError(f"No endpoint named {name!r} in the manifest. Known endpoints: {known}")
