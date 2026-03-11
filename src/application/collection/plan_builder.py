from __future__ import annotations

from typing import Any

from src.tasks.collection.shop_dashboard_plan_builder import CollectionPlanUnit
from src.tasks.collection.shop_dashboard_plan_builder import build_collection_plan


class CollectionPlanBuilder:
    def build(self, runtime_config: Any) -> list[CollectionPlanUnit]:
        return build_collection_plan(runtime_config)
