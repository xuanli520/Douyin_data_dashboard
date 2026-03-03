def test_register_jobs_uses_fixed_ids(monkeypatch):
    from src.tasks import beat as module

    calls = []

    class _FakeJobAdder:
        def __init__(self, func, job_store_kind):
            calls.append(("init", getattr(func, "__name__", str(func)), job_store_kind))

        def add_push_job(self, **kwargs):
            calls.append(("add", kwargs["id"], kwargs["trigger"]))

    monkeypatch.setattr(module, "ApsJobAdder", _FakeJobAdder)
    module.register_jobs()

    add_ids = [item[1] for item in calls if item[0] == "add"]
    assert "daily_collection_orders_sync" in add_ids
    assert "daily_collection_products_sync" in add_ids
