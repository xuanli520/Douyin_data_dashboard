from __future__ import annotations

import argparse
from pathlib import Path


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


def _safe_name(value: str) -> str:
    return str(value).replace("\\", "_").replace("/", "_").strip()


def _bundle_path(base_dir: Path, account_id: str, shop_id: str) -> Path:
    return base_dir / "bundles" / _safe_name(account_id) / f"{_safe_name(shop_id)}.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--shop-ids", required=True)
    parser.add_argument("--base-dir", default=".runtime/shop_dashboard_state")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    account_id = str(args.account_id).strip()
    shop_ids = _parse_shop_ids(args.shop_ids)
    if not account_id or not shop_ids:
        print("invalid_arguments")
        return 1

    base_dir = Path(args.base_dir)
    hit_paths: list[Path] = []
    for shop_id in shop_ids:
        target = _bundle_path(base_dir, account_id, shop_id)
        exists = target.exists()
        if exists:
            hit_paths.append(target)
        print(f"{target}\texists={str(exists).lower()}")

    if args.dry_run:
        print(f"dry_run=true\thit={len(hit_paths)}")
        return 0

    deleted = 0
    for path in hit_paths:
        try:
            path.unlink()
            deleted += 1
        except FileNotFoundError:
            continue
    print(f"deleted={deleted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
