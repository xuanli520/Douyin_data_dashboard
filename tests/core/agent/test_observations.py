from src.core.agent.models import LocatorSpec
from src.core.agent.models import ObservationSpec
from src.core.agent.observations import read_observation


class TextDriver:
    def current_url(self) -> str:
        return "https://example.test"

    def title(self) -> str:
        return "Title"

    def text(self, locator: LocatorSpec) -> str:
        return "1\n2\n3"


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
