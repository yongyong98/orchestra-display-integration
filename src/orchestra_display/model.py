"""Event model shared by the public client and local simulator."""

from __future__ import annotations

import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class RobotState(str, Enum):
    STARTING = "STARTING"
    READY = "READY"
    REQUEST_RECEIVED = "REQUEST_RECEIVED"
    DETECTING_TOOL = "DETECTING_TOOL"
    PLANNING = "PLANNING"
    PICKING_TOOL = "PICKING_TOOL"
    MOVING_TO_HANDOVER = "MOVING_TO_HANDOVER"
    WAITING_FOR_HAND = "WAITING_FOR_HAND"
    HAND_TRACKING = "HAND_TRACKING"
    WAITING_FOR_RELEASE = "WAITING_FOR_RELEASE"
    RELEASING_TOOL = "RELEASING_TOOL"
    RETURNING = "RETURNING"
    COMPLETED = "COMPLETED"
    SAFE_WAIT = "SAFE_WAIT"
    ERROR = "ERROR"

    @classmethod
    def parse(cls, value: RobotState | str) -> RobotState:
        if isinstance(value, cls):
            return value
        return cls(value)


@dataclass(frozen=True)
class DisplayEvent:
    schema_version: int
    event_id: str
    event_type: str
    robot_id: str
    session_id: str
    sequence: int
    state: str
    severity: str
    display_message: str
    occurred_at: str
    payload: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class EventFactory:
    """Create ordered events for one robot session."""

    def __init__(self, robot_id: str, session_id: str) -> None:
        self._robot_id = robot_id
        self._session_id = session_id
        self._sequence = 0
        self._latest_state = RobotState.STARTING
        self._latest_payload: dict[str, Any] = {}
        self._lock = threading.Lock()

    def state(
        self,
        state: RobotState | str,
        display_message: str,
        payload: dict[str, Any],
    ) -> DisplayEvent:
        parsed = RobotState.parse(state)
        with self._lock:
            self._latest_state = parsed
            self._latest_payload = dict(payload)
            return self._create(
                event_type="STATE",
                state=parsed,
                severity=_severity(parsed),
                display_message=display_message,
                payload=payload,
            )

    def heartbeat(self, payload: dict[str, Any] | None = None) -> DisplayEvent:
        with self._lock:
            heartbeat_payload = dict(self._latest_payload)
            heartbeat_payload.update(payload or {})
            return self._create(
                event_type="HEARTBEAT",
                state=self._latest_state,
                severity="INFO",
                display_message="",
                payload=heartbeat_payload,
            )

    def _create(
        self,
        *,
        event_type: str,
        state: RobotState,
        severity: str,
        display_message: str,
        payload: dict[str, Any],
    ) -> DisplayEvent:
        self._sequence += 1
        return DisplayEvent(
            schema_version=1,
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            robot_id=self._robot_id,
            session_id=self._session_id,
            sequence=self._sequence,
            state=state.value,
            severity=severity,
            display_message=display_message,
            occurred_at=datetime.now(timezone.utc).isoformat(),
            payload=dict(payload),
        )


def _severity(state: RobotState) -> str:
    if state is RobotState.ERROR:
        return "ERROR"
    if state is RobotState.SAFE_WAIT:
        return "WARNING"
    return "INFO"
