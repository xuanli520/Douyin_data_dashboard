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


@dataclass
class ValidationError:
    field_name: str
    message: str
    severity: ValidationSeverity = ValidationSeverity.ERROR
    rule_name: str = "unknown"
    value: Any = None
    row_index: int | None = None


@dataclass
class ValidationResult:
    row_index: int | None = None
    status: ValidationStatus = ValidationStatus.PASS
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)

    def add_error(
        self,
        field_name: str,
        message: str,
        rule_name: str = "unknown",
        value: Any = None,
        severity: ValidationSeverity = ValidationSeverity.ERROR,
    ) -> None:
        error = ValidationError(
            field_name=field_name,
            message=message,
            rule_name=rule_name,
            value=value,
            severity=severity,
            row_index=self.row_index,
        )
        if severity == ValidationSeverity.ERROR:
            self.errors.append(error)
            if self.status != ValidationStatus.FAIL:
                self.status = ValidationStatus.FAIL
        else:
            self.warnings.append(error)
            if self.status == ValidationStatus.PASS:
                self.status = ValidationStatus.SKIP

    def merge(self, other: ValidationResult) -> None:
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        if other.status == ValidationStatus.FAIL:
            self.status = ValidationStatus.FAIL
        elif (
            other.status == ValidationStatus.SKIP
            and self.status == ValidationStatus.PASS
        ):
            self.status = ValidationStatus.SKIP

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "errors": [
                {
                    "field": e.field_name,
                    "message": e.message,
                    "severity": e.severity.value,
                    "rule": e.rule_name,
                    "value": str(e.value) if e.value is not None else None,
                }
                for e in self.errors
            ],
            "warnings": [
                {
                    "field": w.field_name,
                    "message": w.message,
                    "severity": w.severity.value,
                    "rule": w.rule_name,
                    "value": str(w.value) if w.value is not None else None,
                }
                for w in self.warnings
            ],
        }


@dataclass
class ValidationRule:
    name: str
    target_field: str
    severity: ValidationSeverity = ValidationSeverity.ERROR
    enabled: bool = True
    rule_params: dict[str, Any] = field(default_factory=dict)
    validate_func: Callable[[Any, dict[str, Any]], tuple[bool, str]] | None = None


class DataValidator(BaseModel):
    rules: list[ValidationRule] = Field(default_factory=list)
    aliases: dict[str, list[str]] = Field(default_factory=dict)

    def add_rule(self, rule: ValidationRule) -> None:
        self.rules.append(rule)

    def get_rules_for_field(self, field_name: str) -> list[ValidationRule]:
        return [r for r in self.rules if r.target_field == field_name and r.enabled]

    def _get_field_value(self, row: dict[str, Any], field_name: str) -> Any:
        if field_name in row:
            return row[field_name]
        for alias in self.aliases.get(field_name, []):
            if alias in row:
                return row[alias]
        return None

    def validate_row(
        self, row: dict[str, Any], row_index: int | None = None
    ) -> ValidationResult:
        result = ValidationResult(row_index=row_index)
        for rule in self.rules:
            if not rule.enabled:
                continue
            field_value = self._get_field_value(row, rule.target_field)
            if rule.validate_func:
                passed, message = rule.validate_func(field_value, rule.rule_params)
                if not passed:
                    result.add_error(
                        field_name=rule.target_field,
                        message=message,
                        rule_name=rule.name,
                        value=field_value,
                        severity=rule.severity,
                    )
        return result

    def validate_batch(self, rows: list[dict[str, Any]]) -> list[ValidationResult]:
        return [self.validate_row(row, i) for i, row in enumerate(rows)]

    def get_summary(self, results: list[ValidationResult]) -> dict[str, Any]:
        total_errors = sum(len(r.errors) for r in results)
        total_warnings = sum(len(r.warnings) for r in results)
        passed_count = sum(1 for r in results if r.status == ValidationStatus.PASS)
        failed_count = sum(1 for r in results if r.status == ValidationStatus.FAIL)
        skipped_count = sum(1 for r in results if r.status == ValidationStatus.SKIP)

        errors_by_field: dict[str, int] = {}
        warnings_by_field: dict[str, int] = {}
        for r in results:
            for e in r.errors:
                errors_by_field[e.field_name] = errors_by_field.get(e.field_name, 0) + 1
            for w in r.warnings:
                warnings_by_field[w.field_name] = (
                    warnings_by_field.get(w.field_name, 0) + 1
                )

        return {
            "total_rows": len(results),
            "passed": passed_count,
            "failed": failed_count,
            "skipped": skipped_count,
            "total_errors": total_errors,
            "total_warnings": total_warnings,
            "errors_by_field": errors_by_field,
            "warnings_by_field": warnings_by_field,
        }


def _required_validator(value: Any, params: dict[str, Any]) -> tuple[bool, str]:
    if value is None or value == "" or (isinstance(value, str) and not value.strip()):
        return (False, params.get("message", "Field is required"))
    return (True, "")


def _not_empty_validator(value: Any, params: dict[str, Any]) -> tuple[bool, str]:
    if value is not None and value != "":
        if isinstance(value, (list, dict)) and len(value) == 0:
            return (False, params.get("message", "Field cannot be empty"))
    return (True, "")


def _string_max_length_validator(
    value: Any, params: dict[str, Any]
) -> tuple[bool, str]:
    if isinstance(value, str):
        max_length = params.get("max_length", 255)
        if len(value) > max_length:
            return (False, f"String length exceeds maximum of {max_length}")
    return (True, "")


def _number_positive_validator(value: Any, params: dict[str, Any]) -> tuple[bool, str]:
    if value is None:
        return (True, "")
    try:
        num = float(value)
        if num < 0:
            return (False, params.get("message", "Value must be non-negative"))
    except (TypeError, ValueError):
        return (False, "Invalid number format")
    return (True, "")


def _number_range_validator(value: Any, params: dict[str, Any]) -> tuple[bool, str]:
    try:
        num = float(value)
        min_val = params.get("min")
        max_val = params.get("max")
        if min_val is not None and num < min_val:
            return (False, f"Value must be >= {min_val}")
        if max_val is not None and num > max_val:
            return (False, f"Value must be <= {max_val}")
    except (TypeError, ValueError):
        return (False, "Invalid number format")
    return (True, "")


def _date_format_validator(value: Any, params: dict[str, Any]) -> tuple[bool, str]:
    formats = params.get("formats", ["%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y"])
    if isinstance(value, datetime):
        return (True, "")
    if isinstance(value, str):
        for fmt in formats:
            try:
                datetime.strptime(value, fmt)
                return (True, "")
            except ValueError:
                continue
        return (False, f"Date must match one of formats: {', '.join(formats)}")
    return (False, "Invalid date format")


class OrderValidator(DataValidator):
    def __init__(self, **data):
        super().__init__(**data)
        self._setup_order_rules()

    def _setup_order_rules(self) -> None:
        self.rules = [
            ValidationRule(
                name="order_id_required",
                target_field="order_id",
                severity=ValidationSeverity.ERROR,
                validate_func=_required_validator,
            ),
            ValidationRule(
                name="order_id_not_empty",
                target_field="order_id",
                severity=ValidationSeverity.ERROR,
                validate_func=_not_empty_validator,
            ),
            ValidationRule(
                name="amount_required",
                target_field="amount",
                severity=ValidationSeverity.ERROR,
                validate_func=_required_validator,
            ),
            ValidationRule(
                name="amount_positive",
                target_field="amount",
                severity=ValidationSeverity.ERROR,
                validate_func=_number_positive_validator,
            ),
            ValidationRule(
                name="amount_range",
                target_field="amount",
                severity=ValidationSeverity.WARNING,
                validate_func=_number_range_validator,
                rule_params={"min": 0, "max": 1000000},
            ),
            ValidationRule(
                name="date_required",
                target_field="order_date",
                severity=ValidationSeverity.ERROR,
                validate_func=_required_validator,
            ),
            ValidationRule(
                name="date_format",
                target_field="order_date",
                severity=ValidationSeverity.ERROR,
                validate_func=_date_format_validator,
                rule_params={"formats": ["%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"]},
            ),
            ValidationRule(
                name="quantity_positive",
                target_field="quantity",
                severity=ValidationSeverity.ERROR,
                validate_func=_number_positive_validator,
            ),
        ]
        self.aliases = {
            "order_id": ["order_no", "order_number", "订单号", "tid", "trade_id"],
            "amount": ["total_amount", "pay_amount", "order_amount", "金额", "总价"],
            "order_date": ["date", "created_at", "下单日期", "交易时间"],
            "quantity": ["num", "count", "数量", "件数"],
        }

    def validate_batch(self, rows: list[dict[str, Any]]) -> list[ValidationResult]:
        seen_order_ids: set[str] = set()
        duplicate_indices: set[int] = set()
        for i, row in enumerate(rows):
            order_id = self._get_field_value(row, "order_id")
            if order_id:
                str_order_id = str(order_id)
                if str_order_id in seen_order_ids:
                    duplicate_indices.add(i)
                else:
                    seen_order_ids.add(str_order_id)
        results = super().validate_batch(rows)
        for i in duplicate_indices:
            order_id = self._get_field_value(rows[i], "order_id")
            results[i].add_error(
                field_name="order_id",
                message=f"Duplicate order ID: {order_id}",
                rule_name="order_id_unique",
                value=order_id,
                severity=ValidationSeverity.ERROR,
            )
        return results


class ProductValidator(DataValidator):
    def __init__(self, **data):
        super().__init__(**data)
        self._setup_product_rules()

    def _setup_product_rules(self) -> None:
        self.rules = [
            ValidationRule(
                name="sku_required",
                target_field="sku",
                severity=ValidationSeverity.ERROR,
                validate_func=_required_validator,
            ),
            ValidationRule(
                name="sku_not_empty",
                target_field="sku",
                severity=ValidationSeverity.ERROR,
                validate_func=_not_empty_validator,
            ),
            ValidationRule(
                name="sku_max_length",
                target_field="sku",
                severity=ValidationSeverity.WARNING,
                validate_func=_string_max_length_validator,
                rule_params={"max_length": 64},
            ),
            ValidationRule(
                name="price_required",
                target_field="price",
                severity=ValidationSeverity.ERROR,
                validate_func=_required_validator,
            ),
            ValidationRule(
                name="price_positive",
                target_field="price",
                severity=ValidationSeverity.ERROR,
                validate_func=_number_positive_validator,
            ),
            ValidationRule(
                name="price_range",
                target_field="price",
                severity=ValidationSeverity.WARNING,
                validate_func=_number_range_validator,
                rule_params={"min": 0, "max": 1000000},
            ),
            ValidationRule(
                name="stock_non_negative",
                target_field="stock",
                severity=ValidationSeverity.ERROR,
                validate_func=_number_positive_validator,
            ),
            ValidationRule(
                name="name_required",
                target_field="name",
                severity=ValidationSeverity.WARNING,
                validate_func=_required_validator,
            ),
            ValidationRule(
                name="name_max_length",
                target_field="name",
                severity=ValidationSeverity.WARNING,
                validate_func=_string_max_length_validator,
                rule_params={"max_length": 255},
            ),
        ]
        self.aliases = {
            "sku": ["sku_code", "skucode", "goods_sn", "product_no", "商品编码"],
            "price": ["unit_price", "sale_price", "goods_price", "单价"],
            "stock": ["quantity", "inventory", "num", "库存"],
            "name": ["product_name", "goods_name", "title", "商品名称"],
        }

    def validate_batch(self, rows: list[dict[str, Any]]) -> list[ValidationResult]:
        seen_skus: set[str] = set()
        duplicate_indices: set[int] = set()
        for i, row in enumerate(rows):
            sku = self._get_field_value(row, "sku")
            if sku:
                str_sku = str(sku)
                if str_sku in seen_skus:
                    duplicate_indices.add(i)
                else:
                    seen_skus.add(str_sku)
        results = super().validate_batch(rows)
        for i in duplicate_indices:
            sku = self._get_field_value(rows[i], "sku")
            results[i].add_error(
                field_name="sku",
                message=f"Duplicate SKU: {sku}",
                rule_name="sku_unique",
                value=sku,
                severity=ValidationSeverity.ERROR,
            )
        return results


class ConfigurableValidator(DataValidator):
    def __init__(
        self,
        rules_config: list[dict[str, Any]],
        aliases: dict[str, list[str]] | None = None,
        **data,
    ):
        super().__init__(**data)
        self._setup_rules_from_config(rules_config)
        if aliases:
            self.aliases = aliases

    def _setup_rules_from_config(self, rules_config: list[dict[str, Any]]) -> None:
        for config in rules_config:
            rule = ValidationRule(
                name=config.get("name", "custom"),
                target_field=config.get("field", ""),
                severity=ValidationSeverity(config.get("severity", "error")),
                enabled=config.get("enabled", True),
                rule_params=config.get("params", {}),
            )
            validator_func = self._get_validator_func(config.get("type"))
            if validator_func:
                rule.validate_func = validator_func
            self.rules.append(rule)

    def _get_validator_func(
        self, rule_type: str | None
    ) -> Callable[[Any, dict[str, Any]], tuple[bool, str]] | None:
        validators = {
            "required": _required_validator,
            "not_empty": _not_empty_validator,
            "string_max_length": _string_max_length_validator,
            "number_positive": _number_positive_validator,
            "number_range": _number_range_validator,
            "date_format": _date_format_validator,
        }
        return validators.get(rule_type or "") if rule_type else None


class ValidationService:
    _validators: dict[str, type[DataValidator]] = {
        "order": OrderValidator,
        "product": ProductValidator,
    }

    @classmethod
    def register_validator(
        cls, data_type: str, validator_class: type[DataValidator]
    ) -> None:
        cls._validators[data_type] = validator_class

    @classmethod
    def get_validator(cls, data_type: str) -> DataValidator:
        validator_class = cls._validators.get(data_type)
        if validator_class:
            return validator_class()
        return DataValidator()

    @classmethod
    def validate(
        cls,
        data_type: str,
        rows: list[dict[str, Any]],
        rules_config: list[dict[str, Any]] | None = None,
        custom_aliases: dict[str, list[str]] | None = None,
    ) -> list[ValidationResult]:
        if rules_config:
            validator = ConfigurableValidator(rules_config, custom_aliases)
        else:
            validator = cls.get_validator(data_type)
        if custom_aliases:
            validator.aliases.update(custom_aliases)
        return validator.validate_batch(rows)

    @classmethod
    def validate_and_summarize(
        cls,
        data_type: str,
        rows: list[dict[str, Any]],
        rules_config: list[dict[str, Any]] | None = None,
        custom_aliases: dict[str, list[str]] | None = None,
    ) -> dict[str, Any]:
        results = cls.validate(data_type, rows, rules_config, custom_aliases)
        validator = cls.get_validator(data_type)
        summary = validator.get_summary(results)
        summary["results"] = [r.to_dict() for r in results]
        return summary
