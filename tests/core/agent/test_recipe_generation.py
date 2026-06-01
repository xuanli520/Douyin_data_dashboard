import pytest

from src.core.agent.llm import RecipeSummaryRequest
from src.core.agent.recipe_generation import RecipeGenerationError, RecipeGenerator
from src.core.agent.tools import ToolCall


class _FakeLLM:
    def __init__(self, recipe):
        self._recipe = recipe

    def complete_tool_call(self, _request):
        return ToolCall(name="done", arguments={})

    def summarize_recipe(self, _request):
        return self._recipe


def _build_recipe(**overrides):
    recipe = {
        "namespace": "generic",
        "key": "generated_recipe",
        "entrypoint": {"url_template": "https://example.com/app"},
        "steps": [
            {
                "id": "step-1",
                "action": "click",
                "target": {"type": "css", "value": "#open"},
            }
        ],
        "observations": {
            "total": {
                "kind": "text",
                "locator": {"type": "css", "value": ".value"},
            }
        },
        "assertions": [{"id": "assert-1", "source": "total", "kind": "not_empty"}],
        "security_policy": {"allowed_origins": ["https://example.com"]},
    }
    recipe.update(overrides)
    return recipe


def test_recipe_generator_accepts_valid_recipe():
    generator = RecipeGenerator(_FakeLLM(_build_recipe()))

    recipe = generator.generate(
        RecipeSummaryRequest(
            goal="collect values",
            entrypoint_url="https://example.com/app",
            trajectory={"entries": []},
        )
    )

    assert recipe["key"] == "generated_recipe"


def test_recipe_generator_uses_request_hints_as_authoritative():
    generator = RecipeGenerator(_FakeLLM(_build_recipe(namespace="wrong", key="wrong")))

    recipe = generator.generate(
        RecipeSummaryRequest(
            goal="collect values",
            entrypoint_url="https://example.com/app",
            trajectory={"entries": []},
            namespace_hint="douyin_shop_dashboard",
            key_hint="experience_score_single_page",
        )
    )

    assert recipe["namespace"] == "douyin_shop_dashboard"
    assert recipe["key"] == "experience_score_single_page"


def test_recipe_generator_rejects_unknown_action():
    generator = RecipeGenerator(_FakeLLM(_build_recipe(steps=[{"action": "evaluate"}])))

    with pytest.raises(RecipeGenerationError):
        generator.generate(
            RecipeSummaryRequest(
                goal="collect values",
                entrypoint_url="https://example.com/app",
                trajectory={"entries": []},
            )
        )


def test_recipe_generator_drops_done_control_step():
    generator = RecipeGenerator(
        _FakeLLM(
            _build_recipe(
                steps=[
                    {"id": "open", "action": "goto", "value": "https://example.com/app"},
                    {"id": "finish", "action": "done"},
                ]
            )
        )
    )

    recipe = generator.generate(
        RecipeSummaryRequest(
            goal="collect values",
            entrypoint_url="https://example.com/app",
            trajectory={"entries": []},
        )
    )

    assert [step["action"] for step in recipe["steps"]] == ["goto"]


def test_recipe_generator_drops_non_object_assertions():
    generator = RecipeGenerator(
        _FakeLLM(
            _build_recipe(
                assertions=[
                    "total must exist",
                    {"id": "assert-1", "source": "total", "kind": "not_empty"},
                ]
            )
        )
    )

    recipe = generator.generate(
        RecipeSummaryRequest(
            goal="collect values",
            entrypoint_url="https://example.com/app",
            trajectory={"entries": []},
        )
    )

    assert recipe["assertions"] == [
        {"id": "assert-1", "source": "total", "kind": "not_empty"}
    ]


def test_recipe_generator_rejects_missing_assertion_source():
    generator = RecipeGenerator(
        _FakeLLM(
            _build_recipe(
                assertions=[{"id": "assert-1", "source": "missing", "kind": "exists"}]
            )
        )
    )

    with pytest.raises(RecipeGenerationError):
        generator.generate(
            RecipeSummaryRequest(
                goal="collect values",
                entrypoint_url="https://example.com/app",
                trajectory={"entries": []},
            )
        )


def test_recipe_generator_rejects_relaxed_security_policy():
    generator = RecipeGenerator(
        _FakeLLM(
            _build_recipe(
                security_policy={
                    "allowed_origins": [
                        "https://example.com",
                        "https://other.example.com",
                    ],
                    "allowed_tools": ["click", "fill", "download"],
                }
            )
        ),
        system_security_policy={
            "allowed_origins": ["https://example.com"],
            "allowed_tools": ["click", "fill"],
        },
    )

    with pytest.raises(RecipeGenerationError):
        generator.generate(
            RecipeSummaryRequest(
                goal="collect values",
                entrypoint_url="https://example.com/app",
                trajectory={"entries": []},
            )
        )
