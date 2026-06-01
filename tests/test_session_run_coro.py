import pytest

from src import session


def test_run_coro_preserves_runtime_error_from_coroutine():
    session.bind_worker_loop(None)

    async def _raise_runtime_error():
        raise RuntimeError("inner runtime failure")

    with pytest.raises(RuntimeError, match="inner runtime failure"):
        session.run_coro(_raise_runtime_error())
