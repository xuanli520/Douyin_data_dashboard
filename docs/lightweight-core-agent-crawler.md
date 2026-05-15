# 轻量 Core Agent 自动爬取模块落地方案

## 0. 文档状态与当前代码事实

本文是目标落地方案，不是当前实现说明。

当前仓库事实：

1. 当前没有 `src/core/agent`、`src/application/collection/browser_agent_adapter.py`、`src/agents/crawl_repair_agent.py`。
2. 当前采集默认配置字符串仍是 `http->llm`，运行时把 `llm` / `agent` 归一为 `agent`；`browser_agent` stage 尚不存在。
3. 当前登录态源头是 `DataSource.extra_config.shop_dashboard_login_state`，执行前由 resolver 解析并物化到 `SessionStateStore`。
4. 当前账号级文件是完整 Playwright `storage_state`；店铺级 bundle 只是 `cookies + common_query + verify metadata`，不是可直接加载的 Playwright state。
5. 当前 `ScrapingRule.extra_config` 会被 `ScrapingRuleConfigMapper` 平铺回 `ScrapingRuleResponse.config`，因此写入 `agent_recipe*` 会成为前后端可见配置面，不是私有存储。
6. 当前 `ScrapingRuleRepository.update()` 没有 `expected_version` / 行锁 CAS 语义；recipe 写回并发保护需要新增 service/repository 支持。
7. 当前测试目录没有 `tests/core/agent/*`、`tests/application/collection/test_browser_agent_adapter.py`、`tests/tasks/test_shop_dashboard_browser_agent_fallback.py`。

## 1. 目标

在本项目中抽象一个轻量级 `src/core/agent` 自动爬取内核，用于承接“浏览器自动化 + 结构化观测 + 失败后受控修复”的通用能力。

该模块不是完整 RPA 平台，也不是业务采集任务本身。它只负责一次自动爬取执行：根据 recipe 打开页面、执行步骤、读取字段、校验输出，并在允许时生成受控修复结果。

业务侧继续负责调度、任务状态、登录态来源、店铺切换、熔断、幂等、数据入库和 fallback 编排。

## 2. 当前项目约束

现有采集主链路已经比较完整：

- `src/application/collection/usecase.py` 已负责计划拆分、幂等、锁、登录态校验、店铺 mismatch guard、结果持久化。
- `src/tasks/collection/douyin_shop_dashboard.py` 当前按 `fallback_chain` 执行 `http` 后进入 `agent`；规则解析层默认字符串是 `http->llm`，内部会把 `llm` 归一为 `agent`。
- `src/scrapers/shop_dashboard/http_scraper.py` 已有确定性 HTTP 采集、endpoint group、payload parser。
- `src/scrapers/shop_dashboard/session_state_store.py` 已有账号级 `storage_state` 文件缓存和店铺 bundle 文件缓存；店铺 bundle 不是完整 Playwright state。
- `src/domains/scraping_rule/models.py` 已有 `ScrapingRule.version` 和 `extra_config`，可承载业务 recipe。
- `src/agents/llm_dashboard_agent.py` 目前是业务补数，不是通用自愈执行内核。

因此轻量 core 不应重复这些已有职责。

## 3. 非目标

首版不做以下能力：

- 不内置 funboost、cron 或任务调度。
- 不管理 `TaskExecution` 状态。
- 不持久化业务数据。
- 不接管完整登录流程。
- 不实现通用 RPA 表单平台。
- 不新增 `agent_recipes`、`agent_artifacts` 等平台表。
- 不让模型生成任意 JavaScript。
- 不让模型决定业务目标或输出业务 payload。
- 不替换现有 HTTP scraper。

## 4. 总体架构

```text
CollectionUseCase
  -> fallback chain
  -> browser_agent stage
  -> Business Adapter
  -> src/core/agent/AgentCrawler
       -> BrowserDriver
       -> StepRunner
       -> ObservationReader
       -> AssertionRunner
       -> RepairPlanner
  -> CrawlResult
  -> Business Output Mapper
  -> CollectionResultPersister
```

Core 只知道：

```text
Recipe -> Step -> Observation -> Assertion -> Failure -> RepairProposal -> ReplayResult
```

业务侧只负责：

```text
Runtime -> input_data
CrawlResult.output -> dashboard payload
CrawlResult.failure -> business fallback / exception
repaired_recipe -> ScrapingRule.extra_config
```

## 5. 推荐目录结构

以下是拟新增目录结构。当前仓库尚未创建这些文件；首版控制在少量文件内，避免文档原方案的多层目录膨胀。

```text
src/core/agent/
  __init__.py
  models.py
  runtime.py
  browser.py
  steps.py
  observations.py
  assertions.py
  repair.py
  security.py
  exceptions.py

src/application/collection/
  browser_agent_adapter.py
```

后续只有当文件明显过大时，再拆分 `browser/`、`recipe/`、`recovery/` 子包。

## 6. Core 模型

### 6.1 AgentCrawlRecipe

```python
class AgentCrawlRecipe(BaseModel):
    key: str
    version: int = 1
    entrypoint: EntrypointSpec
    steps: list[CrawlStep] = []
    observations: dict[str, ObservationSpec] = {}
    assertions: list[AssertionSpec] = []
    repair_policy: RepairPolicy = RepairPolicy()
    security_policy: SecurityPolicy = SecurityPolicy()
    metadata: dict[str, Any] = {}
```

命名使用 `Crawl`，避免绑定抖店，也避免扩大成通用工作流平台。

### 6.2 EntrypointSpec

```python
class EntrypointSpec(BaseModel):
    url_template: str
    wait_until: Literal["load", "domcontentloaded", "networkidle"] = "domcontentloaded"
```

渲染规则：

```text
url_template + input_data -> url
```

渲染后的 URL 必须通过 `SecurityPolicy.allowed_origins` 校验。

### 6.3 CrawlStep

```python
class CrawlStep(BaseModel):
    name: str
    action: Literal[
        "goto",
        "wait_visible",
        "click",
        "fill",
        "select",
        "wait_network_idle",
        "wait_timeout",
    ]
    target: LocatorSpec | None = None
    value_template: str | None = None
    timeout_ms: int = 30000
    optional: bool = False
```

首版不支持 `evaluate`。确实需要页面脚本读取时，只允许 core 内置固定只读脚本，不允许 recipe 或模型传入 JS。

### 6.4 LocatorSpec

```python
class LocatorSpec(BaseModel):
    type: Literal["css", "xpath", "text", "role"]
    value: str
```

限制：

- 单条 locator 不超过 500 字符。
- 单个 observation 最多 5 个 locator。
- 不允许 `javascript:`、`<script`、`eval(` 等可执行片段。
- XPath 只作为 fallback。

### 6.5 ObservationSpec

```python
class ObservationSpec(BaseModel):
    kind: Literal["scalar", "list", "object"]
    locators: list[LocatorSpec]
    source: Literal["inner_text", "text_content", "attribute"] = "inner_text"
    attribute: str | None = None
    parser: str = "text"
    required: bool = False
    children: dict[str, ObservationSpec] | None = None
```

首版不做复杂 table 抽象。表格可先用 `list/object` 组合表达。

内置 parser：

```text
text
number
integer
boolean
date
datetime
json
```

业务特殊 parser 不放入 core，可由 adapter 后处理。

### 6.6 AssertionSpec

```python
class AssertionSpec(BaseModel):
    name: str
    type: Literal["required", "range", "regex", "equals", "not_equals", "contains"]
    target: str
    params: dict[str, Any] = {}
    recoverable: bool = True
```

首版不做 `custom` assertion，避免 core 依赖业务注册器。

### 6.7 CrawlResult

```python
class CrawlResult(BaseModel):
    ok: bool
    status: Literal["succeeded", "failed", "repaired", "degraded"]
    output: dict[str, Any] = {}
    failure: CrawlFailure | None = None
    repaired_recipe: AgentCrawlRecipe | None = None
    metadata: dict[str, Any] = {}
```

core 不负责把 `output` 转成抖店分数结构。

## 7. Runtime 接口

```python
class AgentCrawler:
    def run(
        self,
        *,
        recipe: AgentCrawlRecipe,
        input_data: dict[str, Any],
        session_state_path: Path | None = None,
        options: CrawlOptions | None = None,
    ) -> CrawlResult:
        ...
```

`CrawlOptions`：

```python
class CrawlOptions(BaseModel):
    headed: bool = False
    enable_repair: bool = False
    max_repair_attempts: int = 1
    timeout_ms: int = 30000
```

执行流程：

```text
1. 渲染 entrypoint URL
2. 校验 URL allowlist
3. 创建 BrowserDriver
4. 加载 session_state_path
5. 执行 steps
6. 读取 observations
7. 执行 assertions
8. 成功则返回 output
9. 失败且允许 repair 时，生成 RepairProposal
10. 校验 proposal
11. 应用 candidate recipe
12. replay 一次
13. replay 成功返回 repaired_recipe
14. replay 失败返回原始 failure
```

## 8. BrowserDriver

首版只实现 Playwright Python Driver，因为项目已经依赖 `playwright`，且 `scripts/douyin_bootstrap_login.py` 已使用同步 Playwright。

```python
class BrowserDriver(Protocol):
    def open(self, *, headed: bool) -> None: ...
    def load_state(self, path: Path) -> None: ...
    def goto(self, url: str, *, wait_until: str, timeout_ms: int) -> None: ...
    def click(self, locator: LocatorSpec, *, timeout_ms: int) -> None: ...
    def fill(self, locator: LocatorSpec, value: str, *, timeout_ms: int) -> None: ...
    def select(self, locator: LocatorSpec, value: str, *, timeout_ms: int) -> None: ...
    def wait_visible(self, locator: LocatorSpec, *, timeout_ms: int) -> None: ...
    def read(self, observation: ObservationSpec) -> Any: ...
    def current_url(self) -> str: ...
    def snapshot_text(self, *, max_chars: int) -> str: ...
    def screenshot_bytes(self) -> bytes | None: ...
    def close(self) -> None: ...
```

Core 不保存 cookie/localStorage，也不回写 session state。当前登录态源头是 `DataSource.extra_config.shop_dashboard_login_state`；执行期由 resolver 解析并物化到 `SessionStateStore`。`SessionBootstrapper` 继续负责店铺切换、bundle 校验与缓存。

## 9. Repair 设计

### 9.1 RepairPolicy

```python
class RepairPolicy(BaseModel):
    enabled: bool = False
    max_attempts: int = 1
    confidence_threshold: float = 0.7
    allow_observation_locator_patch: bool = True
    allow_parser_patch: bool = False
    allow_timeout_patch: bool = False
```

首版默认只允许修 observation locator。

### 9.2 可恢复失败

```text
locator_not_found
observation_empty
parse_failed
```

不可恢复失败：

```text
auth_required
access_denied
url_not_allowed
shop_mismatch
browser_crashed
assertion_failed
```

`shop_mismatch` 这类业务语义不进入 core，由 adapter 根据 output 判定。

### 9.3 RepairProposal

```python
class RepairProposal(BaseModel):
    base_version: int
    patches: list[RecipePatch]
    confidence: float
    summary: str
```

```python
class RecipePatch(BaseModel):
    op: Literal["replace_observation_locators", "append_observation_locator"]
    target: str
    value: Any
    confidence: float
```

示例：

```json
{
  "base_version": 3,
  "patches": [
    {
      "op": "replace_observation_locators",
      "target": "total_score",
      "value": [{"type": "css", "value": ".score-panel .total"}],
      "confidence": 0.86
    }
  ],
  "confidence": 0.86,
  "summary": "Updated locator for total_score"
}
```

### 9.4 Proposal 校验

必须本地校验：

- `base_version == recipe.version`
- `confidence >= threshold`
- patch target 必须在失败 observation 内。
- patch op 必须被 policy 允许。
- locator 数量和长度合规。
- locator 不包含 JS。
- 不允许修改 entrypoint。
- 不允许修改 steps 顺序。
- 不允许修改 assertions。
- candidate recipe 能通过 Pydantic 校验。

### 9.5 Replay

Repair 成功的唯一依据是 replay 成功：

```text
proposal -> candidate_recipe -> same input_data -> run without repair -> ok
```

Replay 失败则丢弃 proposal，继续返回 failure，由业务 fallback 到下一个 stage。

## 10. SecurityPolicy

```python
class SecurityPolicy(BaseModel):
    allowed_origins: list[str]
    snapshot_max_chars: int = 30000
    upload_screenshot: bool = False
    redaction_patterns: list[str] = []
```

首版只把文本 snapshot 发给模型。截图默认关闭；如果后续打开截图，必须先做遮罩和脱敏。

内置脱敏：

```text
手机号
邮箱
身份证样式数字
长 token
cookie 字段
authorization 字段
```

## 11. 业务接入

以下文件为拟新增文件，当前仓库尚不存在。

新增：

```text
src/application/collection/browser_agent_adapter.py
```

职责：

```text
1. 从 ScrapingRule.extra_config.agent_recipe 读取 recipe。
2. 将 ShopDashboardRuntimeConfig + metric_date 转成 input_data。
3. 找到当前账号级 Playwright `storage_state` 文件；店铺 bundle 只能作为 cookies/common_query/校验元数据来源，不能直接当作 Playwright state 加载。
4. 调用 AgentCrawler。
5. 将 output 映射成 CollectionResultPersister 已接受的 payload。
6. 校验 actual_shop_id 与 target_shop_id。
7. 如果 repaired_recipe 存在，则写回 ScrapingRule.extra_config.agent_recipe。
```

适配器接口：

```python
class ShopDashboardBrowserAgentAdapter:
    def collect(
        self,
        *,
        runtime: ShopDashboardRuntimeConfig,
        metric_date: str,
        state_store: SessionStateStore,
    ) -> dict[str, Any]:
        ...
```

## 12. Fallback Chain 调整

当前规则解析会把 `browser` 丢弃，只允许 `http` 和 `agent`。配置层默认字符串仍是 `http->llm`，内部会把 `llm` 归一为 `agent`。

调整为：

```text
http -> browser_agent -> agent
```

修改点：

- `src/scrapers/shop_dashboard/rule_config_resolver.py`
  - `_normalize_fallback_chain` 支持 `browser_agent`
  - 兼容输入别名：`browser`、`crawl`、`agent_crawl` -> `browser_agent`
- `src/tasks/collection/douyin_shop_dashboard.py`
  - `_normalize_fallback_stage` 支持 `browser_agent`
  - `_collect_one_day` 增加 browser agent 分支

新增 `browser_agent` 后，建议默认仍保持当前运行效果：

```text
http -> agent
```

只有配置了 `fallback_chain=http->browser_agent->agent` 的规则才启用新 core。`browser_agent` 属于拟新增 stage，当前代码尚不支持。

## 13. Recipe 存储

首版不新增数据库表，使用：

```text
scraping_rules.extra_config.agent_recipe
scraping_rules.extra_config.agent_recipe_version
scraping_rules.extra_config.agent_recipe_updated_at
scraping_rules.extra_config.agent_recipe_update_reason
```

注意：`ScrapingRule.extra_config` 会被 `ScrapingRuleConfigMapper` 平铺回 API 响应的 `config`，因此这些字段会成为前后端可见配置面。若 recipe 需要保持内部私有，需要另建表或调整响应映射。

示例：

```json
{
  "agent_recipe": {
    "key": "shop_dashboard_score_page",
    "version": 1,
    "entrypoint": {
      "url_template": "https://fxg.jinritemai.com/xxx?shop_id={{ shop_id }}"
    },
    "steps": [
      {
        "name": "wait_score_panel",
        "action": "wait_visible",
        "target": {"type": "css", "value": ".score-panel"},
        "timeout_ms": 30000
      }
    ],
    "observations": {
      "total_score": {
        "kind": "scalar",
        "locators": [{"type": "css", "value": ".total-score"}],
        "parser": "number",
        "required": true
      }
    },
    "assertions": [
      {
        "name": "total_score_required",
        "type": "required",
        "target": "total_score"
      }
    ],
    "security_policy": {
      "allowed_origins": ["https://fxg.jinritemai.com"]
    }
  }
}
```

目标写回策略：

```text
1. 新增 service/repository 级 CAS 或事务锁能力。
2. 重新读取 ScrapingRule。
3. 比较 rule.version 是否仍等于运行时版本。
4. 相等则写入 repaired_recipe，rule.version + 1。
5. 不相等则丢弃本次 repair，不覆盖人工或其他任务更新。
```

当前 `ScrapingRuleRepository.update()` 只是直接赋值，`ScrapingRuleService.update_rule()` 虽会递增 version，但没有 `expected_version` 比较或行锁；上述并发保护不是现有仓库自动具备的能力。

## 14. 与现有模块关系

保留：

- `CollectionUseCase`
- `HttpScraper`
- `SessionBootstrapper`
- `SessionStateStore`
- `CollectionResultPersister`
- `LLMDashboardAgent`

新增 core 只作为 fallback stage 插入，不影响默认 HTTP 成功路径。

```text
HTTP 成功：不进入 browser_agent
HTTP 失败且配置 browser_agent：尝试浏览器爬取
browser_agent 成功：输出 source=browser_agent
browser_agent 失败：继续 agent/llm
repair 成功：输出 source=browser_agent，写回 recipe
repair 失败：不写 recipe
```

## 15. 分阶段实施计划

本节列出的文件均为目标态改动，未列为当前已存在文件。

### Phase 1：Core Skeleton

新增：

```text
src/core/agent/models.py
src/core/agent/exceptions.py
src/core/agent/security.py
```

完成：

- Pydantic 模型。
- URL allowlist。
- locator 校验。
- parser 基础模型。

验收：

- recipe schema 可校验。
- 非 allowlist URL 被拒绝。
- 非法 locator 被拒绝。

### Phase 2：确定性浏览器执行

新增：

```text
src/core/agent/browser.py
src/core/agent/steps.py
src/core/agent/observations.py
src/core/agent/assertions.py
src/core/agent/runtime.py
```

完成：

- Playwright driver。
- step 执行。
- observation 读取。
- parser。
- assertion。
- `AgentCrawler.run()`。

验收：

- 测试页面可读取 scalar/list/object。
- 缺失 locator 返回明确 failure。
- parser 失败返回明确 failure。
- 正常执行不调用模型。

### Phase 3：业务 adapter 接入

新增：

```text
src/application/collection/browser_agent_adapter.py
```

修改：

```text
src/scrapers/shop_dashboard/rule_config_resolver.py
src/tasks/collection/douyin_shop_dashboard.py
```

完成：

- fallback stage `browser_agent`。
- recipe 从 `ScrapingRule.extra_config` 读取。
- output 映射成现有 dashboard payload。
- source 标记为 `browser_agent`。

验收：

- 默认规则行为不变。
- 配置 `http->browser_agent->agent` 后，HTTP 失败可进入 browser agent。
- browser agent 成功结果可被 `CollectionResultPersister` 入库。

### Phase 4：受控 repair

新增：

```text
src/core/agent/repair.py
src/agents/crawl_repair_agent.py
```

完成：

- failure snapshot。
- 模型 proposal。
- proposal validator。
- replay。
- repaired_recipe 返回。

验收：

- 只有 locator 失败触发 repair。
- proposal 越权修改被拒绝。
- replay 失败不写回。
- replay 成功才写回 `ScrapingRule.extra_config.agent_recipe`。

### Phase 5：稳定化

完成：

- 补充 metrics。
- 增加 repair 结果日志。
- 增加 recipe 写回冲突保护。
- 评估是否需要独立 revision 表。

是否新增表的判断标准：

```text
1. 发生过多次自动 repair，需要可视化历史。
2. 多个业务复用同一 recipe。
3. 需要跨规则共享 recipe。
4. 需要独立回滚能力。
```

## 16. 测试计划

以下为目标测试计划，当前仓库尚无这些 browser-agent 测试文件。

Core 单元测试：

```text
tests/core/agent/test_models.py
tests/core/agent/test_security.py
tests/core/agent/test_observations.py
tests/core/agent/test_assertions.py
tests/core/agent/test_runtime.py
tests/core/agent/test_repair.py
```

业务接入测试：

```text
tests/application/collection/test_browser_agent_adapter.py
tests/tasks/test_shop_dashboard_browser_agent_fallback.py
tests/scrapers/shop_dashboard/test_rule_config_resolver_browser_agent.py
```

重点覆盖：

- 默认 fallback 不变。
- `browser_agent` stage 归一化。
- recipe 缺失时跳过或失败进入下个 fallback。
- browser agent 输出可持久化。
- shop mismatch 不入库。
- repair 成功写回。
- repair 版本冲突不覆盖。

## 17. 风险与边界

### 17.1 浏览器执行慢

控制方式：

- 默认不启用。
- 只在 HTTP 失败后启用。
- 单次 timeout 受 `CrawlOptions.timeout_ms` 限制。

### 17.2 模型误修

控制方式：

- 首版只允许修 locator。
- proposal 必须本地校验。
- 必须 replay 成功。
- 写回必须检查 `ScrapingRule.version`。

### 17.3 登录态污染

控制方式：

- core 只加载 state，不回写 state。
- 账号级 `storage_state` 来自 `DataSource.extra_config.shop_dashboard_login_state` 并物化到 `SessionStateStore`。
- 店铺 bundle 仍由 `SessionBootstrapper` 管理，当前 bundle 仅包含 cookies/common_query/校验元数据。
- core 不读取或记录 cookie/localStorage。

### 17.4 抽象再次变重

控制方式：

- 首版不建平台表。
- 首版不拆多层目录。
- 首版不支持任意 custom action。
- 第二个业务真实接入前，不抽共享 recipe store。

## 18. 推荐落地顺序

优先做：

```text
1. Core schema + security
2. Playwright deterministic execution
3. browser_agent fallback 接入
4. 业务 output mapper
5. locator repair + replay
```

暂缓做：

```text
1. agent_recipes 表
2. agent_artifacts 表
3. 多 provider 模型抽象
4. table observation
5. custom assertion 注册器
6. session state merge/persist
```

## 19. 最终形态

```text
src/core/agent
  = 轻量、无业务、无数据库依赖的浏览器自动爬取内核

src/application/collection/browser_agent_adapter.py
  = 抖店采集业务接入层

scraping_rules.extra_config.agent_recipe
  = 首版 recipe 存储
```

这套方案保留 core 抽象，但把边界压到最小：core 只处理一次浏览器爬取和受控 repair；业务系统继续处理调度、登录态、店铺语义、持久化和 fallback。
