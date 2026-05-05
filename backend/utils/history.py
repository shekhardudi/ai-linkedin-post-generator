"""Append-only JSONL manifest of finalized post runs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backend.core.paths import history_path


def append_run(record: dict[str, Any]) -> None:
    """Append one record. Caller is responsible for the schema below.

    Schema:
      {
        "run_id": str,
        "created_at": ISO8601 str,
        "topic": str,
        "leader_angle": str,
        "audience": str,                     # "engineering" | "business"
        "post_path": str | None,
        "image_paths": list[str],
        "cost_breakdown": dict | None,
        "models": dict[str, str] | None,
      }
    """
    record.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    line = json.dumps(record, ensure_ascii=False) + "\n"
    p = history_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(line)


def list_runs(limit: int = 50) -> list[dict[str, Any]]:
    p = history_path()
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            rows.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return rows[:limit]


def get_run(run_id: str) -> Optional[dict[str, Any]]:
    for row in list_runs(limit=10_000):
        if row.get("run_id") == run_id:
            return row
    return None


def history_file() -> Path:
    return history_path()
