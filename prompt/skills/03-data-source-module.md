# Skill: 数据接入模块

## 功能列表

| 功能 | 描述 | 角色 |
|------|------|------|
| 数据源管理 | 配置抖店导出表、截图抓取、人工表三类数据源 | Super/Admin |
| 数据导入/上传 | 上传导出表、字段映射、导入校验、失败回滚 | Super/Admin |
| 抓取规则配置 | 截图/网页源码特征提取规则、更新频率、失败告警 | Super/Admin |
| 人工数据录入 | 补录/修正人工表、版本记录、审批(可选) | Admin/User |
| 数据质量监控 | 缺失/重复/口径异常提示、数据延迟提示 | Super/Admin |

## 数据源类型

```
数据源类型:
├── 抖店导出表 (DouyinExport)
│   ├── 订单数据 (Orders)
│   ├── 商品数据 (Products)
│   └── 销售数据 (Sales)
│
├── 截图/网页源码 (Scraped)
│   ├── 截图数据 (Screenshots)
│   └── 网页源码 (WebSource)
│
└── 人工维护表 (Manual)
    ├── 竞品数据 (Competitor)
    └── 用户画像 (UserProfile)
```

## API端点

```bash
# 数据源管理
GET    /api/v1/data-sources            # 数据源列表
POST   /api/v1/data-sources            # 创建数据源
GET    /api/v1/data-sources/{id}       # 数据源详情
PUT    /api/v1/data-sources/{id}       # 更新数据源
DELETE /api/v1/data-sources/{id}       # 删除数据源

# 数据导入
POST   /api/v1/data-import/upload      # 上传文件
POST   /api/v1/data-import/parse       # 解析文件
POST   /api/v1/data-import/validate   # 验证数据
POST   /api/v1/data-import/confirm    # 确认导入
GET    /api/v1/data-import/history    # 导入历史

# 抓取规则
GET    /api/v1/scraping/rules          # 抓取规则列表
POST   /api/v1/scraping/rules          # 创建抓取规则
GET    /api/v1/scraping/rules/{id}     # 规则详情
PUT    /api/v1/scraping/rules/{id}     # 更新规则
DELETE /api/v1/scraping/rules/{id}     # 删除规则
POST   /api/v1/scraping/rules/{id}/test # 测试规则

# 人工数据
GET    /api/v1/manual-data             # 人工数据列表
POST   /api/v1/manual-data             # 录入数据
PUT    /api/v1/manual-data/{id}        # 更新数据
DELETE /api/v1/manual-data/{id}        # 删除数据
POST   /api/v1/manual-data/{id}/approve # 审批(可选)

# 数据质量
GET    /api/v1/data-quality/issues     # 质量问题列表
GET    /api/v1/data-quality/stats      # 数据质量统计
POST   /api/v1/data-quality/check      # 触发质量检查
```

## 文件位置

```
src/
├── api/v1/data_source/
│   └── router.py

├── api/v1/data_import/
│   └── router.py

├── api/v1/scraping/
│   └── router.py

├── schemas/
│   ├── data_source.py
│   ├── data_import.py
│   └── scraping.py

├── services/
│   ├── data_source_service.py
│   ├── data_import_service.py
│   └── scraping_service.py

├── repositories/
│   ├── data_source_repository.py
│   ├── data_import_repository.py
│   └── scraping_repository.py

└── models/
    ├── data_source.py
    ├── data_import.py
    └── scraping.py
```

## 实现要求

### 数据导入流程

1. 上传文件 → 临时存储
2. 解析文件 → 提取数据
3. 校验数据 → 字段映射、格式校验
4. 确认导入 → 写入数据库
5. 失败回滚 → 事务回滚

### 抓取规则

- 规则包含: URL、特征提取规则、更新频率、超时设置
- 支持测试运行
- 失败自动告警
