"""CLI for the UAT parity checker.

Usage (from the AP-V3 repo root):
    ENV=scripts/api_parity_check/parity_check.env
    python -m scripts.api_parity_check.cli --env-file $ENV --all
    python -m scripts.api_parity_check.cli --env-file $ENV --endpoint countries
    python -m scripts.api_parity_check.cli --env-file $ENV --ping
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

from .config import ConfigError, SystemConfig, load_config, load_env_file
from .endpoints import ENDPOINTS, get_endpoint
from .report import print_console_report, write_curl_files, write_json_report
from .runner import run_endpoint


def _ping(legacy: SystemConfig, v3: SystemConfig) -> int:
    ok = True
    with httpx.Client() as client:
        for system, path in ((legacy, "/"), (v3, "/health")):
            url = f"{system.base_url}{path}"
            try:
                resp = client.get(url, timeout=10.0)
                print(f"{system.label}: {url} -> HTTP {resp.status_code}")
            except httpx.HTTPError as exc:
                ok = False
                print(f"{system.label}: {url} -> UNREACHABLE ({exc})")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=None, help="Path to a KEY=VALUE env file")
    parser.add_argument(
        "--endpoint", action="append", default=[], help="Run only this endpoint (repeatable)"
    )
    parser.add_argument("--all", action="store_true", help="Run every endpoint in the manifest")
    parser.add_argument(
        "--ping", action="store_true", help="Just check both UAT base URLs are reachable"
    )
    parser.add_argument(
        "--json-report", type=Path, default=None, help="Write full results as JSON here"
    )
    parser.add_argument(
        "--save-curl",
        type=Path,
        default=None,
        help="Write each side's curl command to files in this dir",
    )
    args = parser.parse_args(argv)

    if args.env_file:
        load_env_file(args.env_file)

    try:
        legacy, v3 = load_config()
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2

    if args.ping:
        return _ping(legacy, v3)

    if args.all:
        selected = list(ENDPOINTS)
    elif args.endpoint:
        try:
            selected = [get_endpoint(name) for name in args.endpoint]
        except KeyError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    else:
        parser.error("pass --all, --endpoint NAME (repeatable), or --ping")
        return 2  # unreachable, argparse exits, keeps type-checkers happy

    with httpx.Client() as client:
        results = [run_endpoint(ep, legacy, v3, client) for ep in selected]

    print_console_report(results)
    if args.json_report:
        write_json_report(results, args.json_report)
        print(f"JSON report written to {args.json_report}")
    if args.save_curl:
        write_curl_files(results, args.save_curl)
        print(f"curl commands written to {args.save_curl}")

    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
