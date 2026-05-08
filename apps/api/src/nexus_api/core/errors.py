"""Domain errors used across the API."""

from __future__ import annotations


class NexusError(Exception):
    """Base for all domain errors."""


class IsolationViolation(NexusError):
    """Raised when a query touches a tenant-scoped table without app.tenant_id set.

    Tripping this is a P1 incident: the architecture/agent-isolation.md guarantee #1
    has been broken. The middleware records the metric and re-raises in production.
    """


class TenantNotFound(NexusError):
    """The (provider, identifier) tuple does not map to an active tenant."""


class HMACVerificationFailed(NexusError):
    """The webhook signature did not match the expected HMAC."""


class AgentConfigConflict(NexusError):
    """Cannot perform the requested transition (e.g. promote a non-staged version)."""
