from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import ceil


def build_pagination_meta(page: int, size: int, total: int) -> dict[str, int | bool]:
    size = max(size, 1)
    page = max(page, 1)
    pages = max(ceil(total / size), 1) if total else 0
    return {
        "page": page,
        "size": size,
        "total": total,
        "pages": pages,
        "has_next": page < pages,
        "has_prev": page > 1 and pages > 0,
    }


def _core_numbers(shop_id: int, date_range: str | None) -> dict[str, float | int]:
    seed = shop_id * 31 + sum(ord(ch) for ch in (date_range or "30d"))
    orders = 1200 + seed % 900
    average_order_value = 95 + seed % 55
    gmv = round(orders * average_order_value, 2)
    refund_rate = round(1.8 + (seed % 42) * 0.05, 2)
    conversion_rate = round(2.1 + (seed % 35) * 0.07, 2)
    return {
        "orders": orders,
        "average_order_value": average_order_value,
        "gmv": gmv,
        "refund_rate": refund_rate,
        "conversion_rate": conversion_rate,
    }


def _series(points: int) -> list[str]:
    now = datetime.now(tz=UTC)
    return [
        (now - timedelta(days=points - index - 1)).date().isoformat()
        for index in range(points)
    ]


def build_dashboard_overview(shop_id: int, date_range: str | None) -> dict[str, object]:
    core = _core_numbers(shop_id, date_range)
    return {
        "shop_id": shop_id,
        "date_range": date_range or "30d",
        "cards": {
            "orders": core["orders"],
            "gmv": core["gmv"],
            "average_order_value": core["average_order_value"],
            "refund_rate": f"{core['refund_rate']}%",
            "conversion_rate": f"{core['conversion_rate']}%",
        },
    }


def build_dashboard_kpis(shop_id: int, date_range: str | None) -> dict[str, object]:
    core = _core_numbers(shop_id, date_range)
    dates = _series(7)
    return {
        "shop_id": shop_id,
        "date_range": date_range or "30d",
        "kpis": [
            {
                "id": "orders",
                "value": core["orders"],
                "change": f"+{round((shop_id % 9) + 1.1, 2)}%",
            },
            {
                "id": "gmv",
                "value": core["gmv"],
                "change": f"+{round((shop_id % 7) + 1.7, 2)}%",
            },
            {
                "id": "refund_rate",
                "value": f"{core['refund_rate']}%",
                "change": f"-{round((shop_id % 3) + 0.2, 2)}%",
            },
        ],
        "trend": [
            {
                "date": day,
                "orders": int(core["orders"] * (0.88 + idx * 0.02)),
                "gmv": round(float(core["gmv"]) * (0.87 + idx * 0.02), 2),
            }
            for idx, day in enumerate(dates)
        ],
    }


def build_orders_trend(
    shop_id: int, date_range: str | None, dimension: str
) -> dict[str, object]:
    core = _core_numbers(shop_id, date_range)
    points = 7 if dimension == "day" else 6 if dimension == "week" else 12
    return {
        "shop_id": shop_id,
        "dimension": dimension,
        "date_range": date_range or "30d",
        "trend": [
            {
                "date": day,
                "order_count": int(core["orders"] * (0.82 + index * 0.025)),
                "gmv": round(float(core["gmv"]) * (0.8 + index * 0.025), 2),
            }
            for index, day in enumerate(_series(points))
        ],
    }


def build_orders_analysis(
    shop_id: int, date_range: str | None, channel: str | None
) -> dict[str, object]:
    core = _core_numbers(shop_id, date_range)
    channels = [("live", 0.38), ("short_video", 0.3), ("store", 0.2), ("search", 0.12)]
    analysis = [
        {
            "channel": name,
            "order_count": int(core["orders"] * ratio),
            "gmv": round(float(core["gmv"]) * (ratio + 0.03), 2),
            "conversion_rate": f"{round(float(core['conversion_rate']) + idx * 0.4, 2)}%",
            "refund_rate": f"{round(float(core['refund_rate']) + idx * 0.25, 2)}%",
        }
        for idx, (name, ratio) in enumerate(channels)
    ]
    if channel:
        analysis = [item for item in analysis if item["channel"] == channel]
    return {"shop_id": shop_id, "date_range": date_range or "30d", "analysis": analysis}


def build_products_funnel(
    shop_id: int, date_range: str | None, product_id: int | None
) -> dict[str, object]:
    core = _core_numbers(shop_id, date_range)
    exposure = int(core["orders"] * 160)
    click = int(exposure * 0.18)
    visit = int(click * 0.68)
    cart = int(visit * 0.26)
    pay = int(cart * 0.54)
    return {
        "shop_id": shop_id,
        "product_id": product_id,
        "date_range": date_range or "30d",
        "funnel": [
            {"stage": "exposure", "value": exposure, "rate": "100%"},
            {
                "stage": "click",
                "value": click,
                "rate": f"{round(click / exposure * 100, 2)}%",
            },
            {
                "stage": "visit",
                "value": visit,
                "rate": f"{round(visit / click * 100, 2)}%",
            },
            {
                "stage": "cart",
                "value": cart,
                "rate": f"{round(cart / visit * 100, 2)}%",
            },
            {"stage": "pay", "value": pay, "rate": f"{round(pay / cart * 100, 2)}%"},
        ],
    }


def build_products_ranking(
    shop_id: int,
    date_range: str | None,
    metric: str,
    page: int,
    size: int,
) -> dict[str, object]:
    total = 60
    page = max(page, 1)
    size = max(size, 1)
    start = (page - 1) * size
    seed = sum(ord(ch) for ch in (date_range or "30d")) + shop_id
    items = [
        {
            "id": product_id,
            "name": f"product_{product_id}",
            "metric": metric,
            "metric_value": round(200 + base * 1.37, 2),
            "orders": 30 + (base % 170),
            "gmv": round(10000 + base * 18.5, 2),
            "refund_rate": f"{round(1.1 + (base % 16) * 0.13, 2)}%",
        }
        for product_id, base in [
            (9000 + index + 1, (seed + index * 13) % 1000)
            for index in range(start, min(start + size, total))
        ]
    ]
    return {
        "items": items,
        "meta": build_pagination_meta(page=page, size=size, total=total),
    }


def build_sales_summary(
    shop_id: int, date_range: str | None, dimension: str
) -> dict[str, object]:
    core = _core_numbers(shop_id, date_range)
    return {
        "shop_id": shop_id,
        "dimension": dimension,
        "date_range": date_range or "30d",
        "summary": {
            "gmv": core["gmv"],
            "paid_orders": core["orders"],
            "average_order_value": core["average_order_value"],
            "conversion_rate": f"{core['conversion_rate']}%",
        },
    }


def build_sales_by_channel(shop_id: int, date_range: str | None) -> dict[str, object]:
    core = _core_numbers(shop_id, date_range)
    channels = [
        ("live", 0.46),
        ("short_video", 0.28),
        ("store", 0.17),
        ("search", 0.09),
    ]
    rows = [
        {
            "channel": channel,
            "gmv": round(float(core["gmv"]) * ratio, 2),
            "share": f"{round(ratio * 100, 2)}%",
        }
        for channel, ratio in channels
    ]
    return {"shop_id": shop_id, "date_range": date_range or "30d", "channels": rows}


def build_after_sales_refund_rate(
    shop_id: int, date_range: str | None
) -> dict[str, object]:
    core = _core_numbers(shop_id, date_range)
    return {
        "shop_id": shop_id,
        "date_range": date_range or "30d",
        "trend": [
            {
                "date": day,
                "refund_rate": f"{round(float(core['refund_rate']) + (idx - 3) * 0.08, 2)}%",
                "refund_count": 15 + idx * 3 + shop_id % 5,
            }
            for idx, day in enumerate(_series(8))
        ],
    }


def build_after_sales_causes(
    shop_id: int, date_range: str | None, page: int, size: int
) -> dict[str, object]:
    reasons = [
        "size_mismatch",
        "quality_issue",
        "delivery_delay",
        "description_mismatch",
        "other",
    ]
    page = max(page, 1)
    size = max(size, 1)
    start = (page - 1) * size
    core = _core_numbers(shop_id, date_range)
    items = [
        {
            "cause": reason,
            "count": 40 + idx * 19 + shop_id % 8,
            "share": f"{round(12 + idx * 7.5, 2)}%",
            "impact_gmv": round(float(core["gmv"]) * (0.03 + idx * 0.008), 2),
        }
        for idx, reason in enumerate(reasons[start : start + size], start=start)
    ]
    return {
        "items": items,
        "meta": build_pagination_meta(page=page, size=size, total=len(reasons)),
    }


def build_alerts(
    level: str | None,
    status: str | None,
    assignee: str | None,
    shop_id: int | None,
    date_range: str | None,
    page: int,
    size: int,
) -> dict[str, object]:
    levels = ["critical", "warning", "info"]
    statuses = ["pending", "processing", "resolved", "ignored"]
    rows = [
        {
            "id": f"alert_{index + 1}",
            "level": levels[index % len(levels)],
            "title": f"{levels[index % len(levels)]}_alert_{index + 1}",
            "occurred_at": (datetime.now(tz=UTC) - timedelta(hours=index * 2))
            .replace(microsecond=0)
            .isoformat(),
            "status": statuses[index % len(statuses)],
            "assignee": f"owner_{index % 5 + 1}" if index % 3 else "",
            "shop_id": shop_id or 1001 + index % 8,
        }
        for index in range(48)
    ]
    filtered = [
        item
        for item in rows
        if (not level or item["level"] == level)
        and (not status or item["status"] == status)
        and (not assignee or item["assignee"] == assignee)
    ]
    page = max(page, 1)
    size = max(size, 1)
    start = (page - 1) * size
    summary = {
        "critical": len([item for item in rows if item["level"] == "critical"]),
        "warning": len([item for item in rows if item["level"] == "warning"]),
        "info": len([item for item in rows if item["level"] == "info"]),
        "total": len(rows),
        "unread": len(
            [item for item in rows if item["status"] in {"pending", "processing"}]
        ),
    }
    return {
        "date_range": date_range or "30d",
        "items": filtered[start : start + size],
        "meta": build_pagination_meta(page=page, size=size, total=len(filtered)),
        "summary": summary,
    }


def build_alert_action(
    alert_id: str, action: str, assignee: str | None = None
) -> dict[str, object]:
    status_map = {
        "assign": "processing",
        "resolve": "resolved",
        "ignore": "ignored",
        "acknowledge": "processing",
    }
    return {
        "id": alert_id,
        "action": action,
        "status": status_map[action],
        "assignee": assignee,
        "updated_at": datetime.now(tz=UTC).replace(microsecond=0).isoformat(),
    }


def build_alert_rules(page: int, size: int) -> dict[str, object]:
    total = 18
    page = max(page, 1)
    size = max(size, 1)
    start = (page - 1) * size
    items = [
        {
            "id": f"rule_{index + 1}",
            "name": f"rule_{index + 1}",
            "metric": ["gmv_drop", "refund_rate", "risk_score"][index % 3],
            "threshold": f"{5 + index}%",
            "level": ["critical", "warning", "info"][index % 3],
            "enabled": index % 4 != 0,
            "recent_hits": 1 + index % 9,
            "last_hit_at": (datetime.now(tz=UTC) - timedelta(hours=index))
            .replace(microsecond=0)
            .isoformat(),
        }
        for index in range(start, min(start + size, total))
    ]
    return {
        "items": items,
        "meta": build_pagination_meta(page=page, size=size, total=total),
    }


def build_created_alert_rule(payload: dict[str, object]) -> dict[str, object]:
    return {
        "id": f"rule_{int(datetime.now(tz=UTC).timestamp())}",
        "name": payload.get("name", "new_rule"),
        "metric": payload.get("metric", "gmv_drop"),
        "threshold": str(payload.get("threshold", "10%")),
        "level": payload.get("level", "warning"),
        "enabled": True,
        "recent_hits": 0,
        "last_hit_at": None,
    }


def build_notification_channels() -> dict[str, object]:
    return {
        "items": [
            {
                "id": "channel_wecom",
                "type": "wecom",
                "name": "wecom_bot",
                "status": "active",
                "last_test_at": (datetime.now(tz=UTC) - timedelta(hours=6))
                .replace(microsecond=0)
                .isoformat(),
                "last_test_result": "success",
                "failure_reason": "",
            },
            {
                "id": "channel_email",
                "type": "email",
                "name": "ops_mailbox",
                "status": "active",
                "last_test_at": (datetime.now(tz=UTC) - timedelta(hours=22))
                .replace(microsecond=0)
                .isoformat(),
                "last_test_result": "failed",
                "failure_reason": "smtp_timeout",
            },
        ]
    }


def build_notification_test(channel_id: str) -> dict[str, object]:
    failed = channel_id.endswith("email")
    return {
        "channel_id": channel_id,
        "result": "failed" if failed else "success",
        "sent_at": datetime.now(tz=UTC).replace(microsecond=0).isoformat(),
        "failure_reason": "smtp_timeout" if failed else "",
    }


def build_tasks(
    status: str | None,
    task_type: str | None,
    date_range: str | None,
    page: int,
    size: int,
) -> dict[str, object]:
    statuses = ["pending", "running", "completed", "failed", "stopped"]
    task_types = ["order_collection", "product_sync", "metric_refresh", "alert_scan"]
    rows = [
        {
            "id": index + 1,
            "name": f"task_{index + 1}",
            "task_type": task_types[index % len(task_types)],
            "last_status": statuses[index % len(statuses)],
            "last_run_at": (datetime.now(tz=UTC) - timedelta(hours=index * 3))
            .replace(microsecond=0)
            .isoformat(),
            "duration_ms": 5000 + index * 170,
        }
        for index in range(44)
    ]
    filtered = [
        item
        for item in rows
        if (not status or item["last_status"] == status)
        and (not task_type or item["task_type"] == task_type)
    ]
    page = max(page, 1)
    size = max(size, 1)
    start = (page - 1) * size
    return {
        "date_range": date_range or "30d",
        "items": filtered[start : start + size],
        "meta": build_pagination_meta(page=page, size=size, total=len(filtered)),
    }


def build_task_create(payload: dict[str, object]) -> dict[str, object]:
    return {
        "id": int(datetime.now(tz=UTC).timestamp()),
        "name": payload.get("name", "task_new"),
        "task_type": payload.get("task_type", "order_collection"),
        "last_status": "pending",
        "last_run_at": None,
        "duration_ms": 0,
    }


def build_task_action(task_id: int, action: str) -> dict[str, object]:
    return {
        "task_id": task_id,
        "execution_id": f"exec_{task_id}_{int(datetime.now(tz=UTC).timestamp())}",
        "status": "running" if action == "run" else "stopped",
        "updated_at": datetime.now(tz=UTC).replace(microsecond=0).isoformat(),
    }


def build_task_executions(task_id: int, page: int, size: int) -> dict[str, object]:
    total = 24
    page = max(page, 1)
    size = max(size, 1)
    start = (page - 1) * size
    rows = [
        {
            "execution_id": f"exec_{task_id}_{index + 1}",
            "task_id": task_id,
            "status": ["completed", "failed", "running"][index % 3],
            "started_at": (datetime.now(tz=UTC) - timedelta(hours=index * 2 + 1))
            .replace(microsecond=0)
            .isoformat(),
            "completed_at": (datetime.now(tz=UTC) - timedelta(hours=index * 2))
            .replace(microsecond=0)
            .isoformat(),
            "duration_ms": 4000 + index * 320,
            "processed_count": 200 + index * 17,
        }
        for index in range(start, min(start + size, total))
    ]
    return {
        "items": rows,
        "meta": build_pagination_meta(page=page, size=size, total=total),
    }


def build_task_execution_detail(task_id: int, execution_id: str) -> dict[str, object]:
    return {
        "task_id": task_id,
        "execution_id": execution_id,
        "status": "failed" if execution_id.endswith("3") else "completed",
        "duration_ms": 8200,
        "processed_count": 1680,
        "failed_samples": [
            {"id": "sample_1", "reason": "validation_failed"},
            {"id": "sample_2", "reason": "timeout"},
        ],
        "retry_chain": [execution_id],
        "log_lines": [
            "task_started",
            "records_loaded:1682",
            "records_processed:1680",
            "records_failed:2",
            "task_finished",
        ],
    }


def build_task_retry(task_id: int, execution_id: str) -> dict[str, object]:
    return {
        "task_id": task_id,
        "source_execution_id": execution_id,
        "execution_id": f"retry_{execution_id}",
        "status": "pending",
        "queued_at": datetime.now(tz=UTC).replace(microsecond=0).isoformat(),
    }


def build_reports(
    status: str | None,
    report_type: str | None,
    date_range: str | None,
    page: int,
    size: int,
) -> dict[str, object]:
    statuses = ["pending", "processing", "completed", "failed", "expired"]
    types = ["sales", "product", "service", "risk"]
    rows = [
        {
            "id": f"report_{index + 1}",
            "name": f"{types[index % len(types)]}_report_{index + 1}",
            "type": types[index % len(types)],
            "status": statuses[index % len(statuses)],
            "created_at": (datetime.now(tz=UTC) - timedelta(days=index))
            .replace(microsecond=0)
            .isoformat(),
            "file_size": 120000 + index * 840,
            "expire_at": (datetime.now(tz=UTC) + timedelta(days=7 - (index % 5)))
            .replace(microsecond=0)
            .isoformat(),
        }
        for index in range(22)
    ]
    filtered = [
        item
        for item in rows
        if (not status or item["status"] == status)
        and (not report_type or item["type"] == report_type)
    ]
    page = max(page, 1)
    size = max(size, 1)
    start = (page - 1) * size
    return {
        "date_range": date_range or "30d",
        "items": filtered[start : start + size],
        "meta": build_pagination_meta(page=page, size=size, total=len(filtered)),
    }


def build_report_generate(payload: dict[str, object]) -> dict[str, object]:
    report_id = f"report_{int(datetime.now(tz=UTC).timestamp())}"
    return {
        "id": report_id,
        "name": payload.get("name", report_id),
        "type": payload.get("type", "sales"),
        "status": "pending",
        "created_at": datetime.now(tz=UTC).replace(microsecond=0).isoformat(),
        "file_size": 0,
        "expire_at": None,
    }


def build_report_download(report_id: str) -> dict[str, object]:
    completed = sum(ord(ch) for ch in report_id) % 2 == 0
    return {
        "id": report_id,
        "status": "completed" if completed else "processing",
        "download_key": f"reports/{report_id}.xlsx" if completed else "",
        "file_size": 240912 if completed else 0,
        "expire_at": (datetime.now(tz=UTC) + timedelta(days=2))
        .replace(microsecond=0)
        .isoformat()
        if completed
        else None,
    }


def build_exports(
    status: str | None, date_range: str | None, page: int, size: int
) -> dict[str, object]:
    statuses = ["pending", "processing", "completed", "failed", "expired"]
    rows = [
        {
            "id": f"export_{index + 1}",
            "name": f"export_{index + 1}",
            "status": statuses[index % len(statuses)],
            "created_at": (datetime.now(tz=UTC) - timedelta(hours=index * 4))
            .replace(microsecond=0)
            .isoformat(),
            "file_size": 84000 + index * 1230,
            "expire_at": (datetime.now(tz=UTC) + timedelta(days=3 - index % 3))
            .replace(microsecond=0)
            .isoformat(),
        }
        for index in range(26)
    ]
    filtered = [item for item in rows if not status or item["status"] == status]
    page = max(page, 1)
    size = max(size, 1)
    start = (page - 1) * size
    return {
        "date_range": date_range or "30d",
        "items": filtered[start : start + size],
        "meta": build_pagination_meta(page=page, size=size, total=len(filtered)),
    }


def build_export_create(payload: dict[str, object]) -> dict[str, object]:
    export_id = f"export_{int(datetime.now(tz=UTC).timestamp())}"
    return {
        "id": export_id,
        "name": payload.get("name", export_id),
        "status": "pending",
        "created_at": datetime.now(tz=UTC).replace(microsecond=0).isoformat(),
        "file_size": 0,
        "expire_at": None,
    }


def build_export_download(export_id: str) -> dict[str, object]:
    completed = sum(ord(ch) for ch in export_id) % 3 != 0
    return {
        "id": export_id,
        "status": "completed" if completed else "processing",
        "download_key": f"exports/{export_id}.csv" if completed else "",
        "file_size": 162048 if completed else 0,
        "expire_at": (datetime.now(tz=UTC) + timedelta(days=1))
        .replace(microsecond=0)
        .isoformat()
        if completed
        else None,
    }


def build_system_config() -> dict[str, object]:
    return {
        "version": "2026.02",
        "env": "development",
        "cache": {"backend": "redis", "ttl_seconds": 300},
        "scheduler": {"workers": 3, "timezone": "Asia/Shanghai"},
    }


def build_system_health() -> dict[str, object]:
    return {
        "status": "healthy",
        "checked_at": datetime.now(tz=UTC).replace(microsecond=0).isoformat(),
        "dependencies": {"database": "healthy", "cache": "healthy", "queue": "healthy"},
    }


def build_system_backup() -> dict[str, object]:
    return {
        "backup_id": f"backup_{int(datetime.now(tz=UTC).timestamp())}",
        "status": "pending",
        "created_at": datetime.now(tz=UTC).replace(microsecond=0).isoformat(),
        "audit": {"action": "backup", "result": "accepted"},
    }


def build_system_cleanup(
    retention_days: int, include_exports: bool
) -> dict[str, object]:
    return {
        "status": "accepted",
        "retention_days": retention_days,
        "include_exports": include_exports,
        "affected": {
            "reports": max(0, retention_days // 2),
            "exports": max(0, retention_days // 3) if include_exports else 0,
            "audit_logs": max(0, retention_days // 4),
        },
        "audit": {"action": "cleanup", "result": "accepted"},
    }


def build_system_user_settings(user_id: int) -> dict[str, object]:
    return {
        "user_id": user_id,
        "emailNotification": True,
        "pushNotification": True,
        "riskAlert": True,
        "taskReminder": False,
        "twoFactorAuth": False,
        "sessionTimeout": 30,
        "language": "zh-CN",
        "timezone": "Asia/Shanghai",
        "theme": "light",
    }


def patch_system_user_settings(
    user_id: int, payload: dict[str, object]
) -> dict[str, object]:
    settings = build_system_user_settings(user_id)
    settings.update(payload)
    settings["updated_at"] = datetime.now(tz=UTC).replace(microsecond=0).isoformat()
    return settings
