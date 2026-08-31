#!/usr/bin/env python3
"""Play every Receive–Place screen for UI and connection verification.

The fixed interval is only for visual inspection. For robot runtime integration, use
``runtime_integration.py`` and call each hook from an existing state transition.
"""

from __future__ import annotations

import argparse
import time

from orchestra_display import PublisherSettings, RobotDisplay, RobotState


SEQUENCE = (
    RobotState.PREPARING,
    RobotState.WAITING_FOR_HAND,
    RobotState.WAITING_FOR_TOOL,
    RobotState.RECEIVING_TOOL,
    RobotState.PLACING_TOOL,
    RobotState.RETURNING,
    RobotState.READY,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--robot-id", default="rby1-instrument")
    parser.add_argument("--interval", type=float, default=0.8)
    args = parser.parse_args()

    settings = PublisherSettings(heartbeat_interval_s=0)
    with RobotDisplay(args.url, args.robot_id, settings=settings) as display:
        for state in (RobotState.STARTING, RobotState.READY):
            queued = display.state(state, tool="grasper")
            print(f"queued={queued} state={state.value}")
            time.sleep(max(args.interval, 0))

        print(f"queued={display.listening_started()} substate=VOICE_LISTENING")
        time.sleep(max(args.interval, 0))
        queued = display.voice("그래스퍼")
        print(f"queued={queued} substate=RECOGNIZED_TEXT")
        time.sleep(max(args.interval, 0))
        queued = display.state(RobotState.REQUEST_RECEIVED, tool="grasper")
        print(f"queued={queued} state={RobotState.REQUEST_RECEIVED.value}")
        time.sleep(max(args.interval, 0))

        for state in SEQUENCE:
            queued = display.state(state, tool="grasper")
            print(f"queued={queued} state={state.value}")
            time.sleep(max(args.interval, 0))
        if not display.flush(timeout_s=10):
            raise SystemExit("events were not delivered within 10 seconds")


if __name__ == "__main__":
    main()
