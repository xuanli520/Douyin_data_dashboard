# CLAUDE.md

This file provides guidance to any coding agent when working on this repository.

## Project Introduction

**Douyin Data Dashboard** - 抖音数据可视化中台系统

基于抖店平台数据，构建自动化数据采集、处理、分析与展示的可视化中台。

## Architecture Overview

项目采用 **分层架构**，基于 FastAPI 框架构建：

```
src/
├── api/            # 表示层 - HTTP 路由 + 处理
├── schemas/        # Schema 层 - Pydantic 模型
├── services/       # 服务层 - 业务逻辑
├── repositories/   # 仓储层 - 数据访问
└── models/         # ORM 模型
```

## Directory Structure

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
├── schemas/                  # Schema 定义
│   ├── __init__.py
│   ├── auth.py
│   ├── users.py
│   ├── orders.py
│   ├── metrics.py
│   └── common.py
│
├── services/                 # 服务层
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

## Layer Responsibilities

| Layer | Location | Responsibility |
|-------|----------|----------------|
| API | `src/api/v1/{module}/` | 路由注册 + HTTP 处理 |
| Schema | `src/schemas/` | 请求/响应数据模型定义 |
| Service | `src/services/` | 业务逻辑编排、调用仓储层 |
| Repository | `src/repositories/` | 数据访问封装 |
| Model | `src/models/` | ORM 映射、数据库表定义 |

## Development Standards

### Code Flow

```
HTTP Request → api/v1/{module}/router.py → service → repository → models
                                        ↓
                                   schemas/
                                        ↓
                                   HTTP Response
```

### File Placement

| Content | Location |
|---------|----------|
| 路由 + 视图函数 | `src/api/v1/{module}/router.py` |
| 请求/响应 Schema | `src/schemas/{module}.py` |
| 业务逻辑 | `src/services/{module}_service.py` |
| 数据访问 | `src/repositories/{module}_repository.py` |
| ORM 模型 | `src/models/{module}.py` |

### Naming Conventions

- Router: `APIRouter`
- Schema: `PascalCase` + `Request`/`Response` 后缀
- Service: `PascalCase` + `Service` 后缀
- Repository: `PascalCase` + `Repository` 后缀

### Adding New Feature

1. **Models**: `src/models/{module}.py` 定义 ORM 模型
2. **Repository**: `src/repositories/{module}_repository.py` 实现数据访问
3. **Schema**: `src/schemas/{module}.py` 定义请求/响应
4. **Service**: `src/services/{module}_service.py` 编写业务逻辑
5. **Router**: `src/api/v1/{module}/router.py` 路由 + 视图函数

## Available Skills

查看 `prompt/skills/` 目录获取各模块详细设计规范：

```
prompt/skills/
├── 01-architecture.md      # 系统架构总览
├── 02-auth-module.md       # 账号权限模块
├── 03-data-source-module.md # 数据接入模块
├── 04-tasks-module.md      # 任务调度模块
├── 05-metrics-module.md    # 指标分析模块
├── 06-alerts-module.md     # 风险预警模块
├── 07-reports-module.md    # 报表导出模块
├── 08-database.md          # 数据库设计
└── 09-deployment.md        # 部署配置
```

## Quick Reference

### Common File Locations

```bash
# 路由 + 视图函数
src/api/v1/{module}/router.py

# Schema 定义
src/schemas/{module}.py

# 服务层
src/services/{module}_service.py

# 仓储实现
src/repositories/{module}_repository.py

# ORM 模型
src/models/{module}.py
```

### Commands

```bash
# 运行开发服务器
uv run uvicorn src.main:app --reload

# 运行 Celery Worker
uv run celery -A tasks worker -l info

# 运行 Celery Beat
uv run celery -A tasks beat -l info

# 运行测试
uv run pytest
```
