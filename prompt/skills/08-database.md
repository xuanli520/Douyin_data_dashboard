# Skill：数据库设计

## 核心数据表

```
核心数据表：
├── auth_users                         # 用户表
├── auth_roles                         # 角色表
├── auth_permissions                   # 权限表
├── auth_user_roles                    # 用户角色关联
├── auth_role_permissions              # 角色权限关联
│
├── data_sources                       # 数据源表
├── data_import_records                # 数据导入记录
├── scraping_rules                     # 抓取规则表
├── manual_data_records                # 人工数据记录
├── data_quality_issues                # 数据质量问题表
│
├── scheduled_tasks                    # 定时任务表
├── task_executions                    # 任务执行记录
├── task_logs                          # 任务日志表
│
├── metrics_definitions                # 指标定义表
├── metrics_values                     # 指标值表
├── metrics_calculations               # 指标计算记录
│
├── orders                             # 订单数据表
├── products                           # 商品数据表
├── sales                              # 销售数据表
├── complaints                         # 投诉数据表
├── workload_records                   # 工作量记录表
│
├── alert_rules                        # 预警规则表
├── alerts                             # 预警记录表
├── alert_notifications                # 预警通知记录
│
├── reports                            # 报表记录表
├── report_templates                   # 报表模板表
├── export_tasks                       # 导出任务表
│
├── audit_logs                         # 审计日志表
├── login_logs                         # 登录日志表
│
└── system_config                      # 系统配置表
```

## ER图概要

```
┌─────────────┐       ┌─────────────┐
│   users     │───────│    roles    │
└─────────────┘       └─────────────┘
      │                     │
      │                     │
      ▼                     ▼
┌─────────────┐       ┌─────────────┐
│ permissions │<──────│   tasks     │
└─────────────┘       └─────────────┘
                           │
                           ▼
                   ┌─────────────┐
                   │  metrics    │
                   └─────────────┘
                           │
      ┌────────────────────┼────────────────────┐
      ▼                    ▼                    ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   orders    │     │  products   │     │   sales     │
└─────────────┘     └─────────────┘     └─────────────┘
      │                     │                    │
      └─────────────────────┼────────────────────┘
                            ▼
                   ┌─────────────┐
                   │   alerts    │
                   └─────────────┘
```

## ORM模型位置

```
src/models/
├── __init__.py
├── user.py                        # User、Role、Permission模型
├── task.py                        # 任务相关模型
├── metric.py                      # 指标相关模型
├── order.py                       # 订单模型
├── product.py                     # 商品模型
├── sales.py                       # 销售模型
├── alert.py                       # 预警模型
├── report.py                      # 报表模型
├── export.py                      # 导出模型
└── base.py                        # 基类模型
```

## 数据库迁移

- 使用Alembic进行版本管理
- 迁移脚本：`migrations/versions/`
- 命令：`alembic upgrade head`

## 优化建议

### 索引优化

- 常用查询字段建立索引
- 避免过多索引
- 复合索引顺序按查询频率

### 查询优化

- 使用分页查询
- 避免N+1查询
- 使用批量操作

### 缓存策略

- Redis缓存热点数据
- 设置合理过期时间
- 缓存更新策略：Cache-Aside
