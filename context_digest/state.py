"""Tiny JSON state store — the 'memory' that makes deltas possible.

Holds, per competitor set: the last run time, the news item IDs already
seen, and a content hash per tracked page. This is the whole state layer
that lets a run answer "what's new since last time."
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save(path: str, state: dict) -> None:
    state["updated_at"] = _now()
    Path(path).write_text(json.dumps(state, indent=2, default=str))


def is_seeded(state: dict) -> bool:
    return bool(state) and "last_run_at" in state
