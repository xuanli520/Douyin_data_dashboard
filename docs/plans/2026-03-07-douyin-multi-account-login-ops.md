# Douyin Multi-Account Login Ops

## Bootstrap

1. Run manual bootstrap per account:
   `python scripts/douyin_bootstrap_login.py --account-id <account_id> --state-dir .runtime/shop_dashboard_state`
2. Complete login in browser and wait for `fxg.jinritemai.com/compass` redirect.
3. Confirm `<state-dir>/<account_id>.json` exists.

## Runtime Rules

- Account key priority: `account_id > user_phone > shop_id`.
- Browser and HTTP collectors read cookies from runtime/session state only.
- Redis is used for locks only; cookie persistence in Redis is disabled.

## Lock Strategy

- Shop lock: guard collection execution for same `shop_id`.
- Account lock: guard browser refresh for same `account_id`.

## Expired Account Handling

- Missing storage state or failed refresh marks account as expired.
- Collection returns deterministic degraded payload (`status=degraded`, `source=degraded`).
