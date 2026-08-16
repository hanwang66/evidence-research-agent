from evidence_research.storage import TaskStateStore


def test_task_store_persists_lifecycle_and_cache(tmp_path) -> None:
    database = tmp_path / "research.db"
    request = {"query": "market growth", "breadth": 1}
    store = TaskStateStore(database)

    job = store.create(request=request, cache_key="cache-1")
    assert job.status == "queued"
    assert store.find_active("cache-1").id == job.id

    assert store.mark_running(job.id).status == "running"
    completed = store.mark_completed(job.id, {"report": "result", "score": 0.9})
    assert completed.status == "completed"
    assert completed.result == {"report": "result", "score": 0.9}
    assert store.find_active("cache-1") is None
    assert store.find_cached("cache-1").id == job.id

    reopened = TaskStateStore(database)
    persisted = reopened.get(job.id)
    assert persisted is not None
    assert persisted.as_dict()["result"] == {"report": "result", "score": 0.9}


def test_task_store_records_failures_and_limits_listing(tmp_path) -> None:
    store = TaskStateStore(tmp_path / "research.db")
    first = store.create(request={"query": "first"}, cache_key="first")
    second = store.create(request={"query": "second"}, cache_key="second")

    failed = store.mark_failed(first.id, "provider unavailable")

    assert failed.status == "failed"
    assert failed.error == "provider unavailable"
    assert store.find_cached("first") is None
    assert len(store.list(limit=1)) == 1
    assert {job.id for job in store.list(limit=10)} == {first.id, second.id}
