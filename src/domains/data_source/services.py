from collections.abc import AsyncGenerator
from typing import Any, Callable
from uuid import uuid4

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.data_source.enums import (
    DataSourceStatus as ModelDataSourceStatus,
    DataSourceType as ModelDataSourceType,
    ScrapingRuleStatus,
    TargetType,
)
from src.domains.data_source.models import DataSource, ScrapingRule
from src.domains.data_source.repository import (
    DataSourceRepository,
    ScrapingRuleRepository,
)
from src.domains.data_source.schemas import (
    DataSourceCreate,
    DataSourceResponse,
    DataSourceStatus,
    DataSourceType,
    DataSourceUpdate,
    ScrapingRuleCreate,
    ScrapingRuleListItem,
    ScrapingRuleResponse,
    ScrapingRuleUpdate,
)
from src.exceptions import BusinessException
from src.session import get_session
from src.shared.errors import ErrorCode


class DataSourceTypeRegistry:
    _validators: dict[DataSourceType, Callable[[dict[str, Any]], None]] = {}
    _config_extractors: dict[
        DataSourceType, Callable[[dict[str, Any]], dict[str, Any]]
    ] = {}
    _connection_testers: dict[ModelDataSourceType, Callable[[DataSource], Any]] = {}

    @classmethod
    def register_validator(cls, ds_type: DataSourceType):
        def decorator(f):
            cls._validators[ds_type] = f
            return f

        return decorator

    @classmethod
    def register_extractor(cls, ds_type: DataSourceType):
        def decorator(f):
            cls._config_extractors[ds_type] = f
            return f

        return decorator

    @classmethod
    def register_connection_tester(cls, model_type: ModelDataSourceType):
        def decorator(f):
            cls._connection_testers[model_type] = f
            return f

        return decorator

    @classmethod
    def validate(cls, ds_type: DataSourceType, config: dict[str, Any]) -> None:
        validator = cls._validators.get(ds_type)
        if not validator:
            raise BusinessException(
                ErrorCode.DATASOURCE_UNSUPPORTED_TYPE,
                f"No validator for type: {ds_type}",
            )
        validator(config)

    @classmethod
    def extract_config(
        cls, ds_type: DataSourceType, config: dict[str, Any]
    ) -> dict[str, Any]:
        extractor = cls._config_extractors.get(ds_type)
        if not extractor:
            raise BusinessException(
                ErrorCode.DATASOURCE_UNSUPPORTED_TYPE,
                f"No config extractor for type: {ds_type}",
            )
        return extractor(config)

    @classmethod
    async def test_connection(cls, ds: DataSource) -> tuple[bool, str]:
        tester = cls._connection_testers.get(ds.source_type)
        if tester:
            return await tester(ds)
        return False, f"Unsupported source type: {ds.source_type}"


@DataSourceTypeRegistry.register_validator(DataSourceType.DOUYIN_SHOP)
def _validate_douyin_api_config(config: dict[str, Any]) -> None:
    required = ["api_key", "api_secret"]
    missing = [f for f in required if not config.get(f)]
    if missing:
        raise BusinessException(
            ErrorCode.DATA_VALIDATION_FAILED,
            f"Missing required fields: {', '.join(missing)}",
        )


@DataSourceTypeRegistry.register_validator(DataSourceType.FILE_IMPORT)
def _validate_file_upload_config(config: dict[str, Any]) -> None:
    if (
        not config.get("file_path")
        and not config.get("upload_endpoint")
        and not config.get("path")
    ):
        raise BusinessException(
            ErrorCode.DATA_VALIDATION_FAILED,
            "File upload source requires 'file_path', 'upload_endpoint', or 'path'",
        )


@DataSourceTypeRegistry.register_validator(DataSourceType.FILE_UPLOAD)
def _validate_file_upload_config_v2(config: dict[str, Any]) -> None:
    if (
        not config.get("file_path")
        and not config.get("upload_endpoint")
        and not config.get("path")
    ):
        raise BusinessException(
            ErrorCode.DATA_VALIDATION_FAILED,
            "File upload source requires 'file_path', 'upload_endpoint', or 'path'",
        )


@DataSourceTypeRegistry.register_validator(DataSourceType.SELF_HOSTED)
def _validate_database_config(config: dict[str, Any]) -> None:
    pass


@DataSourceTypeRegistry.register_validator(DataSourceType.DOUYIN_APP)
def _validate_webhook_config(config: dict[str, Any]) -> None:
    pass


@DataSourceTypeRegistry.register_validator(DataSourceType.DOUYIN_API)
def _validate_douyin_api_config_v2(config: dict[str, Any]) -> None:
    required = ["api_key", "api_secret"]
    missing = [f for f in required if not config.get(f)]
    if missing:
        raise BusinessException(
            ErrorCode.DATA_VALIDATION_FAILED,
            f"Missing required fields: {', '.join(missing)}",
        )


@DataSourceTypeRegistry.register_extractor(DataSourceType.DOUYIN_SHOP)
def _extract_douyin_api_config(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "extra_config": config,
        "api_key": config.get("api_key"),
        "api_secret": config.get("api_secret"),
        "shop_id": config.get("shop_id"),
        "access_token": config.get("access_token"),
        "refresh_token": config.get("refresh_token"),
        "rate_limit": config.get("rate_limit", 100),
        "retry_count": config.get("retry_count", 3),
        "timeout": config.get("timeout", 30),
    }


@DataSourceTypeRegistry.register_extractor(DataSourceType.SELF_HOSTED)
def _extract_database_config(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "extra_config": config,
        "account_name": config.get("connection_string", ""),
    }


@DataSourceTypeRegistry.register_extractor(DataSourceType.FILE_IMPORT)
def _extract_file_upload_config(config: dict[str, Any]) -> dict[str, Any]:
    return {"extra_config": config}


@DataSourceTypeRegistry.register_extractor(DataSourceType.DOUYIN_APP)
def _extract_webhook_config(config: dict[str, Any]) -> dict[str, Any]:
    return {"extra_config": config}


@DataSourceTypeRegistry.register_extractor(DataSourceType.DOUYIN_API)
def _extract_douyin_api_config_v2(config: dict[str, Any]) -> dict[str, Any]:
    return {"extra_config": config}


@DataSourceTypeRegistry.register_extractor(DataSourceType.FILE_UPLOAD)
def _extract_file_upload_config_v2(config: dict[str, Any]) -> dict[str, Any]:
    return {"extra_config": config}


@DataSourceTypeRegistry.register_connection_tester(ModelDataSourceType.DOUYIN_SHOP)
async def _test_douyin_shop_connection(ds: DataSource) -> tuple[bool, str]:
    if not ds.api_key or not ds.api_secret:
        return False, "Missing API credentials"
    return True, "Connection validated"


@DataSourceTypeRegistry.register_connection_tester(ModelDataSourceType.DOUYIN_API)
async def _test_douyin_api_connection(_ds: DataSource) -> tuple[bool, str]:
    return True, "Douyin API connection validation skipped"


@DataSourceTypeRegistry.register_connection_tester(ModelDataSourceType.DOUYIN_APP)
async def _test_douyin_app_connection(_ds: DataSource) -> tuple[bool, str]:
    return True, "Douyin App connection validation skipped"


@DataSourceTypeRegistry.register_connection_tester(ModelDataSourceType.FILE_UPLOAD)
async def _test_file_upload_connection(_ds: DataSource) -> tuple[bool, str]:
    return True, "File upload connection validation skipped"


@DataSourceTypeRegistry.register_connection_tester(ModelDataSourceType.FILE_IMPORT)
async def _test_file_import_connection(_ds: DataSource) -> tuple[bool, str]:
    return True, "File source validation skipped"


@DataSourceTypeRegistry.register_connection_tester(ModelDataSourceType.SELF_HOSTED)
async def _test_self_hosted_connection(_ds: DataSource) -> tuple[bool, str]:
    return True, "Self-hosted source validation skipped"


class DataSourceService:
    _SCHEMA_TO_MODEL_TYPE: dict[DataSourceType, ModelDataSourceType] = {
        DataSourceType.DOUYIN_API: ModelDataSourceType.DOUYIN_API,
        DataSourceType.DOUYIN_SHOP: ModelDataSourceType.DOUYIN_SHOP,
        DataSourceType.DOUYIN_APP: ModelDataSourceType.DOUYIN_APP,
        DataSourceType.FILE_IMPORT: ModelDataSourceType.FILE_IMPORT,
        DataSourceType.FILE_UPLOAD: ModelDataSourceType.FILE_UPLOAD,
        DataSourceType.SELF_HOSTED: ModelDataSourceType.SELF_HOSTED,
    }
    _MODEL_TO_SCHEMA_TYPE: dict[ModelDataSourceType, DataSourceType] = {
        v: k for k, v in _SCHEMA_TO_MODEL_TYPE.items()
    }

    def __init__(
        self,
        ds_repo: DataSourceRepository,
        rule_repo: ScrapingRuleRepository,
        session: AsyncSession,
    ):
        self.ds_repo = ds_repo
        self.rule_repo = rule_repo
        self.session = session

    async def create(self, data: DataSourceCreate, user_id: int) -> DataSourceResponse:
        DataSourceTypeRegistry.validate(data.type, data.config)

        ds_data = {
            "name": data.name,
            "source_type": self._map_schema_type_to_model_type(data.type),
            "status": data.status,
            "description": data.description,
            "created_by_id": user_id,
            "updated_by_id": user_id,
            **DataSourceTypeRegistry.extract_config(data.type, data.config),
        }

        ds = await self.ds_repo.create(ds_data)
        await self.session.commit()
        return self._build_data_source_response(ds)

    async def get_by_id(self, ds_id: int) -> DataSourceResponse:
        ds = await self.ds_repo.get_by_id(ds_id, include_rules=True)
        if not ds:
            raise BusinessException(
                ErrorCode.DATASOURCE_NOT_FOUND, "DataSource not found"
            )
        return self._build_data_source_response(ds)

    async def list_paginated(
        self,
        page: int,
        size: int,
        status: DataSourceStatus | None = None,
        source_type: DataSourceType | None = None,
        name: str | None = None,
    ) -> tuple[list[DataSourceResponse], int]:
        model_type = (
            self._map_schema_type_to_model_type(source_type) if source_type else None
        )
        ds_list, total = await self.ds_repo.get_paginated(
            page,
            size,
            ModelDataSourceStatus(status.value.upper()) if status else None,
            model_type,
            name,
        )
        return [self._build_data_source_response(ds) for ds in ds_list], total

    async def update(
        self, ds_id: int, data: DataSourceUpdate, user_id: int
    ) -> DataSourceResponse:
        ds = await self.ds_repo.get_by_id(ds_id)
        if not ds:
            raise BusinessException(
                ErrorCode.DATASOURCE_NOT_FOUND, "DataSource not found"
            )

        if data.config:
            type_enum = self._map_model_type_to_schema_type(ds.source_type)
            DataSourceTypeRegistry.validate(type_enum, data.config)

        update_data: dict[str, Any] = {"updated_by_id": user_id}
        if data.name is not None:
            update_data["name"] = data.name
        if data.description is not None:
            update_data["description"] = data.description
        if data.status is not None:
            update_data["status"] = ModelDataSourceStatus(data.status.value)
        if data.config is not None:
            update_data.update(
                DataSourceTypeRegistry.extract_config(
                    self._map_model_type_to_schema_type(ds.source_type), data.config
                )
            )

        ds = await self.ds_repo.update(ds_id, update_data)
        await self.session.commit()
        return self._build_data_source_response(ds)

    async def delete(self, ds_id: int) -> None:
        await self.ds_repo.delete(ds_id)
        await self.session.commit()

    async def activate(self, ds_id: int, user_id: int) -> DataSourceResponse:
        ds = await self.ds_repo.get_by_id(ds_id)
        if not ds:
            raise BusinessException(
                ErrorCode.DATASOURCE_NOT_FOUND, "DataSource not found"
            )

        if ds.status == ModelDataSourceStatus.ACTIVE:
            raise BusinessException(
                ErrorCode.DATASOURCE_ALREADY_ACTIVE, "DataSource is already active"
            )

        ds = await self.ds_repo.update(
            ds_id,
            {
                "status": ModelDataSourceStatus.ACTIVE,
                "updated_by_id": user_id,
                "last_error_msg": None,
            },
        )
        await self.session.commit()
        return self._build_data_source_response(ds)

    async def deactivate(self, ds_id: int, user_id: int) -> DataSourceResponse:
        ds = await self.ds_repo.get_by_id(ds_id)
        if not ds:
            raise BusinessException(
                ErrorCode.DATASOURCE_NOT_FOUND, "DataSource not found"
            )

        if ds.status == ModelDataSourceStatus.INACTIVE:
            raise BusinessException(
                ErrorCode.DATASOURCE_ALREADY_INACTIVE, "DataSource is already inactive"
            )

        ds = await self.ds_repo.update(
            ds_id,
            {
                "status": ModelDataSourceStatus.INACTIVE,
                "updated_by_id": user_id,
            },
        )
        await self.session.commit()
        return self._build_data_source_response(ds)

    async def validate_connection(self, ds_id: int) -> dict[str, Any]:
        ds = await self.ds_repo.get_by_id(ds_id)
        if not ds:
            raise BusinessException(
                ErrorCode.DATASOURCE_NOT_FOUND, "DataSource not found"
            )

        is_valid, message = await DataSourceTypeRegistry.test_connection(ds)

        if is_valid:
            await self.ds_repo.update_last_used(ds_id)
            await self.session.commit()
            return {"valid": True, "message": message}
        else:
            await self.ds_repo.record_error(ds_id, message)
            await self.session.commit()
            return {"valid": False, "message": message}

    async def create_scraping_rule(
        self, ds_id: int, data: ScrapingRuleCreate
    ) -> ScrapingRuleResponse:
        ds = await self.ds_repo.get_by_id(ds_id)
        if not ds:
            raise BusinessException(
                ErrorCode.DATASOURCE_NOT_FOUND, "DataSource not found"
            )

        if ds.status != ModelDataSourceStatus.ACTIVE:
            raise BusinessException(
                ErrorCode.DATA_VALIDATION_FAILED,
                "Cannot create rule for inactive data source",
            )

        rule_data = {
            "data_source_id": ds_id,
            "name": data.name,
            "target_type": data.target_type,
            "description": data.description,
            "schedule": {"cron": data.schedule} if data.schedule else None,
            **data.config,
        }

        rule = await self.rule_repo.create(rule_data)
        await self.session.commit()
        return self._build_scraping_rule_response(rule)

    async def list_scraping_rules(self, ds_id: int) -> list[ScrapingRuleResponse]:
        ds = await self.ds_repo.get_by_id(ds_id)
        if not ds:
            raise BusinessException(
                ErrorCode.DATASOURCE_NOT_FOUND, "DataSource not found"
            )

        rules = await self.rule_repo.get_by_data_source(ds_id)
        return [self._build_scraping_rule_response(r) for r in rules]

    async def list_scraping_rules_paginated(
        self,
        page: int,
        size: int,
        name: str | None = None,
        target_type: TargetType | None = None,
        status: ScrapingRuleStatus | None = None,
        data_source_id: int | None = None,
    ) -> tuple[list[ScrapingRuleListItem], int]:
        rules, total = await self.rule_repo.get_paginated(
            page=page,
            size=size,
            name=name,
            rule_type=target_type,
            status=ScrapingRuleStatus(status.value.upper()) if status else None,
            data_source_id=data_source_id,
        )

        return [self._build_scraping_rule_list_item(r) for r in rules], total

    def _build_scraping_rule_list_item(
        self, rule: ScrapingRule
    ) -> ScrapingRuleListItem:
        return ScrapingRuleListItem(
            id=rule.id if rule.id is not None else 0,
            data_source_id=rule.data_source_id
            if rule.data_source_id is not None
            else 0,
            name=rule.name,
            target_type=rule.target_type,
            config=rule.filters or {},
            schedule=rule.schedule.get("cron") if rule.schedule else None,
            is_active=rule.status == ScrapingRuleStatus.ACTIVE,
            description=rule.description,
            created_at=rule.created_at,
            updated_at=rule.updated_at,
            data_source_name=rule.data_source.name if rule.data_source else None,
        )

    async def get_scraping_rule(self, rule_id: int) -> ScrapingRuleResponse:
        rule = await self.rule_repo.get_by_id(rule_id)
        if not rule:
            raise BusinessException(
                ErrorCode.SCRAPING_RULE_NOT_FOUND, "ScrapingRule not found"
            )
        return self._build_scraping_rule_response(rule)

    async def update_scraping_rule(
        self, rule_id: int, data: ScrapingRuleUpdate
    ) -> ScrapingRuleResponse:
        rule = await self.rule_repo.get_by_id(rule_id)
        if not rule:
            raise BusinessException(
                ErrorCode.SCRAPING_RULE_NOT_FOUND, "ScrapingRule not found"
            )

        update_data: dict[str, Any] = {}
        if data.name is not None:
            update_data["name"] = data.name
        if data.description is not None:
            update_data["description"] = data.description
        if data.schedule is not None:
            update_data["schedule"] = {"cron": data.schedule}
        if data.is_active is not None:
            update_data["status"] = (
                ScrapingRuleStatus.ACTIVE
                if data.is_active
                else ScrapingRuleStatus.INACTIVE
            )
        if data.config is not None:
            update_data.update(data.config)

        rule = await self.rule_repo.update(rule_id, update_data)
        await self.session.commit()
        return self._build_scraping_rule_response(rule)

    async def delete_scraping_rule(self, rule_id: int) -> None:
        await self.rule_repo.delete(rule_id)
        await self.session.commit()

    async def trigger_collection(
        self, ds_id: int, rule_id: int | None = None
    ) -> dict[str, Any]:
        ds = await self.ds_repo.get_by_id(ds_id, include_rules=True)
        if not ds:
            raise BusinessException(
                ErrorCode.DATASOURCE_NOT_FOUND, "DataSource not found"
            )

        if ds.status != ModelDataSourceStatus.ACTIVE:
            raise BusinessException(
                ErrorCode.DATA_VALIDATION_FAILED,
                "Cannot trigger collection for inactive data source",
            )

        rules = (
            ds.scraping_rules
            if rule_id is None
            else [r for r in ds.scraping_rules if r.id == rule_id]
        )
        if rule_id and not rules:
            raise BusinessException(
                ErrorCode.SCRAPING_RULE_NOT_FOUND, "ScrapingRule not found"
            )

        triggered = []
        for rule in rules:
            execution_id = f"exec_{uuid4().hex}"
            triggered.append(
                {
                    "rule_id": rule.id,
                    "rule_name": rule.name,
                    "execution_id": execution_id,
                    "status": "pending",
                }
            )

        return {
            "data_source_id": ds_id,
            "triggered_rules": triggered,
            "total": len(triggered),
        }

    def _map_schema_type_to_model_type(
        self, schema_type: DataSourceType | None
    ) -> ModelDataSourceType | None:
        if schema_type is None:
            return None
        return self._SCHEMA_TO_MODEL_TYPE.get(schema_type)

    def _map_model_type_to_schema_type(
        self, model_type: ModelDataSourceType
    ) -> DataSourceType:
        result = self._MODEL_TO_SCHEMA_TYPE.get(model_type)
        if result is None:
            raise BusinessException(
                ErrorCode.DATASOURCE_UNSUPPORTED_TYPE,
                f"Unsupported data source type: {model_type}",
            )
        return result

    def _build_data_source_response(self, ds: DataSource) -> DataSourceResponse:
        return DataSourceResponse(
            id=ds.id if ds.id is not None else 0,
            name=ds.name,
            type=self._map_model_type_to_schema_type(ds.source_type),
            config=ds.extra_config or {},
            status=DataSourceStatus(ds.status.value),
            description=ds.description,
            created_at=ds.created_at,
            updated_at=ds.updated_at,
        )

    def _build_scraping_rule_response(self, rule: ScrapingRule) -> ScrapingRuleResponse:
        return ScrapingRuleResponse(
            id=rule.id if rule.id is not None else 0,
            data_source_id=rule.data_source_id
            if rule.data_source_id is not None
            else 0,
            name=rule.name,
            target_type=rule.target_type,
            config=rule.filters or {},
            schedule=rule.schedule.get("cron") if rule.schedule else None,
            is_active=rule.status == ScrapingRuleStatus.ACTIVE,
            description=rule.description,
            created_at=rule.created_at,
            updated_at=rule.updated_at,
        )


async def get_data_source_service(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[DataSourceService, None]:
    ds_repo = DataSourceRepository(session=session)
    rule_repo = ScrapingRuleRepository(session=session)
    yield DataSourceService(ds_repo=ds_repo, rule_repo=rule_repo, session=session)
