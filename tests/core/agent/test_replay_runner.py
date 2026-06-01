from src.core.agent.replay import ReplayRunner


class _Crawler:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def run(self, recipe, *, input_data=None, context=None):
        self.calls.append((recipe, input_data, context))
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def test_replay_runner_returns_success_when_expected_targets_recover():
    crawler = _Crawler(
        {
            "success": True,
            "recovered_targets": ["/observations/price/locator"],
        }
    )

    outcome = ReplayRunner(crawler).replay(
        {"id": "recipe-1"},
        input_data={"subject": "x"},
        context={"trace_id": "abc"},
        failed_targets=["/observations/price/locator"],
    )

    assert outcome.success is True
    assert outcome.recovered_targets == ["/observations/price/locator"]
    assert crawler.calls[0][1] == {"subject": "x"}
    assert crawler.calls[0][2] == {"trace_id": "abc"}


def test_replay_runner_marks_missing_recovered_targets_as_failure():
    outcome = ReplayRunner(_Crawler({"success": True, "recovered_targets": []})).replay(
        {"id": "recipe-1"},
        failed_targets=["/observations/price/locator"],
    )

    assert outcome.success is False
    assert outcome.reason == "replay_missing_targets"
    assert outcome.failed_targets == ["/observations/price/locator"]


def test_replay_runner_returns_failure_on_crawler_exception():
    outcome = ReplayRunner(_Crawler(RuntimeError("driver gone"))).replay(
        {"id": "recipe-1"},
        failed_targets=["/observations/price/locator"],
    )

    assert outcome.success is False
    assert outcome.reason == "driver gone"
    assert outcome.failed_targets == ["/observations/price/locator"]
