# Skill: 风险预警模块

## 功能列表

| 功能 | 描述 |
|------|------|
| 预警配置 | 阈值配置 |
| 预警列表 | 查看 + 标记已处理 |
| 邮件通知 | 告警邮件发送 |

## 预警类型

```
阈值预警 - 指标超过设定阈值
任务预警 - 任务执行失败
```

## 预警等级

```
P0 - 紧急  # 立即处理
P1 - 高    # 尽快处理
P2 - 低    # 关注
```

## API端点

```bash
# 预警规则
GET    /api/v1/alerts/rules             # 规则列表
POST   /api/v1/alerts/rules             # 创建规则
GET    /api/v1/alerts/rules/{id}        # 规则详情
PUT    /api/v1/alerts/rules/{id}        # 更新规则
DELETE /api/v1/alerts/rules/{id}        # 删除规则
POST   /api/v1/alerts/rules/{id}/enable # 启用规则
POST   /api/v1/alerts/rules/{id}/disable # 禁用规则

# 预警中心
GET    /api/v1/alerts                   # 预警列表
GET    /api/v1/alerts/{id}              # 预警详情
POST   /api/v1/alerts/{id}/handle       # 标记已处理

# 邮件配置
GET    /api/v1/alerts/email-config      # 邮件配置
PUT    /api/v1/alerts/email-config      # 更新邮件配置
```

## 文件位置

```
src/
├── api/v1/alerts/
│   └── router.py

├── schemas/
│   └── alerts.py

├── services/
│   └── alert_service.py

├── repositories/
│   └── alert_repository.py

└── models/
    └── alert.py
```

## 实现要求

### 预警规则配置

- 阈值条件: >, <, >=, <=
- 支持启用/禁用

### 预警通知

- 邮件通知
- 告警抑制: 相同预警N分钟内不重复通知

### 预警处理流程

1. 预警触发 → 记录预警
2. 发送通知 → 通知负责人
3. 处置反馈 → 标记已处理
