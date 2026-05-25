from src.core.agent.models import LocatorSpec
from src.core.agent.models import ObservationSpec
from src.core.agent.observations import read_observation
from src.core.agent.browser import DriverResult


class TextDriver:
    def current_url(self) -> str:
        return "https://example.test"

    def title(self) -> str:
        return "Title"

    def text(self, locator: LocatorSpec) -> str:
        return "1\n2\n3"


class TableDriver(TextDriver):
    def extract_table(self, locator: LocatorSpec) -> DriverResult:
        return DriverResult(data={"headers": ["metric", "score"], "rows": [["a", 1]]})


def test_read_list_observation_limits_items():
    result = read_observation(
        driver=TextDriver(),
        spec=ObservationSpec(
            id="items",
            kind="list",
            locator=LocatorSpec(kind="css", value=".items"),
            max_items=2,
            parser="json",
        ),
    )

    assert result == ["1", "2"]


def test_read_table_observation_uses_extract_table():
    result = read_observation(
        driver=TableDriver(),
        spec=ObservationSpec(
            id="score_table",
            kind="table",
            locator=LocatorSpec(kind="css", value="table"),
            required=True,
        ),
    )

    assert result == {"headers": ["metric", "score"], "rows": [["a", 1]]}
