"""UAT endpoint/credential config, loaded from environment variables.

No new dependency is pulled in for this (no python-dotenv) — `load_env_file` below is a
deliberately tiny `.env`-style parser so `--env-file` keeps working without adding a package
for something ~15 lines of stdlib code covers. Real secrets belong in your shell/CI secrets
store, not committed anywhere; `parity_check.env.example` documents the variable names only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_env_file(path: Path) -> None:
    """Populate os.environ from a simple KEY=VALUE file, without overriding vars already set."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class SystemConfig:
    label: str
    base_url: str
    admin_token: str | None
    student_token: str | None

    def token_for(self, role: str) -> str | None:
        if role == "admin":
            return self.admin_token
        if role == "student":
            return self.student_token
        return None


class ConfigError(RuntimeError):
    pass


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(
            f"Missing required env var {name}. Copy parity_check.env.example to "
            "parity_check.env, fill it in, and pass --env-file parity_check.env "
            "(or export the vars yourself)."
        )
    return value.rstrip("/")


def load_config() -> tuple[SystemConfig, SystemConfig]:
    """Read LEGACY_* / AP_V3_* env vars. Tokens are optional — only required for
    endpoints whose `auth` field actually needs them; `_require` is only applied to
    the base URLs, which every run needs."""
    legacy = SystemConfig(
        label="Lawsikho-Assignment-Portal-API (AP-V2, UAT)",
        base_url=_require("LEGACY_BASE_URL"),
        admin_token=os.environ.get("LEGACY_ADMIN_TOKEN") or None,
        student_token=os.environ.get("LEGACY_STUDENT_TOKEN") or None,
    )
    v3 = SystemConfig(
        label="AP-V3 (UAT)",
        base_url=_require("AP_V3_BASE_URL"),
        admin_token=os.environ.get("AP_V3_ADMIN_TOKEN") or None,
        student_token=os.environ.get("AP_V3_STUDENT_TOKEN") or None,
    )
    return legacy, v3
