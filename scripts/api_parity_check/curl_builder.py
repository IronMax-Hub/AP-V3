"""Build the exact curl command used for a request, and compare two such commands
ignoring only what's *expected* to differ between environments (host, token value).
"""

from __future__ import annotations

import json
import shlex
from typing import Any

# Headers that legitimately differ per request/environment and must not be part of an
# "exact match" claim — the point isn't that these are identical, it's that everything
# else (method, path, query params, header *names*, body shape) is.
_VOLATILE_HEADER_NAMES = {"authorization", "cookie", "x-request-id", "date", "host"}


def build_curl(
    method: str,
    url: str,
    headers: dict[str, str],
    json_body: dict[str, Any] | None,
) -> str:
    parts = ["curl", "-sS", "-X", method.upper()]
    for key, value in headers.items():
        parts += ["-H", f"{key}: {value}"]
    if json_body is not None:
        parts += ["-H", "Content-Type: application/json"]
        parts += ["-d", json.dumps(json_body, sort_keys=True, separators=(",", ":"))]
    parts.append(url)
    return " ".join(shlex.quote(p) for p in parts)


def _normalize_for_comparison(curl_cmd: str) -> list[str]:
    """Tokenize a curl command and blank out the pieces that are allowed to differ
    (the URL's scheme+host, and the value of any volatile header/auth token) so what's
    left reflects method, path, query params, header names, and body.
    """
    tokens = shlex.split(curl_cmd)
    normalized: list[str] = []
    expect_header_value = False
    for tok in tokens:
        if expect_header_value:
            name, _, value = tok.partition(":")
            if name.strip().lower() in _VOLATILE_HEADER_NAMES:
                normalized.append(f"{name.strip()}: <redacted>")
            else:
                normalized.append(tok)
            expect_header_value = False
            continue
        if tok == "-H":
            normalized.append(tok)
            expect_header_value = True
            continue
        if tok.startswith("http://") or tok.startswith("https://"):
            # Strip scheme + host, keep path + query string — that's the part that
            # must match exactly between the two systems.
            after_scheme = tok.split("://", 1)[1]
            path_and_query = after_scheme.split("/", 1)
            rest = "/" + path_and_query[1] if len(path_and_query) > 1 else "/"
            normalized.append(rest)
            continue
        normalized.append(tok)
    return normalized


def diff_curls(legacy_curl: str, v3_curl: str) -> list[str]:
    """Return a list of human-readable differences, empty if the two curl commands are
    an exact match once host and auth-token values are normalized away."""
    legacy_norm = _normalize_for_comparison(legacy_curl)
    v3_norm = _normalize_for_comparison(v3_curl)
    if legacy_norm == v3_norm:
        return []
    return [
        "curl commands differ after normalizing host + auth token:",
        f"  legacy (normalized): {' '.join(legacy_norm)}",
        f"  v3     (normalized): {' '.join(v3_norm)}",
    ]
