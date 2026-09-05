"""Standalone UAT parity checker: AP-V3 vs. Lawsikho-Assignment-Portal-API (AP-V2).

See README.md in this folder for setup and usage. Not wired into pytest/CI on purpose —
this is an ad-hoc tool run by hand against real UAT deployments, not a unit/contract test
that runs on every commit (that suite, when it's built, belongs in AP-V3/tests/contract/
per docs/MIGRATION_PLAN.md §11.3).
"""
