# Skill: 系统架构总览

项目使用 DDD (Domain-Driven Design) 架构，基于 FastAPI + PostgreSQL + Celery 构建。

## 技术栈

- **后端**: FastAPI (Python 3.12+)
- **数据库**: PostgreSQL + Redis
- **认证**: JWT + RBAC
- **任务调度**: Celery + Redis
- **部署**: Docker

## 分层架构

```
客户端层 → API网关 → 应用服务 → 领域服务 → 基础设施
```

### 目录结构

```
src/
├── api/v1/          # 表示层 - HTTP API (views.py + schemas.py)
├── domains/         # 领域层 - 业务逻辑 (entities/repositories/services)
├── services/        # 应用服务层
├── tasks/           # Celery异步任务
├── models/          # ORM模型
├── schemas/         # Pydantic Schema
├── utils/           # 工具模块
└── middleware/      # 中间件
```

## 核心模块

| 模块 | 路径 | 功能 |
|------|------|------|
| auth | `src/auth/` | JWT认证、登录登出、Token刷新 |
| users | `src/api/v1/users/` | 用户管理CRUD |
| roles | `src/api/v1/roles/` | 角色权限管理 |
| dashboard | `src/api/v1/dashboard/` | 数据看板 |
| metrics | `src/api/v1/metrics/` | 指标分析 |
| orders | `src/api/v1/orders/` | 订单数据 |
| products | `src/api/v1/products/` | 商品数据 |
| sales | `src/api/v1/sales/` | 销售数据 |
| data_source | `src/api/v1/data_source/` | 数据源管理 |
| data_import | `src/api/v1/data_import/` | 数据导入 |
| scraping | `src/api/v1/scraping/` | 数据抓取 |
| tasks | `src/api/v1/tasks/` | 任务调度 |
| alerts | `src/api/v1/alerts/` | 风险预警 |
| reports | `src/api/v1/reports/` | 报表中心 |
| exports | `src/api/v1/exports/` | 导出管理 |
| system | `src/api/v1/system/` | 系统运维 |

## 开发规范

### 添加新API模块

1. 在 `src/api/v1/{module}/` 创建 `views.py`, `router.py`, `schemas.py`
2. 在 `src/domains/{module}/` 创建领域文件
3. 在 `src/services/` 创建应用服务

### 添加Celery任务

1. 任务放在 `tasks/{category}/` 目录
2. 继承 `BaseTask` 基类
3. 注册到 `celery_app`

## 配置文件

- `.env` - 环境变量
- `docker-compose.yml` - 容器配置
- `alembic.ini` - 数据库迁移
