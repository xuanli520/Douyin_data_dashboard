from __future__ import annotations

import json
from typing import Any

import httpx
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_exponential

from src.config import get_settings


class LLMDashboardAgent:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._settings = get_settings().shop_dashboard
        self._owns_client = client is None
        self._client = client or httpx.Client()

    def __enter__(self) -> LLMDashboardAgent:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def supplement_cold_data(
        self,
        result: dict[str, Any],
        shop_id: str,
        date: str,
        reason: str,
    ) -> dict[str, Any]:
        base = dict(result)
        try:
            snapshot = self._capture_snapshot(shop_id, date, base)
            patch = self._call_llm(
                snapshot=snapshot,
                result=base,
                shop_id=shop_id,
                date=date,
                reason=reason,
            )
            return self._merge_patch(base, patch, reason)
        except Exception as exc:
            return self._mark_failed(base, reason, exc)

    def _capture_snapshot(
        self,
        shop_id: str,
        date: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        raw = result.get("raw")
        html = ""
        if isinstance(raw, dict):
            html = str(raw.get("html") or "")
        return {
            "shop_id": shop_id,
            "metric_date": date,
            "html": html,
            "raw": raw if isinstance(raw, dict) else {},
        }

    def _call_llm(
        self,
        *,
        snapshot: dict[str, Any],
        result: dict[str, Any],
        shop_id: str,
        date: str,
        reason: str,
    ) -> dict[str, Any]:
        payload = {
            "shop_id": shop_id,
            "metric_date": date,
            "reason": reason,
            "result": result,
            "snapshot": snapshot,
        }
        retries = max(int(self._settings.llm_retry_times), 1)
        timeout = int(self._settings.llm_timeout_seconds)
        retryer = Retrying(
            stop=stop_after_attempt(retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception(self._should_retry),
            reraise=True,
        )
        for attempt in retryer:
            with attempt:
                patch = self._request_provider(payload, timeout=timeout)
                return self._normalize_patch(patch)
        return self._empty_patch()

    def _request_provider(
        self, payload: dict[str, Any], timeout: int
    ) -> dict[str, Any]:
        endpoint = (self._settings.llm_endpoint or "").strip()
        model = (self._settings.llm_model or "").strip()
        if not endpoint or not model:
            return self._empty_patch()

        provider = str(self._settings.llm_provider or "claude").strip().lower()
        if provider == "openai":
            body: dict[str, Any] = {
                "model": model,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": "Return JSON with violations_detail, arbitration_detail, dsr_trend.",
                    },
                    {
                        "role": "user",
                        "content": json.dumps(payload, ensure_ascii=False),
                    },
                ],
            }
        else:
            body = {
                "model": model,
                "max_tokens": 1024,
                "messages": [
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}
                ],
            }

        response = self._client.post(endpoint, json=body, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        return self._parse_provider_response(data)

    def _parse_provider_response(self, data: Any) -> dict[str, Any]:
        if not isinstance(data, dict):
            return self._empty_patch()
        if self._looks_like_patch(data):
            return data

        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            message = (
                choices[0].get("message") if isinstance(choices[0], dict) else None
            )
            if isinstance(message, dict):
                parsed = self._parse_text_payload(message.get("content"))
                if parsed:
                    return parsed

        content = data.get("content")
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                text = item.get("text")
                parsed = self._parse_text_payload(text)
                if parsed:
                    return parsed

        return self._empty_patch()

    def _parse_text_payload(self, value: Any) -> dict[str, Any]:
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    def _merge_patch(
        self,
        result: dict[str, Any],
        patch: dict[str, Any],
        reason: str,
    ) -> dict[str, Any]:
        merged = dict(result)
        normalized = self._normalize_patch(patch)
        for key, value in normalized.items():
            existing = merged.get(key)
            if value:
                merged[key] = value
                continue
            if isinstance(existing, list):
                merged[key] = existing
                continue
            merged[key] = []

        raw = merged.get("raw")
        if not isinstance(raw, dict):
            raw = {}
        raw["llm_patch"] = {
            "status": "success",
            "reason": reason,
            "violations_detail": merged["violations_detail"],
            "arbitration_detail": merged["arbitration_detail"],
            "dsr_trend": merged["dsr_trend"],
        }
        merged["raw"] = raw
        return merged

    def _mark_failed(
        self,
        result: dict[str, Any],
        reason: str,
        exc: Exception,
    ) -> dict[str, Any]:
        merged = dict(result)
        raw = merged.get("raw")
        if not isinstance(raw, dict):
            raw = {}
        raw["llm_patch"] = {
            "status": "failed",
            "reason": reason,
            "error": str(exc),
        }
        merged["raw"] = raw
        return merged

    def _normalize_patch(self, patch: Any) -> dict[str, Any]:
        if not isinstance(patch, dict):
            return self._empty_patch()
        return {
            "violations_detail": self._normalize_list(patch.get("violations_detail")),
            "arbitration_detail": self._normalize_list(patch.get("arbitration_detail")),
            "dsr_trend": self._normalize_list(patch.get("dsr_trend")),
        }

    def _normalize_list(self, value: Any) -> list[Any]:
        return value if isinstance(value, list) else []

    def _empty_patch(self) -> dict[str, Any]:
        return {
            "violations_detail": [],
            "arbitration_detail": [],
            "dsr_trend": [],
        }

    def _looks_like_patch(self, data: dict[str, Any]) -> bool:
        keys = {"violations_detail", "arbitration_detail", "dsr_trend"}
        return bool(keys.intersection(data.keys()))

    def _should_retry(self, exc: BaseException) -> bool:
        if isinstance(exc, (TimeoutError, httpx.NetworkError, httpx.TimeoutException)):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code >= 500
        return False
