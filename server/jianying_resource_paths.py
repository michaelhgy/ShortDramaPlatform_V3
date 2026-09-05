"""Optional paths for Jianying resources that the editor can hydrate on open."""

from __future__ import annotations

from pathlib import Path


def latest_cached_payload(root: Path) -> Path | None:
    """Return the newest local payload directory, if this Windows user has one.

    A missing cache is not a generation error: drafts retain the resource ID and
    Jianying is responsible for downloading the resource when it opens them.
    """
    if not root.is_dir():
        return None
    payloads = [item for item in root.iterdir() if item.is_dir()]
    if not payloads:
        return None
    return max(payloads, key=lambda item: item.stat().st_mtime)


def attach_cached_path_if_present(material: dict[str, object], root: Path) -> Path | None:
    """Reuse a compatible local cache without making it a hard prerequisite."""
    payload = latest_cached_payload(root)
    if payload is None:
        material.pop("path", None)
    else:
        material["path"] = payload.as_posix()
    return payload
