"""Transport boundary for Orchestra events."""

from __future__ import annotations

import json
from typing import Any, Protocol
from urllib import error, request


class RetryableTransportError(RuntimeError):
    pass


class PermanentTransportError(RuntimeError):
    pass


class EventTransport(Protocol):
    def send(self, event: dict[str, Any], timeout_s: float) -> None:
        """Deliver one event or raise a classified transport error."""


class HttpEventTransport:
    def __init__(self, base_url: str) -> None:
        self._events_url = f"{base_url.rstrip('/')}/api/v1/events"

    def send(self, event: dict[str, Any], timeout_s: float) -> None:
        try:
            body = json.dumps(
                event,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise PermanentTransportError(
                "event payload is not JSON-serializable"
            ) from exc
        http_request = request.Request(
            self._events_url,
            data=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=timeout_s) as response:
                if response.status != 202:
                    raise RetryableTransportError(f"unexpected HTTP status {response.status}")
        except error.HTTPError as exc:
            if 400 <= exc.code < 500:
                raise PermanentTransportError(f"request rejected with HTTP {exc.code}") from exc
            raise RetryableTransportError(f"server returned HTTP {exc.code}") from exc
        except (error.URLError, TimeoutError, OSError) as exc:
            raise RetryableTransportError(str(exc)) from exc
