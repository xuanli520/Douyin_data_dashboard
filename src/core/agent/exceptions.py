from __future__ import annotations


class AgentError(Exception):
    pass


class BrowserDriverError(AgentError):
    pass


class SecurityPolicyError(AgentError):
    pass


class RecipeValidationError(AgentError):
    pass


class ObservationError(AgentError):
    pass


class AssertionFailedError(AgentError):
    pass
