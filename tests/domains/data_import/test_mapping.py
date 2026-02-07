from src.domains.data_import.mapping import (
    FieldMapper,
    FieldMapping,
    MappingTemplate,
    MappingType,
    FieldConfidence,
    FieldNormalizer,
    FieldSimilarityMatcher,
)


class TestFieldNormalizer:
    def test_normalize_removes_special_chars(self):
        assert FieldNormalizer.normalize("order_no") == "orderno"
        assert FieldNormalizer.normalize("order-no") == "orderno"
        assert FieldNormalizer.normalize("order_no_id") == "ordernoid"

    def test_normalize_lowercase(self):
        assert FieldNormalizer.normalize("OrderNo") == "orderno"
        assert FieldNormalizer.normalize("ORDER_NO") == "orderno"

    def test_get_synonyms_includes_common_terms(self):
        synonyms = FieldNormalizer.get_synonyms("order_no")
        assert "orderno" in synonyms
        assert "订单" in synonyms

    def test_get_synonyms_product(self):
        synonyms = FieldNormalizer.get_synonyms("product_id")
        assert "productid" in synonyms
        assert "商品" in synonyms

    def test_get_synonyms_amount(self):
        synonyms = FieldNormalizer.get_synonyms("total_amount")
        assert "amount" in synonyms
        assert "金额" in synonyms


class TestFieldSimilarityMatcher:
    def test_calculate_similarity_exact_match(self):
        score = FieldSimilarityMatcher.calculate_similarity("order_no", "order_no")
        assert score == 1.0

    def test_calculate_similarity_similar(self):
        score = FieldSimilarityMatcher.calculate_similarity("order_no", "ordernumber")
        assert score > 0.5

    def test_calculate_similarity_different(self):
        score = FieldSimilarityMatcher.calculate_similarity("order_no", "product_id")
        assert score < 0.5

    def test_find_best_match_returns_best(self):
        targets = ["order_id", "product_name", "amount"]
        result = FieldSimilarityMatcher.find_best_match("order_no", targets)
        assert result is not None
        matched_field, score = result
        assert matched_field == "order_id"
        assert score > 0.6

    def test_find_best_match_no_match_below_threshold(self):
        targets = ["product_name", "address"]
        result = FieldSimilarityMatcher.find_best_match(
            "xyz123", targets, threshold=0.8
        )
        assert result is None

    def test_get_confidence_high(self):
        confidence = FieldSimilarityMatcher.get_confidence(0.9)
        assert confidence == FieldConfidence.HIGH

    def test_get_confidence_medium(self):
        confidence = FieldSimilarityMatcher.get_confidence(0.7)
        assert confidence == FieldConfidence.MEDIUM

    def test_get_confidence_low(self):
        confidence = FieldSimilarityMatcher.get_confidence(0.5)
        assert confidence == FieldConfidence.LOW

    def test_get_confidence_none(self):
        confidence = FieldSimilarityMatcher.get_confidence(0.3)
        assert confidence == FieldConfidence.NONE

    def test_get_field_category_order(self):
        category = FieldSimilarityMatcher.get_field_category("tid")
        assert category == "order"

    def test_get_field_category_product(self):
        category = FieldSimilarityMatcher.get_field_category("goods_id")
        assert category == "product"

    def test_get_field_category_unknown(self):
        category = FieldSimilarityMatcher.get_field_category("xyz123")
        assert category is None


class TestFieldMapper:
    def test_add_manual_mapping(self):
        mapper = FieldMapper()
        mapper.set_target_fields(["order_id", "amount", "date"])

        mapping = mapper.add_manual_mapping(
            source_field="ord_no",
            target_field="order_id",
            is_required=True,
        )

        assert mapping.source_field == "ord_no"
        assert mapping.target_field == "order_id"
        assert mapping.mapping_type == MappingType.MANUAL
        assert mapping.confidence == FieldConfidence.HIGH
        assert mapping.is_required is True

    def test_auto_map_with_exact_match(self):
        mapper = FieldMapper()
        mapper.set_target_fields(["order_id", "amount", "date"])
        mapper.set_target_fields(["order_id", "amount", "order_date"])

        source_fields = ["order_no", "total_amount", "order_dt"]
        mappings = mapper.auto_map(source_fields, threshold=0.6)

        assert len(mappings) >= 2
        mapping_dict = {m.source_field: m.target_field for m in mappings}
        assert "order_no" in mapping_dict
        assert "total_amount" in mapping_dict

    def test_auto_map_with_required_fields(self):
        mapper = FieldMapper()
        mapper.set_target_fields(["order_id", "amount", "date"])

        source_fields = ["order_no", "total_amount"]
        mappings = mapper.auto_map(source_fields, required_fields=["order_id"])

        order_mapping = next(
            (m for m in mappings if m.target_field == "order_id"), None
        )
        assert order_mapping is not None
        assert order_mapping.is_required is True

    def test_auto_map_manual_overrides_auto(self):
        mapper = FieldMapper()
        mapper.set_target_fields(["order_id", "amount"])

        mapper.add_manual_mapping("order_no", "custom_order_id")
        mappings = mapper.auto_map(["order_no", "total_amount"])

        mapping_dict = {m.source_field: m.target_field for m in mappings}
        assert mapping_dict["order_no"] == "custom_order_id"

    def test_get_mapping_returns_field_mapping(self):
        mapper = FieldMapper()
        mapper.set_target_fields(["order_id"])
        mapper.add_manual_mapping("ord_no", "order_id")

        mapping = mapper.get_mapping("ord_no")
        assert mapping is not None
        assert mapping.target_field == "order_id"

    def test_get_mapping_dict(self):
        mapper = FieldMapper()
        mapper.set_target_fields(["order_id", "amount"])
        mapper.add_manual_mapping("ord_no", "order_id")
        mapper.add_manual_mapping("total", "amount")

        mapping_dict = mapper.get_mapping_dict()
        assert mapping_dict == {"ord_no": "order_id", "total": "amount"}

    def test_get_reverse_mapping_dict(self):
        mapper = FieldMapper()
        mapper.set_target_fields(["order_id", "amount"])
        mapper.add_manual_mapping("ord_no", "order_id")

        reverse_dict = mapper.get_reverse_mapping_dict()
        assert reverse_dict == {"order_id": "ord_no"}

    def test_transform_data(self):
        mapper = FieldMapper()
        mapper.set_target_fields(["order_id", "amount"])
        mapper.add_manual_mapping("ord_no", "order_id")
        mapper.add_manual_mapping("total_amount", "amount", transform_func="float")

        row = {"ord_no": "O123", "total_amount": "100.50"}
        transformed = mapper.transform_data(row)

        assert transformed["order_id"] == "O123"
        assert transformed["amount"] == 100.50

    def test_transform_data_with_default_value(self):
        mapper = FieldMapper()
        mapper.set_target_fields(["order_id", "amount"])
        mapper.add_manual_mapping("ord_no", "order_id")
        mapper.add_manual_mapping("total_amount", "amount", default_value=0)

        row = {"ord_no": "O123"}
        transformed = mapper.transform_data(row)

        assert transformed["order_id"] == "O123"
        assert transformed["amount"] == 0

    def test_apply_transforms(self):
        mapper = FieldMapper()
        mapper.set_target_fields(["name", "code"])
        mapper.add_manual_mapping("Name", "name", transform_func="strip")
        mapper.add_manual_mapping("Code", "code", transform_func="upper")

        row = {"Name": "  test name  ", "Code": "abc123"}
        transformed = mapper.transform_data(row)

        assert transformed["name"] == "test name"
        assert transformed["code"] == "ABC123"

    def test_get_mapping_report(self):
        mapper = FieldMapper()
        mapper.set_target_fields(["order_id", "amount"])
        mapper.add_manual_mapping("ord_no", "order_id", is_required=True)
        mapper.auto_map(["total_amount"])

        report = mapper.get_mapping_report()

        assert report["total_mappings"] == 2
        assert report["required_count"] == 1
        assert "MANUAL" in report["by_type"]


class TestMappingTemplate:
    def test_create_mapping_template(self):
        mappings = [
            FieldMapping(
                source_field="ord_no",
                target_field="order_id",
                mapping_type=MappingType.MANUAL,
            )
        ]

        template = MappingTemplate(
            name="Order Mapping",
            data_type="order",
            description="Test template",
            mappings=mappings,
        )

        assert template.name == "Order Mapping"
        assert template.data_type == "order"
        assert len(template.mappings) == 1
        assert template.is_system is False

    def test_mapping_template_with_id(self):
        template = MappingTemplate(
            id=1,
            name="Test Template",
            data_type="product",
        )

        assert template.id == 1
