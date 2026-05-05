from backend.core.jobs import JobStatus, JobStore


def test_job_create_and_update_persist_to_jsonl(tmp_path):
    store = JobStore(root=tmp_path)
    job = store.create("scout", {"modules": ["technical_deep_dive"], "days": 7})
    assert job.status == JobStatus.queued

    store.update(job.id, status=JobStatus.running, progress={"step": 1, "total": 5})
    store.update(job.id, status=JobStatus.completed, result={"report_md": "ok"})

    rehydrated = JobStore(root=tmp_path)
    same = rehydrated.get(job.id)
    assert same is not None
    assert same.status == JobStatus.completed
    assert same.result == {"report_md": "ok"}


def test_job_list_filters_by_kind(tmp_path):
    store = JobStore(root=tmp_path)
    store.create("scout", {})
    store.create("posts", {})
    store.create("scout", {})

    scout_jobs = store.list(kind="scout")
    post_jobs = store.list(kind="posts")
    assert len(scout_jobs) == 2
    assert len(post_jobs) == 1


def test_cancel_inflight(tmp_path):
    store = JobStore(root=tmp_path)
    a = store.create("scout", {})
    b = store.create("posts", {})
    store.update(a.id, status=JobStatus.completed)
    cancelled = store.cancel_inflight()
    assert cancelled == 1
    assert store.get(b.id).status == JobStatus.cancelled
    assert store.get(a.id).status == JobStatus.completed
