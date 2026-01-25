import pytest
from src.core.circuit_breaker import (
    circuit,
    CircuitBreakerError,
    CircuitBreakerPolicy,
    STATE_CLOSED,
    STATE_OPEN,
    STATE_HALF_OPEN,
)


class TestCircuitBreakerPolicy:
    def test_default_values(self):
        policy = CircuitBreakerPolicy()
        assert policy.failure_threshold == 5
        assert policy.recovery_timeout == 60

    def test_custom_values(self):
        policy = CircuitBreakerPolicy(failure_threshold=3, recovery_timeout=30)
        assert policy.failure_threshold == 3
        assert policy.recovery_timeout == 30

    def test_call_returns_circuit_breaker(self):
        from circuitbreaker import CircuitBreaker

        policy = CircuitBreakerPolicy()
        cb = policy(name="test_cb")
        assert isinstance(cb, CircuitBreaker)
        assert cb._failure_threshold == 5
        assert cb._recovery_timeout == 60


class TestCircuitDecorator:
    def test_default_parameters(self):
        @circuit()
        def simple_func():
            return "success"

        assert simple_func() == "success"

    def test_circuit_opens_after_threshold(self):
        call_count = 0

        @circuit(failure_threshold=3, recovery_timeout=60)
        def failing_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("fail")

        for _ in range(3):
            with pytest.raises(ValueError):
                failing_func()

        assert call_count == 3

        with pytest.raises(CircuitBreakerError):
            failing_func()

        assert call_count == 3

    def test_circuit_blocks_further_calls_when_open(self):
        call_count = 0

        @circuit(failure_threshold=2, recovery_timeout=60)
        def failing_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("fail")

        with pytest.raises(ValueError):
            failing_func()

        with pytest.raises(ValueError):
            failing_func()

        with pytest.raises(CircuitBreakerError):
            failing_func()

        assert call_count == 2

    def test_successful_call_prevents_opening(self):
        call_count = 0

        @circuit(failure_threshold=3, recovery_timeout=60)
        def sometimes_failing():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise ValueError("fail")
            return "success"

        with pytest.raises(ValueError):
            sometimes_failing()

        with pytest.raises(ValueError):
            sometimes_failing()

        result = sometimes_failing()
        assert result == "success"
        assert call_count == 3


class TestAsyncCircuitBreaker:
    @pytest.mark.asyncio
    async def test_async_function_success(self):
        @circuit(failure_threshold=3, recovery_timeout=60)
        async def async_func():
            return "async success"

        result = await async_func()
        assert result == "async success"

    @pytest.mark.asyncio
    async def test_async_opens_after_threshold(self):
        call_count = 0

        @circuit(failure_threshold=3, recovery_timeout=60)
        async def async_failing():
            nonlocal call_count
            call_count += 1
            raise ValueError("fail")

        for _ in range(3):
            with pytest.raises(ValueError):
                await async_failing()

        with pytest.raises(CircuitBreakerError):
            await async_failing()

        assert call_count == 3

    @pytest.mark.asyncio
    async def test_async_circuit_blocks_when_open(self):
        call_count = 0

        @circuit(failure_threshold=2, recovery_timeout=60)
        async def async_failing():
            nonlocal call_count
            call_count += 1
            raise ValueError("fail")

        with pytest.raises(ValueError):
            await async_failing()

        with pytest.raises(ValueError):
            await async_failing()

        with pytest.raises(CircuitBreakerError):
            await async_failing()

        assert call_count == 2


class TestCircuitBreakerState:
    def test_state_constants_exist(self):
        assert STATE_CLOSED == "closed"
        assert STATE_OPEN == "open"
        assert STATE_HALF_OPEN == "half_open"


class TestCircuitBreakerError:
    def test_error_message_contains_details(self):
        @circuit(failure_threshold=2, recovery_timeout=60, name="test_cb")
        def failing_func():
            raise ValueError("original error")

        for _ in range(2):
            with pytest.raises(ValueError):
                failing_func()

        with pytest.raises(CircuitBreakerError) as exc_info:
            failing_func()

        assert "test_cb" in str(exc_info.value)
        assert "OPEN" in str(exc_info.value)
