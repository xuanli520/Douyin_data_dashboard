# 店铺批量采集与 Agent Recipe 稳定态实施计划

## 目标

批量店铺采集只允许在存在稳定的半自动 Agent Recipe 后执行。首次 Agent Discovery、单店验证、失败后的 Recovery 都必须是单店铺任务，不能进入批量或并行链路。

## 源码调研结论

### 当前批量入口

- 任务入口 `src/tasks/bootstrap.py` 已透传 `shop_id`、`shop_ids`、`all`、`fallback_chain`、`collection_path`、`extra_config`。
- 采集任务 `src/tasks/collection/douyin_shop_dashboard.py` 接收 `shop_ids`、`all`、`fallback_chain`，并把 override 交给 `CollectionUseCase`。
- `src/scrapers/shop_dashboard/shop_selection_validator.py` 会把显式店铺选择规范化：`all=true` 表示全店，`shop_ids` 表示指定批量。
- `src/scrapers/shop_dashboard/rule_config_resolver.py` 将 `all=true` 解析为 `shop_mode=ALL`，将 `shop_ids` 解析为 `shop_mode=EXACT`。
- `src/application/collection/runtime_loader.py` 在 `ALL` 模式下通过 `AccountShopCatalogService.get_shop_catalog()` 解析账号店铺目录。
- `src/application/collection/plan_builder_impl.py` 把店铺与日期窗口展开为 `CollectionPlanUnit`。

### 当前执行模型

- `src/application/collection/usecase.py` 在 `_collect_and_persist()` 中先生成 `plan_units`，再逐个 `for plan_unit in plan_units` 执行。
- 当前采集是多店顺序执行，不是并行执行。
- HTTP bootstrap 的 `src/scrapers/shop_dashboard/session_bootstrapper.py` 支持 `bootstrap_concurrency_limit` 并发，但这只覆盖 HTTP 切店预热，不等于 Agent 并行采集。
- `src/application/collection/browser_agent_adapter.py` 会为每个店铺准备或复用 `playwright_states/{account_id}/{shop_id}.json`，然后运行 `AgentCrawler`。

### 当前 Agent Recipe 生命周期

- `src/domains/agent_recipe/models.py` 只有 `active`、`degraded`、`disabled`。
- `src/domains/agent_recipe/repository.py` 的 `get_active()` 只读取 `active` 版本；`create_next_version()` 会把旧 active 置为 disabled，再创建新 active。
- `src/tasks/collection/douyin_shop_discovery.py` discovery 成功且 replay 通过后直接写入 active recipe。
- 当前没有 `candidate`、`validated`、`stable` 这类能表达“半自动确认后可批量”的状态。

### 当前 Recovery 行为

- `src/application/collection/browser_agent_adapter.py` 在 `collect()` 失败后默认尝试 `_attempt_recovery()`。
- Recovery 成功后会通过 `create_next_version()` 写入新 active recipe，并将本次采集结果标记为 recovered。
- `runtime.extra_config.agent_recovery_enabled=False` 可以关闭 recovery。
- 当前没有批量任务自动禁止 recovery 的逻辑。

## 必须补齐的规则

### 店铺数量判定

统一使用计划生成后的唯一店铺数判定：

- `shop_count = len({unit.shop_id for unit in plan_units})`
- `shop_count == 1` 是单店任务
- `shop_count > 1` 是批量任务

这个判定应放在 `src/application/collection/usecase.py` 的 `_collect_and_persist()` 中，紧跟 `plan_units = self.plan_builder(runtime)` 之后。

### 批量准入规则

批量任务必须同时满足：

- `shop_count > 1`
- collection stage 包含 `browser_agent`
- recipe 引用存在
- recipe 状态是稳定态
- 当前任务不是 discovery
- 当前任务不是 recovery
- 当前任务强制禁用 agent recovery

任一条件不满足时拒绝任务，错误原因使用稳定的机器可读值，例如：

- `agent_recipe_not_stable_for_batch`
- `agent_recipe_missing_for_batch`
- `agent_recovery_disabled_for_batch_required`

### 单店限定规则

以下任务必须 `shop_count == 1`：

- 首次 Agent Discovery
- Discovery 后单店验证
- Recovery 修复
- Recovery 后单店验证
- recipe 状态从 candidate 晋级 stable 前的所有验证任务

### 状态机

新增或等价表达以下状态：

- `candidate`: discovery 或 recovery 产出的候选 recipe，只允许单店验证
- `stable`: 半自动验证通过后的稳定 recipe，允许批量并行采集
- `degraded`: 执行失败或 recovery 失败后的不可批量状态
- `disabled`: 不可使用

不建议继续让 `active` 代表“可批量”。可以保留 `active` 作为兼容查询状态，但必须增加批量资格字段或新状态。

推荐实现：

- `status`: 保留 `active/degraded/disabled`
- 新增 `stability`: `candidate/stable`
- 批量准入要求 `status=active` 且 `stability=stable`

这样对现有 `get_active()` 影响最小。

## 实施计划

### Phase 1：Recipe 稳定态模型

修改：

- `src/domains/agent_recipe/models.py`
- `src/domains/agent_recipe/schemas.py`
- `src/domains/agent_recipe/repository.py`
- `src/domains/agent_recipe/services.py`
- `migrations/versions/*`

内容：

- 给 `agent_recipes` 增加 `stability` 字段，默认 `candidate`。
- 增加索引：`namespace,key,status,stability,version`。
- repository 增加 `get_stable_active(namespace, key)`。
- service 增加稳定态晋级方法，例如 `mark_stable(recipe_id, expected_version)`。
- `create_next_version()` 创建的新版本默认 `candidate`。
- `mark_degraded()` 同时使 recipe 不可批量。

验收：

- 新 discovery 写出的 recipe 是 `candidate`。
- 新 recovery 写出的 recipe 是 `candidate`。
- 只有显式晋级后的 recipe 才是 `stable`。

### Phase 2：批量准入闸门

修改：

- `src/application/collection/usecase.py`
- `src/application/collection/browser_agent_adapter.py`

内容：

- 在 `_collect_and_persist()` 生成 `plan_units` 后计算 `shop_count`。
- 如果 `shop_count > 1`，读取当前 recipe 的稳定态。
- 非 stable recipe 直接拒绝批量。
- 批量任务执行前强制写入 `runtime.extra_config.agent_recovery_enabled=False`。
- `BrowserAgentAdapter._recovery_enabled()` 增加批量上下文保护，避免调用方遗漏配置时仍触发 recovery。

验收：

- `shop_ids=["a", "b"]` 且 recipe 为 candidate 时失败。
- `all=true` 解析出多个店铺且 recipe 为 candidate 时失败。
- recipe 为 stable 时允许进入采集。
- 批量采集中 crawler 失败时不触发 `_attempt_recovery()`。

### Phase 3：单店 Discovery 与验证闭环

修改：

- `src/api/v1/agent_discovery.py`
- `src/tasks/collection/douyin_shop_discovery.py`
- `src/tasks/bootstrap.py`
- `src/tasks/collection/douyin_shop_dashboard.py`

内容：

- Discovery 请求显式接收单个 `shop_id` 或从 entrypoint 上下文绑定单店。
- Discovery 任务禁止 `all` 和多 `shop_ids`。
- Discovery replay 仍只验证当前单店。
- 增加 recipe 单店验证任务模式，例如 `extra_config.agent_recipe_validation=true`。
- 验证通过后不自动批量，只把 recipe 标记为可晋级。
- 半自动确认动作调用 `mark_stable()`。

验收：

- Discovery 不能提交多店参数。
- candidate recipe 可以跑单店验证。
- candidate recipe 不能跑批量验证。
- stable 前没有任何自动批量入口。

### Phase 4：Recovery 单店化

修改：

- `src/application/collection/browser_agent_adapter.py`
- `src/application/collection/usecase.py`
- `src/domains/agent_recipe/repository.py`
- `src/domains/agent_recipe/services.py`

内容：

- 批量任务中任何 recipe 级失败只记录失败，不内联修复。
- 批量失败把当前 stable recipe 标记为 degraded，阻止后续批量。
- Recovery 只能由单店任务触发。
- Recovery 成功写出 candidate 新版本。
- 新版本必须再经过单店验证和半自动确认，才能变为 stable。

验收：

- 多店批量失败不会创建 next version。
- 多店批量失败不会返回 `raw.agent.recovery`。
- 单店 recovery 可以创建 candidate next version。
- candidate next version 不能批量。

### Phase 5：并行采集执行器

修改：

- `src/application/collection/usecase.py`
- `src/config/shop_dashboard.py`

内容：

- 增加配置：`agent_batch_concurrency_limit`，默认 1，启用后才并行。
- 只对 stable recipe 的批量任务启用并行。
- 并行粒度是 `CollectionPlanUnit`，但同一 `account_id + shop_id` 仍必须保留店铺锁。
- 每个 plan unit 保持独立 idempotency key、业务锁、状态写入和失败 item。
- 并发任务共享 `state_store`，但不可共享 Playwright driver 实例。
- rate limit 从当前串行 `rate_limiter.wait()` 调整为并发安全限速。

验收：

- stable recipe 多店任务可以按配置并发。
- candidate/degraded recipe 即使配置并发也不能并行。
- 同店多日期窗口不破坏锁和幂等。
- 任一 plan unit 失败只影响自己的 item，recipe 级失败触发 degraded 后停止新 unit 调度。

## 关键实现细节

### Recipe 稳定态读取

批量准入不要使用 `BrowserAgentAdapter._load_recipe()` 的副作用式加载来判断状态。应在 usecase 层通过 repository 查询 recipe 元信息：

- 从 `runtime.agent_recipe_ref` 读取 `namespace/key`
- 查 `get_stable_active(namespace, key)`
- 找不到则拒绝批量
- 找到后再让现有 `_load_browser_agent_recipe()` 注入 inline recipe

### Recovery 禁用

批量 runtime 应在 usecase 层统一注入：

- `extra_config["agent_recovery_enabled"] = False`
- `extra_config["agent_batch_mode"] = True`

adapter 层再做兜底：

- 如果 `agent_batch_mode=True`，`_recovery_enabled()` 永远返回 False。

### 状态降级

批量任务中出现以下失败时应降级 recipe：

- `observation_empty`
- `assertion_failed`
- `browser_agent_output_missing_required_fields`
- `browser_agent_output_invalid_score_field`
- replay/recovery 相关失败不应在批量中出现

登录过期、店铺上下文 mismatch、单店锁失败不应直接降级 recipe。

### 失败结果

批量禁止 recovery 后，失败 item 应包含：

- `status=failed`
- `reason=agent_recipe_failed`
- `error_code` 保留原始 failure kind
- `recommended_next_step=single_shop_recovery`
- `recipe_status=degraded` 或 `recipe_stability=candidate`

## 测试计划

新增或调整：

- `tests/domains/agent_recipe/test_repository.py`
- `tests/domains/agent_recipe/test_services.py`
- `tests/tasks/test_shop_dashboard_collection.py`
- `tests/application/collection/test_browser_agent_adapter.py`
- `tests/tasks/test_shop_dashboard_recovery_flow.py`
- `tests/tasks/test_agent_discovery_session.py`

覆盖：

- discovery 写 candidate
- recovery 写 candidate
- candidate 禁止批量
- stable 允许批量
- 批量强制禁用 recovery
- 批量失败不创建 next version
- 单店 recovery 创建 candidate next version
- mark stable 后才允许并行
- `all=true` 解析多店时同样受稳定态闸门限制

## 推荐实施顺序

1. 先加 recipe `stability` 字段和 repository/service 能力。
2. 再加 usecase 批量准入闸门。
3. 再加批量强制禁用 recovery。
4. 再调整 discovery/recovery 写入 candidate。
5. 再加半自动确认晋级 stable API。
6. 最后实现真正并行采集。

这样可以先阻断不安全批量，再逐步开放稳定态并行。
