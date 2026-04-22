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

## 核心功能

- **数据采集** - Playwright 自动化登录抖店后台，采集店铺经营数据
- **采集编排** - 计划构建器、运行时加载器、店铺切换、账号店铺目录
- **数据导入** - Excel 文件解析与批量导入
- **体验分析** - 体验分概览、趋势、问题诊断、维度下钻
- **店铺看板** - KPI 概览、指标监控、数据可视化
- **任务调度** - funboost 分布式任务队列 + beat 定时调度
- **告警通知** - 自定义告警规则与通知推送
- **报表导出** - 数据分析报表生成与导出
- **ETL 管道** - 订单、商品数据清洗转换
- **LLM 数据补全** - 智能体补充冷数据缺失字段
- **审计日志** - 全链路操作审计

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

## 任务调度系统

基于 funboost 构建的分布式任务系统：

- **Worker** - 采集任务执行器，支持幂等性保证
- **Beat Scheduler** - 定时任务调度，管理周期性采集计划
- **队列映射** - 任务类型到消息队列的路由配置
- **熔断器** - 任务执行异常时自动熔断保护

## 开发环境搭建

### 前置依赖

- Python >= 3.12
- [uv](https://github.com/astral-sh/uv)
- [just](https://github.com/casey/just)
- PostgreSQL
- Redis

### 安装步骤

```bash
# 安装依赖
just dev

# 安装 pre-commit hooks
just hooks

# 数据库迁移
just db-upgrade

# 启动开发服务器
just run
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
| `just db-current` | 查看当前迁移版本 |
| `just db-history` | 查看迁移历史 |
| `just funboost-worker` | 启动 funboost worker |
| `just funboost-beat` | 启动 beat 调度器 |
| `just arch-check` | 架构检查 |
| `just ci-gate` | CI 门禁检查 |

## 抖店登录状态管理

- 登录会话持久化使用 Playwright `storage_state` 文件
- 采集流程锁策略：店铺级锁用于采集，账号级锁用于浏览器刷新
- 账号过期时采集返回降级数据，跳过浏览器刷新

## 贡献指南

详见 [CONTRIBUTIONS.md](/CONTRIBUTIONS.md)。
