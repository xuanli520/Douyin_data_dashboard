from src.core.agent.recovery import RecoveryService


class _Model:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def propose_recovery(self, request, messages):
        self.calls.append((request, messages))
        return self.payload


class _Crawler:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def run(self, recipe, *, input_data=None, context=None):
        self.calls.append((recipe, input_data, context))
        return self.payload


def _recipe() -> dict:
    return {
        "id": "recipe-1",
        "version": 2,
        "entrypoint": {"url": "https://example.test/dashboard"},
        "observations": {
            "price": {
                "locator": {"type": "css", "value": ".old-price"},
            }
        },
        "security_policy": {"allowed_origins": ["https://example.test"]},
        "recovery_policy": {
            "enabled": True,
            "max_attempts": 1,
            "confidence_threshold": 0.7,
        },
    }


def test_recovery_service_skips_non_recoverable_failure():
    model = _Model({})
    crawler = _Crawler({})
    result = RecoveryService(model, crawler).recover(
        _recipe(),
        {"type": "auth_required", "failed_targets": ["/observations/price/locator"]},
    )

    assert result.status == "skipped"
    assert result.reason == "auth_required"
    assert model.calls == []
    assert crawler.calls == []


def test_recovery_service_returns_recovered_result():
    model = _Model(
        {
            "base_version": 2,
            "confidence": 0.86,
            "reason": "replace observation locator",
            "expected_effect": "price recovers",
            "patches": [
                {
                    "op": "replace",
                    "path": "/observations/price/locator",
                    "value": {"type": "css", "value": ".new-price"},
                    "confidence": 0.86,
                }
            ],
        }
    )
    crawler = _Crawler(
        {
            "success": True,
            "recovered_targets": ["/observations/price/locator"],
        }
    )
    result = RecoveryService(model, crawler).recover(
        _recipe(),
        {
            "type": "locator_not_found",
            "failed_targets": ["/observations/price/locator"],
            "reason": "missing locator",
        },
        artifacts={"current_url": "https://example.test/dashboard"},
    )

    assert result.status == "recovered"
    assert result.success is True
    assert result.candidate_recipe is not None
    assert (
        result.candidate_recipe["observations"]["price"]["locator"]["value"]
        == ".new-price"
    )
    assert result.request is not None
    assert result.request.current_url == "https://example.test/dashboard"
    assert len(model.calls) == 1
    assert model.calls[0][1][0]["role"] == "system"


def test_recovery_service_returns_proposal_invalid_when_patch_overreaches():
    model = _Model(
        {
            "base_version": 2,
            "confidence": 0.86,
            "reason": "replace observation locator",
            "patches": [
                {
                    "op": "replace",
                    "path": "/observations/other/locator",
                    "value": {"type": "css", "value": ".new-price"},
                }
            ],
        }
    )
    crawler = _Crawler(
        {
            "success": True,
            "recovered_targets": ["/observations/price/locator"],
        }
    )
    result = RecoveryService(model, crawler).recover(
        _recipe(),
        {
            "type": "locator_not_found",
            "failed_targets": ["/observations/price/locator"],
            "reason": "missing locator",
        },
    )

    assert result.status == "proposal_invalid"
    assert result.reason == "patch_target_not_failed"
    assert crawler.calls == []
