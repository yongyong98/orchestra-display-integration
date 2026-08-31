"""Reference hooks for connecting an existing robot runtime to Display.

This module does not implement motion, waiting, timing, or safety decisions. Call each
hook from the corresponding transition that already exists in the robot runtime.
"""

from __future__ import annotations

from typing import Protocol

from orchestra_display import RobotState


class DisplayClient(Protocol):
    """The small RobotDisplay surface used by the runtime hooks."""

    def state(
        self,
        state: RobotState,
        *,
        tool: str | None = None,
        message: str = "",
    ) -> bool: ...

    def voice(self, text: str) -> bool: ...

    def listening_started(self) -> bool: ...

    def listening_stopped(self) -> bool: ...


class RuntimeDisplayHooks:
    """Translate existing runtime transitions into non-blocking Display events."""

    def __init__(self, display: DisplayClient) -> None:
        self._display = display

    def initialization_started(self) -> None:
        self._display.state(RobotState.STARTING)

    def ready(self) -> None:
        """Call after both the ready pose and request receiver are available."""
        self._display.state(RobotState.READY)

    def listening_started(self) -> None:
        self._display.listening_started()

    def listening_cancelled(self) -> None:
        self._display.listening_stopped()

    def recognized_tool(self, tool_display_name: str) -> None:
        """Send the finalized tool noun shown to the user, for example '그래스퍼'."""
        self._display.voice(tool_display_name)

    def request_accepted(self, tool: str) -> None:
        """Call only after the tool is supported and the robot command is accepted."""
        self._display.state(RobotState.REQUEST_RECEIVED, tool=tool)

    def tool_detection_started(self, tool: str) -> None:
        self._display.state(RobotState.DETECTING_TOOL, tool=tool)

    def planning_started(self, tool: str) -> None:
        self._display.state(RobotState.PLANNING, tool=tool)

    def tool_pick_started(self, tool: str) -> None:
        self._display.state(RobotState.PICKING_TOOL, tool=tool)

    def handover_move_started(self, tool: str) -> None:
        self._display.state(RobotState.MOVING_TO_HANDOVER, tool=tool)

    def waiting_for_hand(self, tool: str) -> None:
        self._display.state(RobotState.WAITING_FOR_HAND, tool=tool)

    def hand_tracking_started(self, tool: str) -> None:
        self._display.state(RobotState.HAND_TRACKING, tool=tool)

    def waiting_for_release(self, tool: str) -> None:
        """Call only when the runtime already provides a stable handover signal."""
        self._display.state(RobotState.WAITING_FOR_RELEASE, tool=tool)

    def tool_release_started(self, tool: str) -> None:
        self._display.state(RobotState.RELEASING_TOOL, tool=tool)

    def return_started(self, tool: str | None = None) -> None:
        self._display.state(RobotState.RETURNING, tool=tool)

    def handover_completed(self, tool: str) -> None:
        """Call after successful delivery and before the next READY transition."""
        self._display.state(RobotState.COMPLETED, tool=tool)

    def placement_preparation_started(self, tool: str) -> None:
        self._display.state(RobotState.PREPARING, tool=tool)

    def waiting_for_tool(self, tool: str) -> None:
        self._display.state(RobotState.WAITING_FOR_TOOL, tool=tool)

    def tool_receive_started(self, tool: str) -> None:
        self._display.state(RobotState.RECEIVING_TOOL, tool=tool)

    def tool_placement_started(self, tool: str) -> None:
        self._display.state(RobotState.PLACING_TOOL, tool=tool)

    def recoverable_hold_started(self, message: str = "") -> None:
        """Call only for an existing hold that the runtime can resume."""
        self._display.state(RobotState.SAFE_WAIT, message=message)

    def terminal_error(self, message: str = "") -> None:
        self._display.state(RobotState.ERROR, message=message)
