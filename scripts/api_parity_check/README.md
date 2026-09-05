# UAT parity checker — AP-V3 vs. Lawsikho-Assignment-Portal-API

Standalone CLI (not pytest, not CI-wired) that hits the **same logical request** against both
UAT deployments and checks:

1. **Status codes match.**
2. **Response bodies match exactly** — recursive diff, dict key order and list order count,
   nothing is treated as "close enough" unless you explicitly list it in `ignore_fields`.
3. **The curl command used for both calls matches exactly**, once host and the auth-token
   *value* are normalized out (method, path, query params, header names, body are compared
   literally).

This is a manual/ad-hoc tool run against real UAT, per `docs/MIGRATION_PLAN.md` §11.3's parity
mandate — the automated, runs-on-every-commit contract-test suite (`tests/contract/`, seeded
data, driven by the same `API_SPECIFICATIONS.md`) is a separate, not-yet-built piece of work.

## Status right now

AP-V3 has only shipped `/health` so far (`docs/PROGRESS.md`: Phase 1 — Identity not started).
`/health` has **no legacy counterpart** (checked: no `health` route anywhere in the Laravel
app), so it's not in the comparison manifest — use `--ping` for a bare connectivity check
instead. The one seeded manifest entry, `countries`, is a real documented endpoint
(`API_SPECIFICATIONS.md` §2) that AP-V3 hasn't built yet, so running it today is *expected* to
report a v3-side failure. That's correct behavior, not a bug — it's here as a working template
to copy from as each endpoint actually lands.

## Setup

```
cp scripts/api_parity_check/parity_check.env.example scripts/api_parity_check/parity_check.env
# edit parity_check.env: fill in LEGACY_BASE_URL / AP_V3_BASE_URL and whatever tokens the
# endpoints you're running need. It's already gitignored — never commit real tokens.
```

Tokens: mint a real UAT admin/student Bearer token by logging in against each UAT deployment's
own `/v1/login` (or student login flow) and pasting the token in. Nothing here logs in for you
yet — AP-V3 doesn't have that endpoint built.

## Usage

```
# Check both UAT URLs are actually reachable before anything else
python -m scripts.api_parity_check.cli --env-file scripts/api_parity_check/parity_check.env --ping

# Run everything in the manifest
python -m scripts.api_parity_check.cli --env-file scripts/api_parity_check/parity_check.env --all

# Run one endpoint by name (repeatable)
python -m scripts.api_parity_check.cli --env-file scripts/api_parity_check/parity_check.env --endpoint countries

# Also write a full JSON report and both sides' curl commands to disk
python -m scripts.api_parity_check.cli --env-file scripts/api_parity_check/parity_check.env --all \
  --json-report scripts/api_parity_check/reports/latest.json \
  --save-curl scripts/api_parity_check/reports/curl
```

Exit code is `0` only if every selected endpoint passed — safe to wire into a script/CI gate
later without parsing console output.

## Adding an endpoint

See the docstring at the top of `endpoints.py`. Short version: look up the shape in
`API_SPECIFICATIONS.md`, add an `Endpoint(...)` entry, list any legitimately-volatile response
fields (timestamps, request IDs, independently-minted surrogate keys) in `ignore_fields`, run it.

## Files

| File | Purpose |
|---|---|
| `models.py` | `Endpoint` / `RequestResult` / `ComparisonResult` dataclasses |
| `config.py` | env-var loading (`LEGACY_*` / `AP_V3_*`), tiny `.env`-file parser |
| `endpoints.py` | the manifest — add entries here |
| `curl_builder.py` | builds the exact curl string per call; normalizes + diffs the two |
| `diff.py` | recursive JSON response diff with `ignore_fields` support |
| `runner.py` | fires one endpoint at both systems, builds a `ComparisonResult` |
| `report.py` | console printer + JSON report + curl-file writer |
| `cli.py` | argparse entrypoint |
