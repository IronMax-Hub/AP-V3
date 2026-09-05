"""Console + JSON reporting for a batch of ComparisonResults."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .models import ComparisonResult

_GREEN = "\033[32m"
_RED = "\033[31m"
_RESET = "\033[0m"


def print_console_report(results: list[ComparisonResult]) -> None:
    for result in results:
        status = f"{_GREEN}PASS{_RESET}" if result.passed else f"{_RED}FAIL{_RESET}"
        header = f"{result.endpoint.method} {result.endpoint.legacy_path}"
        print(f"\n[{status}] {result.endpoint.name}  ({header})")

        if not result.legacy.ok:
            print(f"  legacy request failed: {result.legacy.error}")
        if not result.v3.ok:
            print(f"  v3 request failed: {result.v3.error}")
        if result.legacy.ok and result.v3.ok:
            print(f"  status: legacy={result.legacy.status_code} v3={result.v3.status_code}"
                  f"{'' if result.status_match else '  <-- MISMATCH'}")
            if result.body_diffs:
                print("  body diffs:")
                for line in result.body_diffs:
                    print(f"    - {line}")
            if result.curl_diffs:
                print("  curl mismatch:")
                for line in result.curl_diffs:
                    print(f"    {line}")
            if not result.body_diffs and not result.curl_diffs:
                print("  body + curl: exact match")

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    print(f"\n{passed}/{total} endpoint(s) passed.\n")


def write_json_report(results: list[ComparisonResult], path: Path) -> None:
    payload = []
    for r in results:
        payload.append(
            {
                "endpoint": r.endpoint.name,
                "method": r.endpoint.method,
                "legacy_path": r.endpoint.legacy_path,
                "v3_path": r.endpoint.v3_path,
                "passed": r.passed,
                "status_match": r.status_match,
                "legacy": asdict(r.legacy),
                "v3": asdict(r.v3),
                "body_diffs": r.body_diffs,
                "curl_diffs": r.curl_diffs,
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def write_curl_files(results: list[ComparisonResult], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for r in results:
        legacy_path = out_dir / f"{r.endpoint.name}.legacy.curl.sh"
        v3_path = out_dir / f"{r.endpoint.name}.v3.curl.sh"
        legacy_path.write_text(r.legacy.curl + "\n", encoding="utf-8")
        v3_path.write_text(r.v3.curl + "\n", encoding="utf-8")
