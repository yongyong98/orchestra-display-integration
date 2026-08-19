from __future__ import annotations

import time
import unittest
from typing import Any

from orchestra_display import PublisherSettings, RobotDisplay, RobotState


class RecordingTransport:
    def __init__(self, delay_s: float = 0) -> None:
        self.delay_s = delay_s
        self.events: list[dict[str, Any]] = []

    def send(self, event: dict[str, Any], _timeout_s: float) -> None:
        time.sleep(self.delay_s)
        self.events.append(event)


class RobotDisplayTest(unittest.TestCase):
    def test_state_returns_before_slow_transport_finishes(self) -> None:
        transport = RecordingTransport(delay_s=0.2)
        display = RobotDisplay(
            "http://127.0.0.1:8080",
            "rby1-instrument",
            transport=transport,
            settings=PublisherSettings(heartbeat_interval_s=0),
        )
        started = time.monotonic()
        queued = display.state(RobotState.PLANNING, tool="grasper")
        elapsed = time.monotonic() - started
        self.assertTrue(queued)
        self.assertLess(elapsed, 0.05)
        self.assertTrue(display.flush())
        display.close()
        self.assertEqual(transport.events[0]["state"], "PLANNING")
        self.assertEqual(transport.events[0]["payload"], {"tool": "grasper"})

    def test_unknown_state_is_rejected_without_network_work(self) -> None:
        transport = RecordingTransport()
        display = RobotDisplay(
            "http://127.0.0.1:8080",
            "rby1-instrument",
            transport=transport,
            settings=PublisherSettings(heartbeat_interval_s=0),
        )
        self.assertFalse(display.state("NOT_A_STATE"))
        display.close()
        self.assertEqual(transport.events, [])


if __name__ == "__main__":
    unittest.main()
