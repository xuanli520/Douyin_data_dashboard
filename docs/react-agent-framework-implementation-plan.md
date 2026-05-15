# ReAct Agent 爬取框架实施计划

## 目标与范围

本计划基于 `docs/react-agent-framework-design.md`，并结合当前源码、相关设计文档与测试现状，将目标方案拆解为可执行的 Phase 1-4 实施计划。

本计划只规划实现，不在当前文档中修改业务代码。实施时必须保持 `src/core/agent` 为通用内核，业务语义只出现在业务 adapter、任务编排、规则配置和持久化映射层。

## 分析输入

- 主设计文档：`docs/react-agent-framework-design.md`
- 相关设计文档：`docs/core-self-healing-agent-framework.md`
- 相关设计文档：`docs/lightweight-core-agent-crawler.md`
- 相关设计文档：`docs/self-healing-agent-extraction-engine.md`
- 当前采集入口：`src/tasks/collection/douyin_shop_dashboard.py`
- 当前业务编排：`src/application/collection/usecase.py`
- 当前执行器抽象：`src/application/collection/executor.py`
- 当前运行时解析：`src/application/collection/runtime_loader.py`
- 当前规则解析：`src/scrapers/shop_dashboard/rule_config_resolver.py`
- 当前 HTTP scraper：`src/scrapers/shop_dashboard/http_scraper.py`
- 当前登录态与店铺切换：`src/scrapers/shop_dashboard/session_bootstrapper.py`
- 当前本地状态存储：`src/scrapers/shop_dashboard/session_state_store.py`
- 当前 LLM fallback：`src/agents/llm_dashboard_agent.py`
- 旧独立 agent 队列已移除
- 当前 worker 注册：`src/tasks/worker.py`
- 当前配置：`src/config/shop_dashboard.py`
- 当前数据库模型：`src/domains/scraping_rule/models.py`
- 当前规则仓储：`src/domains/scraping_rule/repository.py`
- 当前 config 映射：`src/domains/data_source/config_mapper.py`
- 当前 API 注册：`src/main.py`
- 当前 Docker 浏览器安装：`docker/Dockerfile`
- 当前测试命令：`justfile`

## 子代理协作结论

- 架构子代理结论：`src/core/agent` 必须保持通用内核，业务接入点应放在 `src/application/collection/browser_agent_adapter.py`；`CollectionUseCase`、`SessionBootstrapper`、`SessionStateStore`、`LockManager`、`CollectionResultPersister` 保持在 core 外侧。
- 源码映射子代理结论：旧主链路是 HTTP fallback 加 LLM 补齐；目标实现已转向 `browser_agent`、`src/core/agent`、`AgentCrawler`、`PlaywrightCLIDriver`、`agent_recipes` 与 WebSocket 观察同步。
- 测试策略子代理结论：新增能力应以 `tests/core/agent/*` 为核心单测区，业务接线测试放在 `tests/application/collection/`、`tests/tasks/`、`tests/integration/`、`tests/api/`；WebSocket 与 browser driver contract 是当前最大测试空白。

## 当前代码事实

| 设计文档判断 | 当前证据 | 计划影响 |
|---|---|---|
| browser_agent 是主链路 | `_collect_one_day()` 在 `src/tasks/collection/douyin_shop_dashboard.py` 内执行 `BrowserAgentAdapter` | Phase 2/4 清理旧 HTTP/LLM fallback |
| core agent 内核已存在 | 仓库已有 `src/core/agent` 与 `tests/core/agent` | 后续变更保持 core 通用边界 |
| fallback 使用 browser_agent | `_normalize_fallback_chain()` 保留 `browser_agent` | 旧 `http/agent/llm` 不再作为目标采集链路 |
| `ScrapingRule.extra_config.agent_recipe` 未驱动采集 | `ScrapingRule.extra_config` 会被 `ScrapingRuleConfigMapper` 平铺回 API response `config` | Phase 3/4 优先新增独立 `agent_recipes` 存储，避免把完整 recipe 暴露到配置面 |
| Playwright 当前是 Node CLI 依赖 | `package.json` 依赖 `@playwright/cli`；`docker/Dockerfile` 执行 `playwright-cli install-browser --with-deps` | Phase 1 定义 `BrowserDriver` contract，首版使用 CLI adapter |
| 登录态源自 DataSource.extra_config | `DataSource.extra_config.shop_dashboard_login_state` 经运行期物化到 `SessionStateStore` | Core 不接管登录态；业务 adapter 负责传入 storage state path |
| 店铺 bundle 不是 Playwright state | `SessionStateStore.save_bundle/load_bundle` 规范化的是 cookies/common_query/verify metadata | Phase 2 需要新增 per-shop Playwright state 原始读写，不能复用 bundle 作为浏览器 state |
| 当前没有 WebSocket 入口 | `src/main.py` 只 include HTTP routers，仓库没有 websocket router | Phase 3 新增观察同步 router 与测试 |
| 当前 LLM 配置是通用配置 | `ShopDashboardSettings` 只有 `llm_provider/llm_endpoint/llm_model/llm_timeout_seconds/llm_retry_times` | Phase 3/4 复用 openai-compatible 抽象；Qwen/DashScope 只能作为 adapter，不污染 core |

## 总体架构边界

### Core 内核边界

新建 `src/core/agent/`，只处理通用浏览器自动化、结构化 Recipe、工具执行、安全校验、观察、断言、artifact、replay、recovery。

`src/core/agent` 内禁止出现以下业务概念：

- `shop_id`
- `metric_date`
- `scraping_rule`
- `douyin`
- `fxg`
- `dashboard`
- `score`
- `collection_job`
- `data_source`

Core 接口只接受通用参数：

- `Recipe`
- `RunContext`
- `BrowserDriver`
- `ToolCall`
- `Observation`
- `Assertion`
- `Artifact`
- `Failure`
- `RecoveryProposal`

### 业务 adapter 边界

新增 `src/application/collection/browser_agent_adapter.py`，负责业务上下文与 core 的双向映射：

- 从 `ShopDashboardRuntimeConfig`、`CollectionPlanUnit`、登录态路径、业务 rule 解析出 core `RunContext`
- 从 `agent_recipes` 或 `ScrapingRule.extra_config.agent_recipe` 引用加载 recipe
- 调用 `AgentCrawler.run()`
- 将 core output 映射为当前任务结果 payload
- 将 `actual_shop_id`、`shop_name`、`reviews`、`violations` 等业务字段交给现有持久化链路
- 把 core failure 映射为 `LoginExpiredError`、`DataIncompleteError`、`ScrapingFailedException` 等业务异常

### 现有模块保留边界

以下模块不进入 core：

- `CollectionUseCase`：保留任务状态、幂等、锁、计划拆分、持久化编排
- `SessionBootstrapper`：保留登录态校验、店铺切换、actual shop 校验
- `SessionStateStore`：保留账号 storage state、HTTP bundle，并新增浏览器店铺态读写
- `LoginStateManager`：保留登录态过期标记
- `CollectionResultPersister`：保留入库
- `LockManager`：保留账号/店铺锁

## 全局实施决策

1. Core 先落地通用接口，再接业务。
2. Browser driver 使用 `@playwright/cli` / `playwright-cli`，只保留 CLI driver。
3. Recipe 存储目标采用独立 `agent_recipes` 表，不把完整 recipe 长期放在 `ScrapingRule.extra_config`。`ScrapingRule.extra_config.agent_recipe` 只保留 `{namespace, key}` 引用。
4. `browser_agent` stage 先灰度接入，再删除 HTTP fallback。删除动作仍属于 Phase 2，但必须排在 browser agent 验收之后。
5. 旧冷数据补齐链路不等同于 ReAct discovery/recovery；Phase 2/4 清理时必须同步 worker、测试、导出。
6. Recovery 只允许修 recipe locator/observation，不允许直接修业务结果，不允许修改 entrypoint 和业务字段定义。
7. Discovery 的 `done` 结果必须能被 deterministic `AgentCrawler` replay，一次 replay 通过后才允许持久化 recipe。
8. WebSocket 观察同步只推管理员可见信息，Agent thought、snapshot YAML、工具结果只进入内部事件和日志，不推给管理员。

## Phase 1：Core Skeleton

### 目标

建立通用 `src/core/agent` 内核骨架，定义 Recipe、Step、Observation、Assertion、Failure、安全策略与浏览器驱动 contract。该阶段不改变当前采集主链路。

### 前置检查

- 确认 `src/core/agent` 不存在。
- 确认 `@playwright/cli` / `playwright-cli` 可用。
- 确认 Docker 安装 `playwright-cli` 浏览器依赖。
- 确认 `ShopDashboardSettings` 现有 browser/llm 配置字段。
- 确认 `tests/core/agent` 不存在。

### 新增文件

| 文件 | 内容 |
|---|---|
| `src/core/agent/__init__.py` | core public exports |
| `src/core/agent/models.py` | `Recipe`、`Entrypoint`、`Step`、`ObservationSpec`、`AssertionSpec`、`Failure`、`RunResult` |
| `src/core/agent/exceptions.py` | `AgentError`、`BrowserDriverError`、`SecurityPolicyError`、`RecipeValidationError`、`ObservationError`、`AssertionFailedError` |
| `src/core/agent/security.py` | URL allowlist、origin 校验、locator 危险模式过滤、危险页面关键词过滤 |
| `src/core/agent/browser.py` | `BrowserDriver` protocol、driver result、artifact path contract |
| `src/core/agent/artifacts.py` | artifact 命名、目录、TTL 清理、敏感字段过滤接口 |
| `src/core/agent/session.py` | 通用 session id 与 storage state path contract，不包含业务状态逻辑 |
| `tests/core/agent/test_models.py` | schema 校验单测 |
| `tests/core/agent/test_security.py` | allowlist/locator/origin 单测 |
| `tests/core/agent/test_browser_contract.py` | driver contract fake 测试 |

### 模型设计

`Recipe` 字段：

- `namespace: str`
- `key: str`
- `version: int`
- `entrypoint: Entrypoint`
- `steps: list[Step]`
- `observations: dict[str, ObservationSpec]`
- `assertions: list[AssertionSpec]`
- `recovery_policy: RecoveryPolicy`
- `security_policy: SecurityPolicy`
- `metadata: dict[str, Any]`

`Step` 字段：

- `id: str`
- `action: Literal["goto", "back", "reload", "click", "fill", "select", "scroll_down", "scroll_up", "scroll_to_element", "wait_visible", "wait_network_idle", "extract_table", "extract_list", "extract_text"]`
- `target: LocatorSpec | None`
- `value: str | None`
- `timeout_seconds: float | None`
- `save_as: str | None`
- `depends_on: list[str]`

`ObservationSpec` 字段：

- `id: str`
- `kind: Literal["text", "table", "list", "attribute", "url", "title"]`
- `locator: LocatorSpec | None`
- `parser: str | None`
- `required: bool`
- `max_items: int | None`

`AssertionSpec` 字段：

- `id: str`
- `kind: Literal["exists", "not_empty", "equals", "contains", "matches", "url_allowed"]`
- `source: str`
- `expected: Any | None`
- `severity: Literal["error", "warning"]`

### 安全策略实现

`security.py` 必须实现：

- `validate_tool_name(tool_name)`
- `validate_url_allowed(url, allowed_origins)`
- `validate_locator(locator)`
- `validate_navigation_target(url, security_policy)`
- `validate_page_risk(url, title, snapshot_text)`

默认禁止模式：

- `delete`
- `remove`
- `confirm`
- `submit`
- `javascript:`
- `eval`
- `download`
- `refund`
- `payment`
- `settlement`
- `checkout`

默认允许工具：

- `goto`
- `back`
- `reload`
- `click`
- `fill`
- `select`
- `scroll_down`
- `scroll_up`
- `scroll_to_element`
- `wait_visible`
- `wait_network_idle`
- `get_current_url`
- `get_page_title`
- `get_element_text`
- `extract_table`
- `extract_list`
- `extract_text`
- `done`

默认禁止工具：

- `submit_form`
- `click_confirm`
- `click_delete`
- `evaluate`
- `download`

### Browser driver contract

先定义通用 `BrowserDriver` protocol：

- `open(url: str | None = None, *, headed: bool = False) -> None`
- `close() -> None`
- `goto(url: str) -> DriverResult`
- `back() -> DriverResult`
- `reload() -> DriverResult`
- `click(locator: LocatorSpec) -> DriverResult`
- `fill(locator: LocatorSpec, value: str) -> DriverResult`
- `select(locator: LocatorSpec, value: str) -> DriverResult`
- `wait_visible(locator: LocatorSpec, timeout_seconds: float) -> DriverResult`
- `wait_network_idle(timeout_seconds: float) -> DriverResult`
- `screenshot(filename: str) -> Path`
- `snapshot(filename: str, max_chars: int) -> str`
- `state_save(path: Path) -> None`
- `state_load(path: Path) -> None`
- `current_url() -> str`
- `title() -> str`
- `text(locator: LocatorSpec) -> str`

首版 driver 实现顺序：

1. `PlaywrightCLIDriver`：基于 Node `@playwright/cli` / `playwright-cli`。

必须同步：

- `pyproject.toml` 不新增浏览器自动化 Python 包。
- `docker/Dockerfile` 安装 Node.js 和 `@playwright/cli`。
- 新增 `playwright_cli_path` 配置。
- contract tests 覆盖 CLI subprocess fake。

### 配置调整

在 `src/config/shop_dashboard.py` 增加最小 agent 配置：

- `agent_artifact_dir: str = ".runtime/agent_artifacts"`
- `agent_artifact_ttl_seconds: int = 86400`
- `agent_max_steps: int = 30`
- `agent_allowed_origins: list[str] = ["https://fxg.jinritemai.com"]`
- `agent_browser_driver: str = "playwright_cli"`
- `agent_browser_headed: bool = False`

不在 Phase 1 增加 Qwen 专用配置；继续复用通用 `llm_provider/llm_endpoint/llm_model`。

### 测试计划

新增：

- `tests/core/agent/test_models.py`
- `tests/core/agent/test_security.py`
- `tests/core/agent/test_browser_contract.py`
- `tests/config/test_shop_dashboard_settings.py` 扩展 agent 配置默认值

覆盖：

- Recipe JSON round-trip
- 非法 action 拒绝
- 非 allowlist origin 拒绝
- 危险 locator 拒绝
- 危险页面关键词拒绝
- artifact path 必须落在 `.runtime/agent_artifacts`
- driver exception 统一包装为 `BrowserDriverError`

命令：

```bash
uv run --frozen pytest -q tests/core/agent tests/config/test_shop_dashboard_settings.py
just arch-check
```

### 验收门禁

- `src/core/agent` 不 import `src.tasks`、`src.application.collection`、`src.scrapers.shop_dashboard`、`src.domains.scraping_rule`。
- `src/core/agent` 文件内容不出现抖店业务词。
- 所有 core 单测不依赖真实网络、真实浏览器、真实 Redis、真实 DB。
- 当前 `sync_shop_dashboard` 行为不变。
- 当前 `just arch-check` 通过。

### Phase 1 完成定义

- 通用模型、异常、安全策略、driver contract 已落地。
- 测试能证明模型校验和安全校验有效。
- 没有接入任务链路。
- 没有新增不可控外部依赖。

## Phase 2：确定性浏览器执行与业务接入

### 目标

实现 `AgentCrawler.run()`，让结构化 Recipe 能通过浏览器确定性执行，并接入 `browser_agent` stage。Phase 2 末尾完成 HTTP fallback 删除，但必须先通过 browser agent 接线与回归测试。

### 前置检查

- Phase 1 core contract 已稳定。
- `SessionStateStore` 能读取账号级 Playwright `storage_state`。
- 已确认店铺 bundle 不能作为 Playwright state 使用。
- 已明确首批内置 recipe 或 seed 的来源。
- 已明确业务输出字段必须兼容 `CollectionResultPersister`。

### 新增 core 文件

| 文件 | 内容 |
|---|---|
| `src/core/agent/crawler.py` | `AgentCrawler.run()` 主入口 |
| `src/core/agent/steps.py` | step 调度与工具到 driver 的映射 |
| `src/core/agent/observations.py` | observation 读取与类型规范化 |
| `src/core/agent/assertions.py` | assertion evaluator |
| `src/core/agent/parsers.py` | 通用 parser registry，不含业务字段 |
| `src/core/agent/drivers/playwright_cli.py` | CLI adapter |

### 新增业务文件

| 文件 | 内容 |
|---|---|
| `src/application/collection/browser_agent_adapter.py` | 业务 adapter |
| `tests/application/collection/test_browser_agent_adapter.py` | adapter 单测 |
| `tests/tasks/test_shop_dashboard_browser_agent_fallback.py` | stage 接线单测 |
| `tests/integration/test_shop_dashboard_pipeline_browser_agent.py` | 真实 usecase 路径集成测试 |

### 修改文件

| 文件 | 修改 |
|---|---|
| `src/scrapers/shop_dashboard/rule_config_resolver.py` | 支持 `browser_agent`，读取 `extra_config.agent_recipe` 引用，最终移除 `api_groups/common_query/token_keys/graphql_query` 对采集链路的必需性 |
| `src/scrapers/shop_dashboard/runtime.py` | `ShopDashboardRuntimeConfig` 增加 `agent_recipe_ref` 或从 `extra_config` 暴露 recipe 引用 |
| `src/application/collection/executor.py` | `collect_one_day()` 支持 `plan_unit` 透传，或新增 `collect_one_unit()` contract |
| `src/application/collection/usecase.py` | 调用 executor 时传入 `plan_unit`，保持幂等、锁、持久化不变 |
| `src/tasks/collection/douyin_shop_dashboard.py` | 新增 `browser_agent` stage 分支，末尾删除 `HttpScraper` stage |
| `src/scrapers/shop_dashboard/session_state_store.py` | 新增 per-shop Playwright state 原始读写，不复用 bundle |
| `src/scrapers/shop_dashboard/session_bootstrapper.py` | 保持店铺切换职责；如果删除 `http_scraper.py`，先迁移 `ENDPOINT_SPECS` / `SHOP_CONTEXT_VERIFY_GROUPS` |
| `src/tasks/worker.py` | Phase 2B/Phase 4 清理旧 agent 队列时同步修改 |
| `tests/scrapers/shop_dashboard/test_rule_config_resolver.py` | 更新 fallback 归一化测试 |
| `tests/tasks/test_collection_tasks.py` | 更新队列预期 |
| `tests/tasks/test_worker_entry.py` | 更新 worker 队列预期 |
| `tests/integration/test_shop_dashboard_pipeline*.py` | 更新 HTTP/LLM fallback 预期 |

### `AgentCrawler.run()` 逻辑

执行流程：

1. 校验 recipe schema。
2. 校验 entrypoint URL 与 security policy。
3. 创建 driver session。
4. 加载 storage state。
5. 打开 entrypoint URL。
6. 采集初始 screenshot 与 snapshot。
7. 顺序执行 steps。
8. 每个 step 前执行 tool/url/locator 安全校验。
9. 每个 step 后记录 trace。
10. 按 observations 读取数据。
11. 运行 assertions。
12. 返回 `RunResult(status="success", outputs=..., trace=..., artifacts=...)`。
13. 失败时返回结构化 `Failure`，不静默补默认 0 分。
14. finally 关闭 driver。

### 业务 adapter 逻辑

`BrowserAgentAdapter.collect()` 输入：

- `runtime: ShopDashboardRuntimeConfig`
- `metric_date: str`
- `plan_unit: CollectionPlanUnit | None`
- `state_store: SessionStateStore`
- `login_state_manager: LoginStateManager`
- `settings: ShopDashboardSettings`

业务 adapter 步骤：

1. 检查登录态是否 active。
2. 解析 `runtime.extra_config.agent_recipe`。
3. 从 recipe store 加载 active recipe。
4. 解析账号级 `storage_state` path。
5. 解析或创建店铺级 Playwright state path。
6. 调用 `SessionBootstrapper` 确保店铺上下文。
7. 调用 `AgentCrawler.run()`。
8. 将 outputs 映射为当前 dashboard payload。
9. 校验 `actual_shop_id` 与 `runtime.shop_id`。
10. 标记 `source="browser_agent"`。
11. 写入 fallback trace。

### fallback chain 调整

Phase 2A 灰度：

- 支持 `browser_agent`。
- 支持别名 `browser`、`crawl`、`agent_crawl` 归一为 `browser_agent`。
- 默认仍允许 `http -> browser_agent -> agent`，方便对比。

Phase 2B 硬切换：

- 删除 `http` stage。
- 删除 `agent/llm` stage。
- 默认 fallback 变为 `("browser_agent",)`。
- 输入中出现 `http`、`agent`、`llm` 时直接过滤或报配置错误。
- 删除 `_build_agent_fallback_result()` 与 `_resolve_agent_reason()`。
- 删除旧 LLM 补齐在主采集链路中的 import。

### HTTP scraper 删除顺序

1. 将 `EndpointSpec`、`ENDPOINT_SPECS`、`SHOP_CONTEXT_VERIFY_GROUPS` 从 `src/scrapers/shop_dashboard/http_scraper.py` 迁到 `src/scrapers/shop_dashboard/bootstrap_contracts.py` 或 `contracts.py`。
2. 修改 `SessionBootstrapper` import。
3. 删除 `HttpScraper` 主链路引用。
4. 删除 `src/scrapers/shop_dashboard/http_scraper.py`。
5. 删除 `tests/scrapers/shop_dashboard/test_http_scraper.py` 与 `test_http_scraper_error_handling.py`，或改为迁移后 contracts 测试。
6. 更新所有仍 monkeypatch `HttpScraper` 的任务/集成测试。

### LLM agent 删除顺序

1. 删除主链路 `_build_agent_fallback_result()`。
2. 删除旧独立 agent 队列模块。
3. 删除 `src/tasks/worker.py` 中旧 agent 队列注册。
4. 删除 `src/tasks/collection/__init__.py`、`src/tasks/__init__.py`、`src/agents/__init__.py` 相关导出。
5. 删除或改写 `tests/agents/test_llm_dashboard_agent.py`。
6. 删除或改写 `tests/tasks/test_shop_dashboard_agent_task.py`。
7. 删除或改写 `tests/tasks/test_worker_entry.py` 中 agent 队列断言。

### 数据输出映射

`RunResult.outputs` 到 dashboard payload 的最小字段：

- `status`
- `shop_id`
- `target_shop_id`
- `actual_shop_id`
- `metric_date`
- `rule_id`
- `execution_id`
- `source="browser_agent"`
- `total_score`
- `product_score`
- `logistics_score`
- `service_score`
- `bad_behavior_score`
- `reviews`
- `violations`
- `raw.agent`
- `fallback_trace`

缺失必填 observation 时：

- 不补 0 分。
- 返回 `status="failed"` 或抛 `DataIncompleteError`。
- 在 `raw.agent.failure` 中记录 `failure_type`、`step_id`、`observation_id`、`artifact_refs`。

### 测试计划

新增：

- `tests/core/agent/test_agent_crawler.py`
- `tests/core/agent/test_agent_crawler_replay.py`
- `tests/core/agent/test_observations.py`
- `tests/core/agent/test_assertions.py`
- `tests/core/agent/test_driver_replaceability.py`
- `tests/application/collection/test_browser_agent_adapter.py`
- `tests/tasks/test_shop_dashboard_browser_agent_fallback.py`
- `tests/integration/test_shop_dashboard_pipeline_browser_agent.py`

修改：

- `tests/scrapers/shop_dashboard/test_rule_config_resolver.py`
- `tests/tasks/test_shop_dashboard_collection.py`
- `tests/tasks/test_shop_dashboard_collection_task.py`
- `tests/tasks/test_shop_dashboard_collection_degraded.py`
- `tests/integration/test_shop_dashboard_pipeline.py`
- `tests/integration/test_shop_dashboard_pipeline_real_path.py`
- `tests/tasks/test_collection_tasks.py`
- `tests/tasks/test_worker_entry.py`

命令：

```bash
uv run --frozen pytest -q tests/core/agent tests/application/collection/test_browser_agent_adapter.py tests/tasks/test_shop_dashboard_browser_agent_fallback.py
uv run --frozen pytest -q tests/scrapers/shop_dashboard/test_rule_config_resolver.py tests/tasks/test_shop_dashboard_collection.py
uv run --frozen pytest -q tests/integration/test_shop_dashboard_pipeline_browser_agent.py
just arch-check
```

### 验收门禁

- 同一 recipe、同一 fake driver transcript 重放两次结果一致。
- driver adapter 替换不影响 crawler 测试。
- `browser_agent` 成功结果可被现有持久化链路写入。
- 登录态失效仍抛 `LoginExpiredError` 并触发现有登录态过期标记。
- 店铺不匹配仍走现有 mismatch/circuit 逻辑。
- Phase 2B 后主采集链路不 import 旧 HTTP/LLM fallback。
- Phase 2B 后 worker 不注册旧 agent 队列。
- 所有旧 HTTP/LLM fallback 测试已删除或改写为 browser agent 预期。

### Phase 2 完成定义

- `AgentCrawler.run()` 可确定性执行 recipe。
- `browser_agent` 接入 `CollectionUseCase` 主路径。
- HTTP scraper 主链路和 LLM fallback 主链路已移除。
- 旧常量依赖已迁移，不因删除 `http_scraper.py` 破坏 `SessionBootstrapper`。
- 业务结果结构与现有 API/持久化兼容。

## Phase 3：ReAct Discovery

### 目标

实现按需探索能力：管理员提供自然语言目标与入口 URL，`ReActDiscoveryAgent` 通过白名单工具探索页面，完成后把完整轨迹总结为结构化 Recipe，并通过 WebSocket 同步管理员可见观察信息。

### 前置检查

- Phase 2 `AgentCrawler` 已能 replay recipe。
- 已有 artifact 存储目录和 TTL 清理。
- 已有 tool/url/locator 安全校验。
- 已确定 recipe store 方案。
- 已确定 WebSocket 鉴权方式和事件 schema。

### 新增 core 文件

| 文件 | 内容 |
|---|---|
| `src/core/agent/discovery.py` | `ReActDiscoveryAgent` |
| `src/core/agent/tools.py` | Tool registry 与 tool schemas |
| `src/core/agent/tool_executor.py` | 工具执行前安全校验与 driver 调用 |
| `src/core/agent/trajectory.py` | discovery trace/trajectory 模型 |
| `src/core/agent/recipe_generation.py` | trajectory 到 recipe 的 LLM 总结与本地校验 |
| `src/core/agent/llm.py` | 通用 LLM client protocol |
| `src/core/agent/events.py` | 内部事件模型 |
| `src/core/agent/observation_sync.py` | 观察同步事件过滤 |

### 新增持久化文件

| 文件 | 内容 |
|---|---|
| `src/domains/agent_recipe/models.py` | `AgentRecipe` SQLModel |
| `src/domains/agent_recipe/repository.py` | recipe 查询、创建、版本更新 |
| `src/domains/agent_recipe/services.py` | recipe service |
| `src/domains/agent_recipe/schemas.py` | API schema |
| `migrations/versions/<revision>_add_agent_recipes_table.py` | `agent_recipes` 表 |
| `tests/domains/agent_recipe/test_repository.py` | repository 单测 |
| `tests/integration/test_agent_recipe_migration.py` | migration smoke |

`agent_recipes` 表字段：

- `id`
- `namespace`
- `key`
- `version`
- `status`
- `entrypoint`
- `steps`
- `observations`
- `assertions`
- `recovery_policy`
- `security_policy`
- `created_at`
- `updated_at`

约束：

- `(namespace, key, version)` unique
- active 查询只返回 `status == "active"`
- JSON 字段使用 SQLAlchemy `JSON`，兼容 sqlite 测试

### 新增 API / WebSocket 文件

| 文件 | 内容 |
|---|---|
| `src/api/v1/agent_discovery.py` | discovery HTTP trigger 与 WebSocket router |
| `src/tasks/collection/douyin_shop_discovery.py` | funboost discovery 异步任务 |
| `tests/api/test_agent_discovery_websocket.py` | WebSocket schema/顺序测试 |
| `tests/api/test_agent_discovery_api.py` | trigger API 测试 |

`src/main.py` 注册：

- HTTP: `/api/v1/agent-discovery`
- WebSocket: `/api/v1/agent-discovery/{run_id}/events`

### Discovery 循环

1. 加载登录态。
2. 创建 driver session。
3. 导航到 entrypoint URL。
4. 截图。
5. 生成 Playwright snapshot YAML。
6. 推送管理员事件：`screenshot/url/title/status`。
7. 构造 agent observation：`screenshot/snapshot/url/title/tool_results`。
8. 调用 LLM 选择下一步 tool。
9. 校验 tool name、locator、URL、origin、危险页面。
10. 执行 tool。
11. 记录 trajectory。
12. 重复直到 `done` 或 `max_steps=30`。
13. `done` 时将完整 trajectory 发给 LLM 生成 recipe。
14. 本地校验 recipe schema、安全策略、可 replay 性。
15. 持久化 recipe。

### Tool Registry

允许工具：

- `goto`
- `back`
- `reload`
- `click`
- `fill`
- `select`
- `scroll_down`
- `scroll_up`
- `scroll_to_element`
- `wait_visible`
- `wait_network_idle`
- `get_current_url`
- `get_page_title`
- `get_element_text`
- `extract_table`
- `extract_list`
- `extract_text`
- `done`

禁止工具：

- `submit_form`
- `click_confirm`
- `click_delete`
- `evaluate`
- `download`
- 任意 shell
- 任意 Python eval
- 任意 JS eval

### 观察同步事件

管理员可见：

- `run_started`
- `page_observed`
- `tool_started`
- `tool_finished`
- `recipe_generated`
- `run_failed`
- `run_finished`

管理员事件字段：

- `run_id`
- `sequence`
- `event_type`
- `current_url`
- `page_title`
- `screenshot_artifact_id`
- `status`
- `message`
- `created_at`

管理员不可见：

- Agent thought
- LLM prompt
- LLM raw response
- snapshot YAML
- cookies
- localStorage
- sessionStorage
- tool internal args 中的敏感值

Agent 内部事件可包含：

- snapshot YAML
- tool args
- tool result
- selected action
- failure classifier result

### Recipe 生成约束

LLM 生成 recipe 后必须本地校验：

- namespace/key 非空
- entrypoint URL allowlisted
- steps 非空
- action 全部在白名单
- locator 全部通过危险模式过滤
- observations id 唯一
- assertions 引用的 source 存在
- recovery_policy 不允许越权修改 entrypoint
- security_policy 不放宽系统默认策略

必须 replay：

- 用 Phase 2 `AgentCrawler` 对新 recipe 做一次 replay。
- replay 成功才持久化为 active。
- replay 失败时 discovery run 标记 failed，不写 active recipe。

### LLM 接口

Core 只定义 protocol：

- `complete_tool_call(request) -> ToolCall`
- `summarize_recipe(request) -> Recipe`

业务配置可使用：

- `llm_provider="openai"`
- `llm_endpoint`
- `llm_model`
- `llm_timeout_seconds`
- `llm_retry_times`

Qwen/DashScope 只作为 provider adapter，不进入 core 命名。

### 测试计划

新增：

- `tests/core/agent/test_tool_registry.py`
- `tests/core/agent/test_react_discovery_agent.py`
- `tests/core/agent/test_recipe_generation.py`
- `tests/core/agent/test_observation_sync.py`
- `tests/domains/agent_recipe/test_models.py`
- `tests/domains/agent_recipe/test_repository.py`
- `tests/api/test_agent_discovery_websocket.py`
- `tests/api/test_agent_discovery_api.py`
- `tests/integration/test_agent_discovery_registry_sync.py`

命令：

```bash
uv run --frozen pytest -q tests/core/agent/test_tool_registry.py tests/core/agent/test_react_discovery_agent.py tests/core/agent/test_recipe_generation.py
uv run --frozen pytest -q tests/domains/agent_recipe tests/api/test_agent_discovery_websocket.py
uv run --frozen pytest -q tests/integration/test_agent_discovery_registry_sync.py
just arch-check
```

### 验收门禁

- LLM 返回未知工具时被拒绝。
- LLM 返回危险 locator 时被拒绝。
- LLM 试图导航非 allowlist URL 时被拒绝。
- `max_steps=30` 生效。
- `done` 前不写 recipe。
- recipe replay 失败不写 active recipe。
- WebSocket 事件 sequence 单调递增。
- 管理员事件不包含 snapshot YAML、thought、cookie、localStorage、sessionStorage。
- `agent_recipes` migration 可 upgrade/downgrade。

### Phase 3 完成定义

- 管理员可触发 discovery。
- Discovery 可通过 WebSocket 观察进度。
- Discovery 可生成 recipe。
- 生成 recipe 通过 replay 后写入 `agent_recipes`。
- 日常采集仍通过 Phase 2 deterministic `AgentCrawler` 执行 recipe，不调用 discovery。

## Phase 4：Recovery

### 目标

实现失败后的受控自愈：日常 `AgentCrawler` 执行失败时，Recovery 使用失败 recipe、失败信息、截图和 snapshot 让模型一次性提出 patch；本地校验 patch；replay 成功后写入新 recipe version；失败则标记 degraded。

### 前置检查

- Phase 2 replay 稳定。
- Phase 3 recipe store 已有版本字段。
- Agent artifacts 可追踪失败上下文。
- LLM adapter 可返回结构化 proposal。
- Recipe repository 支持并发写回保护。

### 新增 core 文件

| 文件 | 内容 |
|---|---|
| `src/core/agent/recovery.py` | recovery service |
| `src/core/agent/proposals.py` | `RecoveryProposal`、`RecipePatch` |
| `src/core/agent/proposal_validator.py` | patch 越权校验 |
| `src/core/agent/replay.py` | `ReplayRunner` |
| `src/core/agent/failures.py` | `FailureClassifier` |
| `src/core/agent/recovery_prompts.py` | recovery prompt builder |

### 修改持久化文件

| 文件 | 修改 |
|---|---|
| `src/domains/agent_recipe/models.py` | 增加 status/version metadata，或新增 revision 表 |
| `src/domains/agent_recipe/repository.py` | 增加 `get_active_for_update()`、`create_next_version()`、`mark_degraded()` |
| `migrations/versions/<revision>_add_agent_recipe_revisions_table.py` | 如果需要完整历史，新增 revisions |
| `src/application/collection/browser_agent_adapter.py` | 日常执行失败时触发 recovery |

建议新增 `agent_recipe_revisions`：

- `id`
- `recipe_id`
- `version`
- `snapshot`
- `change_reason`
- `created_at`

如果暂不新增 revision 表：

- `agent_recipes` 采用 append-only version rows。
- active 查询取 `status="active"` 且 version 最大的一条。
- 写入新版本必须同事务停用旧 active。

### 可恢复失败类型

允许进入 Recovery：

- `locator_not_found`
- `observation_empty`
- `parse_failed`
- `assertion_failed` 且 assertion 指向 observation locator
- `timeout` 且失败点是等待元素

禁止进入 Recovery：

- `login_expired`
- `permission_denied`
- `shop_context_mismatch`
- `url_not_allowed`
- `dangerous_page`
- `security_policy_violation`
- `driver_crashed`
- `recipe_schema_invalid`

### Proposal schema

`RecoveryProposal` 字段：

- `confidence: float`
- `reason: str`
- `patches: list[RecipePatch]`
- `expected_effect: str`

`RecipePatch` 仅允许：

- `op="replace"`
- `path="/observations/{id}/locator"`
- `value=LocatorSpec`

默认禁止：

- 修改 `entrypoint`
- 修改 `steps`
- 修改 `assertions`
- 修改 `security_policy`
- 修改 `recovery_policy`
- 添加任意新工具
- 删除 observation
- 修改业务 parser 名称

### Recovery 流程

1. `AgentCrawler` 返回 failure。
2. `FailureClassifier` 判断是否可恢复。
3. 收集失败 artifact：screenshot、snapshot、step trace、failure detail。
4. 构造 `RecoveryRequest`。
5. 调用 recovery LLM。
6. 解析 `RecoveryProposal`。
7. `ProposalValidator` 校验 confidence、patch path、locator、安全策略。
8. 应用 patch 到 recipe copy。
9. `ReplayRunner` 使用相同输入 replay patched recipe。
10. replay 成功时写入新 version。
11. replay 失败时原 recipe 不变，标记 degraded 或记录 failure。
12. 返回业务结果或失败原因。

### 并发写回策略

Recipe 写回必须满足：

- 读取 active recipe 时带当前 version。
- 写入前校验 active version 未变化。
- version 冲突时丢弃本次 proposal，不覆盖新版本。
- 新版本写入与旧版本状态切换在同一事务。
- replay 成功前不写 active。

如果使用 Postgres：

- repository 使用 `SELECT ... FOR UPDATE`。

如果使用 sqlite 测试：

- 用事务和 version 条件模拟 CAS。

### 业务接线

`browser_agent_adapter` recovery 接线：

1. `AgentCrawler.run()` 失败。
2. 如果 `runtime.extra_config.agent_recovery_enabled` 未显式禁用，则尝试 Recovery。
3. Recovery 成功后重新执行 patched recipe。
4. 成功 payload 标记：
   - `source="browser_agent"`
   - `raw.agent.recovery.status="success"`
   - `raw.agent.recovery.previous_version`
   - `raw.agent.recovery.next_version`
5. Recovery 失败时返回明确 failure：
   - `status="failed"` 或 `status="degraded"`
   - `reason="agent_recovery_failed"`
   - `raw.agent.recovery.status="failed"`

### 旧链路最终清理

Phase 4 结束后确认：

- 没有 `HttpScraper` import。
- 没有旧 LLM 补齐主链路 import。
- 没有旧 agent 队列。
- 没有 `fallback_chain` 中的 `http`、`agent`、`llm`。
- `ScrapingRule.extra_config` 不再承载旧 `api_groups/common_query/token_keys/graphql_query` 的采集必需配置。

### 测试计划

新增：

- `tests/core/agent/test_failure_classifier.py`
- `tests/core/agent/test_proposal_validator.py`
- `tests/core/agent/test_replay_runner.py`
- `tests/core/agent/test_recovery_service.py`
- `tests/domains/agent_recipe/test_versioning.py`
- `tests/tasks/test_shop_dashboard_recovery_flow.py`
- `tests/integration/test_agent_recipe_versioning.py`

覆盖：

- 可恢复失败进入 recovery。
- 不可恢复失败不调用 LLM。
- proposal 只能修改 observation locator。
- proposal 修改 entrypoint 被拒绝。
- proposal 修改 steps 被拒绝。
- confidence 低于阈值被拒绝。
- replay 成功才写新 version。
- replay 失败原 version 不变。
- version 冲突时放弃写回。
- degraded 状态可被查询和告警。

命令：

```bash
uv run --frozen pytest -q tests/core/agent/test_failure_classifier.py tests/core/agent/test_proposal_validator.py tests/core/agent/test_replay_runner.py tests/core/agent/test_recovery_service.py
uv run --frozen pytest -q tests/domains/agent_recipe/test_versioning.py tests/tasks/test_shop_dashboard_recovery_flow.py
uv run --frozen pytest -q tests/integration/test_agent_recipe_versioning.py
just arch-check
```

### 验收门禁

- Recovery 不处理登录过期、权限错误、店铺不匹配。
- Recovery proposal 不可越权修改 recipe 结构。
- Replay 成功是唯一写回条件。
- Recipe version 单调递增。
- 版本冲突不覆盖。
- Recovery 失败不会污染 active recipe。
- 清理旧 HTTP/LLM 链路后 `just ci-gate` 通过。

### Phase 4 完成定义

- 日常执行失败可触发一次性 Recovery。
- 成功 Recovery 会写入新 recipe version。
- 失败 Recovery 会保留旧 recipe 并标记 degraded。
- 旧 HTTP scraper、LLM fallback、agent 队列已从目标采集链路清理。

## 迁移与发布顺序

1. Phase 1 合入：只新增 core skeleton，无行为变化。
2. Phase 2A 合入：新增 `browser_agent` stage，允许灰度配置。
3. Phase 2B 合入：默认 `browser_agent`，删除 HTTP/LLM 主链路。
4. Phase 3 合入：新增 discovery、WebSocket、recipe store。
5. Phase 4 合入：新增 recovery、versioning、旧链路最终清理。

## 验证总门禁

每个 Phase 合入前必须运行：

```bash
just arch-check
uv run --frozen pytest -q
```

涉及迁移时必须运行：

```bash
just migration-ci
```

涉及 Docker/Playwright CLI 路线时必须额外验证：

```bash
playwright-cli --version
```

其中 `playwright-cli --version` 只在实际引入 Node CLI 后才作为硬门禁。

## 风险清单

| 风险 | 影响 | 控制措施 |
|---|---|---|
| 过早删除 HTTP 链路 | 主采集不可用 | Phase 2A 先灰度，Phase 2B 再删除 |
| Core 污染业务语义 | 后续不可复用 | 架构测试扫描 `src/core/agent` 禁止业务词和业务 imports |
| Recipe 存在 `extra_config` 暴露 | 配置面泄露与并发写回风险 | 独立 `agent_recipes` 表，`extra_config` 只存引用 |
| 店铺 bundle 被误当 Playwright state | localStorage/origins 丢失，店铺上下文错误 | 新增 per-shop Playwright state 原始读写 |
| LLM 生成危险工具 | 安全事故 | Tool registry + security policy 双层拦截 |
| Recovery 越权 patch | Recipe 被污染 | ProposalValidator 只允许 observation locator replace |
| Replay 假阳性 | 错误 recipe 写入 active | replay 使用 deterministic transcript 和真实 driver contract 测试 |
| WebSocket 泄露内部 thought/snapshot | 敏感信息泄露 | 管理员事件过滤，内部事件与管理员事件分离 |
| CLI 路线新增 Node 依赖 | Docker 与 CI 变复杂 | 只保留 CLI driver 与容器安装门禁 |

## 完成审计清单

| 要求 | 证据 |
|---|---|
| 每个 phase 有详尽计划 | 本文包含 Phase 1-4 的目标、文件、流程、测试、验收门禁 |
| 分析当前源码现状 | 本文“当前代码事实”列出主链路、规则解析、存储、Playwright、WebSocket、LLM 配置现状 |
| 分析文档现状 | 本文“分析输入”覆盖主设计文档与三份相关设计文档 |
| 使用多个高级子代理 | 本文“子代理协作结论”记录架构、源码映射、测试策略三个子代理结论 |
| 落盘为 md 文档 | 文件路径：`docs/react-agent-framework-implementation-plan.md` |
