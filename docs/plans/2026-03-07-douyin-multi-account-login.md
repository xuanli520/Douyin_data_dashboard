# Douyin Multi-Account Persistent Login Without Redis Cookie Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement multi-account persistent login using Playwright `storage_state` only, remove Redis cookie persistence completely, and keep shop dashboard collection stable.

**Architecture:** Runtime resolves stable account key (`account_id > user_phone > shop_id`), BrowserScraper and HttpScraper read cookies directly from storage_state, LoginStateManager performs layered checks and expiry downgrade, and collection flow uses dual locks (`shop` for collect, `account` for refresh).

**Tech Stack:** Python 3.12, Playwright, Redis (locks only), SQLModel, pytest, fakeredis

---

### Task 1: Add Account Key Priority Strategy

**Files:**
- Modify: `src/scrapers/shop_dashboard/runtime.py`
- Create: `tests/scrapers/shop_dashboard/test_runtime_account_key.py`

**Step 1: Write the failing test**

```python
def test_runtime_account_key_priority_account_id_then_phone_then_shop_id():
    runtime = build_runtime_config(
        data_source=_ds(extra_config={"account_id": "acct-1", "user_phone": "13800000000"}, shop_id="shop-1"),
        rule=_rule(),
        execution_id="exec-1",
    )
    assert runtime.account_id == "acct-1"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/scrapers/shop_dashboard/test_runtime_account_key.py::test_runtime_account_key_priority_account_id_then_phone_then_shop_id -v`
Expected: FAIL because priority strategy is not implemented.

**Step 3: Write minimal implementation**

```python
account_id = (
    str(pick("account_id", default="")).strip()
    or str(pick("user_phone", default="")).strip()
    or f"shop_{shop_id}"
)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/scrapers/shop_dashboard/test_runtime_account_key.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/scrapers/shop_dashboard/runtime.py tests/scrapers/shop_dashboard/test_runtime_account_key.py
git commit -m "feat: add account key priority strategy"
```

### Task 2: Implement Session State Store + Cookie Extraction Helper

**Files:**
- Create: `src/scrapers/shop_dashboard/session_state_store.py`
- Create: `tests/scrapers/shop_dashboard/test_session_state_store.py`

**Step 1: Write the failing test**

```python
def test_state_store_can_extract_cookie_mapping(tmp_path):
    store = SessionStateStore(base_dir=tmp_path)
    store.save("acct-1", {"cookies": [{"name": "sid", "value": "v"}], "origins": []})

    cookies = store.load_cookie_mapping("acct-1")
    assert cookies["sid"] == "v"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/scrapers/shop_dashboard/test_session_state_store.py::test_state_store_can_extract_cookie_mapping -v`
Expected: FAIL because extraction helper does not exist.

**Step 3: Write minimal implementation**

```python
class SessionStateStore:
    def save(self, account_id: str, state: dict[str, Any]) -> Path: ...
    def load(self, account_id: str) -> dict[str, Any] | None: ...
    def load_cookie_mapping(self, account_id: str) -> dict[str, str]: ...
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/scrapers/shop_dashboard/test_session_state_store.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/scrapers/shop_dashboard/session_state_store.py tests/scrapers/shop_dashboard/test_session_state_store.py
git commit -m "feat: add session state store and cookie extraction"
```

### Task 3: Add Layered Login Detector (URL -> DOM -> API)

**Files:**
- Create: `src/scrapers/shop_dashboard/login_state.py`
- Create: `tests/scrapers/shop_dashboard/test_login_state.py`

**Step 1: Write the failing test**

```python
async def test_check_login_status_url_layer_returns_false(fake_page):
    fake_page.url = "https://fxg.jinritemai.com/login/common"
    assert await check_login_status(fake_page) is False
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/scrapers/shop_dashboard/test_login_state.py::test_check_login_status_url_layer_returns_false -v`
Expected: FAIL because detector is not implemented.

**Step 3: Write minimal implementation**

```python
async def check_login_status(page: Page, dom_selector: str = '[data-testid="user-avatar"]', dom_timeout_ms: int = 3000, api_timeout_seconds: float = 5.0) -> bool:
    ...
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/scrapers/shop_dashboard/test_login_state.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/scrapers/shop_dashboard/login_state.py tests/scrapers/shop_dashboard/test_login_state.py
git commit -m "feat: add layered login detector"
```

### Task 4: Remove Redis Cookie Persistence From CookieManager Layer

**Files:**
- Modify: `src/scrapers/shop_dashboard/cookie_manager.py`
- Modify: `tests/scrapers/shop_dashboard/test_cookie_manager.py`

**Step 1: Write the failing test**

```python
def test_cookie_manager_no_longer_writes_cookie_to_redis(fake_redis):
    manager = CookieManager(redis_client=fake_redis)
    manager.set("acct-1", {"x_tt_token": "abc"})
    assert fake_redis.hgetall("douyin:shop_dashboard:cookie:acct-1") == {}
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/scrapers/shop_dashboard/test_cookie_manager.py::test_cookie_manager_no_longer_writes_cookie_to_redis -v`
Expected: FAIL because current implementation still writes Redis cookies.

**Step 3: Write minimal implementation**

```python
# Keep lock-related helpers only (or deprecate class)
# Remove cookie set/get persistence behavior
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/scrapers/shop_dashboard/test_cookie_manager.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/scrapers/shop_dashboard/cookie_manager.py tests/scrapers/shop_dashboard/test_cookie_manager.py
git commit -m "refactor: remove redis cookie persistence"
```

### Task 5: Refactor HttpScraper To Read Cookies From Runtime/State Only

**Files:**
- Modify: `src/scrapers/shop_dashboard/http_scraper.py`
- Modify: `tests/scrapers/shop_dashboard/test_http_scraper.py`

**Step 1: Write the failing test**

```python
def test_http_scraper_uses_runtime_cookie_mapping_without_redis():
    runtime = _runtime(cookies={"sid": "from_state"})
    result = scraper.fetch_dashboard_with_context(runtime, "2026-03-03")
    assert result["source"] == "script"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/scrapers/shop_dashboard/test_http_scraper.py::test_http_scraper_uses_runtime_cookie_mapping_without_redis -v`
Expected: FAIL before refactor.

**Step 3: Write minimal implementation**

```python
# use runtime_config.cookies only
# remove hidden reliance on redis cookie provider in shop dashboard path
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/scrapers/shop_dashboard/test_http_scraper.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/scrapers/shop_dashboard/http_scraper.py tests/scrapers/shop_dashboard/test_http_scraper.py
git commit -m "refactor: use runtime cookies from storage state only"
```

### Task 6: Refactor BrowserScraper To Storage-State-Only Session Refresh

**Files:**
- Modify: `src/scrapers/shop_dashboard/browser_scraper.py`
- Modify: `tests/scrapers/shop_dashboard/test_browser_scraper.py`

**Step 1: Write the failing test**

```python
async def test_browser_scraper_loads_and_saves_state_without_redis(tmp_path):
    store = SessionStateStore(base_dir=tmp_path)
    runtime = _runtime(account_id="acct-1", cookies={})
    scraper = BrowserScraper(state_store=store)

    await scraper.refresh_runtime_context(runtime)
    assert store.exists("acct-1") is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/scrapers/shop_dashboard/test_browser_scraper.py::test_browser_scraper_loads_and_saves_state_without_redis -v`
Expected: FAIL before refactor.

**Step 3: Write minimal implementation**

```python
# load storage_state if exists
# execute layered login check
# save updated storage_state
# update runtime.cookies from context.cookies in-memory only
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/scrapers/shop_dashboard/test_browser_scraper.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/scrapers/shop_dashboard/browser_scraper.py tests/scrapers/shop_dashboard/test_browser_scraper.py
git commit -m "feat: storage-state-only browser refresh flow"
```

### Task 7: Add Dual Lock Manager (Redis For Locks Only)

**Files:**
- Create: `src/scrapers/shop_dashboard/lock_manager.py`
- Create: `tests/scrapers/shop_dashboard/test_lock_manager.py`

**Step 1: Write the failing test**

```python
def test_lock_manager_keys():
    lock = LockManager(redis_client=fake_redis)
    assert lock.account_lock_key("acct-1") == "douyin:account:lock:acct-1"
    assert lock.shop_lock_key("shop-1") == "douyin:shop:lock:shop-1"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/scrapers/shop_dashboard/test_lock_manager.py::test_lock_manager_keys -v`
Expected: FAIL because manager does not exist.

**Step 3: Write minimal implementation**

```python
class LockManager:
    ...  # lock acquire/release for account/shop
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/scrapers/shop_dashboard/test_lock_manager.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/scrapers/shop_dashboard/lock_manager.py tests/scrapers/shop_dashboard/test_lock_manager.py
git commit -m "feat: add lock manager for account and shop scopes"
```

### Task 8: Add LoginStateManager (7-Day Probe + Expiry Downgrade)

**Files:**
- Create: `src/scrapers/shop_dashboard/login_state_manager.py`
- Create: `tests/scrapers/shop_dashboard/test_login_state_manager.py`

**Step 1: Write the failing test**

```python
async def test_login_state_manager_marks_expired_when_state_missing(tmp_path):
    mgr = LoginStateManager(...)
    assert await mgr.check_and_refresh("acct-1") is False
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/scrapers/shop_dashboard/test_login_state_manager.py::test_login_state_manager_marks_expired_when_state_missing -v`
Expected: FAIL because manager not implemented.

**Step 3: Write minimal implementation**

```python
class LoginStateManager:
    async def check_and_refresh(self, account_id: str) -> bool: ...
    async def mark_expired(self, account_id: str, reason: str) -> None: ...
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/scrapers/shop_dashboard/test_login_state_manager.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/scrapers/shop_dashboard/login_state_manager.py tests/scrapers/shop_dashboard/test_login_state_manager.py
git commit -m "feat: add login state manager with expiry downgrade"
```

### Task 9: Add Manual Bootstrap Script (No Redis Cookie Sync)

**Files:**
- Create: `scripts/douyin_bootstrap_login.py`
- Create: `tests/scripts/test_douyin_bootstrap_login.py`

**Step 1: Write the failing test**

```python
def test_bootstrap_waits_for_compass_and_saves_state(mocker):
    page = mocker.Mock()
    bootstrap_login(...)
    page.wait_for_url.assert_called_once_with("**/fxg.jinritemai.com/compass/**", timeout=300000)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/scripts/test_douyin_bootstrap_login.py::test_bootstrap_waits_for_compass_and_saves_state -v`
Expected: FAIL because script missing.

**Step 3: Write minimal implementation**

```python
# open login page
# wait_for_url compass (5 min)
# save storage_state only
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/scripts/test_douyin_bootstrap_login.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add scripts/douyin_bootstrap_login.py tests/scripts/test_douyin_bootstrap_login.py
git commit -m "feat: add bootstrap login script without redis cookie sync"
```

### Task 10: Wire Collection Flow With Dual Locks + Storage State Cookies

**Files:**
- Modify: `src/tasks/collection/douyin_shop_dashboard.py`
- Modify: `tests/tasks/test_shop_dashboard_collection.py`

**Step 1: Write the failing test**

```python
def test_collection_uses_shop_lock_refresh_uses_account_lock(monkeypatch):
    ...
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/tasks/test_shop_dashboard_collection.py::test_collection_uses_shop_lock_refresh_uses_account_lock -v`
Expected: FAIL before wiring.

**Step 3: Write minimal implementation**

```python
# collect by shop lock
# refresh by account lock
# on refresh success set runtime.cookies from state store
# on expired return deterministic degraded payload
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/tasks/test_shop_dashboard_collection.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/tasks/collection/douyin_shop_dashboard.py tests/tasks/test_shop_dashboard_collection.py
git commit -m "feat: wire dual lock and storage-state cookies into collection"
```

### Task 11: Add Browser Anti-Risk Config Fields

**Files:**
- Modify: `src/config/shop_dashboard.py`
- Modify: `tests/config/test_shop_dashboard_settings.py`
- Modify: `src/scrapers/shop_dashboard/browser_scraper.py`

**Step 1: Write the failing test**

```python
def test_browser_anti_risk_settings_exposed(monkeypatch):
    monkeypatch.setenv("SHOP_DASHBOARD__BROWSER_LOCALE", "zh-CN")
    settings = get_settings()
    assert settings.shop_dashboard.browser_locale == "zh-CN"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/config/test_shop_dashboard_settings.py::test_browser_anti_risk_settings_exposed -v`
Expected: FAIL because fields missing.

**Step 3: Write minimal implementation**

```python
# locale/timezone/viewport/user-agent fields
# apply to browser.new_context(...)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/config/test_shop_dashboard_settings.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/config/shop_dashboard.py src/scrapers/shop_dashboard/browser_scraper.py tests/config/test_shop_dashboard_settings.py
git commit -m "feat: add anti-risk browser context settings"
```

### Task 12: Add Isolation + Concurrent Refresh Tests And Docs

**Files:**
- Create: `tests/integration/test_shop_dashboard_multi_account_isolation.py`
- Create: `tests/integration/test_shop_dashboard_concurrent_refresh.py`
- Modify: `README.md`
- Create: `docs/plans/2026-03-07-douyin-multi-account-login-ops.md`

**Step 1: Write the failing test**

```python
async def test_multi_account_isolation():
    ...

async def test_concurrent_refresh():
    ...
```

**Step 2: Run tests to verify they fail first**

Run: `pytest tests/integration/test_shop_dashboard_multi_account_isolation.py tests/integration/test_shop_dashboard_concurrent_refresh.py -v`
Expected: FAIL before integration wiring.

**Step 3: Write minimal implementation support + docs**

```markdown
# Ops
- bootstrap login
- no redis cookie persistence
- dual lock strategy
- expired account handling
```

**Step 4: Run full regression**

Run: `pytest tests/scrapers/shop_dashboard tests/tasks/test_shop_dashboard_collection.py tests/config/test_shop_dashboard_settings.py tests/integration/test_shop_dashboard_multi_account_isolation.py tests/integration/test_shop_dashboard_concurrent_refresh.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add tests/integration/test_shop_dashboard_multi_account_isolation.py tests/integration/test_shop_dashboard_concurrent_refresh.py README.md docs/plans/2026-03-07-douyin-multi-account-login-ops.md
git commit -m "docs+test: finalize storage-state-only multi-account plan"
```
