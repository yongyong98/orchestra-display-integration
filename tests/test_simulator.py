from __future__ import annotations

import json
import threading
import unittest
from urllib import request

from orchestra_display.simulator import SimulatorServer


class SimulatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.server = SimulatorServer(("127.0.0.1", 0))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_simple_state_is_visible_in_robot_snapshot(self) -> None:
        body = json.dumps(
            {"robot_id": "rby1-instrument", "state": "PLANNING"}
        ).encode("utf-8")
        post = request.Request(
            f"{self.base_url}/api/v1/state",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(post, timeout=2) as response:
            self.assertEqual(response.status, 202)
        with request.urlopen(f"{self.base_url}/api/v1/robots", timeout=2) as response:
            robots = json.loads(response.read().decode("utf-8"))["robots"]
        self.assertEqual(robots[0]["state"], "PLANNING")


if __name__ == "__main__":
    unittest.main()
