from __future__ import annotations

import unittest
from typing import Any

from examples.runtime_integration import RuntimeDisplayHooks
from orchestra_display import RobotState


class RecordingDisplay:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def state(
        self,
        state: RobotState,
        *,
        tool: str | None = None,
        message: str = "",
    ) -> bool:
        self.calls.append((state.value, {"tool": tool, "message": message}))
        return True

    def voice(self, text: str) -> bool:
        self.calls.append(("VOICE", text))
        return True

    def listening_started(self) -> bool:
        self.calls.append(("VOICE_LISTENING", None))
        return True

    def listening_stopped(self) -> bool:
        self.calls.append(("READY", None))
        return True


class RuntimeDisplayHooksTest(unittest.TestCase):
    def setUp(self) -> None:
        self.display = RecordingDisplay()
        self.hooks = RuntimeDisplayHooks(self.display)

    def test_pick_handover_follows_runtime_transition_order(self) -> None:
        self.hooks.initialization_started()
        self.hooks.ready()
        self.hooks.listening_started()
        self.hooks.recognized_tool("그래스퍼")
        self.hooks.request_accepted("grasper")
        self.hooks.tool_detection_started("grasper")
        self.hooks.planning_started("grasper")
        self.hooks.tool_pick_started("grasper")
        self.hooks.handover_move_started("grasper")
        self.hooks.waiting_for_hand("grasper")
        self.hooks.hand_tracking_started("grasper")
        # WAITING_FOR_RELEASE is omitted when the runtime has no stable signal.
        self.hooks.tool_release_started("grasper")
        self.hooks.return_started("grasper")
        self.hooks.handover_completed("grasper")
        self.hooks.ready()

        self.assertEqual(
            [name for name, _ in self.display.calls],
            [
                "STARTING",
                "READY",
                "VOICE_LISTENING",
                "VOICE",
                "REQUEST_RECEIVED",
                "DETECTING_TOOL",
                "PLANNING",
                "PICKING_TOOL",
                "MOVING_TO_HANDOVER",
                "WAITING_FOR_HAND",
                "HAND_TRACKING",
                "RELEASING_TOOL",
                "RETURNING",
                "COMPLETED",
                "READY",
            ],
        )

    def test_receive_place_follows_runtime_transition_order(self) -> None:
        self.hooks.request_accepted("grasper")
        self.hooks.placement_preparation_started("grasper")
        self.hooks.waiting_for_hand("grasper")
        self.hooks.waiting_for_tool("grasper")
        self.hooks.tool_receive_started("grasper")
        self.hooks.tool_placement_started("grasper")
        self.hooks.return_started("grasper")
        self.hooks.ready()

        self.assertEqual(
            [name for name, _ in self.display.calls],
            [
                "REQUEST_RECEIVED",
                "PREPARING",
                "WAITING_FOR_HAND",
                "WAITING_FOR_TOOL",
                "RECEIVING_TOOL",
                "PLACING_TOOL",
                "RETURNING",
                "READY",
            ],
        )
