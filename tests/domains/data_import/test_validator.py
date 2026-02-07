from src.domains.data_import.validator import (
    DataValidator,
    OrderValidator,
    ProductValidator,
    ValidationService,
    ValidationResult,
    ValidationError,
    ValidationSeverity,
    ValidationRule,
    ValidationStatus,
    ConfigurableValidator,
)


class TestValidationError:
    def test_create_validation_error(self):
        error = ValidationError(
            field_name="order_id",
            message="Order ID is required",
            severity=ValidationSeverity.ERROR,
            rule_name="required",
            value=None,
            row_index=0,
        )

        assert error.field_name == "order_id"
        assert error.message == "Order ID is required"
        assert error.severity == ValidationSeverity.ERROR
        assert error.rule_name == "required"
        assert error.value is None
        assert error.row_index == 0


class TestValidationResult:
    def test_create_valid_result(self):
        result = ValidationResult(row_index=0)
        assert result.status.value == "PASS"
        assert len(result.errors) == 0
        assert len(result.warnings) == 0

    def test_add_error_changes_status_to_fail(self):
        result = ValidationResult(row_index=0)
        result.add_error(
            field_name="order_id",
            message="Required field",
            severity=ValidationSeverity.ERROR,
        )

        assert result.status.value == "FAIL"
        assert len(result.errors) == 1
        assert len(result.warnings) == 0

    def test_add_warning_changes_status_to_skip(self):
        result = ValidationResult(row_index=0)
        result.add_error(
            field_name="amount",
            message="Value is high",
            severity=ValidationSeverity.WARNING,
        )

        assert result.status.value == "SKIP"
        assert len(result.errors) == 0
        assert len(result.warnings) == 1

    def test_merge_results(self):
        result1 = ValidationResult(row_index=0)
        result1.add_error(
            field_name="order_id",
            message="Error 1",
            severity=ValidationSeverity.ERROR,
        )

        result2 = ValidationResult(row_index=1)
        result2.add_error(
            field_name="amount",
            message="Warning 1",
            severity=ValidationSeverity.WARNING,
        )

        result1.merge(result2)
        assert len(result1.errors) == 1
        assert len(result1.warnings) == 1

    def test_to_dict(self):
        result = ValidationResult(row_index=0)
        result.add_error(
            field_name="order_id",
            message="Required",
            severity=ValidationSeverity.ERROR,
            rule_name="required_check",
            value=None,
        )

        result_dict = result.to_dict()
        assert result_dict["status"] == "FAIL"
        assert len(result_dict["errors"]) == 1
        assert result_dict["errors"][0]["field"] == "order_id"
        assert result_dict["errors"][0]["rule"] == "required_check"


class TestDataValidator:
    def test_add_rule(self):
        validator = DataValidator()
        rule = ValidationRule(
            name="test_required",
            target_field="name",
            severity=ValidationSeverity.ERROR,
        )
        validator.add_rule(rule)

        assert len(validator.rules) == 1

    def test_get_rules_for_field(self):
        validator = OrderValidator()
        rules = validator.get_rules_for_field("order_id")
        assert len(rules) > 0

    def test_validate_row_passes(self):
        validator = DataValidator()
        validator.rules = [
            ValidationRule(
                name="required",
                target_field="order_id",
                severity=ValidationSeverity.ERROR,
                validate_func=lambda v, p: (True, "") if v else (False, "Required"),
            )
        ]

        result = validator.validate_row({"order_id": "O123"})
        assert result.status.value == "PASS"

    def test_validate_row_fails_required(self):
        validator = DataValidator()
        from src.domains.data_import.validator import _required_validator

        validator.rules = [
            ValidationRule(
                name="required",
                target_field="order_id",
                severity=ValidationSeverity.ERROR,
                validate_func=_required_validator,
            )
        ]

        result = validator.validate_row({})
        assert result.status.value == "FAIL"
        assert len(result.errors) == 1
        assert result.errors[0].field_name == "order_id"

    def test_validate_batch(self):
        validator = DataValidator()
        from src.domains.data_import.validator import _required_validator

        validator.rules = [
            ValidationRule(
                name="required",
                target_field="order_id",
                severity=ValidationSeverity.ERROR,
                validate_func=_required_validator,
            )
        ]

        rows = [
            {"order_id": "O1"},
            {"order_id": "O2"},
            {},
        ]

        results = validator.validate_batch(rows)
        assert len(results) == 3
        assert results[0].status.value == "PASS"
        assert results[1].status.value == "PASS"
        assert results[2].status.value == "FAIL"

    def test_get_summary(self):
        results = [
            ValidationResult(status=ValidationStatus.PASS),
            ValidationResult(
                status=ValidationStatus.FAIL,
                errors=[ValidationError(field_name="order_id", message="err")],
            ),
            ValidationResult(status=ValidationStatus.SKIP),
        ]

        validator = DataValidator()
        summary = validator.get_summary(results)
        assert summary["total_rows"] == 3
        assert summary["passed"] == 1
        assert summary["failed"] == 1
        assert summary["skipped"] == 1
        assert summary["total_errors"] == 1


class TestOrderValidator:
    def test_order_validator_has_required_rules(self):
        validator = OrderValidator()
        rules = validator.get_rules_for_field("order_id")
        assert len(rules) > 0

    def test_order_validator_validates_order_id_required(self):
        validator = OrderValidator()
        result = validator.validate_row({})
        assert result.status.value == "FAIL"
        error = next((e for e in result.errors if e.field_name == "order_id"), None)
        assert error is not None

    def test_order_validator_validates_amount_required(self):
        validator = OrderValidator()
        result = validator.validate_row({"order_id": "O123"})
        assert result.status.value == "FAIL"
        error = next((e for e in result.errors if e.field_name == "amount"), None)
        assert error is not None

    def test_order_validator_validates_amount_positive(self):
        validator = OrderValidator()
        result = validator.validate_row({"order_id": "O123", "amount": -100})
        error = next((e for e in result.errors if e.field_name == "amount"), None)
        assert error is not None

    def test_order_validator_detects_duplicate_order_id(self):
        validator = OrderValidator()
        rows = [
            {"order_id": "O1", "amount": 100},
            {"order_id": "O1", "amount": 200},
        ]

        results = validator.validate_batch(rows)
        assert len(results) == 2
        assert results[1].status.value == "FAIL"
        duplicate_error = next(
            (e for e in results[1].errors if "duplicate" in e.message.lower()), None
        )
        assert duplicate_error is not None

    def test_order_validator_validates_date_format(self):
        validator = OrderValidator()
        result = validator.validate_row(
            {"order_id": "O123", "amount": 100, "order_date": "invalid-date"}
        )
        error = next((e for e in result.errors if e.field_name == "order_date"), None)
        assert error is not None

    def test_order_validator_accepts_valid_date_formats(self):
        validator = OrderValidator()
        valid_dates = ["2024-01-15", "2024/01/15", "2024-01-15 10:30:00"]

        for date_str in valid_dates:
            result = validator.validate_row(
                {"order_id": "O123", "amount": 100, "order_date": date_str}
            )
            error = next(
                (e for e in result.errors if e.field_name == "order_date"), None
            )
            assert error is None, f"Date {date_str} should be valid"

    def test_order_validator_aliases(self):
        validator = OrderValidator()
        row = {"order_no": "O123", "total_amount": 100}
        result = validator.validate_row(row)
        order_error = next(
            (e for e in result.errors if e.field_name == "order_id"), None
        )
        amount_error = next(
            (e for e in result.errors if e.field_name == "amount"), None
        )
        assert order_error is None
        assert amount_error is None


class TestProductValidator:
    def test_product_validator_has_required_rules(self):
        validator = ProductValidator()
        rules = validator.get_rules_for_field("sku")
        assert len(rules) > 0

    def test_product_validator_validates_sku_required(self):
        validator = ProductValidator()
        result = validator.validate_row({})
        assert result.status.value == "FAIL"
        error = next((e for e in result.errors if e.field_name == "sku"), None)
        assert error is not None

    def test_product_validator_validates_price_required(self):
        validator = ProductValidator()
        result = validator.validate_row({"sku": "S001"})
        assert result.status.value == "FAIL"
        error = next((e for e in result.errors if e.field_name == "price"), None)
        assert error is not None

    def test_product_validator_validates_stock_non_negative(self):
        validator = ProductValidator()
        result = validator.validate_row({"sku": "S001", "price": 100, "stock": -5})
        error = next((e for e in result.errors if e.field_name == "stock"), None)
        assert error is not None

    def test_product_validator_detects_duplicate_sku(self):
        validator = ProductValidator()
        rows = [
            {"sku": "S001", "price": 100, "name": "Product 1"},
            {"sku": "S001", "price": 100, "name": "Product 2"},
        ]

        results = validator.validate_batch(rows)
        assert len(results) == 2
        assert results[1].status.value == "FAIL"
        duplicate_error = next(
            (e for e in results[1].errors if "duplicate" in e.message.lower()), None
        )
        assert duplicate_error is not None

    def test_product_validator_validates_price_positive(self):
        validator = ProductValidator()
        result = validator.validate_row({"sku": "S001", "price": -50, "stock": 10})
        error = next((e for e in result.errors if e.field_name == "price"), None)
        assert error is not None

    def test_product_validator_aliases(self):
        validator = ProductValidator()
        row = {"sku_code": "S001", "unit_price": 100, "quantity": 50}
        result = validator.validate_row(row)
        sku_error = next((e for e in result.errors if e.field_name == "sku"), None)
        price_error = next((e for e in result.errors if e.field_name == "price"), None)
        stock_error = next((e for e in result.errors if e.field_name == "stock"), None)
        assert sku_error is None
        assert price_error is None
        assert stock_error is None


class TestConfigurableValidator:
    def test_create_from_config(self):
        config = [
            {
                "name": "custom_required",
                "field": "custom_field",
                "type": "required",
                "severity": "error",
            }
        ]

        validator = ConfigurableValidator(config)
        assert len(validator.rules) == 1
        assert validator.rules[0].name == "custom_required"

    def test_custom_params(self):
        config = [
            {
                "name": "max_length",
                "field": "name",
                "type": "string_max_length",
                "severity": "warning",
                "params": {"max_length": 10},
            }
        ]

        validator = ConfigurableValidator(config)
        result = validator.validate_row({"name": "a" * 15})
        assert len(result.warnings) == 1
        assert result.warnings[0].field_name == "name"


class TestValidationService:
    def test_get_order_validator(self):
        validator = ValidationService.get_validator("order")
        assert isinstance(validator, OrderValidator)

    def test_get_product_validator(self):
        validator = ValidationService.get_validator("product")
        assert isinstance(validator, ProductValidator)

    def test_get_default_validator(self):
        validator = ValidationService.get_validator("unknown_type")
        assert isinstance(validator, DataValidator)

    def test_validate_orders(self):
        rows = [
            {"order_id": "O1", "amount": 100, "order_date": "2024-01-15"},
            {"order_id": "O2", "amount": 200, "order_date": "2024-01-16"},
        ]

        results = ValidationService.validate("order", rows)
        assert len(results) == 2
        assert all(r.status.value == "PASS" for r in results)

    def test_validate_products(self):
        rows = [
            {"sku": "S1", "price": 100, "stock": 10},
            {"sku": "S2", "price": 200, "stock": 20},
        ]

        results = ValidationService.validate("product", rows)
        assert len(results) == 2

    def test_validate_and_summarize(self):
        rows = [
            {"order_id": "O1", "amount": 100, "order_date": "2024-01-15"},
            {"order_id": "O2", "amount": -50, "order_date": "2024-01-16"},
        ]

        summary = ValidationService.validate_and_summarize("order", rows)
        assert "total_rows" in summary
        assert "passed" in summary
        assert "failed" in summary
        assert "results" in summary

    def test_custom_aliases(self):
        rows = [{"ord_no": "O1", "total_amount": 100, "order_date": "2024-01-15"}]
        results = ValidationService.validate(
            "order",
            rows,
            custom_aliases={"order_id": ["ord_no"], "amount": ["total_amount"]},
        )
        assert results[0].status.value == "PASS"
