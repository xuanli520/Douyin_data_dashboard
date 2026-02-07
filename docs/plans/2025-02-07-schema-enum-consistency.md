# Schema与Enum一致性修复实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标:** 修复后端数据源schemas与数据库枚举类型定义不一致的问题，确保API层、业务层、数据层使用统一的枚举定义。

**架构方案:** 
- 采用"单一数据源"原则：所有枚举定义统一放在`src/domains/{domain}/enums.py`
- Schemas层仅导入和使用enums层的枚举，不再重复定义
- 统一使用`StrEnum`作为枚举基类（Python 3.11+推荐）
- 修复`AuditLog`模型中枚举字段类型定义不完整的问题

**技术栈:** Python 3.12+, FastAPI, SQLModel, Pydantic v2

---

## 问题分析总结

### 1. 关键问题：DataSourceType枚举值不一致（严重）

**`src/domains/data_source/enums.py` (数据库层使用):**
```python
class DataSourceType(str, Enum):
    DOUYIN_SHOP = "DOUYIN_SHOP"
    DOUYIN_APP = "DOUYIN_APP"
    FILE_IMPORT = "FILE_IMPORT"
    SELF_HOSTED = "SELF_HOSTED"
```

**`src/domains/data_source/schemas.py` (API层使用):**
```python
class DataSourceType(StrEnum):
    DOUYIN_API = "DOUYIN_API"
    FILE_UPLOAD = "FILE_UPLOAD"
    DATABASE = "DATABASE"
    WEBHOOK = "WEBHOOK"
```

**影响:** 数据库模型使用enums.py中的定义，但API schemas使用不同的定义，导致数据持久化和API交互时类型不匹配。

### 2. 次要问题：ScrapingRuleType与ScrapingRuleStatus混淆

- 数据库模型使用`ScrapingRuleStatus` (ACTIVE/INACTIVE) 表示规则状态
- API schemas定义了`ScrapingRuleType` (ORDERS/PRODUCTS/USERS/COMMENTS) 表示规则类型
- 这两个是不同的概念，但命名容易引起混淆

### 3. 代码风格不一致

- 部分枚举使用`(str, Enum)`继承
- 部分枚举使用`StrEnum`（Python 3.11+推荐）
- 需要统一为`StrEnum`

### 4. AuditLog枚举字段类型不完整

**`src/audit/schemas.py`:**
```python
action: str = Field(nullable=False, max_length=64, index=True)
result: str = Field(nullable=False, max_length=32)
```

虽然定义了`AuditAction`和`AuditResult`枚举，但数据库字段类型为`str`，失去了类型安全。

---

## 实施任务清单

### Task 1: 统一enums.py中的枚举基类为StrEnum

**文件:**
- 修改: `src/domains/data_source/enums.py:1-59`
- 修改: `src/domains/data_import/enums.py:1-17`

**步骤1: 修改data_source/enums.py**

将所有枚举类从`(str, Enum)`改为继承`StrEnum`：

```python
from enum import StrEnum


class DataSourceStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ERROR = "ERROR"


class DataSourceType(StrEnum):
    DOUYIN_SHOP = "DOUYIN_SHOP"
    DOUYIN_APP = "DOUYIN_APP"
    FILE_IMPORT = "FILE_IMPORT"
    SELF_HOSTED = "SELF_HOSTED"


class ScrapingRuleStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class TargetType(StrEnum):
    """抖店罗盘主题类型"""

    SHOP_OVERVIEW = "SHOP_OVERVIEW"
    TRAFFIC = "TRAFFIC"
    PRODUCT = "PRODUCT"
    LIVE = "LIVE"
    CONTENT_VIDEO = "CONTENT_VIDEO"
    ORDER_FULFILLMENT = "ORDER_FULFILLMENT"
    AFTERSALE_REFUND = "AFTERSALE_REFUND"
    CUSTOMER = "CUSTOMER"
    ADS = "ADS"


class Granularity(StrEnum):
    """时间粒度"""

    HOUR = "HOUR"
    DAY = "DAY"
    WEEK = "WEEK"
    MONTH = "MONTH"


class IncrementalMode(StrEnum):
    """增量方式"""

    BY_DATE = "BY_DATE"
    BY_CURSOR = "BY_CURSOR"


class DataLatency(StrEnum):
    """数据延迟假设"""

    REALTIME = "REALTIME"
    T_PLUS_1 = "T+1"
    T_PLUS_2 = "T+2"
    T_PLUS_3 = "T+3"
```

**步骤2: 修改data_import/enums.py**

```python
from enum import StrEnum


class ImportStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"
    VALIDATION_FAILED = "VALIDATION_FAILED"


class FileType(StrEnum):
    EXCEL = "EXCEL"
    CSV = "CSV"
```

**步骤3: 运行测试验证**

```bash
cd /h/project/douyin/fix-schema-enum-consistency
python -c "from src.domains.data_source.enums import DataSourceType; print(DataSourceType.DOUYIN_SHOP)"
python -c "from src.domains.data_import.enums import ImportStatus; print(ImportStatus.PENDING)"
```

**步骤4: Commit**

```bash
git add src/domains/data_source/enums.py src/domains/data_import/enums.py
git commit -m "refactor(enums): unify enum base class to StrEnum for consistency"
```

---

### Task 2: 修复schemas.py中重复定义的枚举

**文件:**
- 修改: `src/domains/data_source/schemas.py:1-108`

**步骤1: 分析当前schemas.py中的问题**

当前文件定义了三个重复的枚举：
1. `DataSourceType` - 与enums.py中的定义完全不同
2. `DataSourceStatus` - 与enums.py中的定义相同但重复
3. `ScrapingRuleType` - 这是一个新概念，但命名容易与`ScrapingRuleStatus`混淆

**步骤2: 修改schemas.py**

删除重复的`DataSourceType`和`DataSourceStatus`枚举定义，改为从enums.py导入。

对于`ScrapingRuleType`，需要评估其用途：
- 如果确实需要表示"规则类型"（如ORDERS/PRODUCTS/USERS/COMMENTS），应该移到enums.py并命名为`ScrapingRuleCategory`或`DataType`以避免与`ScrapingRuleStatus`混淆
- 如果实际上应该使用`TargetType`（因为数据库模型中是`target_type`字段），则应该删除`ScrapingRuleType`，改用`TargetType`

根据数据库模型`ScrapingRule.target_type`使用`TargetType`枚举的事实，正确的修复方案是：

1. 删除`DataSourceType`、`DataSourceStatus`、`ScrapingRuleType`的定义
2. 从enums.py导入正确的枚举
3. 将`ScrapingRuleCreate.rule_type`和`ScrapingRuleResponse.rule_type`改为使用`TargetType`

**修改后的src/domains/data_source/schemas.py:**

```python
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.domains.data_source.enums import (
    DataSourceStatus,
    DataSourceType,
    TargetType,
)


class DataSourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: DataSourceType
    config: dict[str, Any] = Field(default_factory=dict)
    status: DataSourceStatus = DataSourceStatus.ACTIVE
    description: str | None = Field(None, max_length=500)


class DataSourceUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    config: dict[str, Any] | None = None
    status: DataSourceStatus | None = None
    description: str | None = Field(None, max_length=500)


class DataSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    type: DataSourceType
    config: dict[str, Any]
    status: DataSourceStatus
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class ScrapingRuleCreate(BaseModel):
    data_source_id: int = Field(..., gt=0)
    name: str = Field(..., min_length=1, max_length=100)
    target_type: TargetType  # Changed from rule_type to target_type
    config: dict[str, Any] = Field(default_factory=dict)
    schedule: str | None = Field(None, max_length=100)
    is_active: bool = True
    description: str | None = Field(None, max_length=500)


class ScrapingRuleUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    config: dict[str, Any] | None = None
    schedule: str | None = Field(None, max_length=100)
    is_active: bool | None = None
    description: str | None = Field(None, max_length=500)


class ScrapingRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    data_source_id: int
    name: str
    target_type: TargetType  # Changed from rule_type to target_type
    config: dict[str, Any]
    schedule: str | None = None
    is_active: bool
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class ScrapingRuleListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    data_source_id: int
    name: str
    target_type: TargetType  # Changed from rule_type to target_type
    config: dict[str, Any]
    schedule: str | None = None
    is_active: bool
    description: str | None = None
    created_at: datetime
    updated_at: datetime
    data_source_name: str | None = None


class ScrapingRuleListResponse(BaseModel):
    items: list[ScrapingRuleListItem]
    total: int
    page: int
    size: int
    pages: int
```

**步骤3: 检查并更新所有使用ScrapingRuleType的地方**

需要搜索并更新所有引用`ScrapingRuleType`或`rule_type`的代码：

```bash
cd /h/project/douyin/fix-schema-enum-consistency
grep -r "ScrapingRuleType" src/ --include="*.py"
grep -r "rule_type" src/ --include="*.py"
```

**步骤4: 运行测试验证**

```bash
cd /h/project/douyin/fix-schema-enum-consistency
python -c "from src.domains.data_source.schemas import DataSourceCreate, ScrapingRuleCreate; print('Import OK')"
```

**步骤5: Commit**

```bash
git add src/domains/data_source/schemas.py
git commit -m "fix(schemas): remove duplicate enum definitions, use TargetType for scraping rules

- Remove duplicate DataSourceType and DataSourceStatus definitions
- Import enums from enums.py instead
- Replace ScrapingRuleType with TargetType to match database model
- Rename rule_type field to target_type for consistency"
```

---

### Task 3: 更新validator.py和mapping.py中的枚举为StrEnum

**文件:**
- 修改: `src/domains/data_import/validator.py:1-11`
- 修改: `src/domains/data_import/mapping.py:1-22`

**步骤1: 修改validator.py**

将`ValidationSeverity`和`ValidationStatus`改为从enums.py导入，或者统一使用StrEnum。

由于这两个枚举只在validator模块内部使用，可以保留在原地，但改为使用StrEnum：

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Callable

from pydantic import BaseModel, Field


class ValidationSeverity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"


class ValidationStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
```

**步骤2: 修改mapping.py**

```python
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import StrEnum
from typing import Any, Callable


class MappingType(StrEnum):
    AUTO = "AUTO"
    MANUAL = "MANUAL"
    ALIAS = "ALIAS"


class FieldConfidence(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"
```

**步骤3: Commit**

```bash
git add src/domains/data_import/validator.py src/domains/data_import/mapping.py
git commit -m "refactor(data_import): unify validator and mapping enums to StrEnum"
```

---

### Task 4: 修复AuditLog模型中的枚举字段类型

**文件:**
- 修改: `src/audit/schemas.py:34-62`

**步骤1: 分析当前问题**

当前`AuditLog`模型使用`str`类型存储`action`和`result`，虽然定义了`AuditAction`和`AuditResult`枚举，但没有在模型中使用。

**步骤2: 修改AuditLog模型**

将`action`和`result`字段的类型从`str`改为相应的枚举类型：

```python
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Text
from sqlmodel import Field, SQLModel

from src.shared.mixins import now


class AuditAction(StrEnum):
    LOGIN = "login"
    LOGOUT = "logout"
    REFRESH = "refresh"
    REGISTER = "register"
    VERIFY_EMAIL = "verify_email"
    FORGOT_PASSWORD = "forgot_password"
    RESET_PASSWORD = "reset_password"
    PERMISSION_CHECK = "permission_check"
    ROLE_CHECK = "role_check"
    PROTECTED_RESOURCE_ACCESS = "protected_resource_access"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class AuditResult(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    GRANTED = "granted"
    DENIED = "denied"


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"

    id: int | None = Field(default=None, primary_key=True)
    occurred_at: datetime = Field(
        default_factory=now,
        sa_type=DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    request_id: str | None = Field(
        default=None,
        max_length=36,
        description="Request correlation ID - groups all audit logs from a single HTTP request",
    )
    actor_id: int | None = Field(
        default=None,
        sa_column=Column(ForeignKey("users.id", ondelete="SET NULL"), index=True),
    )
    action: AuditAction = Field(nullable=False, max_length=64, index=True)
    resource_type: str | None = Field(default=None, max_length=64)
    resource_id: str | None = Field(default=None, sa_column=Column(Text))
    result: AuditResult = Field(nullable=False, max_length=32)
    user_agent: str | None = Field(default=None, sa_column=Column(Text))
    ip: str | None = Field(default=None, max_length=45)
    extra: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
```

**步骤3: 检查所有使用AuditLog的地方**

需要确保所有创建或更新AuditLog的地方都使用枚举值而不是字符串：

```bash
cd /h/project/douyin/fix-schema-enum-consistency
grep -r "AuditLog" src/ --include="*.py" -A 2 -B 2
```

**步骤4: Commit**

```bash
git add src/audit/schemas.py
git commit -m "fix(audit): use enum types for AuditLog action and result fields

- Change action field type from str to AuditAction
- Change result field type from str to AuditResult
- Ensures type safety and consistency across the codebase"
```

---

### Task 5: 更新data_import/schemas.py中的状态字段类型

**文件:**
- 修改: `src/domains/data_import/schemas.py:1-87`

**步骤1: 分析当前问题**

当前`data_import/schemas.py`中的多个schema使用`str`类型表示状态，应该使用`ImportStatus`枚举：

- `ImportUploadResponse.status: str`
- `ImportHistoryItem.status: str`
- `ImportDetailResponse.status: str`
- `ImportCancelResponse.status: str`
- `ImportMappingResponse.status: str`

**步骤2: 修改data_import/schemas.py**

```python
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from src.domains.data_import.enums import ImportStatus


class ImportUploadResponse(BaseModel):
    id: int
    file_name: str
    file_size: int
    status: ImportStatus
    created_at: datetime


class FieldMappingRequest(BaseModel):
    mappings: dict[str, str]
    target_fields: list[str]


class ImportValidateResponse(BaseModel):
    id: int
    total_rows: int
    passed: int
    failed: int
    errors_by_field: dict[str, int]
    warnings_by_field: dict[str, int]


class ImportConfirmResponse(BaseModel):
    id: int
    total: int
    success: int
    failed: int
    errors: list[dict[str, Any]]


class ImportHistoryItem(BaseModel):
    id: int
    file_name: str
    status: ImportStatus
    total_rows: int
    success_rows: int
    failed_rows: int
    created_at: datetime


class ImportHistoryResponse(BaseModel):
    items: list[ImportHistoryItem]
    total: int
    page: int
    size: int


class ImportDetailResponse(BaseModel):
    id: int
    file_name: str
    file_size: int
    status: ImportStatus
    field_mapping: dict[str, str] | None
    total_rows: int
    success_rows: int
    failed_rows: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime | None


class ImportCancelResponse(BaseModel):
    id: int
    status: ImportStatus
    message: str


class ImportParseResponse(BaseModel):
    id: int
    total_rows: int
    preview: list[dict[str, Any]] = Field(default_factory=list)


class ImportMappingResponse(BaseModel):
    id: int
    status: ImportStatus


class ImportUploadRequest(BaseModel):
    pass
```

**步骤3: Commit**

```bash
git add src/domains/data_import/schemas.py
git commit -m "fix(data_import): use ImportStatus enum in response schemas

- Replace str type with ImportStatus enum for all status fields
- Ensures type consistency between API and database layers"
```

---

### Task 6: 更新所有导入语句和引用

**步骤1: 搜索所有受影响的导入**

```bash
cd /h/project/douyin/fix-schema-enum-consistency
# 查找从schemas导入枚举的地方
grep -r "from src.domains.data_source.schemas import" src/ --include="*.py"
grep -r "from src.domains.data_import.schemas import" src/ --include="*.py"

# 查找使用rule_type的地方
grep -r "rule_type" src/ --include="*.py"
```

**步骤2: 更新API路由文件**

检查并更新以下文件：
- `src/api/v1/data_source.py`
- `src/api/v1/data_import.py`

确保它们从正确的位置导入枚举：
- 从`src.domains.data_source.enums`导入`DataSourceType`, `DataSourceStatus`, `TargetType`等
- 从`src.domains.data_import.enums`导入`ImportStatus`, `FileType`

**步骤3: 更新服务层文件**

检查并更新：
- `src/domains/data_source/services.py`
- `src/domains/data_source/repository.py`
- `src/domains/data_import/service.py`
- `src/domains/data_import/repository.py`

**步骤4: Commit**

```bash
git add -A
git commit -m "fix(imports): update all enum imports to use correct sources

- Update API routes to import enums from enums.py
- Update service layer to use TargetType instead of ScrapingRuleType
- Update all references from rule_type to target_type"
```

---

### Task 7: 运行完整测试套件

**步骤1: 运行单元测试**

```bash
cd /h/project/douyin/fix-schema-enum-consistency
just test
```

或者：

```bash
cd /h/project/douyin/fix-schema-enum-consistency
python -m pytest tests/ -v --tb=short
```

**步骤2: 检查代码格式和类型**

```bash
cd /h/project/douyin/fix-schema-enum-consistency
just check
```

或者：

```bash
cd /h/project/douyin/fix-schema-enum-consistency
ruff check src/
ruff format --check src/
```

**步骤3: 验证导入**

```bash
cd /h/project/douyin/fix-schema-enum-consistency
python -c "
from src.domains.data_source.enums import DataSourceType, DataSourceStatus, TargetType
from src.domains.data_import.enums import ImportStatus, FileType
from src.domains.data_source.schemas import DataSourceCreate, ScrapingRuleCreate
from src.domains.data_import.schemas import ImportUploadResponse
from src.audit.schemas import AuditAction, AuditResult, AuditLog
print('All imports successful!')
"
```

**步骤4: 修复任何测试失败**

根据测试结果修复任何失败的测试。常见问题可能包括：
- 测试中使用旧的枚举值
- 测试中使用`rule_type`而不是`target_type`
- 测试中期望字符串而不是枚举值

**步骤5: Commit测试修复**

```bash
git add -A
git commit -m "test: update tests for enum consistency changes

- Update test assertions to use new enum values
- Replace rule_type with target_type in tests
- Fix type expectations from str to enum"
```

---

### Task 8: 创建数据库迁移（如需要）

**步骤1: 检查是否需要迁移**

如果`AuditLog`表的`action`和`result`列从`str`改为枚举类型，可能需要创建迁移：

```bash
cd /h/project/douyin/fix-schema-enum-consistency
just db-migrate -m "update audit log enum columns"
```

**步骤2: 检查生成的迁移文件**

查看生成的迁移文件，确保变更符合预期。

**步骤3: Commit迁移文件**

```bash
git add migrations/
git commit -m "chore(migrations): add migration for audit log enum columns"
```

---

## 验证清单

完成所有任务后，请确认以下事项：

- [ ] 所有枚举定义统一使用`StrEnum`基类
- [ ] `DataSourceType`只在`enums.py`中定义，schemas.py中不再重复定义
- [ ] `DataSourceStatus`只在`enums.py`中定义，schemas.py中不再重复定义
- [ ] `ScrapingRuleType`已被移除，所有地方使用`TargetType`
- [ ] `rule_type`字段已重命名为`target_type`
- [ ] `AuditLog.action`和`AuditLog.result`使用枚举类型而非`str`
- [ ] `data_import/schemas.py`中的状态字段使用`ImportStatus`枚举
- [ ] 所有导入语句指向正确的源文件
- [ ] 所有测试通过
- [ ] 代码格式检查通过
- [ ] 应用可以正常启动

---

## 回滚计划

如果在实施过程中遇到问题，可以按以下步骤回滚：

```bash
cd /h/project/douyin/fix-schema-enum-consistency
git reset --hard HEAD~N  # N为实施的commit数量
```

或者切换到main分支：

```bash
cd /h/project/douyin/Douyin_data_dashboard
git checkout main
```

---

## 风险评估

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| API接口变更导致前端不兼容 | 高 | 高 | 确保前端使用相同的枚举值；如果`DataSourceType`值变更，需要协调前端更新 |
| 数据库现有数据与新枚举不匹配 | 中 | 高 | 检查现有数据中的枚举值，确保与新定义兼容；必要时创建数据迁移 |
| 测试覆盖不足 | 中 | 中 | 运行完整测试套件；手动验证关键路径 |
| 第三方集成受影响 | 低 | 中 | 检查是否有外部系统依赖这些枚举值 |

**特别注意：**
- `DataSourceType`的值从`DOUYIN_API/FILE_UPLOAD/DATABASE/WEBHOOK`变为`DOUYIN_SHOP/DOUYIN_APP/FILE_IMPORT/SELF_HOSTED`，这是破坏性变更
- 如果数据库中已有数据使用旧的枚举值，需要创建数据迁移脚本

---

## 后续建议

1. **添加枚举值验证**：在API层添加枚举值验证，确保传入的值是有效的枚举成员
2. **文档更新**：更新API文档，说明所有枚举类型的有效值
3. **前端同步**：确保前端使用相同的枚举定义
4. **考虑使用枚举注册表**：对于大型项目，可以考虑实现一个枚举注册表，集中管理所有枚举定义
