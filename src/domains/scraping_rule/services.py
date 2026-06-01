from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import datetime
from typing import Any

from fastapi import Depends
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.agent.exceptions import RecipeValidationError
from src.core.agent.models import Recipe
from src.domains.agent_recipe.repository import AgentRecipeRepository
from src.domains.agent_recipe.validation import is_shop_score_recipe
from src.domains.agent_recipe.validation import validate_shop_score_recipe
from src.domains.agent_recipe.validation import validate_stable_recipe
from src.domains.collection_job.enums import CollectionJobStatus
from src.domains.collection_job.models import CollectionJob
from src.domains.collection_job.repository import CollectionJobRepository
from src.domains.collection_job.schemas import ScheduleConfig
from src.domains.data_source.config_mapper import ScrapingRuleConfigMapper
from src.domains.data_source.enums import (
    DataSourceStatus,
    ScrapingRuleStatus,
    TargetType,
)
from src.domains.data_source.models import DataSource
from src.domains.data_source.repository import DataSourceRepository
from src.domains.scraping_rule.models import ScrapingRule
from src.domains.scraping_rule.repository import ScrapingRuleRepository
from src.domains.scraping_rule.schemas import (
    ScrapingRuleCreate,
    ScrapingRuleListItem,
    ScrapingRuleResponse,
    ScrapingRuleUpdate,
)
from src.domains.task.models import TaskExecution
from src.domains.task.repository import TaskExecutionRepository
from src.exceptions import BusinessException
from src.scrapers.shop_dashboard.shop_selection_validator import (
    ensure_explicit_shop_selection_valid,
    has_explicit_shop_selection,
    normalize_shop_selection,
    normalize_shop_selection_payload,
)
from src.session import get_session
from src.shared.errors import ErrorCode

_UNSET = object()
DataSourceLookup = Callable[[int], Awaitable[DataSource | None]]


class ScrapingRuleService:
    def __init__(
        self,
        session: AsyncSession,
        data_source_lookup: DataSourceLookup,
        rule_repo: ScrapingRuleRepository | None = None,
    ):
        self.session = session
        self.data_source_lookup = data_source_lookup
        self.rule_repo = rule_repo or ScrapingRuleRepository(session=session)

    async def create_rule(
        self,
        *,
        data_source_id: int,
        name: str,
        target_type: TargetType,
        config: dict[str, Any],
        description: str | None = None,
        is_active: bool = True,
    ) -> ScrapingRuleResponse:
        ds = await self.data_source_lookup(data_source_id)
        if not ds:
            raise BusinessException(
                ErrorCode.DATASOURCE_NOT_FOUND, "DataSource not found"
            )
        if ds.status != DataSourceStatus.ACTIVE:
            raise BusinessException(
                ErrorCode.DATA_VALIDATION_FAILED,
                "Cannot create rule for inactive data source",
            )

        rule_data = {
            "data_source_id": data_source_id,
            "name": name,
            "target_type": target_type,
            "description": description,
            "status": (
                ScrapingRuleStatus.ACTIVE if is_active else ScrapingRuleStatus.INACTIVE
            ),
            "version": 1,
        }
        normalized_config = normalize_shop_selection_payload(config)
        if has_explicit_shop_selection(config):
            try:
                ensure_explicit_shop_selection_valid(normalized_config)
            except ValueError as exc:
                raise BusinessException(
                    ErrorCode.DATA_VALIDATION_FAILED,
                    str(exc),
                ) from exc
        await self._validate_agent_recipe_config(normalized_config)
        rule_data.update(
            ScrapingRuleConfigMapper.map_to_model_fields(normalized_config)
        )
        rule = await self.rule_repo.create(rule_data)
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        return self._build_scraping_rule_response(rule)

    async def create(self, data: ScrapingRuleCreate) -> ScrapingRuleResponse:
        return await self.create_rule(
            data_source_id=data.data_source_id,
            name=data.name,
            target_type=data.target_type,
            config=data.config,
            description=data.description,
            is_active=data.is_active,
        )

    async def list_rules_by_data_source(
        self, data_source_id: int
    ) -> list[ScrapingRuleResponse]:
        ds = await self.data_source_lookup(data_source_id)
        if not ds:
            raise BusinessException(
                ErrorCode.DATASOURCE_NOT_FOUND, "DataSource not found"
            )

        rules = await self.rule_repo.get_by_data_source(data_source_id)
        last_execution_map = await self._load_last_execution_map(rules)
        schedule_map = await self._load_schedule_map(
            [rule.id for rule in rules if rule.id is not None]
        )
        return [
            self._build_scraping_rule_response(
                rule,
                schedule=schedule_map.get(rule.id if rule.id is not None else 0),
                last_executed_at=self._resolve_last_executed_at(
                    rule,
                    last_execution_map.get(rule.id if rule.id is not None else 0),
                ),
                last_execution_id=self._resolve_last_execution_id(
                    rule,
                    last_execution_map.get(rule.id if rule.id is not None else 0),
                ),
            )
            for rule in rules
        ]

    async def list_rules_paginated(
        self,
        *,
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
        last_execution_map = await self._load_last_execution_map(rules)
        schedule_map = await self._load_schedule_map(
            [rule.id for rule in rules if rule.id is not None]
        )
        return [
            self._build_scraping_rule_list_item(
                rule,
                schedule=schedule_map.get(rule.id if rule.id is not None else 0),
                last_executed_at=self._resolve_last_executed_at(
                    rule,
                    last_execution_map.get(rule.id if rule.id is not None else 0),
                ),
                last_execution_id=self._resolve_last_execution_id(
                    rule,
                    last_execution_map.get(rule.id if rule.id is not None else 0),
                ),
            )
            for rule in rules
        ], total

    async def get_rule(self, rule_id: int) -> ScrapingRuleResponse:
        rule = await self.rule_repo.get_by_id(rule_id)
        if not rule:
            raise BusinessException(
                ErrorCode.SCRAPING_RULE_NOT_FOUND, "ScrapingRule not found"
            )
        last_execution_map = await self._load_last_execution_map([rule])
        schedule_map = await self._load_schedule_map(
            [rule.id] if rule.id is not None else []
        )
        return self._build_scraping_rule_response(
            rule,
            schedule=schedule_map.get(rule.id if rule.id is not None else 0),
            last_executed_at=self._resolve_last_executed_at(
                rule,
                last_execution_map.get(rule.id if rule.id is not None else 0),
            ),
            last_execution_id=self._resolve_last_execution_id(
                rule,
                last_execution_map.get(rule.id if rule.id is not None else 0),
            ),
        )

    async def update_rule(
        self,
        rule_id: int,
        data: ScrapingRuleUpdate,
    ) -> ScrapingRuleResponse:
        rule = await self.rule_repo.get_by_id(rule_id)
        if not rule:
            raise BusinessException(
                ErrorCode.SCRAPING_RULE_NOT_FOUND, "ScrapingRule not found"
            )

        update_data: dict[str, Any] = {}
        provided_fields = data.model_fields_set
        if "name" in provided_fields and data.name is not None:
            update_data["name"] = data.name
        if "description" in provided_fields:
            update_data["description"] = data.description
        if "is_active" in provided_fields and data.is_active is not None:
            update_data["status"] = (
                ScrapingRuleStatus.ACTIVE
                if data.is_active
                else ScrapingRuleStatus.INACTIVE
            )
        if "config" in provided_fields and data.config is not None:
            normalized_config = normalize_shop_selection_payload(data.config)
            if has_explicit_shop_selection(data.config):
                try:
                    ensure_explicit_shop_selection_valid(normalized_config)
                except ValueError as exc:
                    raise BusinessException(
                        ErrorCode.DATA_VALIDATION_FAILED,
                        str(exc),
                    ) from exc
            current_config = ScrapingRuleConfigMapper.build_config_from_model(rule)
            await self._validate_agent_recipe_config(
                {
                    **current_config,
                    **normalized_config,
                }
            )
            update_data.update(
                ScrapingRuleConfigMapper.map_to_model_fields(normalized_config)
            )
        if update_data:
            update_data["version"] = (rule.version or 1) + 1

        rule = await self.rule_repo.update(rule_id, update_data)
        if not rule:
            raise BusinessException(
                ErrorCode.SCRAPING_RULE_NOT_FOUND, "ScrapingRule not found"
            )
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        return self._build_scraping_rule_response(rule)

    async def delete_rule(self, rule_id: int) -> None:
        deleted = await self.rule_repo.delete(rule_id)
        if not deleted:
            raise BusinessException(
                ErrorCode.SCRAPING_RULE_NOT_FOUND, "ScrapingRule not found"
            )
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def _load_last_execution_map(
        self,
        rules: list[ScrapingRule],
    ) -> dict[int, TaskExecution]:
        missing_rule_ids = [
            rule.id
            for rule in rules
            if rule.id is not None
            and (rule.last_executed_at is None or rule.last_execution_id is None)
        ]
        if not missing_rule_ids:
            return {}
        execution_repo = TaskExecutionRepository(self.session)
        return await execution_repo.get_latest_completed_by_rule_ids(missing_rule_ids)

    def _format_schedule_summary(self, jobs: list[CollectionJob]) -> str | None:
        items: list[str] = []
        for job in jobs:
            schedule = ScheduleConfig.model_validate(job.schedule or {})
            items.append(f"{job.name}: {schedule.cron} ({schedule.timezone})")
        return " | ".join(items) if items else None

    async def _load_schedule_map(self, rule_ids: list[int]) -> dict[int, str | None]:
        if not rule_ids:
            return {}
        job_repo = CollectionJobRepository(self.session)
        jobs = await job_repo.list_by_rule_ids(
            rule_ids,
            status=CollectionJobStatus.ACTIVE,
        )
        grouped: dict[int, list[CollectionJob]] = {}
        for job in jobs:
            grouped.setdefault(job.rule_id, []).append(job)
        return {
            rule_id: self._format_schedule_summary(grouped.get(rule_id, []))
            for rule_id in rule_ids
        }

    def _resolve_last_executed_at(
        self,
        rule: ScrapingRule,
        execution: TaskExecution | None,
    ) -> datetime | None:
        if rule.last_executed_at is not None:
            return rule.last_executed_at
        if execution is None:
            return None
        return execution.completed_at or execution.updated_at or execution.created_at

    def _resolve_last_execution_id(
        self,
        rule: ScrapingRule,
        execution: TaskExecution | None,
    ) -> str | None:
        if rule.last_execution_id is not None:
            return rule.last_execution_id
        if execution is None:
            return None
        payload = execution.payload if isinstance(execution.payload, dict) else {}
        normalized_execution_id = str(payload.get("execution_id") or "").strip()
        return normalized_execution_id[:100] if normalized_execution_id else None

    def _build_scraping_rule_response(
        self,
        rule: ScrapingRule,
        *,
        schedule: str | None = None,
        last_executed_at: datetime | None | object = _UNSET,
        last_execution_id: str | None | object = _UNSET,
    ) -> ScrapingRuleResponse:
        if last_executed_at is _UNSET:
            last_executed_at = rule.last_executed_at
        if last_execution_id is _UNSET:
            last_execution_id = rule.last_execution_id
        return ScrapingRuleResponse(
            id=rule.id if rule.id is not None else 0,
            data_source_id=rule.data_source_id
            if rule.data_source_id is not None
            else 0,
            name=rule.name,
            target_type=rule.target_type,
            config=ScrapingRuleConfigMapper.build_config_from_model(rule),
            schedule=schedule,
            is_active=rule.status == ScrapingRuleStatus.ACTIVE,
            status=rule.status,
            version=rule.version,
            description=rule.description,
            last_executed_at=last_executed_at,
            last_execution_id=last_execution_id,
            created_at=rule.created_at,
            updated_at=rule.updated_at,
        )

    def _build_scraping_rule_list_item(
        self,
        rule: ScrapingRule,
        *,
        schedule: str | None = None,
        last_executed_at: datetime | None | object = _UNSET,
        last_execution_id: str | None | object = _UNSET,
    ) -> ScrapingRuleListItem:
        if last_executed_at is _UNSET:
            last_executed_at = rule.last_executed_at
        if last_execution_id is _UNSET:
            last_execution_id = rule.last_execution_id
        return ScrapingRuleListItem(
            id=rule.id if rule.id is not None else 0,
            data_source_id=rule.data_source_id
            if rule.data_source_id is not None
            else 0,
            name=rule.name,
            target_type=rule.target_type,
            config=ScrapingRuleConfigMapper.build_config_from_model(rule),
            schedule=schedule,
            is_active=rule.status == ScrapingRuleStatus.ACTIVE,
            status=rule.status,
            version=rule.version,
            description=rule.description,
            last_executed_at=last_executed_at,
            last_execution_id=last_execution_id,
            created_at=rule.created_at,
            updated_at=rule.updated_at,
            data_source_name=rule.data_source.name if rule.data_source else None,
        )

    async def _validate_agent_recipe_config(self, config: dict[str, Any]) -> None:
        needs_stable = _needs_stable_agent_recipe(config)
        recipe_ref = _agent_recipe_ref(config.get("agent_recipe"))
        if recipe_ref is None:
            if needs_stable:
                raise BusinessException(
                    ErrorCode.DATA_VALIDATION_FAILED,
                    "Stable Agent Recipe is required for all-shop collection",
                )
            return

        recipe = await AgentRecipeRepository(self.session).get_active_version(
            recipe_ref["namespace"],
            recipe_ref["key"],
            recipe_ref["version"],
        )
        if recipe is None:
            raise BusinessException(
                ErrorCode.DATA_VALIDATION_FAILED,
                "Agent Recipe is not active or does not exist",
            )
        if needs_stable and recipe.stability != "stable":
            raise BusinessException(
                ErrorCode.DATA_VALIDATION_FAILED,
                "All-shop collection requires stable Agent Recipe",
            )

        try:
            parsed = Recipe.model_validate(_agent_recipe_payload_from_model(recipe))
            if needs_stable or recipe.stability == "stable":
                validate_stable_recipe(parsed)
            elif is_shop_score_recipe(recipe.namespace, recipe.key):
                validate_shop_score_recipe(parsed)
        except (ValidationError, RecipeValidationError, ValueError) as exc:
            raise BusinessException(ErrorCode.DATA_VALIDATION_FAILED, str(exc)) from exc


async def get_scraping_rule_service(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[ScrapingRuleService, None]:
    ds_repo = DataSourceRepository(session=session)
    yield ScrapingRuleService(
        session=session,
        data_source_lookup=ds_repo.get_by_id,
    )


def _needs_stable_agent_recipe(config: dict[str, Any]) -> bool:
    selection_payload = _agent_recipe_shop_selection_payload(config)
    if selection_payload is None:
        return False
    selection = normalize_shop_selection(selection_payload)
    return selection.all or len(selection.shop_ids) != 1


def _agent_recipe_shop_selection_payload(
    config: dict[str, Any],
) -> dict[str, Any] | None:
    payload = {
        key: config[key] for key in ("all", "shop_id", "shop_ids") if key in config
    }
    filters = config.get("filters")
    if (
        isinstance(filters, dict)
        and "shop_id" in filters
        and "shop_id" not in payload
        and "shop_ids" not in payload
    ):
        payload["shop_ids"] = filters["shop_id"]
    return payload or None


def _agent_recipe_ref(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise BusinessException(
            ErrorCode.DATA_VALIDATION_FAILED,
            "Agent Recipe is invalid",
        )
    namespace = str(value.get("namespace") or "").strip()
    key = str(value.get("key") or "").strip()
    version = _positive_int(value.get("version"))
    if not namespace or not key or version is None:
        raise BusinessException(
            ErrorCode.DATA_VALIDATION_FAILED,
            "Agent Recipe version is required",
        )
    return {
        "namespace": namespace,
        "key": key,
        "version": version,
    }


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _agent_recipe_payload_from_model(recipe: Any) -> dict[str, Any]:
    return {
        "namespace": recipe.namespace,
        "key": recipe.key,
        "version": recipe.version,
        "entrypoint": recipe.entrypoint,
        "steps": recipe.steps,
        "observations": recipe.observations,
        "assertions": recipe.assertions,
        "recovery_policy": recipe.recovery_policy,
        "security_policy": recipe.security_policy,
    }
