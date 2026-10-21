#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["websockets>=17.3"]
# ///
"""Offline stand-in for the Codex app-server daemon, for test_codex_thread_turn.py.

fake_codex_daemon.py <codex-home> <scenario.json> <log.jsonl>: serve one thread on
<codex-home>/app-server-control/app-server-control.sock; scenario holds the thread id, its
status type and its turns, and is reread on each connection so one daemon can serve several
scenarios. Every request is appended to the log; a sent turn completes at once with the final
answer "done".
"""

import asyncio
import json
from pathlib import Path
import sys

from websockets.asyncio.server import unix_serve


async def main(home, scenario_path, log_path):
    sock = Path(home) / "app-server-control" / "app-server-control.sock"
    sock.parent.mkdir(parents=True, exist_ok=True)
    log = Path(log_path)

    async def handle(ws):
        scenario = json.loads(Path(scenario_path).read_text())
        async for raw in ws:
            message = json.loads(raw)
            if "id" not in message:
                continue
            with log.open("a") as fh:
                fh.write(json.dumps(message) + "\n")
            method, params = message["method"], message.get("params") or {}
            turn_id = None
            if method == "thread/loaded/list":
                result = {"data": [scenario["thread_id"]]}
            elif method == "thread/read":
                thread = {
                    "id": scenario["thread_id"],
                    "status": {"type": scenario["status"]},
                }
                if params.get("includeTurns"):
                    thread["turns"] = scenario.get("turns", [])
                result = {"thread": thread}
            elif method == "turn/start":
                turn_id = "new-turn"
                result = {"turn": {"id": turn_id}}
            elif method == "turn/steer":
                turn_id = params["expectedTurnId"]
                result = {"turnId": turn_id}
            else:
                result = {}
            await ws.send(json.dumps({"id": message["id"], "result": result}))
            if turn_id:
                for note in (
                    {
                        "method": "item/completed",
                        "params": {"item": {"type": "agentMessage", "text": "done"}},
                    },
                    {
                        "method": "turn/completed",
                        "params": {"turn": {"id": turn_id, "status": "completed"}},
                    },
                ):
                    await ws.send(json.dumps(note))

    async with unix_serve(handle, str(sock)):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main(*sys.argv[1:4]))
