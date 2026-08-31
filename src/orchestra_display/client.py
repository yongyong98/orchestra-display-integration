"""Small API used by the robot runtime."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from .model import EventFactory, RobotState
from .publisher import AsyncEventPublisher, PublisherSettings
from .transport import EventTransport, HttpEventTransport


LOGGER = logging.getLogger(__name__)
IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")


class RobotDisplay:
    """Publish display-only state without blocking robot control."""

    def __init__(
        self,
        tablet_url: str,
        robot_id: str,
        *,
        session_id: str | None = None,
        settings: PublisherSettings | None = None,
        transport: EventTransport | None = None,
    ) -> None:
        if not IDENTIFIER.fullmatch(robot_id):
            raise ValueError("robot_id must use 2-64 lowercase letters, numbers, '_' or '-'")
        resolved_session = session_id or datetime.now().strftime("run-%Y%m%d-%H%M%S")
        if not IDENTIFIER.fullmatch(resolved_session):
            raise ValueError("session_id must use 2-64 lowercase letters, numbers, '_' or '-'")
        self._publisher = AsyncEventPublisher(
            event_factory=EventFactory(robot_id, resolved_session),
            transport=transport or HttpEventTransport(tablet_url),
            settings=settings or PublisherSettings(),
        )

    def state(
        self,
        state: RobotState | str,
        *,
        tool: str | None = None,
        message: str = "",
        details: dict[str, Any] | None = None,
    ) -> bool:
        """Queue a state change and return before network delivery finishes."""
        payload = dict(details or {})
        if tool:
            payload["tool"] = tool
        try:
            return self._publisher.emit_state(state, message, payload)
        except ValueError:
            LOGGER.error("unknown display state: %s", state)
            return False

    def voice(self, text: str) -> bool:
        """Queue finalized recognition text; a tool noun is recommended."""
        try:
            return self._publisher.emit_voice(text)
        except (AttributeError, ValueError, TypeError):
            LOGGER.error("voice text must be a 1-80 character string")
            return False

    def listening_started(self) -> bool:
        """Show the conditional voice-listening UI inside READY."""
        return self._publisher.emit_listening(active=True)

    def listening_stopped(self) -> bool:
        """Return to the idle READY UI after a cancelled or empty listen."""
        return self._publisher.emit_listening(active=False)

    def flush(self, timeout_s: float = 5.0) -> bool:
        return self._publisher.flush(timeout_s)

    def close(self) -> None:
        self._publisher.close()

    def __enter__(self) -> RobotDisplay:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
