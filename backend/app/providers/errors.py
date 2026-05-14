"""Provider-layer exceptions.

These live alongside the provider protocols rather than under
`app/core/exceptions.py` because they represent infrastructure failure,
not request-shaped errors. The service layer translates them into
`AppException` subclasses (typically `ProviderError`) for the response
envelope.
"""

from __future__ import annotations


class ProviderError(Exception):
    """Base class for provider-layer infrastructure failures.

    Raised when a provider call fails in a way the caller can't handle —
    network error, auth error, malformed response, exhausted retries.
    Subclasses narrow the cause.
    """


class ProviderRetryExhausted(ProviderError):
    """Raised after the provider exhausted its retry budget on transient
    failures (5xx, 429, timeouts). The wrapped cause carries the last
    underlying error for diagnostics.
    """


class ProviderConfigError(ProviderError):
    """Raised when a provider can't be constructed because its
    configuration is invalid (missing API key, unsupported quality,
    Bedrock without an enablement form, etc.). Distinct from runtime
    failures because the cause is structural, not transient.
    """
