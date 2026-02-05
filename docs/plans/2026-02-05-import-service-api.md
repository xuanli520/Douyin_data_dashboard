# 导入服务与API端点实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现完整的导入流程服务，整合解析、映射、验证，提供RESTful API供前端调用。

**Architecture:** 基于DDD架构，创建ImportService核心服务类编排导入流程（上传→解析→映射→验证→确认），通过Redis实现断点续传，使用SQLModel实现批量写入数据库，API层遵循Response.success()规范。

**Tech Stack:** FastAPI 0.115+, SQLModel, Redis, Pydantic, openpyxl/csv

---

## 前置条件检查

### 任务0: 环境依赖检查

**Files:**
- Modify: `pyproject.toml`

**Step 1: 检查现有依赖**

Run: `cat pyproject.toml | grep -E "(openpyxl|pandas|xlsxwriter)"`
Expected: 无输出（需要添加）

**Step 2: 添加文件解析依赖**

```toml
openpyxl = "^3.1.0"
```

**Step 3: 运行依赖安装**

Run: `uv add openpyxl`
Expected: 成功安装依赖

---

## 数据模型

### 任务1: 创建DataImportRecord模型

**Files:**
- Create: `src/domains/data_import/models.py`

**Step 1: 写入模型代码**

```python
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlmodel import Field, Relationship, SQLModel


class ImportStatus(StrEnum):
    UPLOADED = "uploaded"
    PARSING = "parsing"
    PARSED = "parsed"
    MAPPING = "mapping"
    MAPPED = "mapped"
    VALIDATING = "validating"
    VALIDATED = "validated"
    IMPORTING = "importing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DataImportRecord(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    file_name: str
    file_path: str
    file_size: int
    data_type: str
    status: ImportStatus = ImportStatus.UPLOADED
    source_fields: str
    mapping_config: str | None = None
    validation_result: str | None = None
    total_rows: int = 0
    processed_rows: int = 0
    success_rows: int = 0
    failed_rows: int = 0
    error_message: str | None = None
    created_by_id: int
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

**Step 2: 验证模型定义**

Run: `python -c "from src.domains.data_import.models import DataImportRecord, ImportStatus; print('OK')"`
Expected: 无错误输出

**Step 3: 提交**

```bash
git add src/domains/data_import/models.py
git commit -m "feat: add DataImportRecord model"
```

---

## 文件解析器

### 任务2: 创建文件解析器

**Files:**
- Create: `src/domains/data_import/parser.py`

**Step 1: 写入解析器代码**

```python
from abc import ABC, abstractmethod
from csv import DictReader
from io import StringIO
from typing import Any

import openpyxl
from openpyxl.utils import get_column_letter


class FileParser(ABC):
    @abstractmethod
    async def parse(self, file_path: str) -> list[dict[str, Any]]: ...


class ExcelParser(FileParser):
    async def parse(self, file_path: str, sheet_name: str = "Sheet1") -> list[dict[str, Any]]:
        workbook = openpyxl.load_workbook(file_path, read_only=True)
        sheet = workbook[sheet_name]
        headers = [cell.value for cell in next(sheet.iter_rows(min_row=1, max_row=1))]
        rows = []
        for row in sheet.iter_rows(min_row=2):
            row_data = {}
            for idx, cell in enumerate(row):
                if headers[idx] is not None:
                    row_data[headers[idx]] = cell.value
            rows.append(row_data)
        workbook.close()
        return rows


class CSVParser(FileParser):
    async def parse(self, file_path: str) -> list[dict[str, Any]]:
        with open(file_path, "r", encoding="utf-8") as f:
            reader = DictReader(f)
            return [dict(row) for row in reader]


class ParserFactory:
    _parsers: dict[str, type[FileParser]] = {
        ".xlsx": ExcelParser,
        ".xls": ExcelParser,
        ".csv": CSVParser,
    }

    @classmethod
    def get_parser(cls, file_path: str) -> FileParser:
        ext = file_path[file_path.rfind("."):].lower()
        parser_class = cls._parsers.get(ext)
        if not parser_class:
            raise ValueError(f"Unsupported file type: {ext}")
        return parser_class()
```

**Step 2: 验证解析器**

Run: `python -c "from src.domains.data_import.parser import ExcelParser, CSVParser, ParserFactory; print('OK')"`
Expected: 无错误输出

**Step 3: 提交**

```bash
git add src/domains/data_import/parser.py
git commit -m "feat: add file parser for Excel/CSV"
```

---

## 导入仓储

### 任务3: 创建ImportRepository

**Files:**
- Create: `src/domains/data_import/repository.py`

**Step 1: 写入仓储代码**

```python
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func

from src.domains.data_import.models import DataImportRecord, ImportStatus
from src.shared.repository import BaseRepository


class ImportRepository(BaseRepository[DataImportRecord]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, DataImportRecord)

    async def create(
        self,
        file_name: str,
        file_path: str,
        file_size: int,
        data_type: str,
        source_fields: str,
        created_by_id: int,
    ) -> DataImportRecord:
        record = DataImportRecord(
            file_name=file_name,
            file_path=file_path,
            file_size=file_size,
            data_type=data_type,
            source_fields=source_fields,
            created_by_id=created_by_id,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def get_by_id(self, import_id: int) -> DataImportRecord | None:
        result = await self.session.execute(
            select(DataImportRecord).where(DataImportRecord.id == import_id)
        )
        return result.scalar_one_or_none()

    async def update_status(
        self, import_id: int, status: ImportStatus, error_message: str | None = None
    ) -> None:
        await self.session.execute(
            update(DataImportRecord)
            .where(DataImportRecord.id == import_id)
            .values(
                status=status,
                error_message=error_message,
                updated_at=datetime.utcnow(),
            )
        )

    async def update_progress(
        self,
        import_id: int,
        processed_rows: int,
        success_rows: int,
        failed_rows: int,
    ) -> None:
        await self.session.execute(
            update(DataImportRecord)
            .where(DataImportRecord.id == import_id)
            .values(
                processed_rows=processed_rows,
                success_rows=success_rows,
                failed_rows=failed_rows,
                updated_at=datetime.utcnow(),
            )
        )

    async def update_mapping_config(self, import_id: int, mapping_config: str) -> None:
        await self.session.execute(
            update(DataImportRecord)
            .where(DataImportRecord.id == import_id)
            .values(
                mapping_config=mapping_config,
                updated_at=datetime.utcnow(),
            )
        )

    async def update_validation_result(self, import_id: int, validation_result: str) -> None:
        await self.session.execute(
            update(DataImportRecord)
            .where(DataImportRecord.id == import_id)
            .values(
                validation_result=validation_result,
                updated_at=datetime.utcnow(),
            )
        )

    async def list_by_user(
        self,
        user_id: int,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[DataImportRecord], int]:
        offset = (page - 1) * size
        result = await self.session.execute(
            select(DataImportRecord)
            .where(DataImportRecord.created_by_id == user_id)
            .order_by(DataImportRecord.created_at.desc())
            .offset(offset)
            .limit(size)
        )
        total_result = await self.session.execute(
            select(func.count()).where(DataImportRecord.created_by_id == user_id)
        )
        return result.scalars().all(), total_result.scalar_one()
```

**Step 2: 验证仓储**

Run: `python -c "from src.domains.data_import.repository import ImportRepository; print('OK')"`
Expected: 无错误输出

**Step 3: 提交**

```bash
git add src/domains/data_import/repository.py
git commit -m "feat: add ImportRepository for data import records"
```

---

## 导入服务

### 任务4: 创建ImportService核心服务

**Files:**
- Create: `src/domains/data_import/service.py`

**Step 1: 写入服务代码**

```python
import json
import os
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.data_import.models import DataImportRecord, ImportStatus
from src.domains.data_import.parser import ParserFactory
from src.domains.data_import.mapping import FieldMapper, MappingService
from src.domains.data_import.validator import ValidationService
from src.domains.data_import.repository import ImportRepository
from src.cache.redis import RedisClient, get_redis
from src.exceptions import BusinessException
from src.shared.errors import ErrorCode


class ImportService:
    IMPORT_PREFIX = "import:"
    PROGRESS_KEY = "progress"
    CANCEL_KEY = "cancel"

    def __init__(
        self,
        session: AsyncSession,
        redis: RedisClient | None = None,
    ):
        self.session = session
        self.redis = redis
        self.repo = ImportRepository(session)

    def _get_progress_key(self, import_id: int) -> str:
        return f"{self.IMPORT_PREFIX}{import_id}:{self.PROGRESS_KEY}"

    def _get_cancel_key(self, import_id: int) -> str:
        return f"{self.IMPORT_PREFIX}{import_id}:{self.CANCEL_KEY}"

    def _is_cancelled(self, import_id: int) -> bool:
        if not self.redis:
            return False
        return self.redis.exists(self._get_cancel_key(import_id))

    async def upload_file(
        self,
        file_path: str,
        file_name: str,
        file_size: int,
        data_type: str,
        source_fields: list[str],
        user_id: int,
    ) -> DataImportRecord:
        source_fields_json = json.dumps(source_fields, ensure_ascii=False)
        record = await self.repo.create(
            file_name=file_name,
            file_path=file_path,
            file_size=file_size,
            data_type=data_type,
            source_fields=source_fields_json,
            created_by_id=user_id,
        )
        await self.session.commit()
        return record

    async def parse_file(self, import_id: int) -> list[dict[str, Any]]:
        record = await self.repo.get_by_id(import_id)
        if not record:
            raise BusinessException(ErrorCode.NOT_FOUND, "Import record not found")

        await self.repo.update_status(import_id, ImportStatus.PARSING)
        await self.session.commit()

        try:
            parser = ParserFactory.get_parser(record.file_path)
            rows = await parser.parse(record.file_path)

            source_fields = json.loads(record.source_fields)
            total_rows = len(rows)

            progress = {
                "stage": "parsing",
                "total": total_rows,
                "processed": total_rows,
            }
            if self.redis:
                self.redis.setex(
                    self._get_progress_key(import_id),
                    3600,
                    json.dumps(progress, ensure_ascii=False),
                )

            await self.repo.update_progress(import_id, total_rows, 0, 0)
            await self.repo.update_status(import_id, ImportStatus.PARSED)
            await self.session.commit()

            return rows
        except Exception as e:
            await self.repo.update_status(
                import_id, ImportStatus.FAILED, str(e)
            )
            await self.session.commit()
            raise

    async def apply_mapping(
        self,
        import_id: int,
        mappings: dict[str, str],
        target_fields: list[str],
    ) -> None:
        record = await self.repo.get_by_id(import_id)
        if not record:
            raise BusinessException(ErrorCode.NOT_FOUND, "Import record not found")

        await self.repo.update_status(import_id, ImportStatus.MAPPING)
        await self.session.commit()

        mapper = FieldMapper()
        mapper.set_target_fields(target_fields)
        for source, target in mappings.items():
            mapper.add_manual_mapping(source, target)

        source_fields = json.loads(record.source_fields)
        auto_mappings = mapper.auto_map(source_fields)

        all_mappings = mapper.get_mapping_dict()
        mapping_config = json.dumps(all_mappings, ensure_ascii=False)

        await self.repo.update_mapping_config(import_id, mapping_config)
        await self.repo.update_status(import_id, ImportStatus.MAPPED)
        await self.session.commit()

    async def validate_data(
        self, import_id: int, rows: list[dict[str, Any]]
    ) -> dict[str, Any]:
        record = await self.repo.get_by_id(import_id)
        if not record:
            raise BusinessException(ErrorCode.NOT_FOUND, "Import record not found")

        await self.repo.update_status(import_id, ImportStatus.VALIDATING)
        await self.session.commit()

        mapping_config = json.loads(record.mapping_config) if record.mapping_config else {}

        mapper = FieldMapper()
        mapper.set_target_fields(list(mapping_config.values()))
        for source, target in mapping_config.items():
            mapper.add_manual_mapping(source, target)

        mapped_rows = [mapper.transform_data(row) for row in rows]

        results = ValidationService.validate_and_summarize(
            record.data_type, mapped_rows
        )

        validation_result = json.dumps(results, ensure_ascii=False)
        await self.repo.update_validation_result(import_id, validation_result)
        await self.repo.update_status(import_id, ImportStatus.VALIDATED)
        await self.session.commit()

        return results

    async def confirm_import(
        self,
        import_id: int,
        rows: list[dict[str, Any]],
        batch_size: int = 1000,
    ) -> dict[str, Any]:
        record = await self.repo.get_by_id(import_id)
        if not record:
            raise BusinessException(ErrorCode.NOT_FOUND, "Import record not found")

        if record.status == ImportStatus.CANCELLED:
            raise BusinessException(ErrorCode.DATA_IMPORT_CANCELLED, "Import was cancelled")

        await self.repo.update_status(import_id, ImportStatus.IMPORTING)
        await self.session.commit()

        if self._is_cancelled(import_id):
            await self.repo.update_status(import_id, ImportStatus.CANCELLED)
            await self.session.commit()
            return {"cancelled": True}

        mapping_config = json.loads(record.mapping_config) if record.mapping_config else {}

        mapper = FieldMapper()
        mapper.set_target_fields(list(mapping_config.values()))
        for source, target in mapping_config.items():
            mapper.add_manual_mapping(source, target)

        processed = 0
        success = 0
        failed = 0
        errors = []

        for i, row in enumerate(rows):
            if i % batch_size == 0:
                if self._is_cancelled(import_id):
                    await self.repo.update_status(import_id, ImportStatus.CANCELLED)
                    await self.session.commit()
                    break

                await self.repo.update_progress(import_id, processed, success, failed)
                await self.session.commit()

            try:
                mapped_row = mapper.transform_data(row)
                await self._save_row(mapped_row, record.data_type)
                success += 1
            except Exception as e:
                failed += 1
                errors.append({"row": i + 1, "error": str(e)})

            processed += 1

        await self.repo.update_progress(import_id, processed, success, failed)
        await self.repo.update_status(import_id, ImportStatus.COMPLETED)
        await self.session.commit()

        return {
            "total": processed,
            "success": success,
            "failed": failed,
            "errors": errors[:100],
        }

    async def _save_row(self, row: dict[str, Any], data_type: str) -> None:
        if data_type == "order":
            from src.domains.data_source.models import Order
            model = Order
        elif data_type == "product":
            from src.domains.data_source.models import Product
            model = Product
        else:
            raise ValueError(f"Unknown data type: {data_type}")

        self.session.add(model(**row))

    async def get_import_detail(self, import_id: int) -> DataImportRecord | None:
        return await self.repo.get_by_id(import_id)

    async def list_import_history(
        self,
        user_id: int,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        records, total = await self.repo.list_by_user(user_id, page, size)
        return [
            {
                "id": r.id,
                "file_name": r.file_name,
                "data_type": r.data_type,
                "status": r.status,
                "total_rows": r.total_rows,
                "success_rows": r.success_rows,
                "failed_rows": r.failed_rows,
                "created_at": r.created_at,
            }
            for r in records
        ], total

    async def cancel_import(self, import_id: int) -> None:
        if self.redis:
            self.redis.setex(self._get_cancel_key(import_id), 3600, "1")
        await self.repo.update_status(import_id, ImportStatus.CANCELLED)
        await self.session.commit()

    async def get_progress(self, import_id: int) -> dict[str, Any] | None:
        if not self.redis:
            return None
        key = self._get_progress_key(import_id)
        data = self.redis.get(key)
        if data:
            return json.loads(data)
        record = await self.repo.get_by_id(import_id)
        if record:
            return {
                "stage": record.status,
                "total": record.total_rows,
                "processed": record.processed_rows,
                "success": record.success_rows,
                "failed": record.failed_rows,
            }
        return None
```

**Step 2: 验证服务**

Run: `python -c "from src.domains.data_import.service import ImportService; print('OK')"`
Expected: 无错误输出

**Step 3: 提交**

```bash
git add src/domains/data_import/service.py
git commit -m "feat: add ImportService core service"
```

---

## API Schemas

### 任务5: 创建导入相关Pydantic Schemas

**Files:**
- Create: `src/domains/data_import/schemas.py`

**Step 1: 写入Schema代码**

```python
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ImportUploadResponse(BaseModel):
    id: int
    file_name: str
    file_size: int
    data_type: str
    status: str
    created_at: datetime


class ImportParseResponse(BaseModel):
    id: int
    total_rows: int
    source_fields: list[str]
    preview: list[dict[str, Any]] = Field(default_factory=list, max_rows=5)


class FieldMappingRequest(BaseModel):
    mappings: dict[str, str]
    target_fields: list[str]


class ImportMappingResponse(BaseModel):
    id: int
    mapping_config: dict[str, str]
    auto_mappings: list[dict[str, Any]]


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
    data_type: str
    status: str
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
    file_path: str
    file_size: int
    data_type: str
    status: str
    source_fields: list[str]
    mapping_config: dict[str, str] | None
    validation_result: dict[str, Any] | None
    total_rows: int
    processed_rows: int
    success_rows: int
    failed_rows: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class ImportCancelResponse(BaseModel):
    id: int
    status: str
    message: str


class ImportUploadRequest(BaseModel):
    data_type: str
```

**Step 2: 验证Schema**

Run: `python -c "from src.domains.data_import.schemas import *; print('OK')"`
Expected: 无错误输出

**Step 3: 提交**

```bash
git add src/domains/data_import/schemas.py
git commit -m "feat: add data import schemas"
```

---

## API端点

### 任务6: 创建DataImport API路由

**Files:**
- Create: `src/api/v1/data_import.py`
- Modify: `src/api/__init__.py`

**Step 1: 写入API路由代码**

```python
import os
import shutil
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import fastapi_users
from src.cache.redis import get_redis
from src.cache.protocol import RedisClient
from src.domains.data_import.models import ImportStatus
from src.domains.data_import.repository import ImportRepository
from src.domains.data_import.schemas import (
    ImportUploadRequest,
    ImportUploadResponse,
    FieldMappingRequest,
    ImportValidateResponse,
    ImportConfirmResponse,
    ImportHistoryResponse,
    ImportDetailResponse,
    ImportCancelResponse,
)
from src.domains.data_import.service import ImportService
from src.exceptions import BusinessException
from src.responses.base import Response
from src.session import get_session
from src.shared.errors import ErrorCode


router = APIRouter()


def get_import_service(
    session: AsyncSession = Depends(get_session),
    redis: RedisClient = Depends(get_redis),
) -> ImportService:
    return ImportService(session=session, redis=redis)


@router.post("/upload", response_model=Response[ImportUploadResponse])
async def upload_file(
    file: UploadFile = File(...),
    data_type: str = Form(...),
    current_user = Depends(fastapi_users.get_current_active_user),
    service: ImportService = Depends(get_import_service),
):
    upload_dir = "uploads/imports"
    os.makedirs(upload_dir, exist_ok=True)

    file_ext = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4().hex}{file_ext}"
    file_path = os.path.join(upload_dir, unique_filename)

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    content = await file.read()
    file_size = len(content)

    source_fields = []
    if file_ext in [".xlsx", ".xls"]:
        import openpyxl
        workbook = openpyxl.load_workbook(file_path, read_only=True)
        sheet = workbook.active
        headers = [cell.value for cell in next(sheet.iter_rows(min_row=1, max_row=1))]
        source_fields = [h for h in headers if h is not None]
        workbook.close()
    elif file_ext == ".csv":
        import csv
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            source_fields = next(reader)
        source_fields = [h for h in source_fields if h]

    record = await service.upload_file(
        file_path=file_path,
        file_name=file.filename,
        file_size=file_size,
        data_type=data_type,
        source_fields=source_fields,
        user_id=current_user.id,
    )

    return Response.success(
        data=ImportUploadResponse(
            id=record.id,
            file_name=record.file_name,
            file_size=record.file_size,
            data_type=record.data_type,
            status=record.status,
            created_at=record.created_at,
        )
    )


@router.post("/parse", response_model=Response[dict[str, Any]])
async def parse_file(
    import_id: int,
    current_user = Depends(fastapi_users.get_current_active_user),
    service: ImportService = Depends(get_import_service),
):
    record = await service.repo.get_by_id(import_id)
    if not record:
        raise BusinessException(ErrorCode.NOT_FOUND, "Import record not found")

    if record.created_by_id != current_user.id:
        raise BusinessException(ErrorCode.FORBIDDEN, "Access denied")

    rows = await service.parse_file(import_id)

    preview = rows[:5]

    return Response.success(
        data={
            "id": import_id,
            "total_rows": len(rows),
            "source_fields": record.source_fields,
            "preview": preview,
        }
    )


@router.post("/mapping", response_model=Response[dict[str, Any]])
async def apply_mapping(
    import_id: int,
    request: FieldMappingRequest,
    current_user = Depends(fastapi_users.get_current_active_user),
    service: ImportService = Depends(get_import_service),
):
    record = await service.repo.get_by_id(import_id)
    if not record:
        raise BusinessException(ErrorCode.NOT_FOUND, "Import record not found")

    if record.created_by_id != current_user.id:
        raise BusinessException(ErrorCode.FORBIDDEN, "Access denied")

    await service.apply_mapping(
        import_id=import_id,
        mappings=request.mappings,
        target_fields=request.target_fields,
    )

    return Response.success(data={"id": import_id, "status": "mapped"})


@router.post("/validate", response_model=Response[ImportValidateResponse])
async def validate_data(
    import_id: int,
    current_user = Depends(fastapi_users.get_current_active_user),
    service: ImportService = Depends(get_import_service),
):
    record = await service.repo.get_by_id(import_id)
    if not record:
        raise BusinessException(ErrorCode.NOT_FOUND, "Import record not found")

    if record.created_by_id != current_user.id:
        raise BusinessException(ErrorCode.FORBIDDEN, "Access denied")

    rows = await service.parse_file(import_id)
    results = await service.validate_data(import_id, rows)

    return Response.success(
        data=ImportValidateResponse(
            id=import_id,
            total_rows=results["total_rows"],
            passed=results["passed"],
            failed=results["failed"],
            errors_by_field=results["errors_by_field"],
            warnings_by_field=results["warnings_by_field"],
        )
    )


@router.post("/confirm", response_model=Response[ImportConfirmResponse])
async def confirm_import(
    import_id: int,
    current_user = Depends(fastapi_users.get_current_active_user),
    service: ImportService = Depends(get_import_service),
):
    record = await service.repo.get_by_id(import_id)
    if not record:
        raise BusinessException(ErrorCode.NOT_FOUND, "Import record not found")

    if record.created_by_id != current_user.id:
        raise BusinessException(ErrorCode.FORBIDDEN, "Access denied")

    rows = await service.parse_file(import_id)
    result = await service.confirm_import(import_id, rows)

    return Response.success(
        data=ImportConfirmResponse(
            id=import_id,
            total=result["total"],
            success=result["success"],
            failed=result["failed"],
            errors=result["errors"],
        )
    )


@router.get("/history", response_model=Response[ImportHistoryResponse])
async def list_import_history(
    page: int = 1,
    size: int = 20,
    current_user = Depends(fastapi_users.get_current_active_user),
    service: ImportService = Depends(get_import_service),
):
    items, total = await service.list_import_history(
        user_id=current_user.id,
        page=page,
        size=size,
    )

    return Response.success(
        data=ImportHistoryResponse(
            items=items,
            total=total,
            page=page,
            size=size,
        )
    )


@router.get("/{import_id}", response_model=Response[ImportDetailResponse])
async def get_import_detail(
    import_id: int,
    current_user = Depends(fastapi_users.get_current_active_user),
    service: ImportService = Depends(get_import_service),
):
    record = await service.get_import_detail(import_id)
    if not record:
        raise BusinessException(ErrorCode.NOT_FOUND, "Import record not found")

    if record.created_by_id != current_user.id:
        raise BusinessException(ErrorCode.FORBIDDEN, "Access denied")

    source_fields = []
    if record.source_fields:
        import json
        source_fields = json.loads(record.source_fields)

    mapping_config = None
    if record.mapping_config:
        import json
        mapping_config = json.loads(record.mapping_config)

    validation_result = None
    if record.validation_result:
        import json
        validation_result = json.loads(record.validation_result)

    return Response.success(
        data=ImportDetailResponse(
            id=record.id,
            file_name=record.file_name,
            file_path=record.file_path,
            file_size=record.file_size,
            data_type=record.data_type,
            status=record.status,
            source_fields=source_fields,
            mapping_config=mapping_config,
            validation_result=validation_result,
            total_rows=record.total_rows,
            processed_rows=record.processed_rows,
            success_rows=record.success_rows,
            failed_rows=record.failed_rows,
            error_message=record.error_message,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
    )


@router.post("/{import_id}/cancel", response_model=Response[ImportCancelResponse])
async def cancel_import(
    import_id: int,
    current_user = Depends(fastapi_users.get_current_active_user),
    service: ImportService = Depends(get_import_service),
):
    record = await service.repo.get_by_id(import_id)
    if not record:
        raise BusinessException(ErrorCode.NOT_FOUND, "Import record not found")

    if record.created_by_id != current_user.id:
        raise BusinessException(ErrorCode.FORBIDDEN, "Access denied")

    if record.status not in [
        ImportStatus.UPLOADED,
        ImportStatus.PARSING,
        ImportStatus.MAPPING,
        ImportStatus.VALIDATING,
        ImportStatus.IMPORTING,
    ]:
        raise BusinessException(ErrorCode.DATA_IMPORT_CANNOT_CANCEL, "Cannot cancel this import")

    await service.cancel_import(import_id)

    return Response.success(
        data=ImportCancelResponse(
            id=import_id,
            status="cancelled",
            message="Import cancelled successfully",
        )
    )
```

**Step 2: 更新api/__init__.py注册路由**

```python
from src.api.v1 import data_import

__all__ = ["data_import"]
```

**Step 3: 在main.py中注册路由**

```python
from src.api.v1 import data_import

app.include_router(data_import.router, prefix="/api/v1/data-import")
```

**Step 4: 验证路由**

Run: `python -c "from src.api.v1.data_import import router; print('OK')"`
Expected: 无错误输出

**Step 5: 提交**

```bash
git add src/api/v1/data_import.py src/api/__init__.py
git commit -m "feat: add data import API endpoints"
```

---

## 导出更新

### 任务7: 更新data_import/__init__.py

**Files:**
- Modify: `src/domains/data_import/__init__.py`

**Step 1: 更新导出**

```python
from src.domains.data_import.mapping import (
    FieldMapper,
    FieldMapping,
    MappingTemplate,
    MappingService,
    MappingType,
    FieldConfidence,
    FieldNormalizer,
    FieldSimilarityMatcher,
)
from src.domains.data_import.validator import (
    DataValidator,
    OrderValidator,
    ProductValidator,
    ValidationService,
    ValidationResult,
    ValidationError,
    ValidationSeverity,
    ValidationRule,
    ConfigurableValidator,
)
from src.domains.data_import.parser import (
    FileParser,
    ExcelParser,
    CSVParser,
    ParserFactory,
)
from src.domains.data_import.models import (
    DataImportRecord,
    ImportStatus,
)
from src.domains.data_import.repository import (
    ImportRepository,
)
from src.domains.data_import.service import (
    ImportService,
)
from src.domains.data_import.schemas import (
    ImportUploadRequest,
    ImportUploadResponse,
    FieldMappingRequest,
    ImportMappingResponse,
    ImportValidateResponse,
    ImportConfirmResponse,
    ImportHistoryResponse,
    ImportDetailResponse,
    ImportCancelResponse,
)

__all__ = [
    "FieldMapper",
    "FieldMapping",
    "MappingTemplate",
    "MappingService",
    "MappingType",
    "FieldConfidence",
    "FieldNormalizer",
    "FieldSimilarityMatcher",
    "DataValidator",
    "OrderValidator",
    "ProductValidator",
    "ValidationService",
    "ValidationResult",
    "ValidationError",
    "ValidationSeverity",
    "ValidationRule",
    "ConfigurableValidator",
    "FileParser",
    "ExcelParser",
    "CSVParser",
    "ParserFactory",
    "DataImportRecord",
    "ImportStatus",
    "ImportRepository",
    "ImportService",
    "ImportUploadRequest",
    "ImportUploadResponse",
    "FieldMappingRequest",
    "ImportMappingResponse",
    "ImportValidateResponse",
    "ImportConfirmResponse",
    "ImportHistoryResponse",
    "ImportDetailResponse",
    "ImportCancelResponse",
]
```

**Step 2: 验证导出**

Run: `python -c "from src.domains.data_import import ImportService, DataImportRecord; print('OK')"`
Expected: 无错误输出

**Step 3: 提交**

```bash
git add src/domains/data_import/__init__.py
git commit -m "feat: update data_import module exports"
```

---

## 验证测试

### 任务8: 运行代码检查

**Files:**
- Modify: `Justfile`

**Step 1: 运行代码检查**

Run: `just check`
Expected: 所有检查通过

**Step 2: 验证导入**

Run: `python -c "from src.domains.data_import.service import ImportService; from src.api.v1.data_import import router; print('All imports successful')"`
Expected: 成功输出

**Step 3: 提交**

```bash
git add .
git commit -m "feat: complete data import service and API endpoints"
```

---

## Plan Complete

**Plan saved to:** `docs/plans/2026-02-05-import-service-api.md`

**Two execution options:**

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**
