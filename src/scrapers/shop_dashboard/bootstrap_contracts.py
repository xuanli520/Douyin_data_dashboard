from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class BootstrapEndpoint:
    method: str
    path: str
    params: Mapping[str, Any] | None = None
    json_body: Mapping[str, Any] | None = None


SHOP_CONTEXT_VERIFY_ENDPOINTS: dict[str, BootstrapEndpoint] = {
    "overview": BootstrapEndpoint(
        method="GET",
        path="/governance/shop/experiencescore/getOverviewByVersion",
        params={
            "exp_version": "release",
            "new_shop_version": "release",
            "source": 1,
        },
    ),
    "analysis": BootstrapEndpoint(
        method="GET",
        path="/governance/shop/experiencescore/getAnalysisScore",
    ),
}
