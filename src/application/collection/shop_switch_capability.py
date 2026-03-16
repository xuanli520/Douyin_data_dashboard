from __future__ import annotations

import json
import logging
from typing import Any

from src.application.collection.redis_client import RedisClient
from src.application.collection.redis_client import resolve_collection_redis_client
from src.config import get_settings
from src.shared.redis_keys import redis_keys


logger = logging.getLogger(__name__)


class ShopSwitchCapabilityService:
    def __init__(self, *, redis_client: RedisClient | None) -> None:
        settings = get_settings().shop_dashboard
        self._redis = resolve_collection_redis_client(
            redis_client,
            component="shop_switch_capability_service",
            logger=logger,
        )
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
        try:
            value = self._redis.get(key)
        except Exception:
            return False
        if value in {None, "", b"", 0, "0", b"0", False}:
            return False
        return True

    def mark_unsupported_http_shop_switch(self, account_id: str) -> None:
        key = redis_keys.shop_dashboard_unsupported_http_shop_switch(
            account_id=account_id,
        )
        try:
            self._redis.set(key, "1", ex=self._unsupported_ttl_seconds)
        except Exception:
            return

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
        try:
            self._redis.delete(key)
        except Exception as exc:
            logger.warning(
                "failed to clear shop switch observation account_id=%s error=%s",
                account_id,
                exc,
            )

    def _load_observation(self, key: str) -> dict[str, Any]:
        try:
            raw = self._redis.get(key)
        except Exception:
            return {}
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
        try:
            self._redis.set(
                key,
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                ex=self._observation_ttl_seconds,
            )
        except Exception:
            return
