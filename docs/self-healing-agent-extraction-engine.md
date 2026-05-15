# Self-Healing Agent Extraction Engine

## Document Status and Current Code Facts

This document is a target design, not a description of code that already exists.

Current repository facts:

1. `src/extraction` and `src/domains/extraction_rule` do not exist.
2. The current collection path runs `browser_agent`.
3. `extraction_engine_enabled`, `extraction_engine_primary`, `playwright_cli_path`, `glm_model`, `extraction_url_allowlist`, and `extraction_explorer_enabled` are not current `ShopDashboardSettings` fields.
4. Docker installs Node `@playwright/cli` browsers with `playwright-cli install-browser --with-deps`.
5. There are no `extraction_rules`, `rule_revisions`, `agent_recipes`, or related migrations.
6. There is no `tests/extraction` directory. Existing tests cover browser-agent task fallback, worker entries, and current persistence behavior.
7. Current persistence tests do not verify `source="extract"` or `raw.extraction.source="extraction_engine"`.

## Context

当前抖店数据采集已转向浏览器执行 + 规则驱动 + 受控自愈，旧 LLM 冷数据补齐不再作为采集链路。

## Architecture

以下是目标架构。当前仓库尚未实现 `ExtractionEngine`、`Explorer`、`RuleStore` 或 `PlaywrightCLI`。

```
Python Orchestrator
  ├── Scheduler / CollectionUseCase / PlanBuilder (复用)
  ├── SessionStateStore / LoginStateManager / LockManager (复用)
  ├── ShopStateMaterializer / PlaywrightShopBootstrapper (账号态 + 店铺态隔离)
  ├── Rule Store (目标：PG JSONB: extraction_rules + rule_revisions, 绑定 data_source + scraping_rule)
  ├── GLM-5.1 Client (候选，仅在 Explorer 自愈时调用)
  └── Browser Driver (playwright-cli subprocess)
        ├── state-load/state-save → 读取账号登录态 + 临时店铺态
        ├── open/goto/click/eval → 页面导航与等待
        ├── eval → 用规则选择器提取数据 (0 token)
        └── screenshot --filename / snapshot --filename → Explorer 素材
```

**自愈闭环：**
```
Executor(eval+规则提取+完整性校验) → 字段缺失/选择器失效 → Explorer(screenshot+快照+GLM-5.1) → 新规则验证 → 更新 PG → 重采集
```

## Planned File Changes

本节列出目标文件变更。当前这些 `src/extraction/*` 与 `src/domains/extraction_rule/*` 文件尚未存在。

### Planned new files

| File | Purpose |
|---|---|
| `src/extraction/__init__.py` | 模块入口 |
| `src/extraction/config.py` | 从 `ShopDashboardSettings` 读取并校验 extraction 配置的 helper |
| `src/extraction/exceptions.py` | ExtractionFailed / SelectorFailed / PermissionDenied 等异常 |
| `src/extraction/types.py` | ExtractionRule / NavigationStep / ExtractionField 类型定义 |
| `src/extraction/rule_store.py` | PG CRUD: extraction_rules, rule_revisions；通过 scraping_rule_id 复用现有 data_source/scraping_rule 服务/仓储解析作用域 |
| `src/extraction/playwright_cli.py` | playwright-cli subprocess 封装器 |
| `src/extraction/session_state.py` | 将账号 storage state 与 per-shop Playwright state 物化为 CLI temp state file |
| `src/extraction/shop_context.py` | Playwright 内店铺切换、actual_shop_id 校验、per-shop storage state 生成 |
| `src/extraction/executor.py` | Rule Executor: 导航 + eval 提取 + 完整性校验 |
| `src/extraction/explorer.py` | Rule Explorer: 截图 + snapshot + GLM-5.1 分析 + 规则更新 |
| `src/extraction/engine.py` | Extraction Engine: 编排 Executor/Explorer，对外统一接口 |
| `src/domains/extraction_rule/__init__.py` | Domain 入口 |
| `src/domains/extraction_rule/models.py` | SQLModel 表: ExtractionRule, RuleRevision |
| `src/domains/extraction_rule/repository.py` | PG 操作层 |

### Planned modified files

| File | Change |
|---|---|
| `src/config/shop_dashboard.py` | 拟新增 extraction_engine / browser driver / glm 配置项 |
| `src/scrapers/shop_dashboard/rule_config_resolver.py` | 拟让 `fallback_chain` 支持 `"extraction_engine"`；移除 `"agent"/"llm"` stage 只能在替代链路稳定后执行 |
| `src/scrapers/shop_dashboard/runtime.py` | 拟让默认 fallback 由 extraction_engine 开关决定；不新增 `data_source_id` |
| `src/scrapers/shop_dashboard/session_state_store.py` | 拟暴露账号 state path；拟新增独立 per-shop Playwright storage state 原始读写；保留旧 cookie bundle |
| `src/tasks/collection/douyin_shop_dashboard.py` | 拟新增 `_collect_via_extraction_engine`；移除 agent fallback 只能在 Rollout 3 后执行 |
| `src/application/collection/executor.py` | collector 透传 `plan_unit`，保证日期窗口/过滤器可用于页面导航 |
| `src/application/collection/usecase.py` | 调用 collector 时传入 `plan_unit` |
| `docker/Dockerfile` | 安装 Node.js + `@playwright/cli` 并执行 `playwright-cli install-browser --with-deps` |

### Eventual removal (Rollout 3, planned)

以下删除项必须等 extraction engine 代码、迁移、worker 注册调整、测试和灰度验证完成后再执行。当前仓库仍保留这些模块。

| File | Reason |
|---|---|
| `src/agents/llm_dashboard_agent.py` | 被 extraction_engine 自愈采集替代 |
| `src/tasks/collection/` | 独立 agent 队列被移除 |
| `src/tasks/worker.py` | 移除旧 agent 队列注册 |
| `src/tasks/collection/__init__.py` / `src/tasks/__init__.py` | 移除 agent task 导出 |
| `src/scrapers/shop_dashboard/http_scraper.py` | 仅在 `SessionBootstrapper` 不再依赖其常量/校验逻辑后删除 |

### Retained files

| File | Reason |
|---|---|
| `src/scrapers/shop_dashboard/session_bootstrapper.py` | Phase 1/2 继续负责 HTTP 旧链路的账号/店铺切换与验证 |
| `src/scrapers/shop_dashboard/login_state_manager.py` | 继续负责登录态有效性标记 |
| `src/scrapers/shop_dashboard/session_state_store.py` | 继续作为账号 storage_state、HTTP cookie bundle、Playwright shop state 的唯一文件存储入口 |
| `src/scrapers/shop_dashboard/lock_manager.py` | 继续负责账号/店铺采集互斥 |

## Phase 1 — Foundation

### 1.1 Config

目标是在 `src/config/shop_dashboard.py` 新增。当前这些字段尚不存在。为减少配置分散，拟新增的 `src/extraction/config.py` 不再定义独立 Settings，只提供从 `get_settings().shop_dashboard` 读取并校验 extraction 配置的 helper。
```python
# browser driver
browser_driver: str = "playwright_cli"
playwright_cli_path: str = "playwright-cli"  # only required if browser_driver == "playwright_cli"
browser_driver_timeout_seconds: int = 60
browser_driver_artifact_dir: str = ".runtime/playwright_driver"
browser_driver_session_prefix: str = "extract"

# Extraction Engine
extraction_engine_enabled: bool = False
extraction_engine_primary: bool = False
extraction_rule_page_key: str = "shop_dashboard"
extraction_url_allowlist: list[str] = []
extraction_explorer_enabled: bool = False
extraction_artifact_ttl_seconds: int = 86400
extraction_snapshot_max_chars: int = 60000

# GLM Explorer (candidate provider)
glm_endpoint: str = ""
glm_model: str = "glm-5.1"
glm_api_key: str = ""
glm_timeout_seconds: int = 120
glm_max_retries: int = 3
explorer_confidence_threshold: float = 0.6
```

配置默认不改变现网采集行为：`extraction_engine_enabled=False` 时 resolver 不得把默认 fallback 解析为 `extraction_engine`。当前默认采集链路由 `browser_agent` 执行。`extraction_explorer_enabled=False` 时只执行规则提取，不调用 GLM；selector 失败直接返回 `ExtractionFailed("selector_failed")`。

### 1.2 Rule Store (`src/domains/extraction_rule/models.py`)

目标新增 `src/domains/extraction_rule/models.py`。当前仓库没有该目录、模型或迁移。

```python
class ExtractionRule(SQLModel, table=True):
    __tablename__ = "extraction_rules"
    __table_args__ = (
        UniqueConstraint(
            "data_source_id",
            "scraping_rule_id",
            "target_type",
            "page_key",
            name="uq_extraction_rule_scope",
        ),
        CheckConstraint(
            "status IN ('active', 'degraded')",
            name="ck_extraction_rules_status",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    data_source_id: int = Field(foreign_key="data_sources.id", index=True, ondelete="CASCADE")
    scraping_rule_id: int = Field(foreign_key="scraping_rules.id", index=True, ondelete="CASCADE")
    target_type: str = Field(index=True, max_length=100)
    page_key: str = Field(index=True, max_length=100)
    name: str = Field(index=True, max_length=200)
    version: int = Field(default=1)
    status: str = Field(default="active")  # active | degraded
    source_url_template: str
    navigation: dict = Field(sa_type=JSON)
    extractions: dict = Field(sa_type=JSON)
    integrity: dict = Field(sa_type=JSON)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class RuleRevision(SQLModel, table=True):
    __tablename__ = "rule_revisions"
    __table_args__ = (
        UniqueConstraint(
            "rule_id",
            "version",
            name="uq_rule_revision_rule_version",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    rule_id: int = Field(foreign_key="extraction_rules.id", index=True, ondelete="CASCADE")
    data_source_id: int = Field(foreign_key="data_sources.id", index=True, ondelete="CASCADE")
    scraping_rule_id: int = Field(foreign_key="scraping_rules.id", index=True, ondelete="CASCADE")
    version: int
    trigger_reason: str = Field(max_length=500)
    change_summary: str | None = Field(default=None, max_length=2000)
    navigation_snapshot: dict = Field(sa_type=JSON)
    extractions_snapshot: dict = Field(sa_type=JSON)
    integrity_snapshot: dict = Field(sa_type=JSON)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

迁移在 Postgres 使用 JSONB；SQLModel 字段保持 `JSON`，避免 SQLite 测试环境不可用。规则按 `(data_source_id, scraping_rule_id, target_type, page_key)` 唯一；revision 按 `(rule_id, version)` 唯一，保存被覆盖前的旧版本快照。更新时必须在同一事务内锁定规则、校验 version、写入 `rule_revisions` 后原地递增版本。

`src/extraction/rule_store.py` 对外提供同步 facade，内部通过 async repository + `session.run_coro()` 访问数据库，避免 `_collect_one_day` 在线程池同步入口里直接暴露 async session。RuleStore 不从 runtime 读取 `data_source_id`：通过 `runtime.rule_id` 复用现有 `ScrapingRuleService` / `DataSourceService` 或对应 repository 解析并校验 data source 与 scraping rule，再用解析出的 `data_source_id` 查询或创建 `extraction_rules`。`get_active()` 只返回 `status == "active"` 的规则。`bootstrap()` 遇到唯一约束冲突时重新读取 active 规则，不重复创建。自愈更新使用 `SELECT ... FOR UPDATE`；version 不匹配时重新读取 active 规则并放弃本次覆盖。降级接口必须带 `expected_version`，版本不匹配不得降级新规则。

Facade 每次调用内部自行打开短生命周期 DB session 并提交/回滚；不得复用调用线程里的 AsyncSession。`update_rule()` 写入 revision 时保存旧规则的 `navigation/extractions/integrity` 快照，更新主表时只接受经过 `types.py` 校验的结构化 rule_data。

RuleStore facade 签名固定为：
```python
get_active(scraping_rule_id: int, target_type: str, page_key: str) -> ExtractionRule | None
bootstrap(runtime, rule_data: dict) -> ExtractionRule
update_rule(rule_id: int, expected_version: int, rule_data: dict, trigger_reason: str) -> ExtractionRule | None
mark_degraded(rule_id: int, expected_version: int, reason: str) -> bool
```

`get_active()` 内部先用 scraping rule 读取所属 data source，不接受调用方传入 `data_source_id`。

### 1.3 Playwright CLI Wrapper (`src/extraction/playwright_cli.py`)

这是当前 CLI 路线实现，仓库通过 Node `@playwright/cli` 提供 `playwright-cli`。

```python
class PlaywrightCLI:
    """Minimal subprocess wrapper. Key methods:

    open(url=None, headed=False) → None
    goto(url) → None
    click(locator) → None
    wait_visible(locator, timeout_ms=30000) → None  # wrapper 用 eval 轮询
    eval(js_func) → dict                         # playwright-cli --raw eval
    screenshot(filename) → Path                  # screenshot --filename
    snapshot(filename, depth=None) → Path        # snapshot --filename
    state_save(path) → None
    state_load(path) → None
    close() → None
    """
```

实现要点：
- 通过 `subprocess.run([self._path, "-s=" + self._session, "--raw", cmd, *args], capture_output=True, timeout=N)` 调用
- `open()` 通过 `playwright-cli -s=<session> open [url] --headed` 传参；`headed=False` 时不传 `--headed`
- `eval` 参数必须是 `() => JSON.stringify({...})`，Python 端 `json.loads(stdout)`
- `-s=<name>` 命名 session 保证并发隔离
- `snapshot` / `screenshot` 必须传 `--filename`，产物写入 `playwright_cli_artifact_dir`
- 所有命令超时由 `subprocess.run(timeout=N)` 控制
- `session` 必须由 `account_id + shop_id + rule_id + execution_id + metric_date + plan_index` 生成，保证并发隔离
- stderr 非空且退出码非 0 时抛 `PlaywrightCLIError`，错误信息写入 `raw.extraction.failure_reasons`，不把 stdout/stderr 中的 cookie/localStorage 内容写日志

Docker 安装必须显式安装 CLI：
```dockerfile
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev build-essential postgresql-client nodejs npm \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @playwright/cli \
    && playwright-cli install-browser --with-deps chromium
```

### 1.4 Login State Scope

登录态不由 extraction engine 接管，不使用单全局 `state_file_path`。账号态、HTTP 旧 bundle、Playwright 店铺态必须分开存储。

当前仓库事实：登录 `storage_state` 的源头是 `DataSource.extra_config.shop_dashboard_login_state`；执行期会物化到 `SessionStateStore` 的账号级 JSON 文件。当前店铺 bundle 只保存 `cookies + common_query + verify metadata`，不是完整 Playwright state。

```
CollectionUseCase
  1. materialize_runtime_storage_state(runtime, state_store)
  2. SessionBootstrapper 继续生成/校验旧 HTTP cookie bundle
  3. _collect_one_day 调用 extraction_engine stage，并透传 plan_unit

ExtractionEngine
  1. 用 runtime.account_id / rule_id 定位 SessionStateStore 账号 storage_state
  2. 用 runtime.shop_id 读取独立 per-shop Playwright storage state
  3. 生成临时 CLI state file：账号 storage_state 为基线，叠加当前店铺完整 Playwright storage state
  4. cli.open() → cli.state_load(temp_state) → PlaywrightShopBootstrapper.ensure_shop_context()
  5. 采集成功后 cli.state_save(temp_state)，把完整 Playwright storage state 只回写当前店铺；账号 storage_state 不由 extraction engine 写入
```

账号 storage_state 仍只由登录上传/登录 bootstrap 写入。`SessionStateStore.save_bundle/load_bundle` 保留给现有 HTTP 采集使用，结构仍是 cookie mapping + common_query，不得作为 Playwright `state-load` 的输入。extraction engine 只读取独立 Playwright 店铺态文件，避免 `_normalize_bundle_payload()` 丢弃 `origins/localStorage`。

`SessionStateStore` 新增方法：
```python
account_state_path(account_id: str) -> Path
shop_storage_state_path(account_id: str, shop_id: str) -> Path
shop_storage_meta_path(account_id: str, shop_id: str) -> Path
save_shop_storage_state(account_id: str, shop_id: str, storage_state: dict) -> Path
load_shop_storage_state(account_id: str, shop_id: str) -> dict | None
save_shop_storage_state_meta(account_id: str, shop_id: str, meta: dict) -> Path
load_shop_storage_state_meta(account_id: str, shop_id: str) -> dict | None
```

per-shop Playwright storage state 文件必须保持 Playwright 原始结构，不能混入业务 metadata：
```python
{
    "cookies": [...],
    "origins": [...]
}
```

metadata 另存 sidecar：
```python
{
    "validated_shop_id": "...",
    "verified_actual_shop_id": "...",
    "verify_status": "passed",
    "session_version": "..."
}
```

Materializer 合并规则：账号 storage_state 为基线，当前店铺 Playwright storage state 覆盖同 `(name, domain, path)` cookie 与同 `origin` 条目；临时 state file 只能包含 `cookies/origins`。采集成功后只把 `state-save` 得到的完整 storage state 写回当前店铺 state file，并写入 sidecar metadata。

`PlaywrightShopBootstrapper` 职责：
- 当 per-shop Playwright state 缺失或 metadata 校验失败时，在已加载账号态的浏览器内完成店铺切换。
- 切换后用页面可见店铺标识或轻量 extraction probe 校验 `actual_shop_id == runtime.shop_id`。
- 校验通过后 `state-save` 到当前店铺 Playwright state；校验失败时抛 `LoginExpiredError` / `PermissionDenied` / `ShopContextMismatch`，不触发 Explorer。
- 不把店铺态写回账号态，不复用旧 HTTP bundle 的 cookie/common_query 作为完整浏览器态。
- 店铺切换规则不由 GLM 生成；首版用固定页面选择器配置或人工 seed rule，失败进入现有 mismatch/circuit 逻辑。

### 1.5 Migration

当前没有该迁移。以下命令是目标实施时生成迁移的步骤。

```bash
just db-migrate "add extraction_rules and rule_revisions tables"
```

---

## Phase 2 — Rule Executor (Daily Collection)

### `src/extraction/executor.py`

目标新增文件。当前仓库没有 `src/extraction/executor.py`。

```
Executor.collect_one_page(cli, rule, runtime, metric_date, plan_unit=None) → dict:
  1. render(rule.source_url_template, runtime, metric_date, plan_unit) 后校验 URL origin 在 allowlist 内
  2. cli.goto(rendered_url)
  3. 执行 rule.navigation steps
  4. 构建受控 JS 函数：只允许 CSS selector / XPath / text/list/object/table parser schema
  5. cli.eval(js) → 解析结果
  6. 逐字段验证 parser + validation + integrity，并给失败分类
  7. 返回兼容 CollectionResultPersister.persist() 的 payload
```

`eval` JS 模板示例：
```javascript
() => JSON.stringify({
  total_score: (() => {
    const selectors = [".score-main .value", "[data-e2e='total-score']"];
    const el = selectors.map((selector) => document.querySelector(selector)).find(Boolean);
    return el ? el.innerText.trim() : null;
  })(),
})
```

选择器来自 `rule.extractions[field].selectors`，用 `json.dumps()` 注入 JS 数组；禁止把 LLM 返回的任意 JS 写入规则。

规则 schema 只允许结构化提取：
- `scalar`: 从 selector/xpath 提取 `innerText`、attribute 或 dataset，再按 `number/int/text/date/shop_id` parser 转换。
- `list`: `container_selector` + `item_selector` + columns，返回对象数组。
- `object`: 多个子字段组成对象，用于 reviews.summary / violations.summary。
- `table`: 表格行列提取，用于违规/评论列表类页面。

规则 JSON 最小形态：
```python
{
    "source_url_template": "https://fxg.jinritemai.com/...",
    "navigation": [
        {"type": "wait_visible", "selector": "...", "timeout_ms": 30000},
        {"type": "click", "selector": "..."},
    ],
    "extractions": {
        "total_score": {
            "kind": "scalar",
            "selectors": ["..."],
            "xpath": [],
            "source": "inner_text",
            "attribute": None,
            "parser": "number",
            "required": True,
        },
        "reviews.items": {
            "kind": "list",
            "container_selector": "...",
            "item_selector": "...",
            "columns": {
                "id": {"selectors": ["..."], "parser": "text"},
                "content": {"selectors": ["..."], "parser": "text"},
            },
            "required": False,
        },
    },
    "integrity": {
        "required_fields": [
            "total_score",
            "product_score",
            "logistics_score",
            "service_score",
            "bad_behavior_score",
        ],
        "score_range": [0, 100],
        "shop_id_match": True,
    },
}
```

`navigation` 首版只支持 `wait_visible`、`click`、`fill`、`select`、`wait_url_not_contains`，且参数只能来自规则 JSON 的结构化字段；`goto` 只能由 `source_url_template` 渲染产生，禁止作为 navigation step 保存。selector 与 xpath 必须是字符串列表，单条长度限制 500 字符，列表最多 5 条。

Executor 必须复用现有 parser 的归一化语义，输出字段包括 `shop_id`、`target_shop_id`、`actual_shop_id`、`shop_name`、五个核心分、`reviews`、`violations`、`raw.extraction`。未通过 parser 或 integrity 的字段写入 `raw.extraction.failed_fields`，不得用 0 静默替代必填字段。`_collect_via_extraction_engine` 必须在进入 `_normalize_task_result()` 前完成必填字段校验；校验失败直接抛 `ExtractionFailed`，避免现有默认值把缺失分数写成 0。

Integrity 至少包含：
- `actual_shop_id == runtime.shop_id`
- 核心分范围校验：`0 <= score <= 100`
- 必填字段完整性：`total_score/product_score/logistics_score/service_score/bad_behavior_score`
- 当前 URL 不在 login/passport 页面
- 列表字段结构为数组，summary 字段结构为对象

失败分类：
- `selector_failed`：字段存在页面变更迹象，允许触发 Explorer。
- `login_expired`：登录页、401/403 API 响应或登录态探测失败，抛 `LoginExpiredError`，不触发 Explorer。
- `permission_denied`：权限不足、店铺不可访问，不触发 Explorer。
- `empty_state`：页面正常但当前窗口无数据，不触发 Explorer。
- `data_not_ready`：指标未产出、日期窗口未完成，不触发 Explorer。

只有 `selector_failed` 可以进入 Explorer 自愈。`source_url_template` 渲染后的 URL 必须限制在 `settings.base_url` 或显式 allowlist 内，禁止规则驱动带登录态浏览器访问外部 origin。

`raw.extraction` 必须包含：
```python
{
    "rule_id": rule.id,
    "rule_version": rule.version,
    "failed_fields": failed_fields,
    "failure_type": failure_type,
    "failure_reasons": failure_reasons,
    "artifact_ids": artifact_ids,
}
```

URL 校验使用 `urllib.parse.urlparse`，只比较 `scheme + netloc`；默认允许 `settings.base_url`，额外允许 `settings.extraction_url_allowlist`。

### `src/extraction/engine.py`

目标新增文件。当前仓库没有 `src/extraction/engine.py`。

```python
class ExtractionEngine:
    def __init__(self, rule_store, executor, explorer, state_materializer, shop_context):
        ...

    def collect(self, runtime, metric_date, state_store, login_state_manager, plan_unit=None) -> dict:
        account_id = resolve_account_id(runtime)
        cli = PlaywrightCLI(session=build_unique_session_name(runtime, metric_date, plan_unit))
        state_file = self.state_materializer.materialize(
            state_store=state_store,
            account_id=account_id,
            shop_id=runtime.shop_id,
        )
        cli.open()
        cli.state_load(state_file)
        try:
            self.shop_context.ensure_shop_context(
                cli=cli,
                runtime=runtime,
                metric_date=metric_date,
                plan_unit=plan_unit,
                state_file=state_file,
                state_store=state_store,
                account_id=account_id,
            )
            rule = self.rule_store.get_active(
                scraping_rule_id=runtime.rule_id,
                target_type=runtime.target_type,
                page_key=settings.extraction_rule_page_key,
            )
            if rule is None:
                rule = self.explorer.bootstrap(cli, runtime, metric_date, plan_unit)
            data = self.executor.collect_one_page(cli, rule, runtime, metric_date, plan_unit)
            if not self.executor.check_integrity(data, rule.integrity, runtime):
                if data["raw"]["extraction"]["failure_type"] != "selector_failed":
                    raise ExtractionFailed(data["raw"]["extraction"]["failure_type"])
                if not settings.extraction_explorer_enabled:
                    raise ExtractionFailed("selector_failed")
                rule = self.explorer.self_heal(cli, rule, data["raw"]["extraction"]["failed_fields"])
                data = self.executor.collect_one_page(cli, rule, runtime, metric_date, plan_unit)
                if not self.executor.check_integrity(data, rule.integrity, runtime):
                    self.rule_store.mark_degraded(
                        rule.id,
                        expected_version=rule.version,
                        reason="integrity_failed_after_self_heal",
                    )
                    raise ExtractionFailed("integrity_failed_after_self_heal")
            cli.state_save(state_file)
            self.state_materializer.persist_shop_storage_state(state_store, account_id, runtime.shop_id, state_file)
            return data
        finally:
            cli.close()
```

`build_unique_session_name()` 输入必须包含 `runtime.execution_id` 和 `plan_unit.plan_index`；缺失时追加 UUID 后缀。

`ensure_shop_context()` 只处理登录态、店铺切换和 actual shop 校验；页面字段缺失不在这里触发 Explorer。若检测到登录页、权限页或店铺不匹配，直接抛对应业务异常并交给 `CollectionUseCase` 现有 login/circuit 逻辑处理。

---

## Phase 3 — Rule Explorer (Self-Healing)

### `src/extraction/explorer.py`

目标新增文件。当前仓库没有 Explorer、自愈闭环、artifact 脱敏或 GLM 调用实现。

```
Explorer.self_heal(cli, rule, failed_fields) → ExtractionRule:
  1. cli.screenshot() → PNG 文件路径
  2. cli.snapshot() → markdown snapshot 文件路径
  3. 脱敏后读取 PNG (base64) + markdown snapshot
  4. 组装 prompt → GLM-5.1
  5. 解析 LLM 返回的 new_extractions schema
  6. 用 cli.eval() 验证新选择器能否提取到值，并运行 parser/integrity
  7. 通过 validation → rule_store.update(rule, new_data)
  8. 不通过 → 重试(最多3次) → 仍失败则标记 degraded + 告警
```

GLM-5.1 prompt 结构：
```
System: 你是抖店后台数据提取规则生成器。输入包括页面截图和可访问性树。
你的任务是定位失败字段在页面中的实际位置，生成新的CSS/XPath选择器。

User:
[截图 base64]
[可访问性树 markdown 摘要]
目标页面URL: {rendered_source_url}
提取失败的字段:
  - total_score: 店铺总分(浮点数,0-100), 旧选择器: [".score-main .value", "[data-e2e='total-score']"]
  - product_score: 商品分(浮点数,0-100), 旧选择器: [".product-score"]

请返回JSON格式的新提取规则。
```

GLM 返回必须是受控 JSON schema：`selectors`、`xpath`、`attribute`、`parser`、`confidence`、`change_summary`。禁止返回或保存任意 JavaScript。首版 self-heal 只允许更新 failed fields 的 extraction 配置，不允许 GLM 增删 `navigation`、`click`、`fill`、`goto` 等动作；bootstrap 规则的导航也必须来自人工种子或固定 allowlist schema。`confidence < explorer_confidence_threshold` 时直接拒绝更新。

Explorer 验证标准：
- failed fields 全部可解析
- 新规则不会破坏非 failed fields
- `actual_shop_id` 与目标店铺一致
- URL 未跳转登录页
- 核心分与列表字段满足 integrity
- rule version 未被其他 Explorer 更新；若已更新则放弃本次覆盖并重新读取 active 规则

Explorer 写回规则只能调用 `rule_store.update_rule(rule.id, expected_version=rule.version, ...)`。返回 `None` 表示版本冲突，Explorer 必须重新读取 active 规则并用新规则重采集，不得覆盖或降级。

截图和 snapshot 产物写入 `playwright_cli_artifact_dir`，只保留本次自愈需要的局部页面信息；上传 GLM 前脱敏手机号、订单号、用户昵称、评论正文中的明显 PII，不读取或上传 cookie/localStorage/sessionStorage。截图脱敏不能只做文本替换：优先截取 failed field 附近区域；评论/订单/用户列表页面默认不上传全屏截图；如必须上传截图，先通过 DOM 定位敏感节点并做像素遮罩。snapshot 超过 `extraction_snapshot_max_chars` 时按 failed field 附近节点裁剪。artifact 按 `extraction_artifact_ttl_seconds` 清理。

### Explorer.bootstrap(cli, runtime, metric_date, plan_unit) → ExtractionRule:

目标接口。当前仓库没有 `Explorer.bootstrap`。
用于首次初始化规则。流程同 self_heal，但没有 failed_fields，而是根据 data_description 让 LLM 识别页面所有目标字段。

bootstrap 必须 seed-first：优先从 `scraping_rule.extra_config["extraction_rule_seed"]` 或内置 seed 读取 `source_url_template/navigation/integrity/target fields`，GLM 只允许补全每个字段的 selectors/xpath，不允许决定目标 URL、导航动作、必填字段或 integrity。缺少 seed 时 bootstrap 返回 `ExtractionFailed("missing_rule_seed")`，不自动让 GLM 从空白页面生成完整规则。

### Rollout 3 Cleanup Boundary

目标态移除旧 `agent` stage 不是只删模型调用。同一阶段必须清理：
- 独立 agent 队列模块
- `src/tasks/worker.py` 中旧 agent 队列注册
- `src/tasks/collection/__init__.py`、`src/tasks/__init__.py`、`src/agents/__init__.py` 的导出
- 依赖 agent fallback 的测试用例

`src/scrapers/shop_dashboard/http_scraper.py` 只能在 `SessionBootstrapper` 不再 import `ENDPOINT_SPECS` / `SHOP_CONTEXT_VERIFY_GROUPS` 后删除。若 Phase 3 仍保留 HTTP bootstrap 校验，则把这些常量先迁到独立 `contracts.py` 或继续保留 `http_scraper.py`。

---

## Phase 4 — Integration

### 4.1 修改 `src/tasks/collection/douyin_shop_dashboard.py`

目标态取消旧 agent stage，`fallback_chain` 只允许目标采集 stage。当前实现使用 `browser_agent`。引入 `extraction_engine` 时应先新增 stage，稳定后再切换默认值：

```python
def _collect_one_day(runtime, metric_date, *, plan_unit=None, **helpers):
    for stage in runtime.fallback_chain:
        if stage == "http":
            try:
                return _collect_via_http(runtime, metric_date, ...)
            except (ScrapingFailedException, ShopDashboardScraperError):
                continue
        if stage == "extraction_engine":
            if not settings.extraction_engine_enabled:
                _append_fallback_trace(fallback_trace, stage="extraction_engine", status="disabled")
                continue
            try:
                return _collect_via_extraction_engine(
                    runtime,
                    metric_date,
                    plan_unit=plan_unit,
                    **helpers,
                )
            except LoginExpiredError:
                _mark_login_state_expired(...)
                raise
            except ExtractionFailed as exc:
                _append_fallback_trace(
                    fallback_trace,
                    stage="extraction_engine",
                    status="failed",
                    error=exc,
                )
                continue
```

目标态 `_normalize_fallback_chain` 只保留 `http` 与 `extraction_engine`。`agent` / `llm` 不再归一化为有效 stage；`rule_config_resolver.py`、`runtime.py` 和 task fallback 默认值统一由 `settings.extraction_engine_enabled` 与 `settings.extraction_engine_primary` 决定。该变更必须同步更新现有 agent 相关测试和 worker 注册。

归一化规则：
```python
VALID_FALLBACK_STAGES = {"http", "extraction_engine"}
DEFAULT_FALLBACK_CHAIN = (
    ("extraction_engine", "http")
    if settings.extraction_engine_enabled and settings.extraction_engine_primary
    else ("http", "extraction_engine")
    if settings.extraction_engine_enabled
    else ("http",)
)
```

输入含旧 stage 时直接丢弃；`extraction_engine_enabled=False` 时也丢弃 `extraction_engine`；归一化后为空则使用 `DEFAULT_FALLBACK_CHAIN`。

`extraction_engine_primary=True` 只影响默认 fallback；用户显式配置了有效 `fallback_chain` 时尊重显式顺序，但 disabled engine 仍会被过滤。

`src/application/collection/executor.py` 的 `collect_one_day()` 协议和 `TaskModuleCollectionExecutor.collect_one_day()` 透传 `plan_unit`。`src/application/collection/usecase.py` 调用 `_collect_one_unit_payload()` 时传入当前 `plan_unit`，包括首次采集和 shop mismatch 后重建 bundle 的第二次采集，供 extraction engine 渲染日期窗口、店铺过滤器和分页参数。

协议签名同步修改：
```python
CollectionExecutor.collect_one_day(..., plan_unit: Any | None = None) -> dict[str, Any]
TaskModuleCollectionExecutor.collect_one_day(..., plan_unit: Any | None = None) -> dict[str, Any]
CollectionUseCase._collect_one_unit_payload(..., plan_unit: Any | None = None) -> dict[str, Any]
_collect_one_day(runtime, metric_date, *, plan_unit=None, **helpers) -> dict[str, Any]
```

### 4.2 数据格式对齐

Executor 输出格式兼容现有 `CollectionResultPersister.persist()` 的 payload 结构：
```python
{
    "shop_id": "...",
    "actual_shop_id": "...",
    "shop_name": "...",
    "source": "extract",
    "total_score": 96.5,
    "product_score": 92.0,
    ...
    "reviews": {"summary": {}, "items": [...]},
    "violations": {"summary": {}, "waiting_list": [...]},
    "raw": {
        "extraction": {
            "source": "extraction_engine",
            "rule_id": 1,
            "rule_version": 3,
            "failed_fields": [],
            "failure_type": "",
            "artifact_ids": [],
        },
    },
}
```
Persister 不改代码即可接收。`source` 长度必须满足 `ShopDashboardScore.source` 的 20 字符限制，固定使用 `"extract"`；`raw.extraction.source` 再记录 `"extraction_engine"`。

### 4.3 配置开关控制迁移节奏

```python
# Phase 1A: foundation only, no runtime behavior change
extraction_engine_enabled = False
extraction_engine_primary = False
fallback_chain = ("http",)

# Phase 1B: extraction_engine 替代 agent fallback
extraction_engine_enabled = True
extraction_engine_primary = False
fallback_chain = ("http", "extraction_engine")

# Phase 2: extraction_engine 主力, http fallback
extraction_engine_enabled = True
extraction_engine_primary = True
fallback_chain = ("extraction_engine", "http")

# Rollout 3: 纯 extraction, 移除 http
extraction_engine_enabled = True
extraction_engine_primary = True
fallback_chain = ("extraction_engine",)
```

---

## Verification

以下是目标验证计划。当前仓库没有 `tests/extraction` 目录，且持久化测试尚未覆盖 `source="extract"` / `raw.extraction.source="extraction_engine"`。

### 单元测试
- `tests/extraction/test_rule_store.py` — CRUD + version 自增 + revision 归档
- `tests/extraction/test_playwright_cli.py` — subprocess mock，验证命令拼装
- `tests/config/test_shop_dashboard_settings.py` — extraction/playwright/glm 配置默认值与 env override
- `tests/extraction/test_session_state.py` — 账号 storage_state + per-shop Playwright 原始 storage state 合并；不复用旧 cookie bundle；采集后只回写当前店铺 state
- `tests/extraction/test_shop_context.py` — per-shop state 缺失时浏览器内选店；actual_shop_id 校验；登录/权限/店铺不匹配不触发 Explorer
- `tests/extraction/test_executor.py` — mock cli，验证 scalar/list/object/table eval 模板生成 + parser/integrity + URL allowlist + 失败分类
- `tests/application/collection/test_result_persister.py` — `source="extract"` 可持久化，`raw.extraction.source="extraction_engine"` 保留完整来源
- `tests/extraction/test_explorer.py` — mock GLM 响应，验证自愈流程、低置信拒绝、禁止 navigation 更新、非 failed 字段不回退、version 冲突不覆盖、PII 遮罩
- `tests/extraction/test_engine.py` — explorer disabled 时 selector_failed 不调用 GLM，直接失败
- `tests/extraction/test_explorer_bootstrap.py` — bootstrap 必须依赖 seed；GLM 只补 selectors/xpath；缺 seed 返回 `missing_rule_seed`
- `tests/tasks/test_shop_dashboard_collection.py` — fallback_chain 不再进入 agent，`plan_unit` 透传 extraction_engine，disabled engine 不进入自愈
- `tests/scrapers/shop_dashboard/test_rule_config_resolver.py` — engine disabled 默认 fallback 为 `http`；enabled 默认 fallback 为 `http->extraction_engine` 或 `extraction_engine->http`
- `tests/scrapers/shop_dashboard/test_runtime_account_key.py` — runtime 不新增 `data_source_id`，默认 fallback 不含 agent/llm
- `tests/tasks/test_worker_entry.py` — Rollout 3 后不再注册 agent 队列

### 集成测试
- CLI 路线：`playwright-cli` 安装后 → 启动 Chromium → 导航到抖店 → snapshot → screenshot → eval 提取
- per-shop Playwright state 缺失 → 浏览器内选店 → `state-save` → 下一次同店铺直接加载正确上下文
- 人工触发字段缺失 → 验证 Explorer 生成新规则 → 更新 PG → 重提取成功
- `SessionStateStore` → 临时 CLI state → `state-load` / `state-save` → 只回写当前店铺 Playwright state
- per-shop Playwright state 保存完整 storage state，且不污染账号 storage_state
- 同一账号连续采集两个店铺，第二个店铺不继承第一个店铺的实际上下文

### Phase 1 验证

以下命令适用于当前 CLI 路线。

```bash
playwright-cli --version                 # @playwright/cli 可用
playwright-cli install-browser --with-deps chromium  # Chromium 已装
just test tests/extraction/             # 单元测试通过
```

### Phase 2 验证
```bash
just run                                # 启动 dev server → 手动触发采集
# 目标：HttpScraper 失败后自动切换 extraction_engine；Rollout 3 后不再进入 agent
```

### Rollout 3 验证
- 故意修改页面 → 采集失败 → Explorer 自愈 → 规则更新 → 重采集成功
- 检查 `rule_revisions` 表有归档记录
