from __future__ import annotations

from src.core.agent.assertions import evaluate_assertions
from src.core.agent.browser import BrowserDriver
from src.core.agent.exceptions import AgentError
from src.core.agent.exceptions import AssertionFailedError
from src.core.agent.exceptions import BrowserDriverError
from src.core.agent.exceptions import ObservationError
from src.core.agent.exceptions import RecipeValidationError
from src.core.agent.exceptions import SecurityPolicyError
from src.core.agent.models import Failure
from src.core.agent.models import Recipe
from src.core.agent.models import RunContext
from src.core.agent.models import RunResult
from src.core.agent.observations import read_observations
from src.core.agent.security import validate_navigation_target
from src.core.agent.security import validate_page_risk
from src.core.agent.steps import run_step


class AgentCrawler:
    def __init__(self, driver: BrowserDriver) -> None:
        self.driver = driver

    def run(self, recipe: Recipe, context: RunContext) -> RunResult:
        try:
            allowed_origins = list(recipe.security_policy.allowed_origins)
            validate_navigation_target(recipe.entrypoint.url, recipe.security_policy)
            self.driver.open(recipe.entrypoint.url, headed=context.headed)
            for step in recipe.steps:
                run_step(
                    driver=self.driver,
                    step=step,
                    entrypoint_url=recipe.entrypoint.url,
                    allowed_origins=allowed_origins,
                )
                validate_page_risk(
                    self.driver.current_url(),
                    self.driver.title(),
                    "",
                )
            output = read_observations(
                driver=self.driver,
                observations=recipe.observations,
            )
            evaluate_assertions(assertions=recipe.assertions, values=output)
            return RunResult(status="succeeded", output=output)
        except AgentError as exc:
            failure = _classify_agent_error(exc)
            return RunResult(
                status="failed",
                failure=Failure(
                    kind=failure["kind"],
                    message=str(exc),
                    observation_id=failure.get("observation_id"),
                    recoverable=bool(failure.get("recoverable")),
                ),
            )
        finally:
            self.driver.close()


def _classify_agent_error(exc: AgentError) -> dict[str, object]:
    if isinstance(exc, ObservationError):
        observation_id = _extract_observation_id(str(exc))
        return {
            "kind": "observation_empty",
            "observation_id": observation_id,
            "recoverable": observation_id is not None,
        }
    if isinstance(exc, AssertionFailedError):
        return {"kind": "assertion_failed", "recoverable": False}
    if isinstance(exc, SecurityPolicyError):
        return {"kind": "security_policy_violation", "recoverable": False}
    if isinstance(exc, RecipeValidationError):
        return {"kind": "recipe_schema_invalid", "recoverable": False}
    if isinstance(exc, BrowserDriverError):
        return {"kind": "driver_crashed", "recoverable": False}
    return {"kind": type(exc).__name__, "recoverable": False}


def _extract_observation_id(message: str) -> str | None:
    prefix = "observation "
    suffix = " is required"
    if not message.startswith(prefix) or suffix not in message:
        return None
    return message[len(prefix) : message.index(suffix)].strip() or None
