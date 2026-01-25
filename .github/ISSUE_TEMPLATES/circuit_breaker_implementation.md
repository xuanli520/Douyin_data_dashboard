---
name: Circuit Breaker Implementation
about: Implement circuit breaker pattern for external service protection
---

## Use Case

When external services (e.g., third-party APIs, microservices) become unavailable or experience high latency, the application should prevent cascading failures by:
- Stopping requests to failing services after a threshold
- Allowing services time to recover
- Providing fallback mechanisms

## Proposed Solution

Implement circuit breaker pattern using the `circuitbreaker` library (Python community standard):

1. **Decorator-based API** - `@circuit(failure_threshold=3, recovery_timeout=60)` for functions
2. **Policy configuration class** - `CircuitBreakerPolicy` for reusable configurations
3. **Key exports**:
   - `circuit` - decorator function
   - `CircuitBreakerError` - exception type
   - `CircuitBreakerPolicy` - configuration class
   - State constants: `STATE_CLOSED`, `STATE_OPEN`, `STATE_HALF_OPEN`

## Alternatives Considered

- **Sentinel (Java)** - No official Python client
- **Custom implementation** - Higher maintenance cost, prone to edge cases
- **Hystrix** - Python support discontinued
- **Tenacity retry only** - Doesn't prevent cascading failures, only retries

## Implementation Notes

- Uses `circuitbreaker>=2.0.0` from PyPI
- Decorator pattern allows fine-grained control per-function
- Integrates with existing `tenacity` retry pattern
- Compatible with async/await functions
- State transitions: CLOSED → OPEN → HALF_OPEN → CLOSED (on success) or OPEN (on failure)
