from __future__ import annotations

import argparse
from typing import Any

from src.cache import resolve_sync_redis_client
from src.shared.redis_keys import redis_keys


def _parse_shop_ids(value: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for chunk in str(value or "").replace(";", ",").split(","):
        text = chunk.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _is_present(value: Any) -> bool:
    if value in {None, "", b"", 0, "0", False}:
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--shop-ids", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    account_id = str(args.account_id).strip()
    shop_ids = _parse_shop_ids(args.shop_ids)
    if not account_id or not shop_ids:
        print("invalid_arguments")
        return 1

    redis_client = resolve_sync_redis_client()
    redis_get = getattr(redis_client, "get", None)
    redis_delete = getattr(redis_client, "delete", None)

    hit_keys: list[str] = []
    for shop_id in shop_ids:
        keys = [
            redis_keys.shop_dashboard_shop_mismatch_fail_count(
                account_id=account_id,
                shop_id=shop_id,
            ),
            redis_keys.shop_dashboard_shop_mismatch_circuit(
                account_id=account_id,
                shop_id=shop_id,
            ),
        ]
        for key in keys:
            value = redis_get(key) if callable(redis_get) else None
            exists = _is_present(value)
            if exists:
                hit_keys.append(key)
            print(f"{key}\texists={str(exists).lower()}")

    if args.dry_run:
        print(f"dry_run=true\thit={len(hit_keys)}")
        return 0

    if not hit_keys:
        print("deleted=0")
        return 0
    if callable(redis_delete):
        deleted = redis_delete(*hit_keys)
        print(f"deleted={int(deleted or 0)}")
        return 0
    print("redis_delete_unavailable")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
