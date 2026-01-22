# Skill: 报表导出模块

## 功能列表

| 功能 | 描述 | 角色 |
|------|------|------|
| 报表中心 | 日报/周报/月报生成与模板管理 | Admin/User |
| 导出管理 | 导出任务、历史记录、权限控制 | Admin/User |

## 报表类型

```
报表类型:
├── 经营报表 (Business Reports)
│   ├── 日报 (Daily Report)
│   ├── 周报 (Weekly Report)
│   └── 月报 (Monthly Report)
│
├── 分析报表 (Analysis Reports)
│   ├── 销售分析报告 (Sales Analysis)
│   ├── 商品分析报告 (Product Analysis)
│   ├── 售后分析报告 (After-sales Analysis)
│   └── 运营分析报告 (Operation Analysis)
│
└── 数据导出 (Data Exports)
    ├── 订单数据导出 (Orders Export)
    ├── 商品数据导出 (Products Export)
    ├── 销售数据导出 (Sales Export)
    └── 定制导出 (Custom Export)
```

## API端点

```bash
# 报表中心
GET    /api/v1/reports                  # 报表列表
POST   /api/v1/reports                  # 创建报表
GET    /api/v1/reports/{id}             # 报表详情
DELETE /api/v1/reports/{id}             # 删除报表
POST   /api/v1/reports/generate         # 生成报表
POST   /api/v1/reports/{id}/download    # 下载报表
GET    /api/v1/reports/templates        # 报表模板

# 报表模板
GET    /api/v1/reports/templates        # 模板列表
POST   /api/v1/reports/templates        # 创建模板
PUT    /api/v1/reports/templates/{id}   # 更新模板
DELETE /api/v1/reports/templates/{id}   # 删除模板

# 导出管理
GET    /api/v1/exports                  # 导出任务列表
POST   /api/v1/exports                  # 创建导出任务
GET    /api/v1/exports/{id}             # 导出任务详情
DELETE /api/v1/exports/{id}             # 取消导出
POST   /api/v1/exports/{id}/download    # 下载导出文件
GET    /api/v1/exports/history          # 导出历史
```

## 文件位置

```
src/api/v1/reports/
├── router.py
├── views.py
└── schemas.py

src/api/v1/exports/
├── router.py
├── views.py
└── schemas.py

src/domains/reports/        # 报表领域
src/domains/exports/        # 导出领域

templates/                   # 报告模板
├── daily_report.html
├── weekly_report.html
├── monthly_report.html
└── alert_notification.html

static/
├── css/report.css
└── js/report.js
```

## 实现要求

### 报表生成

- 异步生成, 通过Celery任务
- 支持HTML/PDF/Excel格式
- 模板引擎: Jinja2
- 生成后存储到文件存储

### 导出任务

- 异步导出, 大数据量分片处理
- 支持Excel/CSV格式
- 导出文件有效期: 7天
- 记录导出审计日志

### 文件存储

- 使用MinIO/S3存储文件
- 临时文件定期清理
- 导出文件下载URL签名
