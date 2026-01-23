# Skill: 系统架构总览

项目使用 **分层架构**，基于 FastAPI + PostgreSQL + Celery 构建。

## 技术栈

- **后端**: FastAPI (Python 3.12+)
- **数据库**: PostgreSQL + Redis
- **认证**: JWT + RBAC
- **任务调度**: Celery + Redis
- **部署**: Docker

## 分层架构

```
客户端 → api/v1/{module}/router.py → service → repository → models
                               ↓
                            schemas/
                               ↓
                            HTTP Response
```

## 目录结构

```
src/
├── api/                      # 表示层 - HTTP 路由 + 处理
│   ├── deps.py               # 依赖注入
│   ├── v1/
│   │   ├── router.py         # 主路由
│   │   ├── users/
│   │   │   ├── router.py     # 路由 + 视图函数
│   │   │   └── __init__.py   # 导出 router
│   │   └── orders/
│   │       ├── router.py
│   │       └── __init__.py
│   └── v2/
│
├── schemas/                  # Pydantic Schema
│   ├── __init__.py
│   ├── auth.py
│   ├── users.py
│   ├── orders.py
│   ├── metrics.py
│   └── common.py
│
├── services/                 # 应用服务层
│   ├── __init__.py
│   ├── auth_service.py
│   ├── user_service.py
│   ├── order_service.py
│   └── ...
│
├── repositories/             # 仓储层
│   ├── __init__.py
│   ├── user_repository.py
│   ├── order_repository.py
│   └── ...
│
└── models/                   # ORM 模型
    ├── __init__.py
    ├── user.py
    └── order.py
```

## 层职责

| 层 | 位置 | 职责 |
|---|------|------|
| API | `src/api/v1/{module}/` | 路由注册 + HTTP 处理 |
| Schema | `src/schemas/` | 请求/响应数据模型定义 |
| Service | `src/services/` | 业务逻辑编排、调用仓储层 |
| Repository | `src/repositories/` | 数据访问封装 |
| Model | `src/models/` | ORM 映射、数据库表定义 |

## 文件放置规范

| 内容 | 位置 |
|------|------|
| 路由 + 视图函数 | `src/api/v1/{module}/router.py` |
| 请求/响应 Schema | `src/schemas/{module}.py` |
| 业务逻辑 | `src/services/{module}_service.py` |
| 数据访问 | `src/repositories/{module}_repository.py` |
| ORM 模型 | `src/models/{module}.py` |

## 添加新模块

1. `src/models/{module}.py` - 定义 ORM 模型
2. `src/repositories/{module}_repository.py` - 实现数据访问
3. `src/schemas/{module}.py` - 定义请求/响应
4. `src/services/{module}_service.py` - 编写业务逻辑
5. `src/api/v1/{module}/` - 路由 + 视图函数

## 配置文件

- `.env` - 环境变量
- `docker-compose.yml` - 容器配置
- `alembic.ini` - 数据库迁移
