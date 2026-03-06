import httpx
import pytest


def test_llm_agent_returns_cold_data_patch(monkeypatch):
    from src.agents.llm_dashboard_agent import LLMDashboardAgent

    agent = LLMDashboardAgent()
    monkeypatch.setattr(
        agent, "_capture_snapshot", lambda *_: {"html": "<div>dsr</div>"}
    )
    monkeypatch.setattr(
        agent,
        "_call_llm",
        lambda *_args, **_kwargs: {
            "violations_detail": [{"id": "v-1"}],
            "arbitration_detail": [{"id": "a-1"}],
            "dsr_trend": [{"date": "2026-03-03", "score": 4.7}],
        },
    )

    data = agent.supplement_cold_data(
        {"total_score": 4.7},
        "shop-1",
        "2026-03-03",
        reason="page_changed",
    )

    assert "violations_detail" in data


def test_llm_agent_preserves_existing_data_on_empty_patch(monkeypatch):
    from src.agents.llm_dashboard_agent import LLMDashboardAgent

    agent = LLMDashboardAgent()
    monkeypatch.setattr(agent, "_call_llm", lambda *_args, **_kwargs: {})

    data = agent.supplement_cold_data(
        {
            "violations_detail": [{"id": "v-existing"}],
            "arbitration_detail": [{"id": "a-existing"}],
            "dsr_trend": [{"date": "2026-03-03", "score": 4.8}],
        },
        "shop-1",
        "2026-03-03",
        reason="cold_metric",
    )

    assert data["violations_detail"] == [{"id": "v-existing"}]
    assert data["arbitration_detail"] == [{"id": "a-existing"}]
    assert data["dsr_trend"] == [{"date": "2026-03-03", "score": 4.8}]


def test_llm_agent_retries_on_timeout(monkeypatch):
    from src.agents.llm_dashboard_agent import LLMDashboardAgent

    agent = LLMDashboardAgent()
    calls = {"count": 0}

    def _fake(*_args, **_kwargs):
        calls["count"] += 1
        if calls["count"] < 3:
            raise TimeoutError("timeout")
        return {"violations_detail": []}

    monkeypatch.setattr(agent, "_request_provider", _fake)

    result = agent._call_llm(
        snapshot={},
        result={},
        shop_id="shop-1",
        date="2026-03-03",
        reason="cold_metric",
    )

    assert result["violations_detail"] == []
    assert calls["count"] == 3


def test_llm_agent_does_not_retry_on_client_error(monkeypatch):
    from src.agents.llm_dashboard_agent import LLMDashboardAgent

    agent = LLMDashboardAgent()
    calls = {"count": 0}
    request = httpx.Request("POST", "https://example.com")
    response = httpx.Response(status_code=400, request=request)

    def _fake(*_args, **_kwargs):
        calls["count"] += 1
        raise httpx.HTTPStatusError("bad request", request=request, response=response)

    monkeypatch.setattr(agent, "_request_provider", _fake)

    with pytest.raises(httpx.HTTPStatusError):
        agent._call_llm(
            snapshot={},
            result={},
            shop_id="shop-1",
            date="2026-03-03",
            reason="cold_metric",
        )

    assert calls["count"] == 1


def test_llm_agent_retries_on_5xx(monkeypatch):
    from src.agents.llm_dashboard_agent import LLMDashboardAgent

    agent = LLMDashboardAgent()
    calls = {"count": 0}
    request = httpx.Request("POST", "https://example.com")
    retryable = httpx.Response(status_code=503, request=request)

    def _fake(*_args, **_kwargs):
        calls["count"] += 1
        if calls["count"] < 3:
            raise httpx.HTTPStatusError(
                "service unavailable", request=request, response=retryable
            )
        return {"violations_detail": []}

    monkeypatch.setattr(agent, "_request_provider", _fake)

    result = agent._call_llm(
        snapshot={},
        result={},
        shop_id="shop-1",
        date="2026-03-03",
        reason="cold_metric",
    )

    assert result["violations_detail"] == []
    assert calls["count"] == 3


def test_llm_agent_guards_non_dict_output(monkeypatch):
    from src.agents.llm_dashboard_agent import LLMDashboardAgent

    agent = LLMDashboardAgent()
    monkeypatch.setattr(agent, "_request_provider", lambda *_args, **_kwargs: "invalid")

    result = agent._call_llm(
        snapshot={},
        result={},
        shop_id="shop-1",
        date="2026-03-03",
        reason="cold_metric",
    )

    assert result == {
        "violations_detail": [],
        "arbitration_detail": [],
        "dsr_trend": [],
    }


def test_llm_agent_marks_failed_patch_on_exception(monkeypatch):
    from src.agents.llm_dashboard_agent import LLMDashboardAgent

    agent = LLMDashboardAgent()
    monkeypatch.setattr(agent, "_call_llm", lambda *_args, **_kwargs: 1 / 0)

    result = agent.supplement_cold_data(
        {"raw": {}},
        "shop-1",
        "2026-03-03",
        reason="cold_metric",
    )

    assert result["raw"]["llm_patch"]["status"] == "failed"
