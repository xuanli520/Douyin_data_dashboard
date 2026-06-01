from src.core.agent.models import Recipe

SHOP_SCORE_RECIPE_REF = (
    "douyin_shop_dashboard",
    "experience_score_single_page",
)
SHOP_SCORE_FIELDS = (
    "total_score",
    "product_score",
    "logistics_score",
    "service_score",
    "bad_behavior_score",
)


def is_shop_score_recipe(namespace: object, key: object) -> bool:
    return (
        str(namespace or "").strip(),
        str(key or "").strip(),
    ) == SHOP_SCORE_RECIPE_REF


def validate_stable_recipe(recipe: Recipe) -> None:
    if not recipe.observations:
        raise ValueError("agent recipe observations are required before stable")
    if is_shop_score_recipe(recipe.namespace, recipe.key):
        validate_shop_score_recipe(recipe)


def validate_shop_score_recipe(recipe: Recipe) -> None:
    missing = [field for field in SHOP_SCORE_FIELDS if field not in recipe.observations]
    if missing:
        raise ValueError(
            "agent recipe missing required score observations: " + ", ".join(missing)
        )

    wrong_parser = [
        field
        for field in SHOP_SCORE_FIELDS
        if recipe.observations[field].parser != "number"
    ]
    if wrong_parser:
        raise ValueError(
            "agent recipe score observations must use number parser: "
            + ", ".join(wrong_parser)
        )

    optional = [
        field
        for field in SHOP_SCORE_FIELDS
        if recipe.observations[field].required is not True
    ]
    if optional:
        raise ValueError(
            "agent recipe score observations must be required: "
            + ", ".join(optional)
        )

    not_empty_sources = {
        assertion.source
        for assertion in recipe.assertions
        if assertion.kind == "not_empty" and assertion.severity == "error"
    }
    missing_assertions = [
        field for field in SHOP_SCORE_FIELDS if field not in not_empty_sources
    ]
    if missing_assertions:
        raise ValueError(
            "agent recipe missing required score assertions: "
            + ", ".join(missing_assertions)
        )
