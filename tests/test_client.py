from __future__ import annotations

import threading
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


class BlockingHeartbeatTransport:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.heartbeat_started = threading.Event()
        self.release_heartbeat = threading.Event()

    def send(self, event: dict[str, Any], _timeout_s: float) -> None:
        if event["event_type"] == "HEARTBEAT" and not self.heartbeat_started.is_set():
            self.heartbeat_started.set()
            self.release_heartbeat.wait(timeout=1.0)
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

    def test_voice_needs_only_final_text_and_follows_current_state(self) -> None:
        transport = RecordingTransport()
        display = RobotDisplay(
            "http://127.0.0.1:8080",
            "rby1-instrument",
            transport=transport,
            settings=PublisherSettings(heartbeat_interval_s=0),
        )
        self.assertTrue(display.state(RobotState.PREPARING))
        self.assertTrue(display.voice("  그래스퍼  "))
        self.assertTrue(display.state(RobotState.WAITING_FOR_HAND))
        self.assertTrue(display.state(RobotState.READY))
        self.assertTrue(display.flush())
        display.close()

        self.assertEqual(transport.events[1]["state"], "PREPARING")
        self.assertEqual(
            transport.events[1]["payload"],
            {"recognized_text": "그래스퍼", "input_source": "voice"},
        )
        self.assertEqual(
            transport.events[2]["payload"]["recognized_text"],
            "그래스퍼",
        )
        self.assertNotIn("recognized_text", transport.events[3]["payload"])

    def test_invalid_voice_text_is_rejected_without_network_work(self) -> None:
        transport = RecordingTransport()
        display = RobotDisplay(
            "http://127.0.0.1:8080",
            "rby1-instrument",
            transport=transport,
            settings=PublisherSettings(heartbeat_interval_s=0),
        )
        self.assertFalse(display.voice("   "))
        self.assertFalse(display.voice("가" * 81))
        display.close()
        self.assertEqual(transport.events, [])

    def test_listening_helpers_keep_voice_ui_inside_ready(self) -> None:
        transport = RecordingTransport()
        display = RobotDisplay(
            "http://127.0.0.1:8080",
            "rby1-instrument",
            transport=transport,
            settings=PublisherSettings(heartbeat_interval_s=0),
        )

        self.assertTrue(display.listening_started())
        self.assertTrue(display.voice("그래스퍼"))
        self.assertTrue(display.listening_stopped())
        self.assertTrue(display.flush())
        display.close()

        self.assertEqual(transport.events[0]["state"], "READY")
        self.assertEqual(transport.events[0]["payload"], {"step": "VOICE_LISTENING"})
        self.assertEqual(transport.events[1]["state"], "READY")
        self.assertEqual(
            transport.events[1]["payload"]["recognized_text"],
            "그래스퍼",
        )
        self.assertEqual(transport.events[2]["state"], "READY")
        self.assertEqual(transport.events[2]["payload"], {})

    def test_heartbeat_does_not_backlog_a_new_state(self) -> None:
        transport = BlockingHeartbeatTransport()
        display = RobotDisplay(
            "http://127.0.0.1:8080",
            "rby1-instrument",
            transport=transport,
            settings=PublisherSettings(
                heartbeat_interval_s=0.01,
                max_attempts=1,
            ),
        )

        self.assertTrue(transport.heartbeat_started.wait(timeout=0.5))
        time.sleep(0.05)
        self.assertTrue(display.state(RobotState.PLANNING))
        transport.release_heartbeat.set()
        display.close()

        self.assertGreaterEqual(len(transport.events), 2)
        self.assertEqual(transport.events[0]["event_type"], "HEARTBEAT")
        self.assertEqual(transport.events[1]["state"], "PLANNING")


if __name__ == "__main__":
    unittest.main()
