from collections.abc import AsyncGenerator
from typing import Any, Callable

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.data_source.enums import (
    DataSourceStatus as ModelDataSourceStatus,
    DataSourceType as ModelDataSourceType,
)
from src.domains.data_source.models import DataSource
from src.domains.data_source.repository import DataSourceRepository
from src.domains.data_source.login_state import (
    build_login_state_meta,
    normalize_login_state,
)
from src.domains.data_source.schemas import (
    DataSourceCreate,
    DataSourceResponse,
    DataSourceStatus,
    DataSourceType,
    DataSourceUpdate,
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


def _extract_shop_dashboard_login_state(config: dict[str, Any]) -> dict[str, Any]:
    payload = config.get("shop_dashboard_login_state")
    if isinstance(payload, dict):
        return dict(payload)
    return {}


def _extract_shop_dashboard_credentials(config: dict[str, Any]) -> dict[str, Any]:
    login_state = _extract_shop_dashboard_login_state(config)
    raw_credentials = login_state.get("credentials")
    credentials: dict[str, Any] = {}
    if isinstance(raw_credentials, dict):
        credentials.update(
            {
                str(key): value
                for key, value in raw_credentials.items()
                if value is not None
            }
        )

    api_key = config.get("api_key")
    if api_key:
        credentials.setdefault("api_key", api_key)
    api_key_password = config.get("api_key_password") or config.get("api_secret")
    if api_key_password:
        credentials.setdefault("api_key_password", api_key_password)
    access_token = config.get("access_token")
    if access_token:
        credentials.setdefault("access_token", access_token)
    refresh_token = config.get("refresh_token")
    if refresh_token:
        credentials.setdefault("refresh_token", refresh_token)
    token_expires_at = config.get("token_expires_at")
    if token_expires_at:
        credentials.setdefault("token_expires_at", token_expires_at)
    return credentials


def _normalize_shop_dashboard_config(config: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(config)
    normalized.pop("request_method", None)

    login_state = _extract_shop_dashboard_login_state(normalized)
    credentials = _extract_shop_dashboard_credentials(normalized)
    if credentials:
        login_state["credentials"] = credentials
    if login_state:
        state_version = login_state.get("state_version")
        login_state["state_version"] = (
            str(state_version).strip() if state_version else "v1"
        )
        normalized["shop_dashboard_login_state"] = login_state

    for key in (
        "api_key",
        "api_secret",
        "api_key_password",
        "access_token",
        "refresh_token",
        "token_expires_at",
    ):
        normalized.pop(key, None)
    return normalized


def _has_valid_storage_state_cookies(config: dict[str, Any]) -> bool:
    login_state = _extract_shop_dashboard_login_state(config)
    storage_state = login_state.get("storage_state")
    if not isinstance(storage_state, dict):
        return False
    cookies = storage_state.get("cookies")
    if not isinstance(cookies, list):
        return False
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue
        name = cookie.get("name")
        value = cookie.get("value")
        if str(name or "").strip() and value is not None and str(value).strip():
            return True
    return False


def _has_valid_cookie_mapping(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            str(key or "").strip() and item is not None and str(item).strip()
            for key, item in value.items()
        )
    if isinstance(value, str):
        cookie_pairs = [item.strip() for item in value.split(";") if item.strip()]
        for pair in cookie_pairs:
            if "=" not in pair:
                continue
            key, item = pair.split("=", 1)
            if key.strip() and item.strip():
                return True
    return False


def _validate_file_upload_source_config(config: dict[str, Any]) -> None:
    if (
        not config.get("file_path")
        and not config.get("upload_endpoint")
        and not config.get("path")
    ):
        raise BusinessException(
            ErrorCode.DATA_VALIDATION_FAILED,
            "File upload source requires 'file_path', 'upload_endpoint', or 'path'",
        )


@DataSourceTypeRegistry.register_validator(DataSourceType.DOUYIN_SHOP)
def _validate_douyin_api_config(config: dict[str, Any]) -> None:
    _ = config


@DataSourceTypeRegistry.register_validator(DataSourceType.FILE_IMPORT)
def _validate_file_upload_config(config: dict[str, Any]) -> None:
    _validate_file_upload_source_config(config)


@DataSourceTypeRegistry.register_validator(DataSourceType.FILE_UPLOAD)
def _validate_file_upload_config_v2(config: dict[str, Any]) -> None:
    _validate_file_upload_source_config(config)


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
    normalized = _normalize_shop_dashboard_config(config)
    return {
        "extra_config": normalized,
        "rate_limit": normalized.get("rate_limit", 100),
        "retry_count": normalized.get("retry_count", 3),
        "timeout": normalized.get("timeout", 30),
    }


@DataSourceTypeRegistry.register_extractor(DataSourceType.SELF_HOSTED)
def _extract_database_config(config: dict[str, Any]) -> dict[str, Any]:
    return {"extra_config": config}


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
    config = dict(ds.extra_config or {})
    if _has_valid_storage_state_cookies(config):
        return True, "Connection validated"
    if _has_valid_cookie_mapping(config.get("cookies")):
        return True, "Connection validated"
    return False, "Missing shop dashboard login state cookies"


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
        session: AsyncSession,
    ):
        self.ds_repo = ds_repo
        self.session = session

    async def _commit(self) -> None:
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    def _require_data_source(self, ds: DataSource | None) -> DataSource:
        if ds is None:
            raise BusinessException(
                ErrorCode.DATASOURCE_NOT_FOUND, "DataSource not found"
            )
        return ds

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
        await self._commit()
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

        ds = self._require_data_source(await self.ds_repo.update(ds_id, update_data))
        await self._commit()
        return self._build_data_source_response(ds)

    async def update_shop_dashboard_login_state(
        self,
        ds_id: int,
        *,
        account_id: str,
        storage_state: dict[str, Any],
        user_id: int,
    ) -> DataSourceResponse:
        ds = await self.ds_repo.get_by_id(ds_id)
        if not ds:
            raise BusinessException(
                ErrorCode.DATASOURCE_NOT_FOUND, "DataSource not found"
            )
        self._ensure_shop_dashboard_source_type(ds)

        raw_state_version = storage_state.get("state_version")
        normalized_storage_state = normalize_login_state(storage_state)
        extra_config = dict(ds.extra_config or {})
        current_login_state = _extract_shop_dashboard_login_state(extra_config)
        credentials = current_login_state.get("credentials")
        next_login_state: dict[str, Any] = {}
        if isinstance(credentials, dict) and credentials:
            next_login_state["credentials"] = dict(credentials)

        state_version = (
            str(raw_state_version).strip()
            if raw_state_version is not None and str(raw_state_version).strip()
            else str(current_login_state.get("state_version") or "").strip()
        ) or str(normalized_storage_state.get("state_version") or "v1").strip()
        normalized_storage_state["state_version"] = state_version
        next_login_state["state_version"] = state_version
        next_login_state["storage_state"] = normalized_storage_state

        extra_config["shop_dashboard_login_state"] = next_login_state
        extra_config["shop_dashboard_login_state_meta"] = build_login_state_meta(
            normalized_storage_state,
            account_id=account_id,
        )

        ds = self._require_data_source(
            await self.ds_repo.update(
                ds_id,
                {
                    "extra_config": extra_config,
                    "updated_by_id": user_id,
                },
            )
        )
        await self._commit()
        return self._build_data_source_response(ds)

    async def clear_shop_dashboard_login_state(
        self,
        ds_id: int,
        *,
        user_id: int,
    ) -> DataSourceResponse:
        ds = await self.ds_repo.get_by_id(ds_id)
        if not ds:
            raise BusinessException(
                ErrorCode.DATASOURCE_NOT_FOUND, "DataSource not found"
            )
        self._ensure_shop_dashboard_source_type(ds)

        extra_config = dict(ds.extra_config or {})
        extra_config.pop("shop_dashboard_login_state", None)
        extra_config.pop("shop_dashboard_login_state_meta", None)

        ds = self._require_data_source(
            await self.ds_repo.update(
                ds_id,
                {
                    "extra_config": extra_config,
                    "updated_by_id": user_id,
                },
            )
        )
        await self._commit()
        return self._build_data_source_response(ds)

    async def delete(self, ds_id: int) -> None:
        deleted = await self.ds_repo.delete(ds_id)
        if not deleted:
            raise BusinessException(
                ErrorCode.DATASOURCE_NOT_FOUND, "DataSource not found"
            )
        await self._commit()

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

        ds = self._require_data_source(
            await self.ds_repo.update(
                ds_id,
                {
                    "status": ModelDataSourceStatus.ACTIVE,
                    "updated_by_id": user_id,
                    "last_error_msg": None,
                },
            )
        )
        await self._commit()
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

        ds = self._require_data_source(
            await self.ds_repo.update(
                ds_id,
                {
                    "status": ModelDataSourceStatus.INACTIVE,
                    "updated_by_id": user_id,
                },
            )
        )
        await self._commit()
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
            await self._commit()
            return {"valid": True, "message": message}
        else:
            await self.ds_repo.record_error(ds_id, message)
            await self._commit()
            return {"valid": False, "message": message}

    def _ensure_shop_dashboard_source_type(self, ds: DataSource) -> None:
        if ds.source_type != ModelDataSourceType.DOUYIN_SHOP:
            raise BusinessException(
                ErrorCode.DATASOURCE_UNSUPPORTED_TYPE,
                "Shop dashboard login state is only supported for DOUYIN_SHOP",
            )

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

    def _build_data_source_config(self, ds: DataSource) -> dict[str, Any]:
        config = dict(ds.extra_config or {})
        config.pop("shop_dashboard_login_state", None)
        return config

    def _build_data_source_response(self, ds: DataSource) -> DataSourceResponse:
        return DataSourceResponse(
            id=ds.id if ds.id is not None else 0,
            name=ds.name,
            type=self._map_model_type_to_schema_type(ds.source_type),
            config=self._build_data_source_config(ds),
            status=DataSourceStatus(ds.status.value),
            description=ds.description,
            created_at=ds.created_at,
            updated_at=ds.updated_at,
        )


async def get_data_source_service(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[DataSourceService, None]:
    ds_repo = DataSourceRepository(session=session)
    yield DataSourceService(ds_repo=ds_repo, session=session)
