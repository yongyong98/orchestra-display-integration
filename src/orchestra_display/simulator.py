"""Local API receiver used when a Lenovo tablet is not available."""

from __future__ import annotations

import argparse
import json
import threading
import uuid
from collections import deque
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from .model import RobotState


ADMIN_PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Orchestra Display Receiver</title><style>
body{font-family:system-ui,sans-serif;margin:32px;color:#152832;background:#f5f8fa}
h1{margin-bottom:4px}.note{color:#607783;margin-top:0}table{width:100%;border-collapse:collapse;background:white}
th,td{padding:12px 14px;text-align:left;border-bottom:1px solid #dce5e9}th{background:#eaf1f4}
.ok{color:#087f67;font-weight:700}code{font-size:13px}</style></head>
<body><h1>Orchestra Display Receiver</h1><p class="note">Lenovo 없이 API 수신만 확인하는 개발용 화면입니다.</p>
<p id="status" class="ok">수신 대기 중</p><table><thead><tr><th>수신 시각</th><th>로봇</th><th>상태</th><th>도구</th></tr></thead>
<tbody id="events"></tbody></table><script>
async function refresh(){const r=await fetch('/debug/events');const d=await r.json();
document.querySelector('#status').textContent=`수신 이벤트 ${d.events.length}건`;
document.querySelector('#events').innerHTML=d.events.slice().reverse().map(e=>
`<tr><td>${e.server_received_at||'-'}</td><td><code>${e.robot_id}</code></td><td><code>${e.state}</code></td><td>${e.payload?.tool||'-'}</td></tr>`).join('');}
refresh();setInterval(refresh,1000);</script></body></html>"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventStore:
    def __init__(self, max_events: int = 200) -> None:
        self._events: deque[dict[str, Any]] = deque(maxlen=max_events)
        self._event_ids: set[str] = set()
        self._lock = threading.Lock()

    def accept(self, event: dict[str, Any]) -> tuple[bool, str]:
        received_at = utc_now()
        event_id = str(event["event_id"])
        with self._lock:
            duplicate = event_id in self._event_ids
            if not duplicate:
                stored = dict(event)
                stored["server_received_at"] = received_at
                self._events.append(stored)
                self._event_ids.add(event_id)
                while len(self._event_ids) > self._events.maxlen * 2:
                    self._event_ids = {item["event_id"] for item in self._events}
        return duplicate, received_at

    def events(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._events)

    def robots(self) -> list[dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        last_seen: dict[str, str] = {}
        for event in self.events():
            last_seen[event["robot_id"]] = event["server_received_at"]
            if event.get("event_type") == "STATE":
                latest[event["robot_id"]] = event
        return [
            {
                "robot_id": event["robot_id"],
                "session_id": event["session_id"],
                "sequence": event["sequence"],
                "state": event["state"],
                "severity": event["severity"],
                "presence": "CONNECTED",
                "display_message": event.get("display_message", ""),
                "last_seen_at": last_seen[event["robot_id"]],
                "payload": event.get("payload", {}),
            }
            for event in latest.values()
        ]


class SimulatorServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int]) -> None:
        self.store = EventStore()
        self.started_at = utc_now()
        super().__init__(address, SimulatorHandler)


class SimulatorHandler(BaseHTTPRequestHandler):
    server: SimulatorServer

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/", "/admin"):
            self._send(HTTPStatus.OK, ADMIN_PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/api/v1/health":
            now = utc_now()
            self._send_json(HTTPStatus.OK, {"status": "ok", "api_version": "v1", "server_time": now, "started_at": self.server.started_at})
        elif path == "/api/v1/robots":
            self._send_json(HTTPStatus.OK, {"server_time": utc_now(), "robots": self.server.store.robots()})
        elif path == "/debug/events":
            self._send_json(HTTPStatus.OK, {"events": self.server.store.events()})
        else:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path not in ("/api/v1/events", "/api/v1/state"):
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        try:
            body = self._read_json()
            event = body if path.endswith("/events") else self._expand_state(body)
            self._validate(event)
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": "validation_failed", "message": str(exc)})
            return
        duplicate, received_at = self.server.store.accept(event)
        print(f"received {event['robot_id']} {event['state']} seq={event['sequence']}")
        self._send_json(
            HTTPStatus.ACCEPTED,
            {"accepted": True, "event_id": event["event_id"], "duplicate": duplicate, "server_received_at": received_at},
        )

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _read_json(self) -> dict[str, Any]:
        if "application/json" not in self.headers.get("Content-Type", ""):
            raise ValueError("Content-Type must be application/json")
        length = int(self.headers.get("Content-Length", "0"))
        if length < 1 or length > 64 * 1024:
            raise ValueError("request body size is invalid")
        value = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("request body must be a JSON object")
        return value

    def _expand_state(self, body: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        return {
            "schema_version": 1,
            "event_id": str(uuid.uuid4()),
            "event_type": "STATE",
            "robot_id": body["robot_id"],
            "session_id": "simulator-state",
            "sequence": len(self.server.store.events()) + 1,
            "state": body["state"],
            "severity": "ERROR" if body["state"] == "ERROR" else "WARNING" if body["state"] == "SAFE_WAIT" else "INFO",
            "display_message": body.get("display_message", ""),
            "occurred_at": now,
            "payload": body.get("payload", {}),
        }

    @staticmethod
    def _validate(event: dict[str, Any]) -> None:
        required = ("event_id", "event_type", "robot_id", "session_id", "sequence", "state", "severity", "occurred_at")
        missing = [key for key in required if key not in event]
        if missing:
            raise ValueError(f"missing fields: {', '.join(missing)}")
        RobotState.parse(event["state"])
        if event["event_type"] not in ("STATE", "HEARTBEAT"):
            raise ValueError("event_type must be STATE or HEARTBEAT")

    def _send_json(self, status: HTTPStatus, value: dict[str, Any]) -> None:
        self._send(status, json.dumps(value, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a local Orchestra Display API receiver")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8080, type=int)
    args = parser.parse_args()
    server = SimulatorServer((args.host, args.port))
    print(f"receiver: http://{args.host}:{server.server_port}")
    print(f"admin:    http://{args.host}:{server.server_port}/admin")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
