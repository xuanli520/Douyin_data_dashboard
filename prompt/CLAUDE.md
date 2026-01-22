# CLAUDE.md

This file provides guidance to any coding agent when working on this repository.

## Project Introduction

**Douyin Data Dashboard** - 抖音数据可视化中台系统

基于抖店平台数据，构建自动化数据采集、处理、分析与展示的可视化中台。

## Architecture Overview

项目采用 **DDD (Domain-Driven Design)** 架构模式，基于 FastAPI 框架构建：

```
src/
├── api/           # 表示层 - HTTP API
├── domains/       # 领域层 - 业务逻辑
├── services/      # 应用服务层
├── repositories/  # 仓储实现层
├── middleware/    # 中间件层
├── models/        # 数据库模型
├── schemas/       # Pydantic Schema
├── tasks/         # Celery异步任务
└── utils/         # 工具模块
```

## Key Modules

| Module | Path | Description |
|--------|------|-------------|
| 账号权限 | `src/auth/` | JWT认证、RBAC权限 |
| 数据接入 | `src/domains/data_source/` | 数据源管理 |
| 任务调度 | `src/domains/tasks/` | Celery定时任务 |
| 指标分析 | `src/domains/metrics/` | 数据指标计算 |
| 风险预警 | `src/domains/alerts/` | 预警规则与通知 |
| 报表导出 | `src/domains/reports/` | 报表生成与导出 |

## Development Standards

### Architecture Patterns

- **DDD**: 领域层包含 entities, repositories, services, models, schemas
- **API**: 遵循 `api/v1/{module}/views.py` 结构
- **Tasks**: Celery任务按类型分组在 `tasks/` 目录

### Code Style

- Python 3.12+, 类型注解完整
- 异步/await 用于所有I/O操作
- 使用 Pydantic Schema 定义请求/响应
- 遵循 `snake_case` 命名规范

## Available Skills

查看 `prompt/skills/` 目录获取各模块的详细设计规范：

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

## Reading Skills

开发前应查阅相关 skill 文档：

1. **新功能开发**: 先读 `01-architecture.md` 和对应模块文档
2. **API开发**: 参考对应模块的 API 端点定义
3. **任务开发**: 参考 `04-tasks-module.md` 任务类型定义
4. **数据库变更**: 参考 `08-database.md` 表结构设计

## Quick Reference

### Common File Locations

```bash
# 添加新API模块
src/api/v1/{module}/views.py      # 视图函数
src/api/v1/{module}/router.py     # 路由注册
src/api/v1/{module}/schemas.py    # 请求响应模型

# 添加新领域
src/domains/{module}/             # 领域模块目录
src/domains/{module}/models.py    # ORM模型
src/domains/{module}/services.py  # 领域服务

# 添加新任务
tasks/{category}/{module}.py      # Celery任务
```

### Commands

```bash
# 运行开发服务器
uv run uvicorn src.main:app --reload

# 运行Celery Worker
uv run celery -A tasks worker -l info

# 运行Celery Beat
uv run celery -A tasks beat -l info

# 运行测试
uv run pytest
```
