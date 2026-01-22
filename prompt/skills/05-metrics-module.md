# Skill: 指标分析模块

## 功能列表

| 功能 | 描述 | 角色 |
|------|------|------|
| 经营总览Dashboard | 店铺体验分、投诉总量、工作总量等关键指标总览 | Admin/User |
| 电商罗盘分析 | 趋势、分渠道/分店铺、Top/Bottom、钻取明细 | Admin/User |
| 投诉分析 | 投诉量趋势、原因分类、处理时效、异常点 | Admin/User |
| 工作量与效率 | 工单/任务量、处理效率、人员/团队对比 | Admin/User |
| 明细数据查询 | 多条件筛选、分页、字段自定义、导出 | Admin/User |

## 指标体系

```
指标分类:
├── 经营指标 (Business Metrics)
│   ├── 店铺体验分 (Shop Score)
│   ├── GMV (Gross Merchandise Volume)
│   ├── 订单量 (Order Count)
│   ├── 客单价 (Average Order Value)
│   └── 转化率 (Conversion Rate)
│
├── 订单指标 (Order Metrics)
│   ├── 订单金额 (Order Amount)
│   ├── 订单数量 (Order Quantity)
│   ├── 退款金额 (Refund Amount)
│   ├── 退款率 (Refund Rate)
│   └── 完单率 (Completion Rate)
│
├── 商品指标 (Product Metrics)
│   ├── 商品数 (Product Count)
│   ├── 在售商品数 (Active Products)
│   ├── 商品销量 (Product Sales)
│   └── 商品销售额 (Product Revenue)
│
├── 售后指标 (After-sales Metrics)
│   ├── 投诉量 (Complaint Count)
│   ├── 投诉率 (Complaint Rate)
│   ├── 售后处理时长 (Processing Time)
│   └── 满意度 (Satisfaction Score)
│
└── 运营指标 (Operation Metrics)
    ├── 工单量 (Ticket Count)
    ├── 处理效率 (Processing Efficiency)
    ├── 响应时间 (Response Time)
    └── 团队产出 (Team Output)
```

## API端点

```bash
# 经营总览
GET    /api/v1/dashboard/overview      # 经营总览数据
GET    /api/v1/dashboard/kpis          # KPI指标列表
GET    /api/v1/dashboard/charts        # 图表数据

# 指标分析
GET    /api/v1/metrics                 # 指标列表
GET    /api/v1/metrics/{id}            # 指标详情
GET    /api/v1/metrics/trend           # 趋势数据
GET    /api/v1/metrics/comparison      # 对比数据
GET    /api/v1/metrics/ranking         # 排名数据
POST   /api/v1/metrics/custom          # 自定义指标

# 订单分析
GET    /api/v1/orders/summary          # 订单汇总
GET    /api/v1/orders/trend            # 订单趋势
GET    /api/v1/orders/analysis         # 订单分析
GET    /api/v1/orders/details          # 订单明细

# 商品分析
GET    /api/v1/products/summary        # 商品汇总
GET    /api/v1/products/trend          # 商品趋势
GET    /api/v1/products/analysis       # 商品分析
GET    /api/v1/products/ranking        # 商品排名
GET    /api/v1/products/details        # 商品明细

# 销售分析
GET    /api/v1/sales/summary           # 销售汇总
GET    /api/v1/sales/trend             # 销售趋势
GET    /api/v1/sales/analysis          # 销售分析
GET    /api/v1/sales/by-channel        # 渠道销售
GET    /api/v1/sales/by-shop           # 店铺销售

# 投诉分析
GET    /api/v1/complaints/summary      # 投诉汇总
GET    /api/v1/complaints/trend        # 投诉趋势
GET    /api/v1/complaints/analysis     # 投诉分析
GET    /api/v1/complaints/categories   # 投诉分类
GET    /api/v1/complaints/details      # 投诉明细

# 工作量分析
GET    /api/v1/workload/summary        # 工作量汇总
GET    /api/v1/workload/trend          # 工作量趋势
GET    /api/v1/workload/by-person      # 个人工作量
GET    /api/v1/workload/by-team        # 团队工作量
GET    /api/v1/workload/efficiency     # 效率分析

# 明细查询
POST   /api/v1/query/orders            # 订单明细查询
POST   /api/v1/query/products          # 商品明细查询
POST   /api/v1/query/sales             # 销售明细查询
POST   /api/v1/query/complaints        # 投诉明细查询
GET    /api/v1/query/export            # 查询结果导出
```

## 文件位置

```
src/
├── api/v1/dashboard/
│   └── router.py

├── api/v1/metrics/
│   └── router.py

├── api/v1/orders/
│   └── router.py

├── api/v1/products/
│   └── router.py

├── api/v1/sales/
│   └── router.py

├── schemas/
│   ├── dashboard.py
│   ├── metrics.py
│   ├── orders.py
│   ├── products.py
│   └── sales.py

├── services/
│   ├── dashboard_service.py
│   ├── metric_service.py
│   ├── order_service.py
│   ├── product_service.py
│   └── sales_service.py

├── repositories/
│   ├── metric_repository.py
│   ├── order_repository.py
│   ├── product_repository.py
│   └── sales_repository.py

└── models/
    ├── metric.py
    ├── order.py
    ├── product.py
    └── sales.py
```

## 实现要求

### 指标计算

- 指标值存储在 `metrics_values` 表
- 支持日/周/月聚合
- 定时刷新指标缓存

### 查询优化

- 使用Redis缓存热点数据
- 分页查询
- 避免N+1查询
