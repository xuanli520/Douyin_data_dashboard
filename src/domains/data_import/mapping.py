from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import StrEnum
from typing import Any, Callable


class MappingType(StrEnum):
    AUTO = "auto"
    MANUAL = "manual"
    ALIAS = "alias"


class FieldConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


@dataclass
class FieldMapping:
    source_field: str
    target_field: str
    mapping_type: MappingType
    confidence: FieldConfidence = FieldConfidence.NONE
    aliases: list[str] = field(default_factory=list)
    is_required: bool = False
    transform_func: str | None = None
    default_value: Any = None


@dataclass
class MappingTemplate:
    name: str
    data_type: str
    id: int | None = None
    description: str | None = None
    mappings: list[FieldMapping] = field(default_factory=list)
    is_system: bool = False


class IMappingRepository(ABC):
    @abstractmethod
    async def get_by_id(self, template_id: int) -> MappingTemplate | None: ...

    @abstractmethod
    async def get_by_name(self, name: str) -> MappingTemplate | None: ...

    @abstractmethod
    async def list_by_data_type(self, data_type: str) -> list[MappingTemplate]: ...

    @abstractmethod
    async def save(self, template: MappingTemplate) -> MappingTemplate: ...

    @abstractmethod
    async def delete(self, template_id: int) -> bool: ...


_NORMALIZE_PATTERN = re.compile(r"[\s\-_]+")
_SYNONYM_MAP: dict[str, tuple[str, ...]] = {
    "order": ("订单", "order_no", "order_id", "ordernum"),
    "product": ("商品", "product_id", "goods", "item"),
    "amount": ("金额", "price", "total", "money", "sum"),
    "date": ("日期", "时间", "time", "dt", "day"),
    "quantity": ("数量", "num", "count", "qty"),
    "sku": ("sku_code", "skucode", "goods_sn"),
    "name": ("名称", "title", "goods_name"),
    "status": ("状态", "state"),
}


class FieldNormalizer:
    @staticmethod
    def normalize(field_name: str) -> str:
        normalized = _NORMALIZE_PATTERN.sub("", field_name.lower())
        return normalized

    @classmethod
    def get_synonyms(cls, field_name: str) -> set[str]:
        normalized = cls.normalize(field_name)
        synonyms = {normalized, field_name.lower()}
        for key, variants in _SYNONYM_MAP.items():
            if key in normalized or any(key in v for v in variants):
                synonyms.update(variants)
                synonyms.add(key)
        return synonyms


_COMMON_FIELDS: dict[str, tuple[str, ...]] = {
    "order": ("order_id", "order_no", "order_number", "订单号", "tid", "trade_id"),
    "product": (
        "product_id",
        "product_no",
        "goods_id",
        "item_id",
        "商品编号",
        "sku_id",
    ),
    "amount": (
        "amount",
        "total_amount",
        "pay_amount",
        "order_amount",
        "金额",
        "总价",
    ),
    "price": ("price", "unit_price", "sale_price", "goods_price", "单价"),
    "quantity": ("quantity", "num", "count", "num_count", "数量", "件数"),
    "sku": ("sku", "sku_code", "skucode", "goods_sn", "商品编码"),
    "name": ("name", "product_name", "goods_name", "title", "商品名称"),
    "status": ("status", "order_status", "state", "订单状态"),
    "date": ("order_date", "created_at", "date", "下单日期", "交易时间"),
    "customer": ("buyer_id", "user_id", "customer_id", "买家ID"),
}


class FieldSimilarityMatcher:
    @classmethod
    def calculate_similarity(cls, field1: str, field2: str) -> float:
        normalized1 = FieldNormalizer.normalize(field1)
        normalized2 = FieldNormalizer.normalize(field2)
        return SequenceMatcher(None, normalized1, normalized2).ratio()

    @classmethod
    def find_best_match(
        cls, source_field: str, target_fields: list[str], threshold: float = 0.6
    ) -> tuple[str, float] | None:
        if not target_fields:
            return None
        best_match = None
        best_score = 0.0
        for target in target_fields:
            score = cls.calculate_similarity(source_field, target)
            if score > best_score:
                best_score = score
                best_match = target
        if best_score >= threshold and best_match is not None:
            return (best_match, best_score)
        return None

    @classmethod
    def get_field_category(cls, field_name: str) -> str | None:
        normalized = FieldNormalizer.normalize(field_name)
        for category, variants in _COMMON_FIELDS.items():
            normalized_variants = [FieldNormalizer.normalize(v) for v in variants]
            if normalized in normalized_variants:
                return category
            for nv in normalized_variants:
                if nv in normalized:
                    return category
        return None

    @classmethod
    def get_confidence(cls, score: float) -> FieldConfidence:
        if score >= 0.85:
            return FieldConfidence.HIGH
        elif score >= 0.6:
            return FieldConfidence.MEDIUM
        elif score >= 0.4:
            return FieldConfidence.LOW
        return FieldConfidence.NONE


class FieldMapper:
    def __init__(
        self,
        repository: IMappingRepository | None = None,
        target_fields: list[str] | None = None,
    ):
        self._repository = repository
        self._target_fields = target_fields or []
        self._mappings: dict[str, FieldMapping] = {}
        self._manual_mappings: dict[str, str] = {}
        self._template: MappingTemplate | None = None

    def set_target_fields(self, fields: list[str]) -> None:
        self._target_fields = fields

    def add_manual_mapping(
        self,
        source_field: str,
        target_field: str,
        is_required: bool = False,
        transform_func: str | None = None,
        default_value: Any = None,
    ) -> FieldMapping:
        mapping = FieldMapping(
            source_field=source_field,
            target_field=target_field,
            mapping_type=MappingType.MANUAL,
            confidence=FieldConfidence.HIGH,
            is_required=is_required,
            transform_func=transform_func,
            default_value=default_value,
        )
        self._mappings[source_field] = mapping
        self._manual_mappings[source_field] = target_field
        return mapping

    def auto_map(
        self,
        source_fields: list[str],
        required_fields: list[str] | None = None,
        threshold: float = 0.6,
    ) -> list[FieldMapping]:
        mappings: list[FieldMapping] = []
        required_set = set(required_fields or [])
        auto_mapped_sources: set[str] = set()

        for source in source_fields:
            if source in self._manual_mappings:
                mappings.append(self._mappings[source])
                auto_mapped_sources.add(source)
                continue

            if not self._target_fields:
                continue

            best_match = FieldSimilarityMatcher.find_best_match(
                source, self._target_fields, threshold
            )

            if best_match:
                target, score = best_match
                confidence = FieldSimilarityMatcher.get_confidence(score)
                is_required = target in required_set
                mapping = FieldMapping(
                    source_field=source,
                    target_field=target,
                    mapping_type=MappingType.AUTO,
                    confidence=confidence,
                    is_required=is_required,
                )
                mappings.append(mapping)
                self._mappings[source] = mapping
                auto_mapped_sources.add(source)

        unmapped_sources = set(source_fields) - auto_mapped_sources
        for source in unmapped_sources:
            category = FieldSimilarityMatcher.get_field_category(source)
            if category:
                synonyms = FieldNormalizer.get_synonyms(source)
                for target in self._target_fields:
                    if FieldNormalizer.normalize(target) in synonyms:
                        confidence = FieldSimilarityMatcher.get_confidence(0.5)
                        is_required = target in required_set
                        mapping = FieldMapping(
                            source_field=source,
                            target_field=target,
                            mapping_type=MappingType.ALIAS,
                            confidence=confidence,
                            is_required=is_required,
                            aliases=list(synonyms),
                        )
                        mappings.append(mapping)
                        self._mappings[source] = mapping
                        break

        return mappings

    def apply_aliases(self, source_fields: list[str]) -> dict[str, str]:
        alias_map: dict[str, str] = {}
        for source in source_fields:
            for target in self._target_fields:
                if FieldNormalizer.normalize(target) in FieldNormalizer.get_synonyms(
                    source
                ):
                    alias_map[source] = target
                    break
        return alias_map

    def get_mapping(self, source_field: str) -> FieldMapping | None:
        return self._mappings.get(source_field)

    def get_all_mappings(self) -> list[FieldMapping]:
        return list(self._mappings.values())

    def get_mapping_dict(self) -> dict[str, str]:
        return {m.source_field: m.target_field for m in self._mappings.values()}

    def get_reverse_mapping_dict(self) -> dict[str, str]:
        return {m.target_field: m.source_field for m in self._mappings.values()}

    def transform_data(self, row: dict[str, Any]) -> dict[str, Any]:
        transformed: dict[str, Any] = {}
        for source, mapping in self._mappings.items():
            if source in row:
                value = row[source]
                if mapping.transform_func:
                    value = self._apply_transform(value, mapping.transform_func)
                transformed[mapping.target_field] = value
            elif mapping.default_value is not None:
                transformed[mapping.target_field] = mapping.default_value
        return transformed

    def _apply_transform(self, value: Any, transform_func: str) -> Any:
        transforms: dict[str, Callable[..., Any]] = {
            "strip": lambda v: str(v).strip() if v is not None else None,
            "lower": lambda v: str(v).lower() if v is not None else None,
            "upper": lambda v: str(v).upper() if v is not None else None,
            "int": lambda v: int(float(v)) if v is not None else None,
            "float": lambda v: float(v) if v is not None else None,
            "abs": lambda v: abs(float(v)) if v is not None else None,
        }
        func = transforms.get(transform_func)
        if func:
            return func(value)
        return value

    async def load_template(self, template_id: int) -> bool:
        if not self._repository:
            return False
        template = await self._repository.get_by_id(template_id)
        if template:
            self._template = template
            for mapping in template.mappings:
                self._mappings[mapping.source_field] = mapping
                if mapping.mapping_type == MappingType.MANUAL:
                    self._manual_mappings[mapping.source_field] = mapping.target_field
            return True
        return False

    async def save_template(
        self,
        name: str,
        data_type: str,
        description: str | None = None,
    ) -> MappingTemplate:
        template = MappingTemplate(
            name=name,
            data_type=data_type,
            description=description,
            mappings=list(self._mappings.values()),
        )
        if self._repository:
            return await self._repository.save(template)
        return template

    def get_mapping_report(self) -> dict[str, Any]:
        by_type = defaultdict(list)
        for mapping in self._mappings.values():
            by_type[mapping.mapping_type.value].append(mapping.source_field)

        by_confidence = defaultdict(list)
        for mapping in self._mappings.values():
            by_confidence[mapping.confidence.value].append(mapping.source_field)

        required_mappings = [m for m in self._mappings.values() if m.is_required]

        return {
            "total_mappings": len(self._mappings),
            "by_type": dict(by_type),
            "by_confidence": dict(by_confidence),
            "required_count": len(required_mappings),
            "required_mapped": len(
                [m for m in required_mappings if m.source_field in self._mappings]
            ),
            "manual_mappings": self._manual_mappings,
        }


class MappingService:
    def __init__(self, repository: IMappingRepository):
        self._repository = repository

    async def create_template(
        self,
        name: str,
        data_type: str,
        source_fields: list[str],
        target_fields: list[str],
        required_fields: list[str] | None = None,
        manual_mappings: dict[str, str] | None = None,
        description: str | None = None,
    ) -> MappingTemplate:
        mapper = FieldMapper(repository=self._repository)
        mapper.set_target_fields(target_fields)

        if manual_mappings:
            for source, target in manual_mappings.items():
                mapper.add_manual_mapping(source, target)

        mapper.auto_map(source_fields, required_fields)

        return await mapper.save_template(name, data_type, description)

    async def get_template(self, template_id: int) -> MappingTemplate | None:
        return await self._repository.get_by_id(template_id)

    async def list_templates(
        self, data_type: str | None = None
    ) -> list[MappingTemplate]:
        if data_type:
            return await self._repository.list_by_data_type(data_type)
        templates = []
        for data_type in ["order", "product"]:
            templates.extend(await self._repository.list_by_data_type(data_type))
        return templates

    async def apply_mapping(
        self,
        template_id: int,
        source_fields: list[str],
        data_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        template = await self._repository.get_by_id(template_id)
        if not template:
            raise ValueError(f"Template {template_id} not found")

        mapper = FieldMapper(repository=self._repository)
        await mapper.load_template(template_id)
        mapper.set_target_fields([m.target_field for m in template.mappings])

        return [mapper.transform_data(row) for row in data_rows]

    def create_mapper(
        self,
        target_fields: list[str],
        manual_mappings: dict[str, str] | None = None,
    ) -> FieldMapper:
        mapper = FieldMapper(repository=self._repository)
        mapper.set_target_fields(target_fields)
        if manual_mappings:
            for source, target in manual_mappings.items():
                mapper.add_manual_mapping(source, target)
        return mapper
