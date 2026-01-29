# CLAUDE.md

This file provides guidance to any coding agent when working on this repository.

## Project Introduction

**Douyin Data Dashboard** - 抖音数据可视化中台系统

基于抖店平台数据，构建自动化数据采集、处理、分析与展示的可视化中台。

Modern FastAPI Boilerplate with authentication, RBAC, caching, monitoring, circuit breaker, and more.

## Architecture Overview

项目采用 **模块化架构**，基于 FastAPI 框架构建：

```
src/
├── api/            # 表示层 - HTTP 路由 + 处理
├── auth/           # 认证授权模块
├── audit/          # 审计日志模块
├── cache/          # 缓存模块 (Redis/本地)
├── config/         # 配置管理
├── core/           # 核心业务逻辑
├── middleware/     # 中间件 (CORS, rate limit, monitoring)
├── responses/      # 标准化响应格式
└── shared/         # 跨切面关注点
```

## Development Standards

### Commands
```bash
just dev          # Install dependencies
just hooks        # Install pre-commit hooks
just check        # Run formatting & linting
just run          # Start dev server (uvicorn --reload)
just test         # Run tests (pytest)
just db-migrate   # Generate migration
just db-upgrade   # Apply migrations
```

### Key Technologies
- **Framework**: FastAPI 0.115+
- **Python**: 3.12+
- **Package Manager**: `uv`
- **Task Runner**: `just`
- **Database**: SQLModel + Alembic
- **Cache**: Redis
- **Auth**: fastapi-users with JWT

### Features
- Authentication with fastapi-users
- Role-Based Access Control (RBAC)
- Redis caching with protocol abstraction
- Circuit breaker pattern
- Prometheus monitoring
- Rate limiting
- CORS middleware
- Standardized JSON responses
- Retry mechanism with tenacity
- Alibaba Cloud CAPTCHA

## Quick Reference

### Common File Locations

```bash
# API 路由
src/api/{module}.py

# 认证模块
src/auth/

# 缓存
src/cache/

# 配置
src/config/

# 中间件
src/middleware/
```

### Available Skills

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

## AGENTS.md

核心规则请参考 `AGENTS.md`，所有 agent 规则文件保持同步。