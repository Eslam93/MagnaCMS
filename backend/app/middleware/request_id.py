"""X-Request-ID middleware. Generates a UUID when the request lacks one.

The id is stored on `request.state.request_id`, exposed via the
`X-Request-ID` response header, and pushed into the contextvar used by
structlog so every log line for the request carries it.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.request_context import set_request_id

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a request id to the request and response."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        request.state.request_id = request_id
        set_request_id(request_id)
        try:
            response = await call_next(request)
        finally:
            set_request_id(None)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
