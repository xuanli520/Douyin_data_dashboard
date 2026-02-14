# API Mock模块接入计划

## 1. 背景概述

基于 `fastapi-template-agent` 模板构建的抖音数据可视化中台系统，需要为前端页面提供Mock数据支撑开发。

### 1.1 技术栈分析

| 组件 | 技术实现 | 用途 |
|------|---------|------|
| 框架 | FastAPI 0.115+ | HTTP路由与处理器 |
| 认证 | fastapi-users + JWT | 用户认证与RBAC |
| 缓存 | Redis/Local | 缓存抽象层 |
| 响应格式 | `Response[T]` | 统一JSON封装 `{code, msg, data}` |
| 端点状态 | `in_development` 装饰器 | 开发中Mock模式 |

### 1.2 Mock装饰器工作原理

`src/core/endpoint_status.py:41` 提供的 `in_development` 装饰器支持三种模式：

1. **纯Mock模式**（默认）：函数体不执行，直接返回mock数据
2. **混合模式**：`prefer_real=True` 时优先执行真实逻辑，异常时回退到mock
3. **动态数据**：支持 `dict` 或 `Callable[[], dict]` 类型生成mock数据

响应格式：
```json
{
    "code": 70001,
    "msg": "该功能正在开发中，当前返回演示数据",
    "data": {
        "mock": true,
        "expected_release": "2026-03-01",
        "data": {...}
    }
}
```

---

## 2. 权限系统改造

### 2.1 新增权限类定义

修改文件：`src/auth/permissions.py`

```python
class DataSourcePermission:
    VIEW = "data_source:view"
    CREATE = "data_source:create"
    UPDATE = "data_source:update"
    DELETE = "data_source:delete"


class DataImportPermission:
    VIEW = "data_import:view"
    UPLOAD = "data_import:upload"
    PARSE = "data_import:parse"
    VALIDATE = "data_import:validate"
    CONFIRM = "data_import:confirm"
    CANCEL = "data_import:cancel"


class TaskPermission:
    VIEW = "task:view"
    CREATE = "task:create"
    EXECUTE = "task:execute"
    CANCEL = "task:cancel"


class AnalyticsPermission:
    VIEW = "analytics:view"


class ShopPermission:
    VIEW = "shop:view"
    SCORE = "shop:score"


class MetricPermission:
    VIEW = "metric:view"


class ReportPermission:
    VIEW = "report:view"


class SchedulePermission:
    VIEW = "schedule:view"


class AnalysisPermission:
    VIEW = "analysis:view"


class AlertPermission:
    VIEW = "alert:view"
```

### 2.2 task.py 权限改造

原始 `src/api/v1/task.py` 权限控制不完整，需要全面改造。

**改造前**：
```python
@router.get("", response_model=Response[list[dict[str, Any]]])
async def list_tasks(
    user: User = Depends(current_user),
    _=Depends(require_permissions(TaskPermission.VIEW, bypass_superuser=True)),
) -> Response[list[dict[str, Any]]]:
    return Response.success(data=[])
```

**改造后**：
```python
from src.core.endpoint_status import in_development

router = APIRouter(prefix="/tasks", tags=["task"])


@router.get("")
@in_development(
    mock_data=[
        {
            "id": 1,
            "name": "订单采集任务",
            "task_type": "order_collection",
            "status": "running",
            "progress": 45,
            "created_at": "2026-01-15T10:00:00",
        },
        {
            "id": 2,
            "name": "商品数据同步",
            "task_type": "product_sync",
            "status": "completed",
            "progress": 100,
            "created_at": "2026-01-14T08:00:00",
        },
    ],
    expected_release="2026-03-01",
)
async def list_tasks(
    user: User = Depends(current_user),
    _=Depends(require_permissions(TaskPermission.VIEW, bypass_superuser=True)),
):
    pass


@router.post("")
@in_development(
    mock_data={
        "id": 3,
        "name": "新建任务",
        "task_type": "order_collection",
        "status": "pending",
        "created_at": "2026-01-15T12:00:00",
    },
    expected_release="2026-03-01",
)
async def create_task(
    data: dict[str, Any],
    user: User = Depends(current_user),
    _=Depends(require_permissions(TaskPermission.CREATE, bypass_superuser=True)),
):
    pass


@router.post("/{task_id}/run")
@in_development(
    mock_data={"execution_id": "exec_123", "status": "running", "started_at": "2026-01-15T12:00:00"},
    expected_release="2026-03-01",
)
async def run_task(
    task_id: int,
    user: User = Depends(current_user),
    _=Depends(require_permissions(TaskPermission.EXECUTE, bypass_superuser=True)),
):
    pass


@router.get("/{task_id}/executions")
@in_development(
    mock_data=[
        {
            "execution_id": "exec_001",
            "task_id": 1,
            "status": "completed",
            "started_at": "2026-01-15T10:00:00",
            "completed_at": "2026-01-15T10:05:00",
            "records_processed": 1256,
        }
    ],
    expected_release="2026-03-01",
)
async def get_task_executions(
    task_id: int,
    user: User = Depends(current_user),
    _=Depends(require_permissions(TaskPermission.VIEW, bypass_superuser=True)),
):
    pass
```

---

## 3. Mock模块创建计划

### 3.1 文件结构规划

```
src/api/v1/
├── __init__.py              # 路由汇总
├── task.py                  # 任务管理 (改造)
├── analytics.py             # 仪表盘分析 [新增]
├── shops.py                 # 店铺管理 [新增]
├── metrics.py               # 指标详情 [新增]
├── reports.py               # 报表管理 [新增]
├── schedules.py             # 任务调度 [新增]
├── analysis.py              # 数据分析 [新增]
└── alerts.py                # 风险预警 [新增]
```

### 3.2 模块职责划分

| 模块 | 前端页面 | 端点数量 | 核心数据 |
|------|---------|---------|---------|
| analytics.py | Dashboard | 3 | GMV、趋势、渠道 |
| shops.py | Compass | 2 | 店铺列表、体验分 |
| metrics.py | Metric Detail | 1 | 指标详情 |
| reports.py | Reports | 1 | 报表数据 |
| schedules.py | Task Schedule | 1 | 调度计划 |
| analysis.py | Data Analysis | 1 | 分析结果 |
| alerts.py | Dashboard | 1 | 预警列表 |
| task.py | - | 4 | 任务状态 |

---

## 4. 各模块Mock数据规范

### 4.1 analytics.py - 仪表盘分析

```python
# /api/v1/analytics/kpi
{
    "gmv": 1250000.00,
    "order_count": 3456,
    "conversion_rate": 3.24,
    "gmv_change": 12.5,
    "order_change": 8.3,
    "conversion_change": -0.5
}

# /api/v1/analytics/trend
{
    "period": "30d",
    "granularity": "day",
    "data": [
        {"date": "2026-01-15", "gmv": 45000, "orders": 120, "visitors": 3500},
        {"date": "2026-01-16", "gmv": 52000, "orders": 145, "visitors": 3800}
    ]
}

# /api/v1/analytics/channel
{
    "channels": [
        {"name": "短视频", "gmv": 500000, "占比": 40.0, "orders": 1382},
        {"name": "直播", "gmv": 375000, "占比": 30.0, "orders": 1037},
        {"name": "店铺", "gmv": 375000, "占比": 30.0, "orders": 1037}
    ]
}
```

### 4.2 shops.py - 店铺管理

```python
# /api/v1/shops
{
    "shops": [
        {
            "id": 1,
            "name": "旗舰店",
            "category": "服装",
            "status": "active",
            "gmv": 1250000,
            "score": 4.8,
            "products_count": 256
        }
    ],
    "total": 10,
    "page": 1,
    "size": 20
}

# /api/v1/shops/{id}/score
{
    "shop_id": 1,
    "shop_name": "旗舰店",
    "overall_score": 4.8,
    "dimensions": [
        {"name": "商品体验", "score": 4.6, "weight": 0.4, "rank": 120},
        {"name": "物流体验", "score": 4.9, "weight": 0.35, "rank": 45},
        {"name": "服务体验", "score": 4.7, "weight": 0.25, "rank": 89}
    ],
    "trend": [
        {"date": "2026-01-01", "score": 4.7},
        {"date": "2026-01-08", "score": 4.75},
        {"date": "2026-01-15", "score": 4.8}
    ]
}
```

### 4.3 metrics.py - 指标详情

```python
# /api/v1/metrics/{type}
# type: product | logistics | service | risk

{
    "type": "product",
    "period": "30d",
    "overview": {
        "total_products": 1256,
        "sold_products": 892,
        "return_rate": 2.3,
        "complaint_rate": 0.8
    },
    "top_products": [
        {"id": 1, "name": "爆款T恤", "sales": 12500, "gmv": 250000}
    ],
    "categories": [
        {"name": "服装", "gmv": 450000, "占比": 36.0},
        {"name": "数码", "gmv": 320000, "占比": 25.6}
    ]
}
```

### 4.4 reports.py - 报表管理

```python
# /api/v1/reports
{
    "reports": [
        {
            "id": 1,
            "name": "月度销售报表",
            "type": "sales",
            "status": "generated",
            "created_at": "2026-01-01T00:00:00",
            "period": "2026-01"
        },
        {
            "id": 2,
            "name": "商品分析报表",
            "type": "product_analysis",
            "status": "generating",
            "created_at": "2026-01-15T10:00:00"
        }
    ],
    "total": 5
}
```

### 4.5 schedules.py - 任务调度

```python
# /api/v1/schedules
{
    "schedules": [
        {
            "id": 1,
            "name": "每日GMV统计",
            "cron": "0 9 * * *",
            "timezone": "Asia/Shanghai",
            "status": "active",
            "last_run": "2026-01-15T09:00:00",
            "next_run": "2026-01-16T09:00:00"
        },
        {
            "id": 2,
            "name": "商品库存同步",
            "cron": "0 */4 * * *",
            "timezone": "Asia/Shanghai",
            "status": "paused",
            "last_run": "2026-01-15T08:00:00",
            "next_run": null
        }
    ],
    "total": 3
}
```

### 4.6 analysis.py - 数据分析

```python
# /api/v1/analysis
{
    "analyses": [
        {
            "id": 1,
            "name": "Q1销售趋势分析",
            "type": "trend_analysis",
            "status": "completed",
            "created_at": "2026-01-10T10:00:00",
            "completed_at": "2026-01-10T10:05:00",
            "result_summary": "GMV环比增长12.5%，直播渠道贡献最大"
        }
    ],
    "total": 8,
    "recent_insights": [
        {
            "title": "转化率提升建议",
            "description": "建议优化详情页图片质量",
            "impact": "high",
            "confidence": 0.85
        }
    ]
}
```

### 4.7 alerts.py - 风险预警

```python
# /api/v1/alerts
{
    "alerts": [
        {
            "id": 1,
            "level": "critical",
            "title": "GMV下降预警",
            "description": "近7天GMV环比下降15%，超过预警阈值",
            "category": "business",
            "status": "unread",
            "created_at": "2026-01-15T10:00:00"
        },
        {
            "id": 2,
            "level": "warning",
            "title": "物流延迟",
            "description": "中通快递配送时效延长至3.5天",
            "category": "logistics",
            "status": "read",
            "created_at": "2026-01-14T15:30:00"
        },
        {
            "id": 3,
            "level": "info",
            "title": "新商品上架",
            "description": "竞品店铺新增爆款商品，建议关注",
            "category": "competitor",
            "status": "unread",
            "created_at": "2026-01-13T09:00:00"
        }
    ],
    "summary": {
        "critical": 1,
        "warning": 5,
        "info": 12,
        "total": 18,
        "unread": 8
    }
}
```

---

## 5. 实现优先级

| 优先级 | 模块 | 端点数量 | 关联页面 | 预估工时 |
|--------|------|---------|---------|---------|
| P0 | analytics.py | 3 | Dashboard | 2h |
| P0 | alerts.py | 1 | Dashboard | 1h |
| P0 | task.py | 4 | 任务管理 | 2h (改造) |
| P1 | shops.py | 2 | Compass | 1.5h |
| P1 | metrics.py | 1 | Metric Detail | 1h |
| P2 | reports.py | 1 | Reports | 1h |
| P2 | schedules.py | 1 | Task Schedule | 1h |
| P2 | analysis.py | 1 | Data Analysis | 1h |

---

## 6. 实施步骤

### 步骤1：权限系统完善
- 修改 `src/auth/permissions.py` 添加新权限类
- 确保RBAC依赖注入正常工作

### 步骤2：创建路由模块
- 按优先级顺序创建各模块文件
- 使用 `in_development` 装饰器封装Mock数据

### 步骤3：路由注册
- 在 `src/api/v1/__init__.py` 中导入并注册所有路由

### 步骤4：权限测试
- 验证无权限用户返回 401
- 验证有权限用户返回Mock数据
- 验证响应格式符合 `Response[T]` 规范

---

## 7. 后续扩展

### 7.1 Mock数据工厂
创建 `src/api/v1/mocks/factory.py` 支持动态生成：

```python
from faker import Faker

faker = Faker('zh_CN')

def generate_kpi_mock() -> dict:
    return {
        "gmv": faker.pydecimal(left_digits=7, right_digits=2, positive=True),
        "order_count": faker.random_int(min=1000, max=10000),
        "conversion_rate": round(faker.pyfloat(min_value=1.0, max_value=5.0), 2),
    }
```

### 7.2 Mock数据版本管理
- 按API版本组织Mock数据
- 支持渐进式切换到真实数据源

---

## 8. 风险与对策

| 风险 | 影响 | 对策 |
|------|------|------|
| Mock数据与真实API不一致 | 前端联调困难 | 统一数据结构定义文档 |
| 权限遗漏 | 安全漏洞 | 全量审查所有端点 |
| 性能问题 | 响应延迟 | Mock数据保持简洁，避免复杂计算 |
