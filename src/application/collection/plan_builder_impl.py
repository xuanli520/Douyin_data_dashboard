from __future__ import annotations

import json
from calendar import monthrange
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from typing import Protocol
from zoneinfo import ZoneInfo

from src.shared.shop_ids import normalize_shop_ids


class CollectionConfig(Protocol):
    granularity: str | None
    timezone: str | None
    resolved_shop_ids: Any
    shop_ids: Any
    shop_id: Any
    time_range: Mapping[str, Any] | None
    incremental_mode: str | None
    data_latency: str | None
    backfill_last_n_days: Any
    cursor: str | None
    filters: Mapping[str, Any] | None
    extra_config: Mapping[str, Any] | None


@dataclass(slots=True)
class CollectionPlanUnit:
    target_shop_id: str
    window_start: datetime
    window_end: datetime
    metric_date: str
    granularity: str
    effective_filters: dict[str, Any]
    plan_index: int

    @property
    def shop_id(self) -> str:
        return self.target_shop_id

    @property
    def cursor(self) -> str | None:
        cursor = self.effective_filters.get("cursor")
        if cursor is None:
            return None
        return str(cursor)


def build_collection_plan(
    config: CollectionConfig,
    *,
    now: datetime | None = None,
) -> list[CollectionPlanUnit]:
    if now is not None and now.tzinfo is None:
        raise ValueError("now must be an aware datetime")
    granularity = str(config.granularity or "DAY").upper()
    timezone_name = str(config.timezone or "Asia/Shanghai")
    timezone = _resolve_timezone(timezone_name)
    current_now = (now or datetime.now(UTC)).astimezone(timezone)

    shop_ids = _resolve_shop_ids(config)
    if not shop_ids:
        return []

    windows = _resolve_windows(config, granularity=granularity, now=current_now)
    if not windows:
        return []

    cursor = _resolve_cursor(config)
    plan_units: list[CollectionPlanUnit] = []
    for shop_id in shop_ids:
        for window_start, window_end in windows:
            plan_units.append(
                CollectionPlanUnit(
                    target_shop_id=shop_id,
                    window_start=window_start,
                    window_end=window_end,
                    metric_date=window_start.date().isoformat(),
                    granularity=granularity,
                    effective_filters=_build_effective_filters(
                        config=config,
                        shop_id=shop_id,
                        cursor=cursor,
                    ),
                    plan_index=len(plan_units),
                )
            )
    return plan_units


def _resolve_shop_ids(config: CollectionConfig) -> list[str]:
    resolved_shop_ids = normalize_shop_ids(config.resolved_shop_ids)
    if resolved_shop_ids:
        return resolved_shop_ids

    explicit_shop_ids = normalize_shop_ids(config.shop_ids)
    if explicit_shop_ids:
        return explicit_shop_ids

    explicit_shop_id = str(config.shop_id or "").strip()
    if explicit_shop_id:
        return [explicit_shop_id]
    return []


def _resolve_windows(
    config: CollectionConfig,
    *,
    granularity: str,
    now: datetime,
) -> list[tuple[datetime, datetime]]:
    time_range = config.time_range
    if isinstance(time_range, dict):
        start_value = time_range.get("start")
        end_value = time_range.get("end")
        if isinstance(start_value, str) and isinstance(end_value, str):
            return _build_windows_from_time_range(
                granularity=granularity,
                start=_parse_time_range_boundary(
                    start_value,
                    fallback=now,
                    end_boundary=False,
                ),
                end=_parse_time_range_boundary(
                    end_value,
                    fallback=now,
                    end_boundary=True,
                ),
            )

    incremental_mode = str(config.incremental_mode or "BY_DATE").upper()
    latency_days = _parse_data_latency(str(config.data_latency or "T+1"))
    base_time = now - timedelta(days=latency_days)

    if incremental_mode == "BY_CURSOR":
        start, end = _build_single_window(base_time, granularity=granularity)
        return [(start, end)]

    backfill = _parse_non_negative_int(config.backfill_last_n_days)
    window_count = max(backfill, 1)
    windows: list[tuple[datetime, datetime]] = []
    for offset in range(window_count):
        shifted_base = _shift_base(base_time, granularity=granularity, offset=offset)
        windows.append(_build_single_window(shifted_base, granularity=granularity))
    windows.reverse()
    return windows


def _build_windows_from_time_range(
    *,
    granularity: str,
    start: datetime,
    end: datetime,
) -> list[tuple[datetime, datetime]]:
    if end < start:
        start, end = end, start
    windows: list[tuple[datetime, datetime]] = []
    cursor = _align_window_start(start, granularity=granularity)
    while cursor <= end:
        next_cursor = _next_window_start(cursor, granularity=granularity)
        window_end = min(next_cursor - timedelta(microseconds=1), end)
        windows.append((cursor, window_end))
        cursor = next_cursor
    return windows


def _resolve_cursor(config: CollectionConfig) -> str | None:
    cursor = _normalize_text(config.cursor)
    if cursor:
        return cursor
    filters = config.filters or {}
    if isinstance(filters, dict):
        filter_cursor = _normalize_text(filters.get("cursor"))
        if filter_cursor:
            return filter_cursor
    extra_config = config.extra_config or {}
    if isinstance(extra_config, dict):
        extra_cursor = _normalize_text(extra_config.get("cursor"))
        if extra_cursor:
            return extra_cursor
    return None


def _build_effective_filters(
    *,
    config: CollectionConfig,
    shop_id: str,
    cursor: str | None,
) -> dict[str, Any]:
    raw_filters = config.filters or {}
    base_filters = dict(raw_filters) if isinstance(raw_filters, dict) else {}
    date_range = _normalize_json_object(config.time_range)
    extra_filters: dict[str, Any] = {}
    for key, value in base_filters.items():
        key_text = str(key).strip()
        if not key_text or key_text in {"shop_id", "cursor", "date_range"}:
            continue
        if not _is_json_serializable(value):
            continue
        extra_filters[key_text] = value
    resolved_cursor = cursor if _is_json_serializable(cursor) else None
    return {
        "shop_id": shop_id,
        "date_range": date_range,
        "cursor": resolved_cursor,
        "extra_filters": extra_filters,
    }


def _resolve_timezone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except Exception:
        return ZoneInfo("Asia/Shanghai")


def _parse_time_range_boundary(
    value: str,
    *,
    fallback: datetime,
    end_boundary: bool,
) -> datetime:
    raw = value.strip()
    if not raw:
        return fallback
    target_tz = fallback.tzinfo or UTC
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        if len(raw) == 10:
            try:
                base = datetime.fromisoformat(f"{raw}T00:00:00")
                if end_boundary:
                    parsed = base.replace(
                        hour=23, minute=59, second=59, microsecond=999999
                    )
                else:
                    parsed = base
            except ValueError:
                return fallback
        else:
            return fallback
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=target_tz)
    return parsed.astimezone(target_tz)


def _align_window_start(base: datetime, *, granularity: str) -> datetime:
    if granularity == "HOUR":
        return base.replace(minute=0, second=0, microsecond=0)
    if granularity == "DAY":
        return base.replace(hour=0, minute=0, second=0, microsecond=0)
    if granularity == "WEEK":
        aligned = base.replace(hour=0, minute=0, second=0, microsecond=0)
        return aligned - timedelta(days=aligned.weekday())
    if granularity == "MONTH":
        return base.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return base.replace(hour=0, minute=0, second=0, microsecond=0)


def _next_window_start(current: datetime, *, granularity: str) -> datetime:
    if granularity == "HOUR":
        return current + timedelta(hours=1)
    if granularity == "DAY":
        return current + timedelta(days=1)
    if granularity == "WEEK":
        return current + timedelta(days=7)
    if granularity == "MONTH":
        month = current.month + 1
        year = current.year
        if month > 12:
            month = 1
            year += 1
        return current.replace(year=year, month=month, day=1)
    return current + timedelta(days=1)


def _build_single_window(
    base: datetime, *, granularity: str
) -> tuple[datetime, datetime]:
    start = _align_window_start(base, granularity=granularity)
    end = _next_window_start(start, granularity=granularity) - timedelta(microseconds=1)
    return start, end


def _shift_base(base: datetime, *, granularity: str, offset: int) -> datetime:
    if granularity == "HOUR":
        return base - timedelta(hours=offset)
    if granularity == "DAY":
        return base - timedelta(days=offset)
    if granularity == "WEEK":
        return base - timedelta(days=7 * offset)
    if granularity == "MONTH":
        return _shift_month(base, offset)
    return base - timedelta(days=offset)


def _shift_month(base: datetime, offset: int) -> datetime:
    total_months = base.year * 12 + (base.month - 1) - offset
    year = total_months // 12
    if year < 1:
        raise ValueError("month offset out of range")
    month = total_months % 12 + 1
    max_day = monthrange(year, month)[1]
    return base.replace(year=year, month=month, day=min(base.day, max_day))


def _parse_data_latency(data_latency: str) -> int:
    text = data_latency.strip().upper()
    if text == "REALTIME":
        return 0
    if text.startswith("T+"):
        try:
            return max(int(text[2:]), 0)
        except ValueError:
            return 0
    return 0


def _parse_non_negative_int(value: Any) -> int:
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0


def _normalize_json_object(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    normalized: dict[str, Any] = {}
    for key, item in value.items():
        key_text = _normalize_text(key)
        if not key_text or not _is_json_serializable(item):
            continue
        normalized[key_text] = item
    return normalized or None


def _is_json_serializable(value: Any) -> bool:
    if value is None:
        return True
    try:
        json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return False
    return True


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
