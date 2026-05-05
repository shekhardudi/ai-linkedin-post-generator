"""Read endpoints over the JSONL run manifest."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.api.schemas import HistoryRow
from backend.utils.history import get_run, list_runs

router = APIRouter(prefix="/history", tags=["history"])


@router.get("", response_model=list[HistoryRow])
def get_history(limit: int = 50) -> list[HistoryRow]:
    return [HistoryRow(**r) for r in list_runs(limit=limit)]


@router.get("/{run_id}", response_model=HistoryRow)
def get_one(run_id: str) -> HistoryRow:
    row = get_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="run not found")
    return HistoryRow(**row)
