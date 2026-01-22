# Skill: 风险预警模块

## 功能列表

| 功能 | 描述 | 角色 |
|------|------|------|
| 预警规则配置 | 阈值/波动/延迟/漏抓规则配置 | Super/Admin |
| 预警中心 | 预警列表、等级、处置状态、备注与指派 | Admin/User |
| 通知渠道配置 | 企业微信/邮件/短信等通知方式配置 | Super/Admin |

## 预警类型

```
预警类型:
├── 业务预警 (Business Alerts)
│   ├── 阈值预警 (Threshold Alert)      # 指标超过阈值
│   ├── 波动预警 (Fluctuation Alert)    # 指标波动异常
│   └── 趋势预警 (Trend Alert)          # 趋势反转预警
│
├── 数据预警 (Data Alerts)
│   ├── 延迟预警 (Delay Alert)          # 数据延迟到达
│   ├── 漏抓预警 (Missing Alert)        # 数据抓取遗漏
│   └── 失败预警 (Failure Alert)        # 任务执行失败
│
└── 系统预警 (System Alerts)
    ├── 服务预警 (Service Alert)        # 服务不可用
    ├── 容量预警 (Capacity Alert)       # 存储空间不足
    └── 性能预警 (Performance Alert)    # 响应时间过长
```

## 预警等级

```
预警等级:
├── P0 - 紧急 (Critical)        # 立即处理，影响核心业务
├── P1 - 高 (High)              # 尽快处理，影响业务
├── P2 - 中 (Medium)            # 计划处理，略有影响
└── P3 - 低 (Low)               # 关注即可，潜在风险
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
PUT    /api/v1/alerts/{id}              # 更新预警
POST   /api/v1/alerts/{id}/acknowledge  # 确认预警
POST   /api/v1/alerts/{id}/assign       # 指派预警
POST   /api/v1/alerts/{id}/resolve      # 解决预警
POST   /api/v1/alerts/{id}/feedback     # 反馈处理

# 通知渠道
GET    /api/v1/notifications/channels   # 渠道列表
POST   /api/v1/notifications/channels   # 创建渠道
PUT    /api/v1/notifications/channels/{id} # 更新渠道
DELETE /api/v1/notifications/channels/{id} # 删除渠道
POST   /api/v1/notifications/channels/{id}/test # 测试渠道
```

## 文件位置

```
src/api/v1/alerts/
├── router.py
├── views.py
└── schemas.py

src/api/v1/notifications/
├── router.py
├── views.py
└── schemas.py

src/domains/alerts/            # 预警领域
```

## 实现要求

### 预警规则配置

- 阈值条件: >, <, >=, <=, ==, !=
- 波动条件: 环比变化百分比
- 延迟条件: 数据更新时间差
- 支持启用/禁用

### 预警通知

- 支持多渠道: 企业微信、邮件、短信
- 通知模板可配置
- 告警抑制: 相同预警N分钟内不重复通知

### 预警处理流程

1. 预警触发 → 记录预警
2. 发送通知 → 通知负责人
3. 确认预警 → 记录确认人
4. 指派处理 → 指派给具体人
5. 解决反馈 → 记录解决方案
