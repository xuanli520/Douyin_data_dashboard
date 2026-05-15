# ReAct Agent 爬取框架设计方案

## 文档状态与当前代码事实

本文是目标方案，不是当前实现说明。

当前仓库事实：

1. 当前采集主链路是 `browser_agent`。`sync_shop_dashboard` 不再执行旧 HTTP/LLM fallback。
2. 当前已有 `src/core/agent`、`AgentCrawler`、`PlaywrightCLIDriver`、`browser_agent` stage、`agent_recipes` 表和 WebSocket 观察入口。
3. 当前规则解析可通过 `ScrapingRule.extra_config.agent_recipe` 引用 recipe。
4. 当前 Playwright 能力来自 Node `@playwright/cli` / `playwright-cli`；Docker 已安装 CLI 浏览器。
5. 当前登录 `storage_state` 存在 `DataSource.extra_config.shop_dashboard_login_state`，执行期会物化到本地；店铺 bundle 不是完整 Playwright state。
6. 当前模型配置是通用 `llm_provider` / `llm_endpoint` / `llm_model`，没有 Qwen 专用配置类或 DashScope 客户端。

## 背景

当前 HTTP Scraper 仍是主采集链路，但它依赖抖店内部 HTTP/GraphQL 端点，长期维护成本高。项目仍处于开发阶段，不需要为线上兼容保留旧链路；目标方案是直接删除 HTTP scraper 链路，引入浏览器自动化 + Tool-Based ReAct 范式，并形成 `src/core/agent` 内核。核心命名、数据模型、流程编排、异常类型、存储结构均不得绑定具体业务。

---

## 核心设计决策

| 决策 | 方案 |
|---|---|
| **探索方式** | 每次 Discovery 全新开始，无记忆 |
| **Recipe 生成** | 目标态：Agent 完成探索后，将完整轨迹发给 LLM 总结生成完整 Recipe |
| **Recovery** | 简化版，模型一次性给出 patch，不循环 |
| **多模态模型** | 候选：`qwen3.6-plus` / openai-compatible / mock。当前仓库尚无 Qwen 专用实现 |
| **Act 方式** | Tool-Based，Agent 调用预定义工具，服务端执行 |
| **安全策略** | 白名单工具，危险操作过滤 |
| **观察同步** | 目标态：管理员看截图，Agent 看截图 + Playwright snapshot YAML。当前仓库尚无 WebSocket 观察同步 |

---

## 架构分层

以下是目标架构，当前仓库尚未落地 `ReActDiscoveryAgent`、`AgentCrawler` 或 `agent_recipes`。

```
用户层：管理员声明目标（自然语言 + 入口 URL）
  │
  ▼
ReAct Discovery Agent（首次/按需：生成 Recipe）
  │
  ▼
Recipe Store（持久化：agent_recipes 表）
  │
  ▼
AgentCrawler（日常执行：确定性执行 Recipe）
  │
  ▼
Recovery（失败时：模型一次性修复 locator）
  │
  ▼
业务层：output_mapper → 持久化
```

---

## ReAct Discovery 循环

```
INIT: 加载登录态 → 导航到入口 URL → 截图 + snapshot
  │
  ▼
OBSERVE: 管理员看到截图，Agent 看到截图 + snapshot YAML
  │
  ▼
THINK: Agent 分析当前状态，决定下一步
  │
  ▼
ACT: Agent 调用预定义工具（不是输出 JSON）
  │
  ▼
TOOL EXECUTE: 工具执行前安全校验（白名单/危险操作/origin）
  │
  ▼
  └─→ 回到 OBSERVE（循环直到 done 或 max_steps）
```

---

## 工具白名单

Agent 只能调用预定义工具，不能执行任意操作。

| 类别 | 工具 | 说明 |
|---|---|---|
| 导航 | `goto`, `back`, `reload` | 页面导航 |
| 交互 | `click`, `fill`, `select` | 元素交互（安全） |
| 滚动 | `scroll_down`, `scroll_up`, `scroll_to_element` | 页面滚动 |
| 等待 | `wait_visible`, `wait_network_idle` | 等待条件 |
| 信息 | `get_current_url`, `get_page_title`, `get_element_text` | 只读信息获取 |
| 提取 | `extract_table`, `extract_list`, `extract_text` | 数据提取（只读） |
| 完成 | `done` | 标记完成，生成 Recipe |

**禁止工具**：`submit_form`, `click_confirm`, `click_delete`, `evaluate`, `download`

---

## 安全校验

以下是目标安全策略，当前仓库尚无 agent 工具白名单、`allowed_origins` 或危险 locator 过滤实现。

```
工具调用前校验：
1. 工具是否在白名单？
2. locator 是否包含危险模式（delete/remove/confirm/submit/javascript/eval）？
3. URL 是否在 allowed_origins 内？
4. 是否进入危险页面（订单确认/退款/结算）？
```

---

## 管理员观察同步

| 内容 | 管理员 | Agent |
|---|---|---|
| 页面截图 | 是 | 是 |
| Playwright snapshot YAML | 否 | 是 |
| 当前 URL | 是 | 是 |
| 页面标题 | 是 | 是 |
| Agent thought | 否 | 是 |
| 选择的工具 | 否 | 是 |
| 工具执行结果 | 否 | 是 |

**目标同步方式**：WebSocket 实时推送。当前仓库只注册普通 HTTP `APIRouter`，尚未实现 WebSocket 入口。

---

## Recipe 生成

Agent 调用 `done` 工具时，将完整探索轨迹发送给 LLM 进行最终总结，生成结构化 Recipe：

```json
{
  "key": "auto_generated_bad_behavior",
  "version": 1,
  "entrypoint": {"url_template": "https://fxg.jinritemai.com/shop/governance/bad-behavior"},
  "steps": [...],
  "observations": {...},
  "assertions": [...]
}
```

---

## Recovery 简化版

```
输入：失败 Recipe + 失败信息 + 截图 + snapshot
  │
  ▼
LLM 一次性分析失败原因
  │
  ▼
输出：修复 patches（仅允许修改 observation locator）
  │
  ▼
本地校验（confidence / 越权检查 / locator 合规）
  │
  ▼
Replay 验证
  │
  ▼
成功 → 更新 Recipe version + 1
失败 → 标记 degraded
```

---

## Playwright CLI Wrapper

实现使用 subprocess 调用 `playwright-cli`，通过进程隔离简化 session 管理。仓库依赖 Node `@playwright/cli`，Docker 执行 `playwright-cli install-browser --with-deps`。

```python
class PlaywrightCLI:
    def open(self, url=None, headed=False): ...
    def close(self): ...
    def goto(self, url): ...
    def click(self, locator): ...
    def fill(self, locator, value): ...
    def screenshot(self, filename) -> Path: ...
    def snapshot(self, filename, max_chars) -> str: ...
    def state_save(self, path): ...
    def state_load(self, path): ...
```

**关键设计**：
- `-s={session}` 保证并发隔离
- `subprocess.run(timeout=...)` 防止 hung
- 截图/snapshot 写入 `.runtime/agent_artifacts`，按 TTL 清理
- 统一抛 `BrowserDriverError`，包含 command/session/stderr

---

## 数据库存储

以下是目标持久化设计，当前仓库没有 `agent_recipes` 模型或迁移。当前可用扩展点是 `ScrapingRule.extra_config`。

### agent_recipes 表

```python
class AgentRecipe(SQLModel, table=True):
    __tablename__ = "agent_recipes"

    id: int | None = Field(default=None, primary_key=True)
    namespace: str = Field(index=True)
    key: str = Field(index=True)
    version: int = Field(default=1)
    status: str = Field(default="active")  # active | degraded | disabled

    entrypoint: dict = Field(sa_type=JSON)
    steps: list[dict] = Field(sa_type=JSON)
    observations: dict = Field(sa_type=JSON)
    assertions: list[dict] = Field(sa_type=JSON)

    recovery_policy: dict = Field(sa_type=JSON)
    security_policy: dict = Field(sa_type=JSON)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

### ScrapingRule 关联

当前 `ScrapingRule.extra_config` 是泛型 JSON，会被 `ScrapingRuleConfigMapper` 平铺回 API 响应的 `config`。因此把 `agent_recipe` 放入 `extra_config` 会成为前后端可见配置，不是私有存储；当前代码也还没有用该结构驱动采集。

```python
class ScrapingRule(SQLModel, ...):
    extra_config: dict | None = Field(default=None, sa_type=JSON)
    # extra_config 中包含：
    # {
    #   "agent_recipe": {"namespace": "...", "key": "..."},
    #   "field_filter": {"include": [...], "exclude": [...]}
    # }
```

---

## 触发方式

| 场景 | 触发方式 |
|---|---|
| Discovery | 管理员通过前端按钮 → API → funboost 异步任务 |
| 日常执行 | 定时任务（现有 funboost 队列） |
| Recovery | 日常执行失败时自动触发 |

---

## 与现有模块的关系

当前真实关系：

| 模块 | 当前状态 |
|---|---|
| `HttpScraper` | 仍是主采集链路 |
| `src/scrapers/shop_dashboard/http_scraper.py` | 仍维护端点规格和 HTTP/GraphQL 请求 |
| `src/scrapers/shop_dashboard/rule_config_resolver.py` | 仍解析 `api_groups`、`fallback_chain`、`common_query`、`token_keys` |
| `src/tasks/collection/douyin_shop_dashboard.py` | 仍按 `http -> agent` 运行，没有 `browser_agent` 分支 |
| `SessionBootstrapper` | 保留，负责店铺切换、bundle 校验与缓存 |
| `CollectionUseCase` | 保留，负责计划拆分、登录态物化、幂等、锁和持久化编排 |

目标关系：

| 模块 | 状态 |
|---|---|
| `HttpScraper` | **删除**，不再作为 fallback 或保留链路 |
| `src/scrapers/shop_dashboard/http_scraper.py` | **删除**；若 `SessionBootstrapper` 仍需 `ENDPOINT_SPECS` / `SHOP_CONTEXT_VERIFY_GROUPS`，先迁到独立 `contracts.py` |
| `src/scrapers/shop_dashboard/parsers.py` | 保留 parser 工具函数，改为从 observation 结果解析 |
| `src/scrapers/shop_dashboard/rule_config_resolver.py` | 移除 `api_groups` 解析，新增 `agent_recipe` 解析 |
| `src/tasks/collection/douyin_shop_dashboard.py` | 移除 HTTP fallback，全部走 `browser_agent` |
| `SessionBootstrapper` | **保留**，继续负责登录态/店铺切换 |
| `CollectionUseCase` | 修改，移除 HTTP scraper 相关逻辑，继续负责业务编排 |

---

## 实施阶段

### Phase 1：Core Skeleton
- 新增 `src/core/agent/` 目录
- 实现 Pydantic 模型（Recipe, Step, Observation, Assertion, Failure）
- 实现 URL allowlist, locator 校验
- 实现 `PlaywrightCLI`

### Phase 2：确定性浏览器执行
- 实现 `AgentCrawler.run()`
- 实现 step 执行, observation 读取, parser, assertion
- 接入业务 `browser_agent`，并删除 HTTP fallback

### Phase 3：ReAct Discovery
- 实现 `ReActDiscoveryAgent`
- 实现 Tool Registry（白名单 + 安全校验）
- 实现管理员观察同步（WebSocket）
- 实现 Recipe 生成（轨迹 → LLM 总结）

### Phase 4：Recovery
- 实现简化版 Recovery（一次性 patch）
- 实现 ProposalValidator
- 实现 ReplayRunner
- 实现 Recipe 版本管理

---

## 关键约束

- **最大步数**：30 步
- **无人工确认**：Agent 自主探索、试错、修正
- **管理员可重试**：删除快照，重新运行，直到满意
- **登录态失效**：抛 `LoginExpiredError`，通知管理员重新上传
- **多店铺切换**：保持现有 `SessionBootstrapper` 逻辑
- **Snapshot 存储**：按 TTL 清理

---

## 模型配置

以下是候选配置，不是当前仓库已有配置。当前仓库只有 `llm_provider`、`llm_endpoint`、`llm_model`、`llm_timeout_seconds`、`llm_retry_times`。

```python
class Qwen36PlusConfig(BaseModel):
    model: str = "qwen3.6-plus"
    endpoint: str = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
    api_key: str = ""
    timeout_seconds: int = 120
    max_retries: int = 3
    max_image_size_mb: int = 10
    image_quality: str = "high"
```

---

## 附录：与三份文档的关系

| 本文档 | 来源 |
|---|---|
| `self-healing-agent-extraction-engine.md` | 业务专用版，绑定抖店采集 |
| `core-self-healing-agent-framework.md` | 通用框架版，过于庞大 |
| `lightweight-core-agent-crawler.md` | 轻量落地版，无 ReAct |
| **本文档** | **MVP 版，Tool-Based ReAct，聚焦实现** |
