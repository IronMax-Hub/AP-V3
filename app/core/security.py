"""Sanctum-compatible Personal Access Token auth scaffolding.

Decided design: Docs/MIGRATION_PLAN.md §6. Two guards (admin, student), same
token mechanism, wire-compatible with AP-V2's `Authorization: Bearer
{id}|{token}` format so existing clients need no changes.

Phase 0 only wires the *shape* of this — header parsing, hashing helper, and
the two Depends() entrypoints other routers will use. The actual DB lookup
(the `personal_access_tokens`-equivalent table and its query) lands in Phase 1
alongside the User/Student models it points at; until then both dependencies
correctly parse a token and then fail loudly (501) rather than silently
accepting anything.
"""

import hashlib
from dataclasses import dataclass
from typing import Protocol

from fastapi import Header, HTTPException, status

from app.core.config import get_settings


@dataclass(frozen=True)
class ParsedToken:
    token_id: str
    plaintext: str


def parse_bearer_token(authorization: str | None) -> ParsedToken:
    """Parse an `Authorization: Bearer {id}|{token}` header.

    Raises 401 on anything malformed — missing header, wrong scheme, or a
    value that isn't `id|token`-shaped. Matches AP-V2's Sanctum wire format,
    not a JWT.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User is Unauthenticated")

    raw = authorization.removeprefix("Bearer ").strip()
    token_id, sep, plaintext = raw.partition("|")
    if not sep or not token_id or not plaintext:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User is Unauthenticated")

    return ParsedToken(token_id=token_id, plaintext=plaintext)


def hash_token(plaintext: str) -> str:
    """Hash a token's plaintext half before comparing/storing it.

    Only the hash is ever persisted (MIGRATION_PLAN.md §6) — never the
    plaintext. Keyed with token_hash_secret so a leaked DB dump alone isn't
    enough to forge valid-looking hashes.
    """
    settings = get_settings()
    payload = f"{settings.token_hash_secret}:{plaintext}".encode()
    return hashlib.sha256(payload).hexdigest()


class TokenLookup(Protocol):
    """Implemented in Phase 1 against the real personal_access_tokens table."""

    async def __call__(self, token_id: str, token_hash: str) -> object: ...


async def get_current_admin(authorization: str | None = Header(default=None)):
    """Depends() entrypoint for the admin/staff guard. Phase 1 TODO: wire to
    the real personal_access_tokens lookup, scoped to the admin tokenable
    type, per MIGRATION_PLAN.md §6."""
    parse_bearer_token(authorization)  # validates shape; raises 401 if malformed
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        "Admin auth not implemented yet — lands in Phase 1 (Identity).",
    )


async def get_current_student(authorization: str | None = Header(default=None)):
    """Depends() entrypoint for the student guard. Phase 1 TODO: wire to the
    real personal_access_tokens lookup, scoped to the student tokenable type,
    per MIGRATION_PLAN.md §6."""
    parse_bearer_token(authorization)
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        "Student auth not implemented yet — lands in Phase 1 (Identity).",
    )
