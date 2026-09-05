"""Data shapes shared across the parity checker."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

AuthRole = Literal["none", "admin", "student"]


@dataclass(frozen=True)
class Endpoint:
    """One logical operation to compare across both systems.

    `legacy_path` and `v3_path` are usually identical (that's the whole point of the
    compatibility mandate — MIGRATION_PLAN.md §2 principle 5) but are kept separate so a
    still-unmigrated path difference can be recorded explicitly instead of silently
    passing/failing.
    """

    name: str
    method: str
    legacy_path: str
    v3_path: str
    description: str = ""
    auth: AuthRole = "none"
    query: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    json_body: dict[str, Any] | None = None
    # Dotted paths (e.g. "data.updated_at", "meta.request_id") into the JSON response body
    # that are expected to legitimately differ between the two systems/runs — timestamps,
    # request IDs, DB-assigned surrogate keys minted independently in each environment, etc.
    # Excluded from both the body diff and the curl body comparison.
    ignore_fields: tuple[str, ...] = ()


@dataclass
class RequestResult:
    ok: bool
    status_code: int | None
    headers: dict[str, str]
    body: Any
    curl: str
    error: str | None = None


@dataclass
class ComparisonResult:
    endpoint: Endpoint
    legacy: RequestResult
    v3: RequestResult
    status_match: bool
    body_diffs: list[str]
    curl_diffs: list[str]

    @property
    def passed(self) -> bool:
        return (
            self.legacy.ok
            and self.v3.ok
            and self.status_match
            and not self.body_diffs
            and not self.curl_diffs
        )
