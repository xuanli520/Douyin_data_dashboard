from __future__ import annotations

import json

from src.core.agent.proposals import RecoveryRequest

_SYSTEM_PROMPT = (
    "You repair failed web automation recipes. "
    "Return only JSON. "
    "Only replace failed observation locators. "
    "Do not change entrypoint, steps, assertions, parsers, security policy, or recovery policy."
)


def build_recovery_prompt(request: RecoveryRequest) -> str:
    body = {
        "failure_type": request.failure_type,
        "failed_targets": request.failed_targets,
        "failure_reasons": request.failure_reasons,
        "recipe_excerpt": request.recipe_excerpt,
        "observation_specs": request.observation_specs,
        "security_policy": request.security_policy,
        "recovery_policy": request.recovery_policy,
        "current_url": request.current_url,
        "rendered_entrypoint_url": request.rendered_entrypoint_url,
        "snapshot_markdown": request.snapshot_markdown,
        "dom_excerpt": request.dom_excerpt,
        "screenshot_ref": request.screenshot_ref,
        "output_schema": {
            "confidence": "float",
            "reason": "string",
            "expected_effect": "string",
            "patches": [
                {
                    "op": "replace",
                    "path": "/observations/{id}/locator",
                    "value": {"type": "css|xpath|text|role|test_id|label|placeholder", "value": "string"},
                }
            ],
        },
    }
    return json.dumps(body, ensure_ascii=True, separators=(",", ":"))


def build_recovery_messages(request: RecoveryRequest) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": build_recovery_prompt(request)},
    ]
