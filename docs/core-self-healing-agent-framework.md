# Core Self-Healing Agent Framework 方案

> 目标：拟建设一个可广泛复用的轻量级自动化 Agent 基建框架，而不是某个采集场景的专用模块。
> 目标框架计划放在 `src/core/agent` 下，核心命名、数据模型、流程编排、异常类型、存储结构均不得绑定具体业务。
> 业务模块只通过 Adapter / Recipe / Policy / Mapper 接入。

## 0. 文档状态与当前代码事实

本文是目标方案，不是当前实现说明。

当前仓库事实：

1. 当前没有 `src/core/agent`、`src/extraction`、`src/domains/extraction_rule`、`src/modules/douyin_dashboard` 目录。
2. 当前采集主链路在 `src/tasks/collection/douyin_shop_dashboard.py`，先执行 `HttpScraper`，失败后按 `fallback_chain` 进入 `agent`。
3. 当前规则解析层默认 fallback 字符串是 `http->llm`，运行时把 `llm` / `agent` 归一为 `agent`。
4. 当前 LLM 补齐实现是 `src/agents/llm_dashboard_agent.py`，默认配置是 `llm_provider="claude"`，可配置 `openai` 风格请求；仓库没有 Qwen 专用 RecoveryModel。
5. 当前 Playwright 只作为登录态/店铺态 bootstrap 基础能力使用，依赖 Python `playwright`；Docker 执行 `python -m playwright install --with-deps chromium`，没有安装 `@playwright/cli` 或 `playwright-cli`。
6. 当前调度由 funboost worker 和 `src.tasks.beat` 负责，`ScheduleConfig` 使用 APScheduler `CronTrigger` 校验 cron 表达式，不依赖系统 cron。
7. 当前已存在的规则表是 `scraping_rules`，可扩展字段是 `ScrapingRule.extra_config`；仓库没有 `agent_recipes`、`agent_recipe_revisions`、`agent_run_logs`、`agent_artifacts` 表或迁移。
8. 当前测试覆盖集中在 `tests/agents`、`tests/tasks`、`tests/scrapers/shop_dashboard`、`tests/application/collection`，没有 `tests/core/agent` 或 `tests/modules/<business>`。

---

## 1. 背景与问题

当前仓库的真实链路是：`HttpScraper` 负责抖店数据采集，`LLMDashboardAgent` 用于 HTTP 失败后的冷数据/失败补丁，Playwright 主要用于登录态 bootstrap。浏览器自动化、结构化规则、失败后自愈、版本化规则、重放验证尚未作为采集主链路落地。

本文讨论的目标技术方向是可行的：基于浏览器自动化、结构化规则、失败后自愈、版本化规则、重放验证，可以逐步替代不可靠的 LLM fallback，并避免日常采集消耗 token。

已有设计草案存在一个关键架构风险：它容易把本应沉淀为基础设施的能力绑定到单一采集场景。

如果按采集专用方式落地，典型问题包括：

1. 文件路径放在 `src/extraction`，导致模块语义天然绑定“采集”。
2. 核心模型命名为 `ExtractionRule`、`RuleExecutor`、`Explorer`，难以复用于表单填写、后台巡检、客服工单、RPA 流程。
3. 核心流程中混入 `shop_id`、`actual_shop_id`、`scraping_rule_id`、`metric_date`、`plan_unit` 等业务概念。
4. 模型调用层直接绑定某一类页面字段修复，而不是抽象成通用 Recovery Proposal。
5. 数据库存储结构绑定 `extraction_rules`、`rule_revisions`，无法作为平台级 Agent Recipe Store 复用。

因此目标方案应重写为：

```text
src/core/agent
  = 通用 Self-Healing Agent Framework

src/modules/<business>
  = 业务 Adapter + Recipe Seed + Output Mapper + Custom Validator
```

---

## 2. 设计目标

### 2.1 核心目标

1. **通用性**：框架不绑定任何业务领域，可用于网页采集、后台巡检、表单填写、运营流程自动化、客服工单处理、页面状态检查等场景。
2. **轻量性**：框架只负责单次任务执行，不内置调度、队列、分布式编排；调度继续由 funboost worker 和应用内 beat/CronTrigger 机制负责。
3. **确定性优先**：日常执行基于 Recipe + Browser Action + Observation + Assertion，默认 0 token。
4. **失败后有限自愈**：只有可恢复失败才调用多模态模型生成受控 patch。
5. **模型输出不可直接执行**：模型只生成结构化 proposal，不允许生成任意 JavaScript 或自由动作。
6. **可审计**：所有 recipe 变更都写 revision，支持版本冲突检测、降级、回滚。
7. **安全可控**：URL allowlist、敏感信息脱敏、artifact TTL、会话态隔离均由核心框架统一提供。
8. **业务隔离**：核心不出现具体业务词，业务语义只存在于 Adapter / Recipe / Mapper 中。

---

## 3. 非目标

本框架不负责：

1. 任务调度。
2. 队列消费。
3. 分布式任务编排。
4. 业务数据持久化。
5. 业务权限判断。
6. 业务 fallback chain 策略。
7. 业务字段定义。
8. 业务输出结构归一化。
9. 账号登录流程的完整托管。
10. 让模型自由决定任务目标或业务逻辑。

---

## 4. 总体架构

```text
funboost / src.tasks.beat
  ↓
Business Task
  ↓
Business Agent Adapter
  ↓
src/core/agent/AgentRuntime
  ├── RecipeStore
  ├── SessionMaterializer
  ├── BrowserDriver
  ├── FlowExecutor
  ├── ObservationReader
  ├── AssertionRunner
  ├── FailureClassifier
  ├── ArtifactCollector
  ├── RecoveryPlanner
  │     └── RecoveryModel
  │           └── RecoveryModel implementation
  ├── ProposalValidator
  ├── ReplayRunner
  └── RunLogger
  ↓
AgentRunResult
  ↓
Business Output Mapper
  ↓
Existing Business Service / Persister
```

核心框架只知道：

```text
Recipe → Action → Observation → Assertion → Failure → Proposal → Validation → Revision → Replay
```

它不知道自己服务的是哪个业务。

---

## 5. 目录结构

以下是目标目录结构，当前仓库尚未创建这些文件。

```text
src/core/agent/
  __init__.py
  config.py
  exceptions.py

  runtime/
    __init__.py
    engine.py
    context.py
    options.py
    result.py
    lifecycle.py

  browser/
    __init__.py
    driver.py
    playwright_cli_driver.py
    playwright_python_driver.py
    actions.py
    locators.py
    script_builder.py

  recipe/
    __init__.py
    models.py
    store.py
    repository.py
    revisions.py
    validator.py
    renderer.py
    patch.py

  execution/
    __init__.py
    executor.py
    action_runner.py
    observation_reader.py
    parser.py
    assertion_runner.py
    failure_classifier.py

  recovery/
    __init__.py
    planner.py
    model_protocol.py
    qwen_multimodal_model.py
    request_builder.py
    proposal.py
    proposal_validator.py
    replay.py

  session/
    __init__.py
    state_store.py
    state_materializer.py
    scope.py
    metadata.py

  artifacts/
    __init__.py
    store.py
    collector.py
    sanitizer.py
    retention.py

  security/
    __init__.py
    allowlist.py
    redaction.py
    secrets.py
    policy.py

  ports/
    __init__.py
    clock.py
    id_generator.py
    transaction.py
    event_bus.py
```

目标业务模块示例，当前仓库尚未创建 `src/modules/douyin_dashboard`：

```text
src/modules/douyin_dashboard/
  agent_adapter.py
  recipe_seed.py
  output_mapper.py
  validators.py
  session_scope_resolver.py
  tasks.py
```

---

## 6. 核心命名规则

### 6.1 Core 禁止出现的业务词

`src/core/agent` 内不得出现以下类型命名：

```text
extraction
scraper
scraping
shop
dashboard
douyin
doudian
fxg
score
review
violation
seller
product_score
logistics_score
service_score
bad_behavior_score
actual_shop_id
target_shop_id
metric_date
plan_unit
data_source
scraping_rule
```

这些词只能出现在业务模块。

### 6.2 通用命名替换

| 旧语义 | Core 通用命名 |
|---|---|
| ExtractionEngine | AgentRuntime / AgentEngine |
| ExtractionRule | AutomationRecipe |
| RuleStore | RecipeStore |
| RuleRevision | RecipeRevision |
| Executor | FlowExecutor |
| Explorer | RecoveryPlanner |
| self_heal | recover / repair |
| failed_fields | failed_targets |
| selector_failed | locator_resolution_failed |
| shop_context | subject_context |
| source_url_template | entrypoint_template |
| navigation | steps |
| extractions | observations |
| integrity | assertions |
| parser | value_parser |
| output payload | task_result |
| screenshot/snapshot | artifacts |
| Qwen Client | RecoveryModel |
| runtime | ExecutionContext |

---

## 7. 核心运行接口

以下接口是目标设计，不是当前仓库已有 API。当前可调用入口仍是 `CollectionUseCase.execute()`、`sync_shop_dashboard()`、`sync_shop_dashboard_agent()`、`LLMDashboardAgent.supplement_cold_data()` 与 `SessionBootstrapper.bootstrap_shop()`。

### 7.1 AgentRuntime

```python
class AgentRuntime:
    def run(
        self,
        recipe_key: str,
        context: ExecutionContext,
        input_data: dict[str, Any],
        *,
        options: RunOptions | None = None,
    ) -> AgentRunResult:
        ...
```

### 7.2 ExecutionContext

```python
class ExecutionContext(BaseModel):
    execution_id: str
    recipe_namespace: str
    recipe_key: str

    actor_ref: str | None = None
    subject_ref: str | None = None
    tenant_ref: str | None = None

    environment: str = "prod"
    trace_id: str | None = None
    metadata: dict[str, Any] = {}
```

说明：

- `actor_ref`：执行主体，例如账号、用户、机器人身份。
- `subject_ref`：任务对象，例如某个租户、页面实体、业务主体。
- `tenant_ref`：租户或组织隔离维度。
- core 不理解这些 ref 的业务含义。

### 7.3 RunOptions

```python
class RunOptions(BaseModel):
    enable_recovery: bool | None = None
    headed: bool = False
    dry_run: bool = False
    max_recovery_attempts: int | None = None
    artifact_retention_seconds: int | None = None
```

### 7.4 AgentRunResult

```python
class AgentRunResult(BaseModel):
    ok: bool
    status: Literal["succeeded", "failed", "recovered", "degraded"]

    output: dict[str, Any] | None = None
    failure: "AgentFailure" | None = None

    recipe_id: int | None = None
    recipe_version: int | None = None
    artifact_refs: list[str] = []
    metadata: dict[str, Any] = {}
```

---

## 8. Recipe 模型

核心中的自动化定义统一叫 `AutomationRecipe`。

```python
class AutomationRecipe(BaseModel):
    id: int | None = None
    namespace: str
    key: str
    version: int = 1
    status: Literal["active", "degraded", "disabled"] = "active"

    entrypoint: "EntrypointSpec"
    steps: list["ActionStep"] = []
    observations: dict[str, "ObservationSpec"] = {}
    assertions: list["AssertionSpec"] = []

    recovery_policy: "RecoveryPolicy" = RecoveryPolicy()
    security_policy: "SecurityPolicy" = SecurityPolicy()

    metadata: dict[str, Any] = {}
```

---

## 9. Entrypoint

```python
class EntrypointSpec(BaseModel):
    method: Literal["browser"] = "browser"
    url_template: str
```

渲染规则：

```text
url_template + input_data + context → rendered_url
```

安全要求：

1. 渲染后的 URL 必须通过 allowed origins 校验。
2. 禁止 Recovery Proposal 修改 entrypoint，除非 recipe policy 显式允许。
3. 默认不允许模型生成新的入口地址。

---

## 10. Action Step

```python
class ActionStep(BaseModel):
    name: str
    action: Literal[
        "goto",
        "wait_visible",
        "click",
        "fill",
        "select",
        "wait_url_not_contains",
        "wait_network_idle",
        "evaluate_readonly",
    ]

    target: "LocatorSpec | None" = None
    value_template: str | None = None
    timeout_ms: int = 30000
    optional: bool = False
    metadata: dict[str, Any] = {}
```

首版支持：

| action | 说明 |
|---|---|
| goto | 打开 entrypoint 渲染后的 URL |
| wait_visible | 等待元素可见 |
| click | 点击元素 |
| fill | 输入文本 |
| select | 下拉选择 |
| wait_url_not_contains | 等待 URL 不包含指定片段 |
| wait_network_idle | 等待网络空闲 |
| evaluate_readonly | 只读 JS 观测，不允许副作用 |

Action 必须由 Recipe 定义，不允许模型自由新增高风险 action。

---

## 11. LocatorSpec

```python
class LocatorSpec(BaseModel):
    type: Literal["css", "xpath", "text", "role"]
    value: str
```

限制：

1. 单条 locator 最大长度 500。
2. 单个 observation 最多 5 个候选 locator。
3. 不允许 locator 中包含可执行脚本。
4. 不允许模型返回 JavaScript。
5. XPath 只作为 CSS 不稳定时的 fallback。

---

## 12. Observation

Observation 是通用“读取目标”。

```python
class ObservationSpec(BaseModel):
    kind: Literal["scalar", "list", "object", "table"]

    locators: list[LocatorSpec] = []
    source: Literal["inner_text", "text_content", "attribute", "dataset"] = "inner_text"
    attribute: str | None = None

    parser: str = "text"
    required: bool = False

    children: dict[str, "ObservationSpec"] | None = None
    metadata: dict[str, Any] = {}
```

支持类型：

| kind | 用途 |
|---|---|
| scalar | 单值读取 |
| list | 列表读取 |
| object | 对象结构读取 |
| table | 表格读取 |

Parser 由 core 内置和业务注册共同组成。

内置 parser：

```text
text
number
integer
boolean
date
datetime
json
url
```

业务可注册：

```python
class ValueParserRegistry:
    def register(self, name: str, parser: Callable[[Any], Any]) -> None:
        ...
```

---

## 13. Assertion

Assertion 是通用校验规则。

```python
class AssertionSpec(BaseModel):
    name: str
    type: Literal[
        "required",
        "range",
        "regex",
        "equals",
        "not_equals",
        "contains",
        "not_contains",
        "url_origin_allowed",
        "url_not_contains",
        "schema",
        "custom",
    ]
    target: str | None = None
    params: dict[str, Any] = {}
    recoverable: bool = True
```

内置 assertion：

| type | 说明 |
|---|---|
| required | 目标值不能为空 |
| range | 数值范围 |
| regex | 正则匹配 |
| equals | 等于 |
| not_equals | 不等于 |
| contains | 包含 |
| not_contains | 不包含 |
| url_origin_allowed | URL origin 必须在 allowlist |
| url_not_contains | URL 不包含指定片段 |
| schema | 输出结构满足 schema |
| custom | 调用业务注册 validator |

---

## 14. BrowserDriver 抽象

### 14.1 接口

```python
class BrowserDriver(Protocol):
    def open(self, url: str | None = None, headed: bool = False) -> None: ...
    def goto(self, url: str) -> None: ...
    def click(self, locator: LocatorSpec) -> None: ...
    def fill(self, locator: LocatorSpec, value: str) -> None: ...
    def select(self, locator: LocatorSpec, value: str) -> None: ...
    def wait_visible(self, locator: LocatorSpec, timeout_ms: int) -> None: ...
    def eval_json(self, js_func: str) -> dict[str, Any]: ...
    def screenshot(self, path: Path, region: "RegionSpec | None" = None) -> Path: ...
    def snapshot(self, path: Path) -> Path: ...
    def state_load(self, path: Path) -> None: ...
    def state_save(self, path: Path) -> None: ...
    def current_url(self) -> str: ...
    def close(self) -> None: ...
```

### 14.2 首版实现

当前仓库已依赖 Python `playwright` 并通过 `scripts/douyin_bootstrap_login.py` 使用同步 Playwright。首版实现应优先复用 Python Playwright；若后续选择 CLI 路线，需要同步新增 Node CLI 依赖、Docker 安装步骤和测试。

```text
PlaywrightPythonDriver
```

后续可增加：

```text
PlaywrightCLIDriver
RemoteBrowserDriver
MockBrowserDriver
```

核心执行层只依赖 `BrowserDriver` 协议。

---

## 15. FlowExecutor

```python
class FlowExecutor:
    def execute(
        self,
        driver: BrowserDriver,
        recipe: AutomationRecipe,
        context: ExecutionContext,
        input_data: dict[str, Any],
    ) -> ExecutionAttempt:
        ...
```

执行流程：

```text
1. 渲染 entrypoint URL
2. 校验 URL 安全策略
3. driver.goto(rendered_url)
4. 执行 steps
5. 读取 observations
6. 解析 values
7. 执行 assertions
8. 返回 ExecutionAttempt
```

### 15.1 ExecutionAttempt

```python
class ExecutionAttempt(BaseModel):
    ok: bool
    output: dict[str, Any] = {}

    failed_targets: list[str] = []
    failure_type: "FailureType | None" = None
    failure_reasons: list[str] = []

    current_url: str | None = None
    artifact_refs: list[str] = []
    metadata: dict[str, Any] = {}
```

---

## 16. FailureClassifier

通用失败类型：

```python
class FailureType(str, Enum):
    LOCATOR_RESOLUTION_FAILED = "locator_resolution_failed"
    VALUE_PARSE_FAILED = "value_parse_failed"
    ASSERTION_FAILED = "assertion_failed"

    AUTH_REQUIRED = "auth_required"
    ACCESS_DENIED = "access_denied"
    SUBJECT_CONTEXT_MISMATCH = "subject_context_mismatch"

    EMPTY_RESULT = "empty_result"
    RESULT_NOT_READY = "result_not_ready"

    NAVIGATION_FAILED = "navigation_failed"
    BROWSER_ERROR = "browser_error"
    SECURITY_VIOLATION = "security_violation"

    MODEL_ERROR = "model_error"
    PROPOSAL_INVALID = "proposal_invalid"
    REPLAY_FAILED = "replay_failed"

    UNKNOWN = "unknown"
```

默认可恢复类型：

```python
DEFAULT_RECOVERABLE_FAILURE_TYPES = {
    FailureType.LOCATOR_RESOLUTION_FAILED,
    FailureType.VALUE_PARSE_FAILED,
}
```

不可恢复类型：

```text
AUTH_REQUIRED
ACCESS_DENIED
SUBJECT_CONTEXT_MISMATCH
SECURITY_VIOLATION
```

这些应交给业务层或上层登录态/circuit 处理，不进入模型自愈。

---

## 17. RecoveryPolicy

```python
class RecoveryPolicy(BaseModel):
    enabled: bool = False

    recoverable_failure_types: list[FailureType] = [
        FailureType.LOCATOR_RESOLUTION_FAILED,
        FailureType.VALUE_PARSE_FAILED,
    ]

    max_attempts: int = 3
    confidence_threshold: float = 0.7

    allow_observation_patch: bool = True
    allow_step_patch: bool = False
    allow_entrypoint_patch: bool = False
    allow_assertion_patch: bool = False

    require_replay_success: bool = True
```

首版建议：

```text
只允许 patch observation locator
不允许 patch steps
不允许 patch entrypoint
不允许 patch assertions
```

---

## 18. RecoveryPlanner

```python
class RecoveryPlanner:
    def recover(
        self,
        driver: BrowserDriver,
        recipe: AutomationRecipe,
        failure: AgentFailure,
        context: ExecutionContext,
        input_data: dict[str, Any],
    ) -> RecoveryProposal:
        ...
```

流程：

```text
1. 判断 failure 是否可恢复
2. 捕获 artifacts
3. 脱敏 artifacts
4. 构造 RecoveryRequest
5. 调用 RecoveryModel
6. 解析 RecoveryProposal
7. 返回 proposal
```

---

## 19. RecoveryModel 抽象

核心只定义协议：

```python
class RecoveryModel(Protocol):
    def propose_recovery(
        self,
        request: RecoveryRequest,
    ) -> RecoveryProposal:
        ...
```

Qwen 只是候选实现之一。当前仓库没有 Qwen 专用客户端，现有 `LLMDashboardAgent` 只按 `llm_provider` 走通用 provider 请求。

```python
class QwenMultimodalRecoveryModel(RecoveryModel):
    ...
```

配置上可以使用：

```python
class AgentModelSettings(BaseModel):
    provider: Literal["openai_compatible", "qwen", "mock"] = "openai_compatible"
    model: str = ""
    endpoint: str = ""
    api_key: str = ""
    timeout_seconds: int = 120
    max_retries: int = 3
```

---

## 20. RecoveryRequest

```python
class RecoveryRequest(BaseModel):
    recipe_id: int
    recipe_namespace: str
    recipe_key: str
    recipe_version: int

    failure_type: FailureType
    failed_targets: list[str]
    failure_reasons: list[str]

    page_url: str
    rendered_entrypoint_url: str

    recipe_excerpt: dict[str, Any]
    observation_specs: dict[str, Any]
    assertion_specs: list[dict[str, Any]]

    snapshot_markdown: str | None = None
    dom_excerpt: str | None = None
    screenshot_ref: str | None = None

    security_policy: dict[str, Any]
    recovery_policy: dict[str, Any]
```

---

## 21. 多模态 RecoveryModel 输入

多模态模型可作为 RecoveryModel 使用，但不污染核心命名。Qwen 3.6 Plus 只是候选模型；是否采用取决于后续配置、供应商和脱敏策略落地。

输入材料：

```text
1. 已脱敏的局部截图或遮罩截图
2. accessibility snapshot
3. failed target 附近 DOM excerpt
4. 当前页面 URL
5. 当前 recipe 片段
6. 失败原因
7. 允许 patch 的范围
8. 输出 JSON schema
```

系统提示词核心约束：

```text
你是一个通用网页自动化 Recipe 修复器。
你只能生成结构化 RecoveryProposal。
你不能生成 JavaScript。
你不能修改业务目标。
你不能修改 entrypoint、steps、assertions，除非 policy 显式允许。
你只能修复 failed_targets 中允许的 observation locator。
输出必须是合法 JSON。
```

---

## 22. RecoveryProposal

```python
class RecoveryProposal(BaseModel):
    recipe_id: int
    base_version: int

    patches: list["RecipePatch"]

    confidence: float
    change_summary: str
    reasoning_summary: str | None = None
    metadata: dict[str, Any] = {}
```

### 22.1 RecipePatch

```python
class RecipePatch(BaseModel):
    op: Literal[
        "replace_observation_locator",
        "append_observation_locator",
        "replace_step_locator",
        "replace_observation_parser",
    ]
    path: str
    value: Any
    confidence: float
```

示例：

```json
{
  "recipe_id": 12,
  "base_version": 3,
  "patches": [
    {
      "op": "replace_observation_locator",
      "path": "observations.total.locators",
      "value": [
        {
          "type": "css",
          "value": ".summary-card .main-value"
        }
      ],
      "confidence": 0.86
    }
  ],
  "confidence": 0.86,
  "change_summary": "Updated locator for observation total"
}
```

---

## 23. ProposalValidator

Proposal 必须经过本地验证后才能写入数据库。

```python
class ProposalValidator:
    def validate(
        self,
        proposal: RecoveryProposal,
        recipe: AutomationRecipe,
        failure: AgentFailure,
    ) -> CandidateRecipe:
        ...
```

校验规则：

1. `base_version == recipe.version`。
2. `confidence >= confidence_threshold`。
3. patch 只能作用于 policy 允许的区域。
4. patch target 必须属于 failed_targets。
5. locator 长度与数量满足限制。
6. 不允许出现 JavaScript。
7. 不允许扩大 allowed origins。
8. 不允许新增高风险 action。
9. candidate recipe 必须通过 schema validation。

---

## 24. ReplayRunner

自愈不是“模型说可以就可以”，必须重放验证。

```python
class ReplayRunner:
    def replay(
        self,
        driver: BrowserDriver,
        candidate_recipe: AutomationRecipe,
        context: ExecutionContext,
        input_data: dict[str, Any],
    ) -> ExecutionAttempt:
        ...
```

通过条件：

```text
1. failed_targets 全部恢复
2. 原本成功的 observation 不退化
3. assertions 全部通过
4. URL 未违反 security policy
5. 页面状态未进入 auth/access denied
```

只有 replay 成功，才调用：

```python
RecipeStore.update_recipe(...)
```

---

## 25. RecipeStore

### 25.1 接口

```python
class RecipeStore:
    def get_active(
        self,
        namespace: str,
        key: str,
    ) -> AutomationRecipe | None:
        ...

    def bootstrap(
        self,
        recipe_data: dict[str, Any],
    ) -> AutomationRecipe:
        ...

    def update_recipe(
        self,
        recipe_id: int,
        expected_version: int,
        candidate: AutomationRecipe,
        trigger_reason: str,
    ) -> AutomationRecipe | None:
        ...

    def mark_degraded(
        self,
        recipe_id: int,
        expected_version: int,
        reason: str,
    ) -> bool:
        ...
```

### 25.2 更新事务

```text
1. SELECT recipe FOR UPDATE
2. 校验 expected_version
3. 写 agent_recipe_revisions
4. 更新 agent_recipes
5. version + 1
6. commit
```

版本冲突时返回 `None`，调用方重新读取 active recipe，不覆盖他人自愈结果。

---

## 26. 目标数据库表设计

以下表当前仓库尚不存在。当前已落地的规则表是 `scraping_rules`，并通过 `ScrapingRule.extra_config` 承载扩展配置。是否新增独立 `agent_*` 表，应在首个业务 adapter 落地后根据复用、回滚、审计需求决定。

### 26.1 agent_recipes

```python
class AgentRecipe(SQLModel, table=True):
    __tablename__ = "agent_recipes"

    id: int | None = Field(default=None, primary_key=True)

    namespace: str = Field(index=True, max_length=100)
    key: str = Field(index=True, max_length=200)
    version: int = Field(default=1)
    status: str = Field(default="active")

    entrypoint: dict = Field(sa_type=JSON)
    steps: list[dict] = Field(sa_type=JSON)
    observations: dict = Field(sa_type=JSON)
    assertions: list[dict] = Field(sa_type=JSON)

    recovery_policy: dict = Field(sa_type=JSON)
    security_policy: dict = Field(sa_type=JSON)
    metadata: dict = Field(default_factory=dict, sa_type=JSON)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

唯一约束：

```text
(namespace, key)
```

### 26.2 agent_recipe_revisions

```python
class AgentRecipeRevision(SQLModel, table=True):
    __tablename__ = "agent_recipe_revisions"

    id: int | None = Field(default=None, primary_key=True)
    recipe_id: int = Field(foreign_key="agent_recipes.id", index=True, ondelete="CASCADE")
    version: int

    trigger_reason: str = Field(max_length=500)
    change_summary: str | None = Field(default=None, max_length=2000)

    entrypoint_snapshot: dict = Field(sa_type=JSON)
    steps_snapshot: list[dict] = Field(sa_type=JSON)
    observations_snapshot: dict = Field(sa_type=JSON)
    assertions_snapshot: list[dict] = Field(sa_type=JSON)
    recovery_policy_snapshot: dict = Field(sa_type=JSON)
    security_policy_snapshot: dict = Field(sa_type=JSON)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

唯一约束：

```text
(recipe_id, version)
```

### 26.3 agent_run_logs

```python
class AgentRunLog(SQLModel, table=True):
    __tablename__ = "agent_run_logs"

    id: int | None = Field(default=None, primary_key=True)

    execution_id: str = Field(index=True)
    namespace: str = Field(index=True)
    recipe_key: str = Field(index=True)
    recipe_version: int

    status: str
    failure_type: str | None = None
    failure_reasons: list[str] = Field(default_factory=list, sa_type=JSON)

    input_summary: dict = Field(default_factory=dict, sa_type=JSON)
    output_summary: dict = Field(default_factory=dict, sa_type=JSON)
    artifact_refs: list[str] = Field(default_factory=list, sa_type=JSON)

    started_at: datetime
    finished_at: datetime | None = None
```

### 26.4 agent_artifacts

```python
class AgentArtifact(SQLModel, table=True):
    __tablename__ = "agent_artifacts"

    id: int | None = Field(default=None, primary_key=True)

    execution_id: str = Field(index=True)
    namespace: str = Field(index=True)
    recipe_key: str = Field(index=True)

    artifact_type: str
    storage_path: str
    sanitized: bool = False
    expires_at: datetime | None = None

    metadata: dict = Field(default_factory=dict, sa_type=JSON)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

---

## 27. Session 抽象

核心不使用账号态、店铺态等业务词，统一叫：

```text
principal state
subject state
temporary state
```

### 27.1 SessionScope

```python
class SessionScope(BaseModel):
    namespace: str
    environment: str = "prod"

    principal_ref: str
    subject_ref: str | None = None

    execution_id: str
```

业务 adapter 决定：

```text
principal_ref = 账号 ID
subject_ref = 业务对象 ID
```

核心不理解其语义。

### 27.2 StateMaterializer

```python
class SessionMaterializer:
    def materialize(self, scope: SessionScope) -> Path:
        principal_state = self.state_store.load_principal_state(scope)
        subject_state = self.state_store.load_subject_state(scope)
        merged = self.merge(principal_state, subject_state)
        return self.write_temp_state(scope, merged)

    def persist(self, scope: SessionScope, driver: BrowserDriver) -> None:
        state = driver.export_state()
        self.state_store.save_subject_state(scope, state)
```

合并规则：

```text
principal state 是基础态
subject state 覆盖同名 cookie 和同 origin localStorage
临时 state 只服务本次执行
成功后只回写 subject state
不回写 principal state
```

---

## 28. Artifact 与脱敏

### 28.1 Artifact 类型

```python
class ArtifactType(str, Enum):
    SCREENSHOT = "screenshot"
    SNAPSHOT = "snapshot"
    DOM_EXCERPT = "dom_excerpt"
    MODEL_REQUEST = "model_request"
    MODEL_RESPONSE = "model_response"
```

### 28.2 SecurityPolicy

```python
class SecurityPolicy(BaseModel):
    allowed_origins: list[str] = []

    upload_screenshot: bool = False
    screenshot_mode: Literal[
        "masked_region",
        "full_masked_page",
        "disabled",
    ] = "masked_region"

    snapshot_max_chars: int = 60000
    dom_excerpt_max_chars: int = 20000
    artifact_ttl_seconds: int = 86400

    redaction_rules: list["RedactionRule"] = []
```

### 28.3 RedactionRule

```python
class RedactionRule(BaseModel):
    name: str
    pattern: str
    replacement: str = "[REDACTED]"
```

内置脱敏规则：

```text
phone_number
email
id_card_like
long_numeric_id
token_like
address_like
```

业务可以追加更细规则。

---

## 29. 目标配置设计

以下配置当前仓库尚不存在。当前 `ShopDashboardSettings` 只有 `llm_*`、`browser_*`、登录态和店铺切换相关配置。

### 29.1 AgentCoreSettings

```python
class AgentCoreSettings(BaseModel):
    enabled: bool = False

    browser_driver: Literal["playwright_python", "playwright_cli"] = "playwright_python"
    playwright_cli_path: str = "playwright-cli"
    browser_timeout_seconds: int = 60
    artifact_dir: str = ".runtime/agent_artifacts"
    session_prefix: str = "agent"

    recovery_enabled: bool = False
    recovery_model_provider: str = "qwen"
    recovery_model_name: str = "qwen3.6-plus"
    recovery_model_endpoint: str = ""
    recovery_model_api_key: str = ""
    recovery_model_timeout_seconds: int = 120
    recovery_model_max_retries: int = 3
    recovery_confidence_threshold: float = 0.7

    artifact_ttl_seconds: int = 86400
    snapshot_max_chars: int = 60000
    dom_excerpt_max_chars: int = 20000
    screenshot_mode: Literal[
        "masked_region",
        "full_masked_page",
        "disabled",
    ] = "masked_region"
```

### 29.2 业务配置示例

业务配置不进入 core：

```python
class BusinessAgentSettings(BaseModel):
    use_agent_core: bool = False
    agent_recipe_namespace: str = "business_namespace"
    agent_recipe_key: str = "business_task_key"
```

---

## 30. AgentRuntime 主流程

```python
class AgentRuntime:
    def run(
        self,
        recipe_key: str,
        context: ExecutionContext,
        input_data: dict[str, Any],
        *,
        options: RunOptions | None = None,
    ) -> AgentRunResult:
        recipe = self.recipe_store.get_active(
            namespace=context.recipe_namespace,
            key=recipe_key,
        )
        if recipe is None:
            return AgentRunResult.failed("recipe_not_found")

        scope = self.session_scope_resolver.resolve(context)
        state_file = self.session_materializer.materialize(scope)

        driver = self.driver_factory.create(context)
        driver.open(headed=options.headed if options else False)
        driver.state_load(state_file)

        try:
            attempt = self.executor.execute(
                driver=driver,
                recipe=recipe,
                context=context,
                input_data=input_data,
            )

            if attempt.ok:
                self.session_materializer.persist(scope, driver)
                return AgentRunResult.success(
                    output=attempt.output,
                    recipe=recipe,
                    artifact_refs=attempt.artifact_refs,
                )

            failure = self.failure_classifier.classify(attempt)

            if not self.should_recover(failure, recipe, options):
                return AgentRunResult.failed(
                    failure=failure,
                    recipe=recipe,
                    artifact_refs=attempt.artifact_refs,
                )

            proposal = self.recovery_planner.recover(
                driver=driver,
                recipe=recipe,
                failure=failure,
                context=context,
                input_data=input_data,
            )

            candidate = self.proposal_validator.validate(
                proposal=proposal,
                recipe=recipe,
                failure=failure,
            )

            replay_attempt = self.replay_runner.replay(
                driver=driver,
                candidate_recipe=candidate,
                context=context,
                input_data=input_data,
            )

            if not replay_attempt.ok:
                self.recipe_store.mark_degraded(
                    recipe_id=recipe.id,
                    expected_version=recipe.version,
                    reason="replay_failed_after_recovery",
                )
                return AgentRunResult.failed(
                    failure=self.failure_classifier.classify(replay_attempt),
                    recipe=recipe,
                    artifact_refs=replay_attempt.artifact_refs,
                )

            updated_recipe = self.recipe_store.update_recipe(
                recipe_id=recipe.id,
                expected_version=recipe.version,
                candidate=candidate,
                trigger_reason=failure.type,
            )

            if updated_recipe is None:
                updated_recipe = self.recipe_store.get_active(
                    namespace=context.recipe_namespace,
                    key=recipe_key,
                )

            self.session_materializer.persist(scope, driver)
            return AgentRunResult(
                ok=True,
                status="recovered",
                output=replay_attempt.output,
                recipe_id=updated_recipe.id if updated_recipe else recipe.id,
                recipe_version=updated_recipe.version if updated_recipe else recipe.version,
                artifact_refs=replay_attempt.artifact_refs,
            )

        finally:
            driver.close()
```

---

## 31. 业务接入方式

业务只做 adapter，不改 core。

### 31.1 Business Adapter

```python
class BusinessAgentAdapter:
    def run_business_task(
        self,
        business_runtime: Any,
        business_input: dict[str, Any],
    ) -> dict[str, Any]:
        context = ExecutionContext(
            execution_id=business_runtime.execution_id,
            recipe_namespace="business_namespace",
            recipe_key="business_task_key",
            actor_ref=business_runtime.actor_ref,
            subject_ref=business_runtime.subject_ref,
            tenant_ref=business_runtime.tenant_ref,
        )

        result = self.agent_runtime.run(
            recipe_key="business_task_key",
            context=context,
            input_data=business_input,
        )

        if not result.ok:
            raise self.map_failure(result.failure)

        return self.output_mapper.to_business_payload(result.output)
```

### 31.2 业务 Recipe Seed

```yaml
namespace: business_namespace
key: business_task_key
status: active

entrypoint:
  method: browser
  url_template: "https://example.com/path?date={{ input.date }}"

steps:
  - name: wait_main_panel
    action: wait_visible
    target:
      type: css
      value: ".main-panel"
    timeout_ms: 30000

observations:
  total:
    kind: scalar
    locators:
      - type: css
        value: ".summary-card .total"
    source: inner_text
    parser: number
    required: true

assertions:
  - name: total_required
    type: required
    target: total

  - name: total_range
    type: range
    target: total
    params:
      min: 0
      max: 100

recovery_policy:
  enabled: true
  recoverable_failure_types:
    - locator_resolution_failed
  allow_observation_patch: true
  allow_step_patch: false
  allow_entrypoint_patch: false
  confidence_threshold: 0.7

security_policy:
  allowed_origins:
    - "https://example.com"
  upload_screenshot: true
  screenshot_mode: masked_region
```

---

## 32. 与现有采集模块的关系

当前采集事实：

```text
src/tasks/collection/douyin_shop_dashboard.py
  = 当前主采集任务，先走 HttpScraper，失败后进入 agent fallback

src/scrapers/shop_dashboard/http_scraper.py
  = 当前 HTTP/GraphQL 采集实现

src/agents/llm_dashboard_agent.py
  = 当前 LLM 冷数据/失败补丁实现

src/scrapers/shop_dashboard/session_state_store.py
  = 当前账号 storage_state 文件缓存和店铺 bundle 文件缓存
```

目标方案中，现有采集场景只是第一个业务 adapter。

目标结构：

```text
src/modules/douyin_dashboard/
  agent_adapter.py
  recipe_seed.py
  output_mapper.py
  validators.py
  session_scope_resolver.py
```

采集任务中只调用：

```python
result = business_agent_adapter.collect(...)
```

业务 adapter 负责：

```text
1. 把业务 runtime 转成 ExecutionContext
2. 把日期窗口、筛选条件转成 input_data
3. 把 AgentRunResult.output 转成现有 CollectionResultPersister 接受的 payload
4. 把 AgentFailure 映射成业务异常
5. 维持原有 fallback chain
```

核心不感知采集业务，也不感知业务持久化。

---

## 33. Rollout 计划

### Phase 1 — Core Foundation

新增：

```text
src/core/agent/runtime
src/core/agent/recipe
src/core/agent/browser
src/core/agent/session
src/core/agent/artifacts
src/core/agent/security
```

完成：

```text
1. AutomationRecipe schema
2. RecipeStore
3. RecipeRevision
4. BrowserDriver protocol
5. PlaywrightPythonDriver skeleton
6. SessionMaterializer
7. ArtifactStore
8. AgentCoreSettings
```

不改现网业务行为。

---

### Phase 2 — Deterministic Execution

完成：

```text
1. FlowExecutor
2. ActionRunner
3. ObservationReader
4. ValueParserRegistry
5. AssertionRunner
6. FailureClassifier
7. URL allowlist
8. 只读 eval 模板
```

验收：

```text
1. 不调用模型即可执行 recipe
2. observation 缺失时返回 locator_resolution_failed
3. parser 失败时返回 value_parse_failed
4. assertion 失败时返回 assertion_failed
5. 不会把缺失值静默填成 0 或空结构
```

---

### Phase 3 — Recovery Framework

完成：

```text
1. ArtifactCollector
2. ArtifactSanitizer
3. RecoveryRequestBuilder
4. RecoveryModel protocol
5. 首个 RecoveryModel implementation
6. RecoveryProposal schema
7. ProposalValidator
8. ReplayRunner
9. RecipeStore.update_recipe with expected_version
```

验收：

```text
1. 只有 recoverable failure 才调用模型
2. 模型 proposal 不能越权修改 recipe
3. 低置信 proposal 被拒绝
4. replay 失败不写 recipe
5. version 冲突不覆盖
```

---

### Phase 4 — First Business Adapter

以现有采集模块作为第一个 adapter。

完成：

```text
1. 业务 recipe seed
2. 业务 runtime → ExecutionContext
3. 业务 plan/filter → input_data
4. Agent output → 业务 payload
5. Agent failure → 业务异常
6. fallback chain 灰度
```

核心仍然不出现业务命名。

---

### Phase 5 — Second Business Scenario

必须接入第二个非采集场景验证复用性，例如：

```text
1. 后台表单自动填写
2. 运营页面巡检
3. 广告投放状态检查
4. 客服工单页面读取
5. 内部管理后台状态核验
```

若第二个场景无法复用 80% 以上 core，说明抽象仍需回炉。

---

## 34. 测试计划

以下为目标测试计划，当前仓库尚无 `tests/core/agent` 或 `tests/modules/<business>`。

### 34.1 Core 单元测试

```text
tests/core/agent/test_recipe_models.py
tests/core/agent/test_recipe_store.py
tests/core/agent/test_recipe_revision.py
tests/core/agent/test_browser_driver.py
tests/core/agent/test_flow_executor.py
tests/core/agent/test_action_runner.py
tests/core/agent/test_observation_reader.py
tests/core/agent/test_value_parser.py
tests/core/agent/test_assertion_runner.py
tests/core/agent/test_failure_classifier.py
tests/core/agent/test_session_materializer.py
tests/core/agent/test_artifact_sanitizer.py
tests/core/agent/test_recovery_planner.py
tests/core/agent/test_proposal_validator.py
tests/core/agent/test_replay_runner.py
```

Core 测试中禁止出现具体业务字段名。

### 34.2 Model Adapter 测试

```text
tests/core/agent/test_qwen_multimodal_model.py
```

覆盖：

```text
1. payload 包含 text + image
2. 截图必须来自 sanitized artifact
3. base64 不写日志
4. 非 JSON 输出被拒绝
5. 越权 patch 被拒绝
6. timeout/retry 生效
```

### 34.3 Business Adapter 测试

```text
tests/modules/<business>/test_agent_adapter.py
tests/modules/<business>/test_output_mapper.py
tests/modules/<business>/test_session_scope_resolver.py
tests/modules/<business>/test_recipe_seed.py
```

---

## 35. 安全边界

### 35.1 模型不能做的事

模型不能：

```text
1. 生成 JavaScript
2. 决定业务目标
3. 修改 entrypoint
4. 修改高风险 action
5. 扩大 URL allowlist
6. 读取 cookie/localStorage/sessionStorage
7. 修改 assertion，除非 policy 明确允许
8. 访问外部未授权 origin
9. 生成业务持久化 payload
```

### 35.2 模型可以做的事

模型只能：

```text
1. 根据截图、snapshot、DOM excerpt 生成 locator patch
2. 解释变更摘要
3. 给出置信度
4. 在 policy 允许时修复 observation parser
```

### 35.3 Artifact 安全

```text
1. 默认只上传 masked_region screenshot
2. 全屏截图必须经过像素遮罩
3. snapshot 和 DOM excerpt 必须脱敏
4. cookie/localStorage/sessionStorage 不进入 artifact
5. model request/response 可配置是否保存
6. artifact 按 TTL 清理
```

---

## 36. 迁移边界

### 36.1 目标方案不再新增的采集专用设计

不再新增：

```text
src/extraction/
src/domains/extraction_rule/
extraction_rules
rule_revisions
ExtractionEngine
ExtractionRule
RuleExplorer
```

### 36.2 替换为

以下是目标替换项，当前仓库尚未存在：

```text
src/core/agent/
agent_recipes
agent_recipe_revisions
AgentRuntime
AutomationRecipe
RecoveryPlanner
```

### 36.3 业务侧保留

业务模块可保留：

```text
1. 原有 HTTP fallback
2. 原有登录态管理
3. 原有持久化器
4. 原有任务入口
5. 原有 circuit/lock 逻辑
```

Agent Core 作为新的可选执行 stage 灰度接入。

---

## 37. 关键验收标准

### 37.1 架构验收

```text
1. src/core/agent 下无业务词
2. core 只依赖通用协议和模型
3. 业务 adapter 可替换
4. recipe 可跨业务 namespace 存储
5. recovery proposal 不绑定字段语义
```

### 37.2 执行验收

```text
1. 正常执行 0 token
2. 可恢复失败才调用模型
3. 模型输出必须 replay 成功后写入 recipe
4. 版本冲突不覆盖
5. 不可恢复失败不上交给模型
```

### 37.3 安全验收

```text
1. URL allowlist 生效
2. artifact 脱敏生效
3. 不记录 cookie/localStorage
4. 不允许模型返回 JS
5. 不允许模型越权 patch
```

### 37.4 复用性验收

```text
1. 第一个业务 adapter 成功接入
2. 第二个非采集业务 adapter 成功接入
3. 第二个业务复用 80% 以上 core
4. 新业务只需新增 recipe + adapter + mapper
```

---

## 38. 最终结论

本方案将原本面向单一采集场景的自愈采集模块，重构为平台级通用 Agent 基建框架。

核心思想：

```text
Core 只处理自动化执行的共性问题：
Recipe、Action、Observation、Assertion、Failure、Recovery、Proposal、Replay、Revision。

Business 只处理业务问题：
输入映射、输出映射、业务校验、业务异常、业务 fallback。
```

最终架构：

```text
src/core/agent
  = 通用 Self-Healing Agent Framework

src/modules/<business>
  = Business Adapter + Recipe Seed + Output Mapper
```

这套设计可以从当前采集场景起步，但不会被采集场景锁死，后续可以复用到任何需要“浏览器自动化 + 结构化观测 + 自愈修复”的业务流程中。
