# Skill: 任务调度模块

## 功能列表

| 功能 | 描述 | 角色 |
|------|------|------|
| 定时任务管理 | 按需求配置定时任务、触发关键环节 | Super/Admin |
| 任务运行监控 | 运行状态、耗时、重试、失败原因 | Super/Admin |
| 采集/计算日志 | ETL/指标计算日志、下载/查看 | Super/Admin |

## 任务类型

```
任务类型:
├── 采集任务 (Collection Tasks)
│   ├── douyin_orders_collect        # 抖店订单采集
│   ├── douyin_products_collect      # 抖店商品采集
│   ├── douyin_sales_collect         # 抖店销售采集
│   ├── screenshot_collect           # 截图数据提取
│   └── web_source_collect           # 网页源码抓取
│
├── 处理任务 (Processing Tasks)
│   ├── etl_orders                   # 订单ETL
│   ├── etl_products                 # 商品ETL
│   ├── etl_sales                    # 销售ETL
│   └── data_cleaning                # 数据清洗
│
├── 指标任务 (Metric Tasks)
│   ├── calculate_daily_metrics      # 日指标计算
│   ├── calculate_weekly_metrics     # 周指标计算
│   ├── calculate_monthly_metrics    # 月指标计算
│   └── refresh_dashboard            # 看板刷新
│
├── 导出任务 (Export Tasks)
│   ├── generate_daily_report        # 日报生成
│   ├── generate_weekly_report       # 周报生成
│   ├── generate_monthly_report      # 月报生成
│   └── export_data                  # 数据导出
│
└── 维护任务 (Maintenance Tasks)
    ├── cleanup_temp_data            # 临时数据清理
    ├── data_backup                  # 数据备份
    ├── health_check                 # 健康检查
    └── alert_check                  # 预警检查
```

## API端点

```bash
# 定时任务管理
GET    /api/v1/tasks                   # 任务列表
POST   /api/v1/tasks                   # 创建任务
GET    /api/v1/tasks/{id}              # 任务详情
PUT    /api/v1/tasks/{id}              # 更新任务
DELETE /api/v1/tasks/{id}              # 删除任务
POST   /api/v1/tasks/{id}/enable       # 启用任务
POST   /api/v1/tasks/{id}/disable      # 禁用任务
POST   /api/v1/tasks/{id}/run          # 手动触发任务

# 任务执行记录
GET    /api/v1/tasks/{id}/executions   # 执行记录列表
GET    /api/v1/tasks/{id}/executions/{eid} # 执行详情
POST   /api/v1/tasks/{id}/executions/{eid}/retry # 重试执行

# 任务监控
GET    /api/v1/tasks/monitor           # 任务监控状态
GET    /api/v1/tasks/stats             # 任务统计

# 任务日志
GET    /api/v1/tasks/{id}/logs         # 任务日志
GET    /api/v1/tasks/logs/download     # 下载日志
```

## 文件位置

```
src/
├── api/v1/tasks/
│   └── router.py                      # 路由 + 视图函数
│
├── schemas/
│   └── tasks.py
│
├── services/
│   └── task_service.py
│
├── repositories/
│   └── task_repository.py
│
└── models/
    └── task.py

tasks/
├── __init__.py
├── celery_app.py              # Celery应用配置
├── base.py                    # 任务基类
│
├──采集任务/
│   ├── douyin_orders.py
│   ├── douyin_products.py
│   ├── douyin_sales.py
│   ├── screenshot_scraper.py
│   └── web_scraper.py
│
├──处理任务/
│   ├── etl_orders.py
│   ├── etl_products.py
│   ├── etl_sales.py
│   └── data_cleaning.py
│
├──指标任务/
│   ├── calculate_metrics.py
│   ├── aggregate_metrics.py
│   └── refresh_dashboard.py
│
├──导出任务/
│   ├── generate_report.py
│   ├── export_data.py
│   └── send_notification.py
│
└──维护任务/
    ├── data_retention.py
    ├── cleanup_temp.py
    ├── backup_data.py
    └── health_check.py
```

## 实现要求

### Celery配置

- 使用 Redis 作为 Broker
- 支持任务优先级
- 任务重试: 最多3次, 指数退避
- 任务超时: 默认300秒

### 任务基类

```python
from tasks.base import BaseTask

class MyTask(BaseTask):
    name = "my_task"
    max_retries = 3
    default_retry_delay = 60

    def run(self, *args, **kwargs):
        # 任务逻辑
        pass
```
