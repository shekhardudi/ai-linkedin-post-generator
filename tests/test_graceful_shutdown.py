from backend.core.jobs import JobStatus, JobStore


def test_cancel_inflight_marks_running_and_queued_only(tmp_path):
    store = JobStore(root=tmp_path)
    queued = store.create("scout", {})
    running = store.create("posts", {})
    completed = store.create("posts", {})
    failed = store.create("scout", {})

    store.update(running.id, status=JobStatus.running)
    store.update(completed.id, status=JobStatus.completed, result={"ok": True})
    store.update(failed.id, status=JobStatus.failed, error="boom")

    cancelled = store.cancel_inflight()
    assert cancelled == 2

    assert store.get(queued.id).status == JobStatus.cancelled
    assert store.get(running.id).status == JobStatus.cancelled
    assert store.get(completed.id).status == JobStatus.completed
    assert store.get(failed.id).status == JobStatus.failed


def test_cancel_inflight_persists_to_jsonl(tmp_path):
    store = JobStore(root=tmp_path)
    a = store.create("posts", {})
    store.update(a.id, status=JobStatus.running)
    store.cancel_inflight()

    rehydrated = JobStore(root=tmp_path)
    assert rehydrated.get(a.id).status == JobStatus.cancelled
