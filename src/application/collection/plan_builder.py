from __future__ import annotations

from typing import Any

from src.application.collection.plan_builder_impl import CollectionPlanUnit
from src.application.collection.plan_builder_impl import build_collection_plan


class CollectionPlanBuilder:
    def build(self, runtime_config: Any) -> list[CollectionPlanUnit]:
        return build_collection_plan(runtime_config)
