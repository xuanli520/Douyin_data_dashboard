# Issue 2 Funboost Task Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将四个核心 collection/etl 任务切换为 Funboost 驱动，并完成 worker/beat 启动链路、任务触发 API、状态查询 API 与测试覆盖。

**Architecture:** 采用“每个任务函数独立队列”的 Funboost 模式：任务函数通过 `@boost(...queue_name=...)` 注册，状态由 `TaskStatusMixin`（SUCCESS/FAILURE）+ 任务函数启动写入（STARTED）组合维护到 Redis Hash。API 层仅负责权限、参数校验、审计和触发 `.push()`，状态查询从 `douyin:task:status:{task_id}` 读取。beat 独立进程使用 `ApsJobAdder(job_store_kind='redis')`，worker 进程集中由 `src/tasks/worker.py` 启动。

**Tech Stack:** FastAPI, Funboost, Redis, Pytest, Fakeredis, Justfile

---

## Scope And Decisions

- 本计划以 Issue 2 为边界，不删除 `celery_app.py`（按需求暂保留依赖与历史文件）。
- 当前仓库内四个任务源码尚未存在，只存在 `src/tasks/base.py`、`params.py`、`idempotency.py` 等基础设施；本计划包含新建这些任务模块。
- `task.py` 当前仍是 mock/in_development 接口，本计划将替换为真实触发接口，并新增 `task_status.py` 状态查询接口。
- 审计日志沿用现有 `AuditAction`，避免新增枚举引发额外迁移；触发接口记录 `TASK_RUN`，状态查询记录 `PROTECTED_RESOURCE_ACCESS`（resource_type=`task_status`）。

## Approach Options (Brainstorming Result)

1. **推荐：显式触发接口 + 显式状态接口（最小侵入）**
- 触发接口按任务类型拆分：`/tasks/collection/orders/trigger` 等。
- 状态接口独立：`/task-status/{task_id}`。
- 优点：权限/审计边界清晰，改造对现有路由影响小，测试可控。
- 缺点：接口数量会增加。

2. 通用发布接口（queue_name + msg_body）
- 类似通用任务网关，后端只维护一个 publish endpoint。
- 优点：扩展新任务时几乎零 API 变更。
- 缺点：类型安全差，权限粒度粗，不符合当前 RBAC 风格。

3. 直接启用 Funboost FaaS Router
- 优点：开发速度快。
- 缺点：与现有 FastAPI 权限/审计体系耦合困难，接口契约变化大。

选择：**方案 1**。

## Task 1: API 契约先行（TDD 基线）

**Files:**
- Modify: `tests/api/test_task_rbac.py`
- Modify: `tests/api/test_mock_modules_rbac.py`
- Modify: `tests/api/test_mock_response_contract.py`
- Create: `tests/api/test_task_trigger_api.py`

**Step 1: 写失败测试（新任务触发接口）**

```python
def test_trigger_collection_orders_requires_auth(...):
    r = client.post("/api/v1/tasks/collection/orders/trigger", json={...})
    assert r.status_code == 401

def test_get_task_status_requires_auth(...):
    r = client.get("/api/v1/task-status/test-task-id")
    assert r.status_code == 401
```

**Step 2: 运行并确认失败**

Run: `uv run --frozen pytest tests/api/test_task_trigger_api.py -v`
Expected: FAIL，路由不存在（404）或导入失败。

**Step 3: 更新旧测试基线**

- 将 `test_task_rbac.py`、`test_mock_modules_rbac.py` 中旧的 `/api/v1/tasks/{id}/run`、`/executions` 断言迁移到新触发/状态路径。
- `test_mock_response_contract.py` 移除 `/api/v1/tasks?page=...` 的 mock 契约断言，改为新真实接口的基础契约断言（`code/msg/data` 与关键字段存在）。

**Step 4: 局部回归**

Run: `uv run --frozen pytest tests/api/test_task_rbac.py tests/api/test_mock_modules_rbac.py tests/api/test_mock_response_contract.py -v`
Expected: FAIL（新接口尚未实现），但失败集中于任务接口。

**Step 5: Commit**

```bash
git add tests/api/test_task_rbac.py tests/api/test_mock_modules_rbac.py tests/api/test_mock_response_contract.py tests/api/test_task_trigger_api.py
git commit -m "test: define funboost task trigger and status api contract"
```

## Task 2: 迁移 collection 任务到 Funboost

**Files:**
- Create: `src/tasks/collection/__init__.py`
- Create: `src/tasks/collection/douyin_orders.py`
- Create: `src/tasks/collection/douyin_products.py`
- Modify: `src/tasks/exceptions.py` (仅在缺少异常类型时补充)
- Test: `tests/tasks/test_collection_tasks.py`

**Step 1: 写失败测试（装饰器注册与 STARTED 状态写入）**

```python
def test_sync_orders_push_has_queue_name():
    assert sync_orders.boost_params.queue_name == "collection_orders"

def test_sync_orders_writes_started_status(monkeypatch):
    # mock publisher.redis_db_frame.hset/expire
    ...
```

**Step 2: 运行并确认失败**

Run: `uv run --frozen pytest tests/tasks/test_collection_tasks.py -v`
Expected: FAIL，模块不存在。

**Step 3: 实现最小可用任务**

- 使用 `@boost(CollectionTaskParams(...))` 定义：
  - `sync_orders` (`queue_name="collection_orders"`)
  - `sync_products` (`queue_name="collection_products"`)
- 统一参数：
  - `consumer_override_cls=TaskStatusMixin`
  - `is_push_to_dlx_queue_when_retry_max_times=True`
  - `retry_interval` 与 `max_retry_times` 使用基类默认值，必要处覆盖。
- 函数开头写入 `STARTED` 状态到 `douyin:task:status:{fct.task_id}`，透传 `triggered_by`。
- 添加限流异常指数退避 `consuming_function_decorator`（只处理 `ScrapingRateLimitException`）。
- 同文件添加死信消费函数（记录 error 日志，先不入库）。

**Step 4: 幂等接入**

- 在 `douyin_orders.py` 中接入 `FunboostIdempotencyHelper`：
  - 使用业务键（建议 `shop_id + date`）获取锁；
  - 长任务分阶段后调用 `refresh_lock`；
  - finally 安全释放锁。

**Step 5: 运行测试**

Run: `uv run --frozen pytest tests/tasks/test_collection_tasks.py -v`
Expected: PASS。

**Step 6: Commit**

```bash
git add src/tasks/collection/__init__.py src/tasks/collection/douyin_orders.py src/tasks/collection/douyin_products.py src/tasks/exceptions.py tests/tasks/test_collection_tasks.py
git commit -m "feat: migrate collection tasks to funboost with idempotency and dlx"
```

## Task 3: 迁移 ETL 任务到 Funboost

**Files:**
- Create: `src/tasks/etl/__init__.py`
- Create: `src/tasks/etl/orders.py`
- Create: `src/tasks/etl/products.py`
- Test: `tests/tasks/test_etl_tasks.py`

**Step 1: 写失败测试（EtlTaskParams 约束）**

```python
def test_etl_task_uses_single_thread_mode():
    assert process_orders.boost_params.concurrent_mode == "SINGLE_THREAD"
    assert process_orders.boost_params.concurrent_num == 1
```

**Step 2: 运行并确认失败**

Run: `uv run --frozen pytest tests/tasks/test_etl_tasks.py -v`
Expected: FAIL，模块不存在。

**Step 3: 实现最小 ETL 任务**

- `@boost(EtlTaskParams(queue_name="etl_orders", ...))`
- `@boost(EtlTaskParams(queue_name="etl_products", ...))`
- 同样写入 `STARTED` 状态，完成态依赖 `TaskStatusMixin`。
- 返回值仅保留必要元数据（例如记录数、批次号），不写完整大结果到 Redis。
- 增加 DLX 消费函数用于异常告警日志。

**Step 4: 运行测试**

Run: `uv run --frozen pytest tests/tasks/test_etl_tasks.py -v`
Expected: PASS。

**Step 5: Commit**

```bash
git add src/tasks/etl/__init__.py src/tasks/etl/orders.py src/tasks/etl/products.py tests/tasks/test_etl_tasks.py
git commit -m "feat: migrate etl tasks to funboost params and status model"
```

## Task 4: 任务发现与 Worker 启动链路

**Files:**
- Modify: `src/tasks/__init__.py`
- Create: `src/tasks/worker.py`
- Test: `tests/tasks/test_worker_entry.py`

**Step 1: 写失败测试（任务导入与入口调用）**

```python
def test_tasks_package_imports_all_task_modules():
    import src.tasks as tasks
    assert hasattr(tasks, "collection")
    assert hasattr(tasks, "etl")

def test_worker_main_invokes_consume_methods(monkeypatch):
    ...
```

**Step 2: 运行并确认失败**

Run: `uv run --frozen pytest tests/tasks/test_worker_entry.py -v`
Expected: FAIL。

**Step 3: 实现**

- `src/tasks/__init__.py` 显式导入四个任务模块，移除 Celery signal 相关遗留（若发现）。
- `src/tasks/worker.py` 提供：
  - `run_all()`：启动 collection 任务 `consume()` 与 ETL 任务 `multi_process_consume(n)`；
  - CLI 参数支持 `--queue`（单队列调试）与 `--etl-processes`。

**Step 4: 运行测试**

Run: `uv run --frozen pytest tests/tasks/test_worker_entry.py -v`
Expected: PASS。

**Step 5: Commit**

```bash
git add src/tasks/__init__.py src/tasks/worker.py tests/tasks/test_worker_entry.py
git commit -m "feat: add funboost worker entry and task auto-discovery"
```

## Task 5: Beat 调度迁移与 justfile 命令

**Files:**
- Create: `src/tasks/beat.py`
- Modify: `justfile`
- Test: `tests/tasks/test_beat_registration.py`

**Step 1: 写失败测试（任务注册与固定 job id）**

```python
def test_beat_registers_expected_jobs(monkeypatch):
    # assert id == "daily_order_sync" ...
```

**Step 2: 运行并确认失败**

Run: `uv run --frozen pytest tests/tasks/test_beat_registration.py -v`
Expected: FAIL。

**Step 3: 实现**

- `src/tasks/beat.py` 使用 `ApsJobAdder(..., job_store_kind="redis")` 注册 cron：
  - 至少包含 orders/products 同步任务；
  - 固定 `id`，避免重复注册；
  - 提供 `register_jobs()` 供脚本入口调用。
- `justfile`：
  - 新增 `funboost-worker`、`funboost-worker-q queue=`、`funboost-beat`。
  - 仅当发现旧 celery 目标时删除；若不存在则不额外改动。

**Step 4: 运行测试**

Run: `uv run --frozen pytest tests/tasks/test_beat_registration.py -v`
Expected: PASS。

**Step 5: Commit**

```bash
git add src/tasks/beat.py justfile tests/tasks/test_beat_registration.py
git commit -m "chore: add funboost beat entry and just commands"
```

## Task 6: 任务触发 API (`task.py`) 实现

**Files:**
- Modify: `src/api/v1/task.py`
- Modify: `src/api/v1/__init__.py`
- Modify: `src/api/__init__.py`
- Modify: `src/main.py` (仅当路由导出链路需要)
- Test: `tests/api/test_task_trigger_api.py`

**Step 1: 写失败测试（鉴权、参数校验、push 调用、审计）**

```python
async def test_trigger_orders_calls_push_with_triggered_by(...):
    ...
    assert called_kwargs["triggered_by"] == user.id
```

**Step 2: 运行并确认失败**

Run: `uv run --frozen pytest tests/api/test_task_trigger_api.py -v`
Expected: FAIL。

**Step 3: 实现最小触发接口**

- 移除 `@in_development` 占位逻辑。
- 定义明确请求模型（例如 `TaskTriggerRequest`）与响应模型（返回 `task_id`、`queue_name`、`triggered_by`）。
- 至少实现四个触发端点：
  - `POST /api/v1/tasks/collection/orders/trigger`
  - `POST /api/v1/tasks/collection/products/trigger`
  - `POST /api/v1/tasks/etl/orders/trigger`
  - `POST /api/v1/tasks/etl/products/trigger`
- 每个端点：
  - `Depends(require_permissions(TaskPermission.EXECUTE, bypass_superuser=True))`
  - 调用对应任务 `.push(..., triggered_by=user.id)`
  - 写审计日志 `AuditAction.TASK_RUN`。

**Step 4: 运行测试**

Run: `uv run --frozen pytest tests/api/test_task_trigger_api.py tests/api/test_task_rbac.py -v`
Expected: PASS。

**Step 5: Commit**

```bash
git add src/api/v1/task.py src/api/v1/__init__.py src/api/__init__.py src/main.py tests/api/test_task_trigger_api.py tests/api/test_task_rbac.py
git commit -m "feat: implement funboost task trigger api with rbac and audit"
```

## Task 7: 状态查询 API (`task_status.py`) 实现

**Files:**
- Create: `src/api/v1/task_status.py`
- Modify: `src/api/v1/__init__.py`
- Modify: `src/api/__init__.py`
- Modify: `src/main.py` (仅当路由导出链路需要)
- Test: `tests/api/test_task_status_api.py`

**Step 1: 写失败测试（404/200/权限/审计）**

```python
async def test_get_task_status_returns_404_when_missing(...):
    assert resp.status_code == 404
```

**Step 2: 运行并确认失败**

Run: `uv run --frozen pytest tests/api/test_task_status_api.py -v`
Expected: FAIL，模块不存在。

**Step 3: 实现**

- `APIRouter(prefix="/task-status", tags=["task-status"])`
- 单例 Redis 客户端（`@lru_cache(maxsize=1)` + `redis.Redis.from_url(...)`）。
- `GET /api/v1/task-status/{task_id}`：
  - 权限 `TaskPermission.VIEW`
  - 查询 `douyin:task:status:{task_id}`
  - 空结果返回 404
  - 写审计日志（建议 `AuditAction.PROTECTED_RESOURCE_ACCESS`）
  - 返回 `task_id` + status hash。

**Step 4: 运行测试**

Run: `uv run --frozen pytest tests/api/test_task_status_api.py tests/api/test_mock_modules_rbac.py -v`
Expected: PASS。

**Step 5: Commit**

```bash
git add src/api/v1/task_status.py src/api/v1/__init__.py src/api/__init__.py src/main.py tests/api/test_task_status_api.py tests/api/test_mock_modules_rbac.py
git commit -m "feat: add task status query api backed by redis hash"
```

## Task 8: 全链路验证与回归

**Files:**
- Modify: `tests/api/test_mock_response_contract.py` (最终契约稳定)
- Modify: `tests/tasks/test_funboost_infra.py` (必要时补充 worker/beat 配置断言)

**Step 1: 运行任务与 API 相关测试集合**

Run:

```bash
uv run --frozen pytest tests/tasks tests/api/test_task_rbac.py tests/api/test_task_trigger_api.py tests/api/test_task_status_api.py tests/api/test_mock_modules_rbac.py tests/api/test_mock_response_contract.py -v
```

Expected: PASS。

**Step 2: 运行项目全量关键回归**

Run: `uv run --frozen pytest -xvs tests`
Expected: PASS（若历史不稳定用例存在，记录并单独说明）。

**Step 3: 手工链路验收（本地）**

Run:

```bash
just funboost-worker
just run
curl -X POST http://127.0.0.1:8000/api/v1/tasks/collection/orders/trigger ...
curl http://127.0.0.1:8000/api/v1/task-status/<task_id>
```

Expected:
- 触发接口返回 `task_id`
- Redis `douyin:task:status:{task_id}` 先出现 `STARTED`，后续转为 `SUCCESS/FAILURE`
- 审计表存在对应记录。

**Step 4: Commit**

```bash
git add tests/tasks/test_funboost_infra.py tests/api/test_mock_response_contract.py
git commit -m "test: finalize funboost task migration verification coverage"
```

## Verification Checklist Before Merge

- [ ] 四个任务文件均使用 `@boost` 且队列名正确。
- [ ] collection 任务接入幂等锁 + `refresh_lock`。
- [ ] 四类任务都配置 `is_push_to_dlx_queue_when_retry_max_times=True` 并有死信消费函数。
- [ ] `src/tasks/worker.py` 与 `src/tasks/beat.py` 可独立启动。
- [ ] `justfile` 存在 `funboost-worker` / `funboost-worker-q` / `funboost-beat`。
- [ ] `task.py` 不再是 `in_development` 占位。
- [ ] `task_status.py` 能正确返回 404/200。
- [ ] RBAC 与审计日志在触发和查询接口均生效。

## Risks And Mitigations

- 风险：Funboost 对象属性（如 `publisher`、`boost_params`）在测试中不稳定。
- 缓解：测试以 monkeypatch/mock 为主，避免依赖真实 Redis 消费。

- 风险：历史 mock 契约测试与新真实接口冲突。
- 缓解：在 Task 1 先调整契约测试边界，避免后续持续红灯。

- 风险：Beat 多实例重复注册。
- 缓解：固定 job id + Redis job store，beat 独立部署。

---

执行时请按任务顺序推进，并在每个 Task 完成后先跑对应最小测试集再继续。
