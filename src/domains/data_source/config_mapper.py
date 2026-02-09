from typing import Any

from src.domains.data_source.models import ScrapingRule


class ScrapingRuleConfigMapper:
    """Maps between frontend config dict and ScrapingRule model fields."""

    _EXCLUDED_FIELDS = {
        "id",
        "data_source_id",
        "name",
        "description",
        "status",
        "created_at",
        "updated_at",
        "last_executed_at",
        "last_execution_id",
        "data_source",
        "extra_config",
    }

    @classmethod
    def _get_valid_fields(cls) -> set[str]:
        """Get all valid config fields from ScrapingRule model."""
        return set(ScrapingRule.model_fields.keys()) - cls._EXCLUDED_FIELDS

    @classmethod
    def map_to_model_fields(cls, config: dict[str, Any]) -> dict[str, Any]:
        """Map frontend config to model fields.

        Known fields go to their respective model fields.
        Unknown fields go to extra_config.
        """
        valid_fields = cls._get_valid_fields()
        model_data: dict[str, Any] = {}
        extra_config: dict[str, Any] = {}

        for key, value in config.items():
            if key in valid_fields:
                model_data[key] = value
            else:
                extra_config[key] = value

        if extra_config:
            model_data["extra_config"] = extra_config

        return model_data

    @classmethod
    def build_config_from_model(cls, rule: ScrapingRule) -> dict[str, Any]:
        """Build complete config dict from ScrapingRule model.

        Returns all known config fields + extra_config.
        Model fields take precedence over extra_config in case of conflict.
        """
        valid_fields = cls._get_valid_fields()
        config: dict[str, Any] = {}

        for field in valid_fields:
            value = getattr(rule, field, None)
            if value is not None:
                config[field] = value

        extra_config = getattr(rule, "extra_config", None)
        if extra_config:
            for key, value in extra_config.items():
                if key not in config:
                    config[key] = value

        return config
