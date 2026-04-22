# 抖音数据可视化中台

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-005571?logo=fastapi)](https://fastapi.tiangolo.com/)
[![GitHub stars](https://img.shields.io/github/stars/xuanli520/Douyin_data_dashboard?style=social)](https://github.com/xuanli520/Douyin_data_dashboard/stargazers)
[![GitHub license](https://img.shields.io/github/license/xuanli520/Douyin_data_dashboard)](https://github.com/xuanli520/Douyin_data_dashboard/blob/main/LICENSE)

基于抖店平台数据，构建自动化数据采集、处理、分析与展示的可视化中台系统。

## 技术栈

| 类别 | 技术 |
|------|------|
| 框架 | FastAPI 0.115+ |
| 运行时 | Python 3.12+ |
| 包管理 | uv |
| 任务运行 | just |
| 数据库 | SQLModel + Alembic (PostgreSQL) |
| 缓存 | Redis |
| 认证 | fastapi-users JWT + RBAC |
| 任务调度 | funboost workers + beat scheduler |
| 监控 | Prometheus metrics, circuit breaker |
| 浏览器自动化 | Playwright |
| 数据导入 | openpyxl (Excel 解析) |

## 项目结构

```
src/
├── api/v1/          # HTTP 路由层 (18+ 路由模块)
├── application/     # 采集编排 (计划构建、运行时加载、店铺切换)
├── agents/          # LLM 看板智能体
├── auth/            # JWT 认证、RBAC、权限种子
├── audit/           # 审计日志
├── cache/           # Redis 缓存协议
├── config/          # 应用配置、日志、监控、熔断器
├── core/            # 异常定义、端点状态装饰器、熔断器
├── domains/
│   ├── collection_job/  # 采集任务管理
│   ├── data_import/     # 数据导入 (Excel 解析)
│   ├── data_source/     # 数据源配置
│   ├── experience/      # 体验分析
│   ├── scraping_rule/   # 采集规则
│   ├── shop_dashboard/  # 店铺看板
│   └── task/            # 任务调度
├── middleware/      # CORS、限流、监控中间件
├── responses/       # 统一 JSON 响应封装
├── shared/          # 跨领域公共模块 (分页、错误码、Schema)
└── tasks/           # Funboost workers、beat 调度器、幂等性、队列映射
```
## 基础设施

### 数据库

异步引擎，支持 PostgreSQL (`asyncpg`) 和 SQLite (`aiosqlite`)。连接池配置通过 `DatabaseSettings` 管理：

```python
class DatabaseSettings(BaseSettings):
    driver: Literal["postgresql", "sqlite"] = "postgresql"
    pool_size: int = Field(default=5, ge=1)
    max_overflow: int = Field(default=10, ge=0)
    pool_recycle: int = Field(default=1800, ge=0)
```

模型使用 `SQLModel` + `TimestampMixin`：

```python
from sqlmodel import SQLModel, Field
from src.shared.mixins import TimestampMixin

class ShopDashboardScore(SQLModel, TimestampMixin, table=True):
    __tablename__ = "shop_dashboard_scores"
    id: int | None = Field(default=None, primary_key=True)
    shop_id: str = Field(max_length=50, index=True)
    # TimestampMixin 自动添加 created_at / updated_at (timezone-aware)
```

路由中通过 `get_session` 依赖注入，自动提交/回滚：

```python
from src.session import get_session

@router.get("/items")
async def list_items(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Item))
    return result.scalars().all()
```

模型通过 AST 扫描自动发现（扫描 `src/` 下所有含 `table=True` 的类），无需手动注册。同步 funboost worker 通过 `bind_worker_loop()` + `run_coro()` 桥接异步数据库调用。

```bash
just db-migrate   # 生成迁移 (alembic revision --autogenerate)
just db-upgrade   # 应用迁移 (alembic upgrade head)
just db-downgrade # 回滚迁移 (alembic downgrade -1)
just db-history   # 查看迁移历史
```
### 缓存

双后端缓存抽象，通过 `CacheProtocol` 统一接口。

| 后端 | 实现 | 场景 |
|------|------|------|
| `redis` | `RedisCache` (redis.asyncio, max_connections=50) | 生产环境 |
| `local` | `LocalCache` (内存 dict + TTL) | 开发/测试 |

```python
from src.cache import get_cache, CacheProtocol

@router.get("/data")
async def get_data(cache: CacheProtocol = Depends(get_cache)):
    cached = await cache.get("my_key")
    if cached:
        return cached
    data = await fetch_from_db()
    await cache.set("my_key", data, ttl=300)
    return data
```

`RedisKeyRegistry` 提供类型化的 key 生成，避免硬编码：

```python
from src.shared.redis_keys import redis_keys

redis_keys.refresh_token(token_hash="abc123")           # refresh_token:abc123
redis_keys.experience_metrics(shop_id=1, ...)           # experience:metrics:1:...
redis_keys.shop_dashboard_shop_catalog(account_id="x")  # shop_dashboard:shop_catalog:x
```

同步 worker 使用 `SyncRedisCache` 访问缓存。
### 认证与授权

基于 `fastapi-users`，双认证后端：`cookie_auth_backend` (HttpOnly Cookie) + `bearer_auth_backend` (Bearer Token)。JWT 使用 HS256/HS512，RefreshToken 存储于 Redis 并经 SHA-256 哈希。

RBAC 模型：`User` ↔ `UserRole` ↔ `Role` ↔ `RolePermission` ↔ `Permission` (多对多)。预置角色：`super_admin`、`admin`、`user`。

```python
from src.auth import current_user, User

@router.get("/profile")
async def get_profile(user: User = Depends(current_user)):
    return {"id": user.id, "username": user.username}
```

权限守卫：

```python
from src.auth.rbac import require_permissions
from src.auth.permissions import ExportPermission

@router.get("/exports")
async def list_exports(
    user: User = Depends(current_user),
    _=Depends(require_permissions(ExportPermission.VIEW, bypass_superuser=True)),
):
    ...
```

权限常量按模块组织（`src/api/v1/permissions.py`），支持通配符：`module:*` 匹配模块下所有操作，`*` 为全局权限。

其他装饰器：
- `require_roles("admin", match="any")` — 角色检查
- `owner_or_perm(get_owner_id, ["task:update"])` — 资源所有者或持有指定权限
### 中间件

四个中间件在 `src/main.py` 通过 `middleware=[]` 列表加载。

| 中间件 | 职责 |
|---|---|
| `CORSMiddleware` | 跨域，读取 `settings.cors` |
| `RateLimitMiddleware` | 滑动窗口限流（Redis sorted set，降级到 CacheProtocol） |
| `MonitorMiddleware` | Prometheus 指标采集 |
| `ResponseWrapperMiddleware` | JSON 响应自动包装为 `{code, msg, data}` |

限流按端点配置，全局默认 1000 req/60s，登录 5 req/60s。超限返回 429 + `Retry-After`，响应头携带：

```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Window: 60.0
```

Prometheus 指标：

```python
http_requests_total          # Counter  [method, endpoint, status_code]
http_request_duration_seconds # Histogram [method, endpoint]
http_requests_in_progress    # Gauge    [method, endpoint]
http_exceptions_total        # Counter  [method, endpoint, exception_type]
```

`generate_metrics()` 返回 Prometheus exposition 格式文本，挂载到 `/metrics` 端点。
### 统一响应

`src/responses/base.py` 定义统一响应信封：

```python
class Response(BaseModel, Generic[T]):
    code: int
    msg: str
    data: T | None = None

    @classmethod
    def success(cls, data=None, msg="success", code=200): ...
    @classmethod
    def error(cls, code, msg, data=None): ...
```

`ResponseWrapperMiddleware` 自动将所有 JSON 响应包装为此格式，跳过 `/docs`、`/health`、认证端点。路由中直接返回业务数据即可：

```python
@router.get("/shops")
async def list_shops():
    return [{"id": 1, "name": "测试店铺"}]
# 实际响应: {"code": 200, "msg": "success", "data": [{"id": 1, "name": "测试店铺"}]}
```

手动控制错误响应：`return Response.error(code=40001, msg="店铺不存在")`
### 分页

`src/shared/schemas/pagination.py` 提供分页三件套：

```python
from src.shared.schemas.pagination import PaginatedData, PaginationParams

@router.get("/shops")
async def list_shops(
    params: PaginationParams = Depends(),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Shop).offset(params.offset()).limit(params.size)
    items = (await session.execute(stmt)).scalars().all()
    total = ...
    return PaginatedData.create(
        items=items, total=total, page=params.page, size=params.size
    )
```

`PaginationParams` 默认 page=1, size=20 (max 100)。`PaginatedData` 自动计算 `pages`、`has_next`、`has_prev`。
### 审计日志

`src/audit/` 提供结构化审计追踪。核心模型 `AuditLog`：

| 字段 | 说明 |
|---|---|
| `actor_id` | FK → users.id |
| `action` | `AuditAction` 枚举（登录/登出/CRUD/权限检查/任务生命周期） |
| `result` | `AuditResult`（success/failure/granted/denied） |
| `resource_type` / `resource_id` | 资源定位 |
| `request_id` | UUID v4 请求关联 |
| `ip` | 客户端 IP（x-forwarded-for 感知） |

`AuditService.log()` 异常静默，不影响业务流程：

```python
from src.audit.service import AuditService, extract_client_info

async def some_handler(request: Request, audit: AuditService = Depends(get_audit_service)):
    user_agent, ip = extract_client_info(request)
    await audit.log(
        action=AuditAction.CREATE, result=AuditResult.SUCCESS,
        actor_id=user.id, resource_type="shop", resource_id=str(shop.id),
        user_agent=user_agent, ip=ip, request_id=request.state.request_id,
    )
```
### 配置管理

`src/config/settings.py` 基于 pydantic-settings，组合 12 个子配置模块：

`app` · `auth` · `db` · `cache` · `captcha` · `log` · `rate_limit` · `circuit_breaker` · `monitor` · `cors` · `funboost` · `shop_dashboard`

`get_settings()` 通过 `@lru_cache()` 单例化。环境变量使用 `__` 分隔符映射嵌套字段：

```bash
DB__POOL_SIZE=10
CACHE__URL=redis://localhost:6379/0
AUTH__SECRET=your-secret-key
RATE_LIMIT__GLOBAL_LIMIT=2000
```
### 任务系统

基于 funboost（Redis 消息队列）构建，非 Celery。

| 队列 | 用途 |
|---|---|
| `collection_shop_dashboard` | 店铺看板数据采集 |
| `collection_shop_dashboard_agent` | 代理采集 |
| `etl_orders` | 订单 ETL（多进程） |
| `etl_products` | 商品 ETL（多进程） |
| `*_dlx` | 各队列对应的死信队列 |

Worker（`src/tasks/worker.py`）启动 asyncio 事件循环，初始化数据库，运行队列消费者。Beat（`src/tasks/beat.py`）从数据库加载已启用的 `CollectionJob`，注册 APScheduler 任务，每 10 分钟刷新。

`TaskStatusMixin` 在任务完成时写入状态记录。任务幂等性通过 `src/tasks/idempotency.py` 保证。

```bash
just funboost-worker              # 启动全部队列
just funboost-worker-q <queue>    # 启动单个队列
just funboost-beat                # 启动调度器
```
### 公共基础设施

**BaseRepository** (`src/shared/repository.py`) — 事务辅助基类，自动回滚，`UNSET` 哨兵值区分 `None` 与未设置：

```python
from src.shared.repository import BaseRepository

class UserRepository(BaseRepository):
    async def create(self, user: User) -> User:
        return await self._add(user)

    async def update_email(self, user: User, email: str) -> None:
        async def _op():
            user.email = email
        await self._tx(_op)
```

**ErrorCode** (`src/shared/errors.py`) — `IntEnum`，60+ 错误码覆盖认证、用户、角色、权限、数据校验、业务、数据源、任务等领域。`ERROR_CODE_TO_HTTP` 映射错误码到 HTTP 状态码。

**TimestampMixin** (`src/shared/mixins.py`) — `created_at` / `updated_at` 自动填充，时区感知（默认 UTC+8）。
### 熔断器

`src/core/circuit_breaker.py` 封装 `circuitbreaker` 库。三态：`CLOSED` → `OPEN` → `HALF_OPEN`。默认 5 次失败触发熔断，60 秒恢复。

```python
from src.core.circuit_breaker import circuit, CircuitBreakerError

@circuit(failure_threshold=5, recovery_timeout=60, name="douyin-api")
def call_douyin_api(shop_id: str) -> dict:
    ...

try:
    result = call_douyin_api("shop_001")
except CircuitBreakerError:
    ...  # 降级处理
```

`CircuitBreakerPolicy` 用于批量创建同策略的熔断器实例。

### 重试机制

`src/retry.py` 基于 tenacity，针对网络错误和 5xx 响应自动重试。指数退避（1s → 2s → 4s），最多 3 次。

```python
from src.retry import retry_on_network, async_retry_on_network

@retry_on_network()
def fetch_shop_data(client: httpx.Client, shop_id: str) -> dict:
    resp = client.get(f"/api/shops/{shop_id}")
    resp.raise_for_status()
    return resp.json()
```

## 核心功能

- **数据采集** — Playwright 自动化登录抖店后台，采集店铺经营数据
- **采集编排** — 计划构建器、运行时加载器、店铺切换、账号店铺目录
- **数据导入** — Excel 文件解析与批量导入
- **体验分析** — 体验分概览、趋势、问题诊断、维度下钻
- **店铺看板** — KPI 概览、指标监控、数据可视化
- **任务调度** — funboost 分布式任务队列 + beat 定时调度
- **告警通知** — 自定义告警规则与通知推送
- **报表导出** — 数据分析报表生成与导出
- **ETL 管道** — 订单、商品数据清洗转换
- **LLM 数据补全** — 智能体补充冷数据缺失字段
- **审计日志** — 全链路操作审计
## API 模块

`api/v1/` 下包含以下路由模块：

| 模块 | 说明 |
|------|------|
| auth | 认证与登录 |
| admin | 管理后台 |
| permissions | 权限管理 |
| shops | 店铺管理 |
| data_source | 数据源配置 |
| scraping_rule | 采集规则 |
| collection_job | 采集任务 |
| data_import | 数据导入 |
| task | 任务管理 |
| schedules | 定时调度 |
| experience | 体验分析 |
| metrics | 指标监控 |
| alerts | 告警管理 |
| notifications | 通知推送 |
| reports | 报表管理 |
| exports | 数据导出 |
| analysis | 数据分析 |
| system | 系统管理 |
| audit | 审计日志 |

## 开发环境搭建

### 前置依赖

- Python >= 3.12
- [uv](https://github.com/astral-sh/uv)
- [just](https://github.com/casey/just)
- PostgreSQL
- Redis

### 安装步骤

```bash
just dev          # 安装依赖
just hooks        # 安装 pre-commit hooks
just db-upgrade   # 数据库迁移
just run          # 启动开发服务器
```

## 部署

### Docker

```bash
# 生产环境
docker compose -f docker/docker-compose.yml up --build

# 开发环境 (热重载)
docker compose -f docker/docker-compose.yml -f docker/docker-compose.dev.yml up --build
```

compose 文件从项目根目录 `.env` 读取环境变量。启动时自动执行数据库迁移。

多节点部署参考 `docker/.env.server-a.example` 和 `docker/.env.server-b.example`。

## 常用命令

| 命令 | 说明 |
|------|------|
| `just dev` | 安装依赖 |
| `just hooks` | 安装 pre-commit hooks |
| `just check` | 代码格式化与 lint 检查 |
| `just test` | 运行测试 |
| `just run` | 启动开发服务器 |
| `just db-migrate` | 生成数据库迁移 |
| `just db-upgrade` | 执行数据库迁移 |
| `just db-downgrade` | 回滚数据库迁移 |
| `just funboost-worker` | 启动 funboost worker |
| `just funboost-beat` | 启动 beat 调度器 |
| `just arch-check` | 架构检查 |
| `just ci-gate` | CI 门禁检查 |

## 贡献指南

详见 [CONTRIBUTIONS.md](/CONTRIBUTIONS.md)。
