from src.core.agent.models import AssertionSpec
from src.core.agent.models import Entrypoint
from src.core.agent.models import LocatorSpec
from src.core.agent.models import ObservationSpec
from src.core.agent.models import Recipe
from src.core.agent.models import SecurityPolicy
from src.core.agent.models import Step


def _recipe_payload() -> dict:
    return {
        "namespace": "generic",
        "key": "overview",
        "version": 1,
        "entrypoint": {"url": "https://example.test/start"},
        "steps": [
            {
                "id": "open",
                "action": "goto",
                "depends_on": [],
            }
        ],
        "observations": {
            "headline": {
                "id": "headline",
                "kind": "text",
                "locator": {"kind": "css", "value": "h1"},
                "required": True,
            }
        },
        "assertions": [
            {
                "id": "headline_exists",
                "kind": "not_empty",
                "source": "headline",
                "severity": "error",
            }
        ],
        "security_policy": {"allowed_origins": ["https://example.test"]},
    }


def test_recipe_json_round_trip():
    recipe = Recipe.model_validate(_recipe_payload())

    restored = Recipe.model_validate_json(recipe.model_dump_json())

    assert restored == recipe
    assert restored.steps[0] == Step(id="open", action="goto")
    assert restored.entrypoint == Entrypoint(url="https://example.test/start")
    assert restored.observations["headline"] == ObservationSpec(
        id="headline",
        kind="text",
        locator=LocatorSpec(kind="css", value="h1"),
        required=True,
    )
    assert restored.assertions[0] == AssertionSpec(
        id="headline_exists",
        kind="not_empty",
        source="headline",
    )
    assert restored.security_policy == SecurityPolicy(
        allowed_origins=["https://example.test"]
    )


def test_recipe_rejects_unknown_action():
    payload = _recipe_payload()
    payload["steps"][0]["action"] = "evaluate"

    try:
        Recipe.model_validate(payload)
    except Exception as exc:
        assert "action" in str(exc)
    else:
        raise AssertionError("invalid action should fail validation")
