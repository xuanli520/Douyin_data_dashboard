import importlib.util
import sys
import types
from pathlib import Path

import pytest
from pydantic import BaseModel

from src.config import get_settings

ROOT = Path(__file__).resolve().parents[2]


def _load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module: {module_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_funboost_common_log_level_is_int(monkeypatch):
    fake_funboost = types.ModuleType("funboost")
    fake_funboost_utils = types.ModuleType("funboost.utils")
    fake_simple_data_class = types.ModuleType("funboost.utils.simple_data_class")

    class DataClassBase:
        pass

    fake_simple_data_class.DataClassBase = DataClassBase
    monkeypatch.setitem(sys.modules, "funboost", fake_funboost)
    monkeypatch.setitem(sys.modules, "funboost.utils", fake_funboost_utils)
    monkeypatch.setitem(
        sys.modules,
        "funboost.utils.simple_data_class",
        fake_simple_data_class,
    )

    module = _load_module("test_funboost_config", ROOT / "funboost_config.py")
    assert isinstance(module.FunboostCommonConfig.FUNBOOST_PROMPT_LOG_LEVEL, int)


def test_task_params_read_latest_settings_per_instance(monkeypatch):
    class FakeBoosterParams(BaseModel):
        queue_name: str
        broker_kind: str = "SQLITE_QUEUE"
        max_retry_times: int = 3
        retry_interval: int = 0
        function_timeout: int | None = None
        is_using_rpc_mode: bool = False
        broker_exclusive_config: dict = {}
        qps: float | int | None = None
        concurrent_num: int = 50
        concurrent_mode: str = "THREADING"

    class FakeConcurrentModeEnum:
        THREADING = "THREADING"
        SINGLE_THREAD = "SINGLE_THREAD"

    fake_funboost = types.ModuleType("funboost")
    fake_funboost.BoosterParams = FakeBoosterParams
    fake_constant = types.ModuleType("funboost.constant")
    fake_constant.ConcurrentModeEnum = FakeConcurrentModeEnum
    monkeypatch.setitem(sys.modules, "funboost", fake_funboost)
    monkeypatch.setitem(sys.modules, "funboost.constant", fake_constant)

    monkeypatch.setenv("FUNBOOST__DEFAULT_MAX_RETRY_TIMES", "5")
    module = _load_module("test_task_params", ROOT / "src/tasks/params.py")
    first = module.DouyinTaskParams(queue_name="q")
    assert first.max_retry_times == 5

    monkeypatch.setenv("FUNBOOST__DEFAULT_MAX_RETRY_TIMES", "9")
    get_settings.cache_clear()
    second = module.DouyinTaskParams(queue_name="q")
    assert second.max_retry_times == 9
