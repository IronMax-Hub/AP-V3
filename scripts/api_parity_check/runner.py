"""Fires one Endpoint at both systems and produces a ComparisonResult."""

from __future__ import annotations

import httpx

from .config import SystemConfig
from .curl_builder import build_curl, diff_curls
from .diff import diff_json
from .models import ComparisonResult, Endpoint, RequestResult

TIMEOUT_SECONDS = 20.0


def _headers_for(endpoint: Endpoint, system: SystemConfig) -> dict[str, str]:
    headers = dict(endpoint.headers)
    headers.setdefault("Accept", "application/json")
    if endpoint.auth != "none":
        token = system.token_for(endpoint.auth)
        if not token:
            raise RuntimeError(
                f"Endpoint {endpoint.name!r} needs a {endpoint.auth} token for "
                f"{system.label}, but none is set (see parity_check.env.example)."
            )
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _call(
    endpoint: Endpoint, path: str, system: SystemConfig, client: httpx.Client
) -> RequestResult:
    url = f"{system.base_url}{path}"
    try:
        headers = _headers_for(endpoint, system)
    except RuntimeError as exc:
        return RequestResult(
            ok=False, status_code=None, headers={}, body=None, curl="", error=str(exc)
        )

    curl = build_curl(endpoint.method, url, headers, endpoint.json_body)
    try:
        response = client.request(
            endpoint.method,
            url,
            params=endpoint.query or None,
            headers=headers,
            json=endpoint.json_body,
            timeout=TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        return RequestResult(
            ok=False, status_code=None, headers=dict(headers), body=None, curl=curl, error=str(exc)
        )

    try:
        body: object = response.json()
    except ValueError:
        body = response.text

    return RequestResult(
        ok=True,
        status_code=response.status_code,
        headers=dict(response.headers),
        body=body,
        curl=curl,
    )


def run_endpoint(
    endpoint: Endpoint, legacy: SystemConfig, v3: SystemConfig, client: httpx.Client
) -> ComparisonResult:
    legacy_result = _call(endpoint, endpoint.legacy_path, legacy, client)
    v3_result = _call(endpoint, endpoint.v3_path, v3, client)

    status_match = (
        legacy_result.ok and v3_result.ok and legacy_result.status_code == v3_result.status_code
    )
    body_diffs = (
        diff_json(legacy_result.body, v3_result.body, endpoint.ignore_fields)
        if legacy_result.ok and v3_result.ok
        else []
    )
    curl_diffs = (
        diff_curls(legacy_result.curl, v3_result.curl)
        if legacy_result.curl and v3_result.curl
        else []
    )

    return ComparisonResult(
        endpoint=endpoint,
        legacy=legacy_result,
        v3=v3_result,
        status_match=status_match,
        body_diffs=body_diffs,
        curl_diffs=curl_diffs,
    )
