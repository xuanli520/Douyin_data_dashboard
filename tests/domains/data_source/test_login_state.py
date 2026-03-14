import pytest

from src.domains.data_source.login_state import (
    build_login_state_meta,
    normalize_login_state,
)
from src.exceptions import BusinessException
from src.shared.errors import ErrorCode


def test_normalize_login_state_requires_cookie_list():
    with pytest.raises(BusinessException) as exc_info:
        normalize_login_state({"cookies": {"sid": "x"}})
    assert exc_info.value.code == ErrorCode.DATASOURCE_LOGIN_STATE_INVALID


def test_normalize_login_state_requires_origins_list_when_present():
    with pytest.raises(BusinessException) as exc_info:
        normalize_login_state(
            {
                "cookies": [],
                "origins": {"url": "https://fxg.jinritemai.com"},
            }
        )
    assert exc_info.value.code == ErrorCode.DATASOURCE_LOGIN_STATE_INVALID


def test_build_login_state_meta_contains_required_fields():
    normalized = normalize_login_state(
        {
            "cookies": [{"name": "sid", "value": "token"}],
            "origins": [],
            "state_version": "v2",
        }
    )
    meta = build_login_state_meta(normalized, account_id="acct-1")
    assert meta["cookie_count"] == 1
    assert meta["account_id"] == "acct-1"
    assert meta["state_version"] == "v2"
