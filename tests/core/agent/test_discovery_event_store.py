import json

from src.core.agent.discovery_event_store import DiscoveryEventStore
from src.core.agent.discovery_event_store import _RUN_EVENTS


def test_discovery_event_store_memory_keys_include_prefix():
    _RUN_EVENTS.clear()
    discovery_store = DiscoveryEventStore(prefix="agent_discovery")
    login_store = DiscoveryEventStore(prefix="agent_login")

    discovery_store.append("run-1", {"event_type": "run_started"})
    login_store.append("run-1", {"event_type": "queued"})

    assert [event["event_type"] for event in discovery_store.list("run-1")] == [
        "run_started"
    ]
    assert [event["event_type"] for event in login_store.list("run-1")] == ["queued"]
    assert set(_RUN_EVENTS) == {"agent_discovery:run-1", "agent_login:run-1"}


def test_discovery_event_store_redis_keys_include_prefix():
    client = _FakeRedis()
    store = DiscoveryEventStore(
        redis_client=client,
        prefix="agent_login",
        ttl_seconds=30,
    )

    store.append("run-2", {"event_type": "queued", "status": "queued"})

    assert client.incr_keys == ["agent_login:run-2:sequence"]
    assert client.expired == [
        ("agent_login:run-2:events", 30),
        ("agent_login:run-2:sequence", 30),
    ]
    assert client.published[0][0] == "agent_login:run-2:pubsub"
    assert store.list("run-2")[0]["event_type"] == "queued"


class _FakeRedis:
    def __init__(self):
        self.data = {}
        self.counters = {}
        self.incr_keys = []
        self.expired = []
        self.published = []

    def incr(self, key):
        self.incr_keys.append(key)
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    def pipeline(self):
        return _FakePipeline(self)

    def rpush(self, key, value):
        self.data.setdefault(key, []).append(value)

    def expire(self, key, seconds):
        self.expired.append((key, seconds))

    def publish(self, channel, value):
        self.published.append((channel, value))

    def lrange(self, key, start, end):
        values = self.data.get(key, [])
        if end == -1:
            return values[start:]
        return values[start : end + 1]


class _FakePipeline:
    def __init__(self, client):
        self.client = client

    def rpush(self, key, value):
        self.client.rpush(key, value)
        return self

    def expire(self, key, seconds):
        self.client.expire(key, seconds)
        return self

    def publish(self, channel, value):
        json.loads(value)
        self.client.publish(channel, value)
        return self

    def execute(self):
        return None
