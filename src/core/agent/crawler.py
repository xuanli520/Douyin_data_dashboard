from __future__ import annotations

from src.core.agent.assertions import evaluate_assertions
from src.core.agent.browser import BrowserDriver
from src.core.agent.exceptions import AgentError
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
            return RunResult(
                status="failed",
                failure=Failure(kind=type(exc).__name__, message=str(exc)),
            )
        finally:
            self.driver.close()
