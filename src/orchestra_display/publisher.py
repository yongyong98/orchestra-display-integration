"""Non-blocking queue and delivery worker."""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any

from .model import EventFactory, RobotState
from .transport import EventTransport, PermanentTransportError, RetryableTransportError


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PublisherSettings:
    queue_size: int = 200
    request_timeout_s: float = 0.5
    max_attempts: int = 5
    heartbeat_interval_s: float = 1.0

    def __post_init__(self) -> None:
        if self.queue_size < 1:
            raise ValueError("queue_size must be at least 1")
        if self.request_timeout_s <= 0:
            raise ValueError("request_timeout_s must be greater than 0")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.heartbeat_interval_s < 0:
            raise ValueError("heartbeat_interval_s must not be negative")


class AsyncEventPublisher:
    """Queue events immediately and perform network I/O on worker threads."""

    def __init__(
        self,
        event_factory: EventFactory,
        transport: EventTransport,
        settings: PublisherSettings,
    ) -> None:
        self._event_factory = event_factory
        self._transport = transport
        self._settings = settings
        self._queue: queue.Queue[dict[str, Any] | None] = queue.Queue(
            maxsize=settings.queue_size
        )
        self._closed = False
        self._state_lock = threading.Lock()
        self._heartbeat_pending = False
        self._heartbeat_stop = threading.Event()
        self._worker = threading.Thread(
            target=self._run,
            name="orchestra-display-sender",
            daemon=True,
        )
        self._heartbeat_worker = threading.Thread(
            target=self._run_heartbeat,
            name="orchestra-display-heartbeat",
            daemon=True,
        )
        self._worker.start()
        if settings.heartbeat_interval_s > 0:
            self._heartbeat_worker.start()

    def emit_state(
        self,
        state: RobotState | str,
        display_message: str,
        payload: dict[str, Any],
    ) -> bool:
        event = self._event_factory.state(state, display_message, payload)
        return self._enqueue(event.as_dict())

    def emit_voice(self, text: str) -> bool:
        return self._enqueue(self._event_factory.voice(text).as_dict())

    def emit_listening(self, active: bool) -> bool:
        return self._enqueue(self._event_factory.listening(active).as_dict())

    def emit_heartbeat(self, payload: dict[str, Any] | None = None) -> bool:
        return self._enqueue(self._event_factory.heartbeat(payload).as_dict())

    def flush(self, timeout_s: float = 5.0) -> bool:
        deadline = time.monotonic() + timeout_s
        while self._queue.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(0.02)
        return self._queue.unfinished_tasks == 0

    def close(self, timeout_s: float = 2.0) -> None:
        with self._state_lock:
            if self._closed:
                return
            self._closed = True
        self._heartbeat_stop.set()
        if self._heartbeat_worker.is_alive():
            self._heartbeat_worker.join(timeout=timeout_s)
        self.flush(timeout_s)
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            return
        self._worker.join(timeout=timeout_s)

    def _enqueue(self, event: dict[str, Any]) -> bool:
        is_heartbeat = event["event_type"] == "HEARTBEAT"
        with self._state_lock:
            if self._closed:
                return False
            if is_heartbeat:
                if self._heartbeat_pending:
                    return False
                self._heartbeat_pending = True
        try:
            self._queue.put_nowait(event)
            return True
        except queue.Full:
            if is_heartbeat:
                self._complete_heartbeat()
                return False
            self._drop_oldest()
            try:
                self._queue.put_nowait(event)
                return True
            except queue.Full:
                return False

    def _drop_oldest(self) -> None:
        try:
            dropped = self._queue.get_nowait()
            self._queue.task_done()
            if dropped is not None and dropped["event_type"] == "HEARTBEAT":
                self._complete_heartbeat()
            LOGGER.warning(
                "display queue full; dropped event %s",
                None if dropped is None else dropped.get("event_id"),
            )
        except queue.Empty:
            return

    def _run(self) -> None:
        while True:
            event = self._queue.get()
            try:
                if event is None:
                    return
                self._send_with_retry(event)
            finally:
                if event is not None and event["event_type"] == "HEARTBEAT":
                    self._complete_heartbeat()
                self._queue.task_done()

    def _run_heartbeat(self) -> None:
        interval = self._settings.heartbeat_interval_s
        while not self._heartbeat_stop.wait(interval):
            self.emit_heartbeat({"source": "orchestra-display-integration"})

    def _send_with_retry(self, event: dict[str, Any]) -> None:
        max_attempts = (
            1 if event["event_type"] == "HEARTBEAT" else self._settings.max_attempts
        )
        for attempt in range(max_attempts):
            try:
                self._transport.send(event, self._settings.request_timeout_s)
                return
            except PermanentTransportError as exc:
                LOGGER.error("display event rejected: %s", exc)
                return
            except RetryableTransportError:
                if attempt + 1 < max_attempts:
                    time.sleep(min(0.25 * (2**attempt), 2.0))
        LOGGER.warning("display event delivery failed: %s", event["event_id"])

    def _complete_heartbeat(self) -> None:
        with self._state_lock:
            self._heartbeat_pending = False
