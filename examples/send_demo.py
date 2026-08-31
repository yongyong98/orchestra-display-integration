#!/usr/bin/env python3
"""Send a short instrument-handover sequence."""

from __future__ import annotations

import argparse
import time

from orchestra_display import PublisherSettings, RobotDisplay, RobotState


ACTION_SEQUENCE = (
    RobotState.DETECTING_TOOL,
    RobotState.PLANNING,
    RobotState.PICKING_TOOL,
    RobotState.MOVING_TO_HANDOVER,
    RobotState.WAITING_FOR_HAND,
    RobotState.HAND_TRACKING,
    RobotState.WAITING_FOR_RELEASE,
    RobotState.RELEASING_TOOL,
    RobotState.RETURNING,
    RobotState.COMPLETED,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--robot-id", default="rby1-instrument")
    parser.add_argument("--interval", type=float, default=0.5)
    args = parser.parse_args()

    settings = PublisherSettings(heartbeat_interval_s=0)
    with RobotDisplay(args.url, args.robot_id, settings=settings) as display:
        for state in (RobotState.STARTING, RobotState.READY):
            queued = display.state(state, tool="grasper")
            print(f"queued={queued} state={state.value}")
            time.sleep(max(args.interval, 0))

        print(f"queued={display.listening_started()} substate=VOICE_LISTENING")
        time.sleep(max(args.interval, 0))
        print(f"queued={display.voice('그래스퍼')} substate=RECOGNIZED_TEXT")
        time.sleep(max(args.interval, 0))
        print(
            "queued={} state={}".format(
                display.state(RobotState.REQUEST_RECEIVED, tool="grasper"),
                RobotState.REQUEST_RECEIVED.value,
            )
        )
        time.sleep(max(args.interval, 0))

        for state in ACTION_SEQUENCE:
            queued = display.state(state, tool="grasper")
            print(f"queued={queued} state={state.value}")
            time.sleep(max(args.interval, 0))
        if not display.flush(timeout_s=10):
            raise SystemExit("events were not delivered within 10 seconds")


if __name__ == "__main__":
    main()
