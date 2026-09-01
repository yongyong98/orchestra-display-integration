from __future__ import annotations

import json
import threading
import time
import unittest
from typing import Any
from unittest import mock

from orchestra_display import PublisherSettings, RobotDisplay, RobotState
from orchestra_display.transport import RetryableTransportError


class RecordingTransport:
    def __init__(self, delay_s: float = 0) -> None:
        self.delay_s = delay_s
        self.events: list[dict[str, Any]] = []

    def send(self, event: dict[str, Any], _timeout_s: float) -> None:
        time.sleep(self.delay_s)
        self.events.append(event)


class BlockingRetryableTransport:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.attempts = 0

    def send(self, _event: dict[str, Any], _timeout_s: float) -> None:
        self.attempts += 1
        self.started.set()
        self.release.wait(timeout=2)
        raise RetryableTransportError("blocked retryable failure")


class AcceptedResponse:
    status = 202

    def __enter__(self) -> AcceptedResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


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

    def test_close_without_drain_is_bounded_and_stops_after_full_queue(self) -> None:
        transport = BlockingRetryableTransport()
        display = RobotDisplay(
            "http://127.0.0.1:8080",
            "rby1-instrument",
            transport=transport,
            settings=PublisherSettings(queue_size=1, heartbeat_interval_s=0),
        )
        try:
            self.assertTrue(display.state(RobotState.PLANNING))
            self.assertTrue(transport.started.wait(timeout=1))
            self.assertTrue(display.state(RobotState.PICKING_TOOL))

            started = time.monotonic()
            display.close(timeout_s=0.05, drain=False)
            elapsed = time.monotonic() - started

            self.assertLess(elapsed, 0.2)
            self.assertTrue(display._publisher._worker.is_alive())
        finally:
            transport.release.set()
            display._publisher._worker.join(timeout=1)

        self.assertFalse(display._publisher._worker.is_alive())
        self.assertEqual(transport.attempts, 1)

    def test_non_json_payload_is_dropped_and_sender_continues(self) -> None:
        display = RobotDisplay(
            "http://127.0.0.1:8080",
            "rby1-instrument",
            settings=PublisherSettings(max_attempts=1, heartbeat_interval_s=0),
        )
        response = AcceptedResponse()
        with mock.patch(
            "orchestra_display.transport.request.urlopen",
            return_value=response,
        ) as urlopen:
            self.assertTrue(
                display.state(
                    RobotState.PLANNING,
                    details={"not_json": object()},
                )
            )
            self.assertTrue(display.state(RobotState.PICKING_TOOL))
            self.assertTrue(display.flush(timeout_s=1))
            display.close()

        self.assertEqual(urlopen.call_count, 1)
        sent_request = urlopen.call_args.args[0]
        sent_event = json.loads(sent_request.data.decode("utf-8"))
        self.assertEqual(sent_event["state"], "PICKING_TOOL")

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
