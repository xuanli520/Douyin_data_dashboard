# Shop Dashboard ScrapingRule 全字段任务化实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在既有“按 `filters.shop_id` 拆分任务”基础上，确保 `scraping_rules` 表中所有可配置采集字段都真实参与任务规划与执行，不再出现“字段已存库但采集链路未生效”的配置空转。  
**Architecture:** 建立三层结构：`RuleConfigResolver`（规则字段归一化）-> `CollectionPlanBuilder`（店铺/时间/粒度任务单元生成）-> `TaskExecutor`（按计划执行并回写状态）。调度与手动触发统一走同一解析与计划层，避免入口分叉导致字段失效。  
**Tech Stack:** Python 3.12, FastAPI, SQLModel, Funboost, Redis, pytest

---

## 字段落地矩阵（ScrapingRule）

| 字段 | 当前状态 | 本次落地行为 | 归属模块 |
| --- | --- | --- | --- |
| `target_type` | 部分生效（仅默认组） | 参与 API 组解析与任务标签 | `runtime.py` |
| `granularity` | 仅 `DAY` 可用 | 任务计划支持 `HOUR/DAY/WEEK/MONTH` 切片 | `shop_dashboard_plan_builder.py` |
| `timezone` | 未生效 | 作为时间基准计算 `metric_date/window` | `shop_dashboard_plan_builder.py` |
| `time_range` | 部分生效 | 作为显式时间窗口覆盖增量策略 | `shop_dashboard_plan_builder.py` |
| `schedule` | 已用于 cron | 调度统一读取并附带 rule timezone | `beat.py` |
| `incremental_mode` | 部分生效 | `BY_DATE/BY_CURSOR` 分支规划任务 | `shop_dashboard_plan_builder.py` |
| `backfill_last_n_days` | 部分生效 | 参与增量窗口与计划单元数 | `shop_dashboard_plan_builder.py` |
| `filters` | 大部分未生效 | 统一解析：`shop_id` 拆分 + 查询过滤条件 | `rule_config_resolver.py` + `query_builder.py` |
| `dimensions` | 未生效 | 注入查询上下文与结果维度标签 | `query_builder.py` |
| `metrics` | 部分生效（仅选组） | 同时参与 API 组选取与字段裁剪 | `runtime.py` + `query_builder.py` |
| `dedupe_key` | 已生效 | 扩展支持粒度窗口变量（hour/week/month） | `douyin_shop_dashboard.py` |
| `rate_limit` | 未实际执行 | 解析为限流策略，控制任务单元执行速率 | `douyin_shop_dashboard.py` |
| `data_latency` | 部分生效 | 与 timezone 联动计算 base time | `shop_dashboard_plan_builder.py` |
| `top_n` | 未生效 | 注入查询参数并影响返回裁剪 | `query_builder.py` |
| `sort_by` | 未生效 | 注入查询排序参数 | `query_builder.py` |
| `include_long_tail` | 未生效 | 注入查询开关与结果裁剪逻辑 | `query_builder.py` |
| `session_level` | 未生效 | 注入会话级查询参数 | `query_builder.py` |
| `extra_config` | 部分生效 | 作为高级覆盖层（fallback/graphql/common_query/token_keys 等） | `runtime.py` |
| `last_executed_at`/`last_execution_id` | 已更新 | 更新时补充 plan 摘要（店铺数/单元数） | `data_source/services.py` |

---

## 模块拆分

| 模块 | 职责 | 输入 | 输出 |
| --- | --- | --- | --- |
| `src/scrapers/shop_dashboard/rule_config_resolver.py` | 规则字段全量归一化与优先级合并 | `DataSource`, `ScrapingRule`, task payload overrides | `ResolvedRuleConfig` |
| `src/tasks/collection/shop_dashboard_plan_builder.py` | 按店铺+时间粒度生成可执行计划单元 | `ResolvedRuleConfig` | `list[CollectionPlanUnit]` |
| `src/scrapers/shop_dashboard/query_builder.py` | 把 filters/dimensions/top_n/sort 等转为请求上下文 | `ResolvedRuleConfig`, `CollectionPlanUnit` | `EndpointQueryContext` |
| `src/tasks/collection/douyin_shop_dashboard.py` | 执行计划单元、幂等、锁、持久化、汇总 | runtime/query context | 任务执行结果 |
| `src/domains/task/services.py` | 透传全字段覆盖参数 | Task payload | funboost push kwargs |
| `src/tasks/beat.py` | schedule + timezone 调度注册 | rule schedule config | APS jobs |

---

### Task 1: 建立“全字段有效性”回归基线（先失败）

**Files:**
- Create: `tests/scrapers/shop_dashboard/test_rule_config_resolver.py`
- Create: `tests/tasks/test_shop_dashboard_plan_builder.py`
- Create: `tests/scrapers/shop_dashboard/test_query_builder.py`
- Modify: `tests/tasks/test_shop_dashboard_collection.py`
- Modify: `tests/domains/task/test_task_dispatch.py`
- Modify: `tests/tasks/test_shop_dashboard_beat.py`

**Step 1: 写 resolver 失败用例**

- 覆盖 `filters.shop_id`（list/string）、`timezone`、`granularity`、`rate_limit`、`top_n/sort_by/include_long_tail/session_level` 的解析结果。
- 覆盖字段优先级：`payload overrides > rule fields > rule.extra_config > data_source`。

**Step 2: 写 plan builder 失败用例**

- `HOUR/DAY/WEEK/MONTH` 生成计划单元。
- `time_range` 覆盖增量。
- `BY_CURSOR` 从 `filters/extra_config` 读取 cursor。

**Step 3: 写 query builder 失败用例**

- 校验 `filters/dimensions/metrics/top_n/sort_by/include_long_tail/session_level` 进入请求上下文。

**Step 4: 写任务链路失败用例**

- `sync_shop_dashboard` 结果数量 = `shop_count * window_count`。
- `TaskService._dispatch_task` 透传全字段覆盖参数。
- `beat` 注册带 rule timezone。

**Step 5: 运行失败用例**

Run: `uv run --frozen pytest tests/scrapers/shop_dashboard/test_rule_config_resolver.py tests/tasks/test_shop_dashboard_plan_builder.py tests/scrapers/shop_dashboard/test_query_builder.py tests/tasks/test_shop_dashboard_collection.py tests/domains/task/test_task_dispatch.py tests/tasks/test_shop_dashboard_beat.py -v`  
Expected: FAIL

**Step 6: Commit**

```bash
git add tests/scrapers/shop_dashboard/test_rule_config_resolver.py tests/tasks/test_shop_dashboard_plan_builder.py tests/scrapers/shop_dashboard/test_query_builder.py tests/tasks/test_shop_dashboard_collection.py tests/domains/task/test_task_dispatch.py tests/tasks/test_shop_dashboard_beat.py
git commit -m "test: add full scraping-rule field coverage regressions"
```

---

### Task 2: 实现 RuleConfigResolver（字段归一化核心）

**Files:**
- Create: `src/scrapers/shop_dashboard/rule_config_resolver.py`
- Modify: `src/scrapers/shop_dashboard/runtime.py`
- Modify: `tests/scrapers/shop_dashboard/test_runtime_account_key.py`
- Modify: `tests/scrapers/shop_dashboard/test_rule_config_resolver.py`

**Step 1: 定义 `ResolvedRuleConfig`**

- 包含 `ScrapingRule` 全部配置字段（含 `timezone/schedule/sort_by` 当前 runtime 缺失字段）。
- 包含派生字段：`shop_ids`, `api_groups`, `rate_limit_policy`, `fallback_chain`。

**Step 2: 实现字段解析与校验**

- 统一标准化：字符串 trim、空值处理、数组去重、枚举 fallback。
- 对无效值给出 fail-fast 异常（带 rule_id + 字段名）。

**Step 3: 提供运行时桥接函数**

- `build_runtime_config()` 保留兼容。
- 新增 `build_runtime_configs()`：输入一条 rule，输出多店 runtime。

**Step 4: 运行单测**

Run: `uv run --frozen pytest tests/scrapers/shop_dashboard/test_rule_config_resolver.py tests/scrapers/shop_dashboard/test_runtime_account_key.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add src/scrapers/shop_dashboard/rule_config_resolver.py src/scrapers/shop_dashboard/runtime.py tests/scrapers/shop_dashboard/test_rule_config_resolver.py tests/scrapers/shop_dashboard/test_runtime_account_key.py
git commit -m "feat: introduce full-field scraping rule resolver"
```

---

### Task 3: 实现 CollectionPlanBuilder（任务单元规划）

**Files:**
- Create: `src/tasks/collection/shop_dashboard_plan_builder.py`
- Modify: `src/tasks/collection/douyin_shop_dashboard.py`
- Modify: `tests/tasks/test_shop_dashboard_plan_builder.py`
- Modify: `tests/tasks/test_shop_dashboard_collection.py`

**Step 1: 定义 `CollectionPlanUnit`**

- 字段：`shop_id`, `window_start`, `window_end`, `metric_date`, `granularity`, `cursor`, `plan_index`。

**Step 2: 实现时间窗口生成**

- `timezone + data_latency + incremental_mode + backfill_last_n_days + time_range` 统一生成窗口。
- `HOUR/DAY/WEEK/MONTH` 都能生成稳定窗口。

**Step 3: 实现店铺 fanout**

- 计划单元为笛卡尔积：`shop_ids x time_windows`。

**Step 4: 接入 `sync_shop_dashboard`**

- 用 plan units 替换“单 runtime + 日期循环”。
- 返回 `shop_count/planned_units/completed_units/failed_units`。

**Step 5: 运行单测**

Run: `uv run --frozen pytest tests/tasks/test_shop_dashboard_plan_builder.py tests/tasks/test_shop_dashboard_collection.py -v`  
Expected: PASS

**Step 6: Commit**

```bash
git add src/tasks/collection/shop_dashboard_plan_builder.py src/tasks/collection/douyin_shop_dashboard.py tests/tasks/test_shop_dashboard_plan_builder.py tests/tasks/test_shop_dashboard_collection.py
git commit -m "feat: build collection plan units from full rule config"
```

---

### Task 4: 实现 QueryBuilder（让 filters/dimensions 等真正入请求）

**Files:**
- Create: `src/scrapers/shop_dashboard/query_builder.py`
- Modify: `src/scrapers/shop_dashboard/http_scraper.py`
- Modify: `tests/scrapers/shop_dashboard/test_query_builder.py`
- Modify: `tests/scrapers/shop_dashboard/test_http_scraper.py`

**Step 1: 构建 endpoint 查询上下文**

- 输出：`params`, `json_body`, `graphql_variables`。
- 解析字段：`filters`, `dimensions`, `metrics`, `top_n`, `sort_by`, `include_long_tail`, `session_level`。

**Step 2: 接入 HTTP 抓取流程**

- 每个 API group 请求前从 QueryBuilder 取上下文并合并默认参数。

**Step 3: 处理未知过滤字段**

- 记录可观测 warning，不中断采集。

**Step 4: 运行单测**

Run: `uv run --frozen pytest tests/scrapers/shop_dashboard/test_query_builder.py tests/scrapers/shop_dashboard/test_http_scraper.py -k "filters or dimensions or top_n or sort" -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add src/scrapers/shop_dashboard/query_builder.py src/scrapers/shop_dashboard/http_scraper.py tests/scrapers/shop_dashboard/test_query_builder.py tests/scrapers/shop_dashboard/test_http_scraper.py
git commit -m "feat: apply rule filters and dimensions into scraper requests"
```

---

### Task 5: 任务分发层支持全字段覆盖参数

**Files:**
- Modify: `src/domains/task/services.py`
- Modify: `src/domains/task/schemas.py`
- Modify: `tests/domains/task/test_task_dispatch.py`
- Modify: `tests/api/test_task_management_api.py`

**Step 1: 扩展 payload 合法键集合**

- 为 `SHOP_DASHBOARD_COLLECTION` 允许覆盖字段：
- `shop_id/shop_ids/granularity/timezone/time_range/incremental_mode/backfill_last_n_days/data_latency/filters/dimensions/metrics/dedupe_key/rate_limit/top_n/sort_by/include_long_tail/session_level/extra_config`。

**Step 2: 分发层透传覆盖参数**

- `_dispatch_task()` 将上述字段透传到 `sync_shop_dashboard.push()`。

**Step 3: API 层回归**

- `POST /tasks/{id}/run` 传覆盖字段，断言执行 payload 保存成功并被分发消费。

**Step 4: 运行单测**

Run: `uv run --frozen pytest tests/domains/task/test_task_dispatch.py tests/api/test_task_management_api.py -k "shop_dashboard or payload" -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add src/domains/task/services.py src/domains/task/schemas.py tests/domains/task/test_task_dispatch.py tests/api/test_task_management_api.py
git commit -m "feat: support full rule field overrides in task dispatch"
```

---

### Task 6: 调度层补齐 schedule + timezone 语义

**Files:**
- Modify: `src/tasks/beat.py`
- Modify: `tests/tasks/test_shop_dashboard_beat.py`

**Step 1: 读取 rule timezone 注册定时任务**

- APS job 注册时附带 rule timezone。

**Step 2: 调度 payload 对齐执行层**

- cron payload 中补充必要字段快照（至少 `granularity/timezone/incremental_mode/data_latency`）。

**Step 3: 运行单测**

Run: `uv run --frozen pytest tests/tasks/test_shop_dashboard_beat.py -v`  
Expected: PASS

**Step 4: Commit**

```bash
git add src/tasks/beat.py tests/tasks/test_shop_dashboard_beat.py
git commit -m "feat: apply rule timezone and config snapshot in scheduler jobs"
```

---

### Task 7: 执行期限流与幂等键扩展

**Files:**
- Modify: `src/tasks/collection/douyin_shop_dashboard.py`
- Modify: `tests/tasks/test_shop_dashboard_collection_task.py`
- Modify: `tests/tasks/test_idempotency.py`

**Step 1: 实现 `rate_limit` 执行策略**

- 支持 `int`（QPS）与 `dict`（qps/burst/concurrency）两类配置。
- 在 plan unit 执行前做节流。

**Step 2: 扩展 dedupe key 变量**

- 支持 `{granularity}`, `{window_start}`, `{window_end}`, `{shop_id}`, `{rule_id}`, `{execution_id}`。

**Step 3: 运行单测**

Run: `uv run --frozen pytest tests/tasks/test_shop_dashboard_collection_task.py tests/tasks/test_idempotency.py -k "rate_limit or dedupe" -v`  
Expected: PASS

**Step 4: Commit**

```bash
git add src/tasks/collection/douyin_shop_dashboard.py tests/tasks/test_shop_dashboard_collection_task.py tests/tasks/test_idempotency.py
git commit -m "feat: enforce per-rule rate limit and extended dedupe key variables"
```

---

### Task 8: 集成回归与上线验收

**Files:**
- Modify: `tests/integration/test_shop_dashboard_pipeline.py`
- Modify: `tests/integration/test_data_source_service.py`
- Modify: `docs/plans/2026-03-09-shop-dashboard-shop-id-task-fanout-plan.md`

**Step 1: 全字段场景集成用例**

- 构造一条 rule，填充 `timezone/granularity/incremental_mode/backfill/data_latency/filters/dimensions/metrics/rate_limit/top_n/sort_by/include_long_tail/session_level/dedupe_key/extra_config`。
- 断言执行链路每个关键字段都进入计划或查询上下文。

**Step 2: 多店真实问题场景回归**

- `rule.id=8` 同类配置：`data_source.shop_id=None + filters.shop_id[13个]`。
- 断言计划单元 >= 13（按窗口扩大）。

**Step 3: 运行回归**

Run: `uv run --frozen pytest tests/integration/test_shop_dashboard_pipeline.py tests/integration/test_data_source_service.py -k "shop_id or rule config or pipeline" -v`  
Expected: PASS

**Step 4: 全量检查**

Run: `just check`  
Expected: PASS

**Step 5: Commit**

```bash
git add tests/integration/test_shop_dashboard_pipeline.py tests/integration/test_data_source_service.py docs/plans/2026-03-09-shop-dashboard-shop-id-task-fanout-plan.md
git commit -m "test: validate full scraping-rule field support end-to-end"
```

---

## Execution Status

- [x] Task 1
- [x] Task 2
- [x] Task 3
- [x] Task 4
- [x] Task 5
- [x] Task 6
- [x] Task 7
- [x] Task 8
