from __future__ import annotations

import json
from typing import Any

from src.config import get_settings
from src.shared.redis_keys import redis_keys


class ShopSwitchCapabilityService:
    def __init__(self, *, redis_client: Any) -> None:
        settings = get_settings().shop_dashboard
        self._redis = redis_client
        self._mismatch_threshold = max(
            int(settings.account_switch_mismatch_threshold),
            1,
        )
        self._min_distinct_targets = max(
            int(settings.account_switch_min_distinct_targets),
            1,
        )
        self._observation_ttl_seconds = max(
            int(settings.account_switch_observation_ttl_seconds),
            1,
        )
        self._unsupported_ttl_seconds = max(
            int(settings.unsupported_http_shop_switch_ttl_seconds),
            1,
        )

    def resolve_capability_account_id(self, raw_account_id: str | None) -> str | None:
        account_id = str(raw_account_id or "").strip()
        if not account_id:
            return None
        if account_id.startswith("shop_"):
            return None
        return account_id

    def is_unsupported_http_shop_switch(self, account_id: str) -> bool:
        key = redis_keys.shop_dashboard_unsupported_http_shop_switch(
            account_id=account_id,
        )
        redis_get = getattr(self._redis, "get", None)
        if callable(redis_get):
            value = redis_get(key)
            if value in {None, "", b"", 0, "0", b"0", False}:
                return False
            return True
        return False

    def mark_unsupported_http_shop_switch(self, account_id: str) -> None:
        key = redis_keys.shop_dashboard_unsupported_http_shop_switch(
            account_id=account_id,
        )
        redis_set = getattr(self._redis, "set", None)
        if callable(redis_set):
            redis_set(key, "1", ex=self._unsupported_ttl_seconds)

    def record_mismatch_evidence(
        self,
        *,
        account_id: str,
        target_shop_id: str,
        actual_shop_id: str,
    ) -> dict[str, Any]:
        normalized_account_id = str(account_id or "").strip()
        normalized_target_shop_id = str(target_shop_id or "").strip()
        normalized_actual_shop_id = str(actual_shop_id or "").strip()
        if not normalized_account_id:
            return {"recorded": False, "unsupported": False}
        if not normalized_target_shop_id or not normalized_actual_shop_id:
            return {"recorded": False, "unsupported": False}
        if normalized_actual_shop_id == normalized_target_shop_id:
            return {"recorded": False, "unsupported": False}

        key = redis_keys.shop_dashboard_account_switch_observation(
            account_id=normalized_account_id,
        )
        observation = self._load_observation(key)
        observed_actual_shop_id = str(observation.get("actual_shop_id") or "").strip()
        mismatch_count = int(observation.get("mismatch_count", 0) or 0)
        target_shop_ids = [
            str(item).strip()
            for item in list(observation.get("target_shop_ids") or [])
            if str(item).strip()
        ]

        if observed_actual_shop_id != normalized_actual_shop_id:
            observed_actual_shop_id = normalized_actual_shop_id
            mismatch_count = 0
            target_shop_ids = []

        mismatch_count += 1
        if normalized_target_shop_id not in target_shop_ids:
            target_shop_ids.append(normalized_target_shop_id)

        updated_observation = {
            "actual_shop_id": observed_actual_shop_id,
            "mismatch_count": mismatch_count,
            "target_shop_ids": target_shop_ids,
        }
        self._save_observation(key, updated_observation)

        unsupported = (
            mismatch_count >= self._mismatch_threshold
            and len(target_shop_ids) >= self._min_distinct_targets
        )
        if unsupported:
            self.mark_unsupported_http_shop_switch(normalized_account_id)

        return {
            "recorded": True,
            "unsupported": unsupported,
            "mismatch_count": mismatch_count,
            "target_shop_count": len(target_shop_ids),
            "actual_shop_id": observed_actual_shop_id,
        }

    def clear_observation(self, account_id: str) -> None:
        key = redis_keys.shop_dashboard_account_switch_observation(
            account_id=account_id
        )
        redis_delete = getattr(self._redis, "delete", None)
        if callable(redis_delete):
            try:
                redis_delete(key)
            except Exception:
                return

    def _load_observation(self, key: str) -> dict[str, Any]:
        redis_get = getattr(self._redis, "get", None)
        if not callable(redis_get):
            return {}
        raw = redis_get(key)
        if raw is None:
            return {}
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="ignore")
        if not isinstance(raw, str):
            return {}
        text = raw.strip()
        if not text:
            return {}
        try:
            payload = json.loads(text)
        except ValueError:
            return {}
        if isinstance(payload, dict):
            return payload
        return {}

    def _save_observation(self, key: str, payload: dict[str, Any]) -> None:
        redis_set = getattr(self._redis, "set", None)
        if not callable(redis_set):
            return
        redis_set(
            key,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            ex=self._observation_ttl_seconds,
        )
