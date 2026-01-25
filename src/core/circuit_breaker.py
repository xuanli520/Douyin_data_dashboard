from circuitbreaker import (
    CircuitBreaker,
    CircuitBreakerError,
    STATE_CLOSED,
    STATE_OPEN,
    STATE_HALF_OPEN,
)

__all__ = [
    "circuit",
    "CircuitBreakerError",
    "CircuitBreakerPolicy",
    "STATE_CLOSED",
    "STATE_OPEN",
    "STATE_HALF_OPEN",
]


class CircuitBreakerPolicy:
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

    def __call__(self, name: str | None = None) -> CircuitBreaker:
        return CircuitBreaker(
            failure_threshold=self.failure_threshold,
            recovery_timeout=self.recovery_timeout,
            name=name,
        )


def circuit(
    failure_threshold: int | None = None,
    recovery_timeout: int | None = None,
    name: str | None = None,
) -> CircuitBreaker:
    return CircuitBreaker(
        failure_threshold=failure_threshold or 5,
        recovery_timeout=recovery_timeout or 60,
        name=name,
    )
