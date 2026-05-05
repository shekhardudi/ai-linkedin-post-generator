from backend.utils.history import append_run, get_run, list_runs


def test_history_round_trip():
    append_run({"run_id": "r1", "topic": "RAG", "leader_angle": "skeptical"})
    append_run({"run_id": "r2", "topic": "MoE"})
    rows = list_runs()
    ids = [r["run_id"] for r in rows]
    assert "r1" in ids
    assert "r2" in ids


def test_history_get_one():
    append_run({"run_id": "alpha", "topic": "T", "leader_angle": ""})
    row = get_run("alpha")
    assert row is not None
    assert row["topic"] == "T"


def test_history_get_missing_returns_none():
    assert get_run("does-not-exist") is None


def test_history_orders_by_created_at_desc():
    append_run({"run_id": "old", "topic": "X", "created_at": "2020-01-01T00:00:00+00:00"})
    append_run({"run_id": "new", "topic": "Y", "created_at": "2030-01-01T00:00:00+00:00"})
    rows = list_runs()
    assert rows[0]["run_id"] == "new"
