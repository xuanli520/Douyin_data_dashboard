from __future__ import annotations

from src.core.agent.assertions import evaluate_assertions
from src.core.agent.browser import BrowserDriver
from src.core.agent.exceptions import AgentError
from src.core.agent.exceptions import AssertionFailedError
from src.core.agent.exceptions import BrowserDriverError
from src.core.agent.exceptions import ObservationError
from src.core.agent.exceptions import RecipeValidationError
from src.core.agent.exceptions import SecurityPolicyError
from src.core.agent.models import Artifact
from src.core.agent.models import Failure
from src.core.agent.models import Recipe
from src.core.agent.models import RunContext
from src.core.agent.models import RunResult
from src.core.agent.models import Step
from src.core.agent.observations import read_observations
from src.core.agent.security import validate_navigation_target
from src.core.agent.security import validate_page_risk
from src.core.agent.steps import run_step


class AgentCrawler:
    def __init__(self, driver: BrowserDriver) -> None:
        self.driver = driver

    def run(self, recipe: Recipe, context: RunContext) -> RunResult:
        trace: list[dict[str, object]] = []
        artifacts: list[Artifact] = []
        current_step: Step | None = None
        try:
            allowed_origins = list(recipe.security_policy.allowed_origins)
            validate_navigation_target(recipe.entrypoint.url, recipe.security_policy)
            self.driver.open(recipe.entrypoint.url, headed=context.headed)
            for step in recipe.steps:
                current_step = step
                try:
                    step_result = run_step(
                        driver=self.driver,
                        step=step,
                        entrypoint_url=recipe.entrypoint.url,
                        allowed_origins=allowed_origins,
                    )
                    trace.append(_step_trace(step=step, result=step_result.data))
                    artifacts.extend(
                        _capture_step_artifacts(
                            driver=self.driver,
                            context=context,
                            step=step,
                            max_chars=recipe.security_policy.snapshot_max_chars,
                        )
                    )
                except AgentError as exc:
                    trace.append(_step_trace(step=step, error=str(exc)))
                    artifacts.extend(
                        _capture_step_artifacts(
                            driver=self.driver,
                            context=context,
                            step=step,
                            max_chars=recipe.security_policy.snapshot_max_chars,
                        )
                    )
                    raise
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
            return RunResult(
                status="succeeded",
                output=output,
                artifacts=artifacts,
                metadata={"trace": trace},
            )
        except AgentError as exc:
            if not artifacts:
                artifacts.extend(
                    _capture_step_artifacts(
                        driver=self.driver,
                        context=context,
                        step=current_step,
                        max_chars=recipe.security_policy.snapshot_max_chars,
                    )
                )
            failure = _classify_agent_error(exc, current_step)
            return RunResult(
                status="failed",
                failure=Failure(
                    kind=failure["kind"],
                    message=str(exc),
                    step_id=failure.get("step_id"),
                    observation_id=failure.get("observation_id"),
                    details=dict(failure.get("details") or {}),
                    recoverable=bool(failure.get("recoverable")),
                ),
                artifacts=artifacts,
                metadata={"trace": trace},
            )
        finally:
            self.driver.close()


def _classify_agent_error(
    exc: AgentError,
    step: Step | None = None,
) -> dict[str, object]:
    details = _failure_details(step)
    if isinstance(exc, ObservationError):
        observation_id = _extract_observation_id(str(exc))
        return {
            "kind": "observation_empty",
            "observation_id": observation_id,
            "details": details,
            "recoverable": observation_id is not None,
        }
    if isinstance(exc, AssertionFailedError):
        return {"kind": "assertion_failed", "details": details, "recoverable": False}
    if isinstance(exc, SecurityPolicyError):
        return {
            "kind": "security_policy_violation",
            "details": details,
            "recoverable": False,
        }
    if isinstance(exc, RecipeValidationError):
        return {
            "kind": "recipe_schema_invalid",
            "details": details,
            "recoverable": False,
        }
    if isinstance(exc, BrowserDriverError):
        message = str(exc).casefold()
        if "timeout" in message:
            return {
                "kind": "timeout",
                "step_id": step.id if step is not None else None,
                "details": details,
                "recoverable": True,
            }
        if any(token in message for token in ("locator", "selector", "element")):
            return {
                "kind": "locator_failed",
                "step_id": step.id if step is not None else None,
                "details": details,
                "recoverable": True,
            }
        return {"kind": "driver_crashed", "details": details, "recoverable": False}
    return {"kind": type(exc).__name__, "details": details, "recoverable": False}


def _extract_observation_id(message: str) -> str | None:
    prefix = "observation "
    suffix = " is required"
    if not message.startswith(prefix) or suffix not in message:
        return None
    return message[len(prefix) : message.index(suffix)].strip() or None


def _step_trace(
    *,
    step: Step,
    result: dict[str, object] | None = None,
    error: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "step_id": step.id,
        "action": step.action,
        "target": step.target.model_dump(mode="json") if step.target else None,
    }
    if result is not None:
        payload["result"] = result
    if error is not None:
        payload["error"] = error
    return payload


def _capture_step_artifacts(
    *,
    driver: BrowserDriver,
    context: RunContext,
    step: Step | None,
    max_chars: int,
) -> list[Artifact]:
    label = step.id if step is not None else "failure"
    safe_session_id = _safe_artifact_name(context.session_id)
    safe_label = _safe_artifact_name(label)
    artifacts: list[Artifact] = []
    screenshot_name = f"{safe_session_id}-{safe_label}.png"
    snapshot_name = f"{safe_session_id}-{safe_label}.yml"
    try:
        screenshot_path = driver.screenshot(screenshot_name)
        artifacts.append(
            Artifact(
                id=f"{label}:screenshot",
                path=str(screenshot_path),
                kind="screenshot",
            )
        )
    except Exception:
        pass
    try:
        driver.snapshot(snapshot_name, max_chars)
        artifacts.append(
            Artifact(
                id=f"{label}:snapshot",
                path=_artifact_path(driver, snapshot_name),
                kind="snapshot",
            )
        )
    except Exception:
        pass
    return artifacts


def _failure_details(step: Step | None) -> dict[str, object]:
    if step is None:
        return {}
    return {"step": step.model_dump(mode="json")}


def _artifact_path(driver: BrowserDriver, filename: str) -> str:
    artifact_dir = getattr(driver, "artifact_dir", None)
    if artifact_dir is None:
        return filename
    return (
        str(artifact_dir / filename)
        if hasattr(artifact_dir, "__truediv__")
        else f"{artifact_dir}/{filename}"
    )


def _safe_artifact_name(value: str) -> str:
    return "".join(
        item if item.isalnum() or item in {"-", "_"} else "_" for item in value
    )
