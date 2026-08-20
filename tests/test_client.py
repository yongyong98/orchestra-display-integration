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


if __name__ == "__main__":
    unittest.main()
