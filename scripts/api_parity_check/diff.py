"""Recursive JSON response diffing, with support for ignoring known-volatile fields."""

from __future__ import annotations

from typing import Any


def _matches_ignored(path: str, ignore_fields: tuple[str, ...]) -> bool:
    return any(
        path == pattern or path.startswith((pattern + ".", pattern + "["))
        for pattern in ignore_fields
    )


def diff_json(
    legacy: Any,
    v3: Any,
    ignore_fields: tuple[str, ...] = (),
    _path: str = "",
) -> list[str]:
    """Return human-readable diff lines; empty list means an exact match (modulo
    ignore_fields). Dict key order and list order both count as real differences —
    "exact match" means exact match.
    """
    if _matches_ignored(_path, ignore_fields):
        return []

    root = _path or "<root>"
    if type(legacy) is not type(v3) and not (
        isinstance(legacy, (int, float)) and isinstance(v3, (int, float))
    ):
        return [f"{root}: type differs — legacy={type(legacy).__name__} v3={type(v3).__name__}"]

    if isinstance(legacy, dict):
        diffs: list[str] = []
        prefix = f"{_path}." if _path else ""
        legacy_keys, v3_keys = set(legacy), set(v3)
        for missing in sorted(legacy_keys - v3_keys):
            diffs.append(f"{prefix}{missing}: present in legacy, missing in v3")
        for extra in sorted(v3_keys - legacy_keys):
            diffs.append(f"{prefix}{extra}: present in v3, missing in legacy")
        for key in sorted(legacy_keys & v3_keys):
            diffs += diff_json(legacy[key], v3[key], ignore_fields, f"{prefix}{key}")
        return diffs

    if isinstance(legacy, list):
        diffs = []
        if len(legacy) != len(v3):
            diffs.append(f"{root}: length differs — legacy={len(legacy)} v3={len(v3)}")
        for i, (lv, vv) in enumerate(zip(legacy, v3)):
            diffs += diff_json(lv, vv, ignore_fields, f"{_path}[{i}]")
        return diffs

    if legacy != v3:
        return [f"{root}: legacy={legacy!r} v3={v3!r}"]
    return []
