#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["websockets>=17.2"]
# ///
"""live-check fixture: a throwaway thread held by the local Codex app-server daemon.

start <cwd> <id-file>: create a thread and write its id to <id-file> at once, then run
one short turn so its rollout exists; on failure archive it before exiting.
archive <id>: archive it so it leaves the user's thread list.
"""

import asyncio
import json
import os
from pathlib import Path
import sys

from websockets.asyncio.client import unix_connect

SOCKET = (
    Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    / "app-server-control"
    / "app-server-control.sock"
)


async def main(command, arg, id_file=None):
    async with unix_connect(
        str(SOCKET.resolve()), uri="ws://localhost/", max_size=None
    ) as ws:
        next_id = 0

        async def call(method, params):
            nonlocal next_id
            next_id += 1
            await ws.send(
                json.dumps({"id": next_id, "method": method, "params": params})
            )
            while True:
                message = json.loads(await ws.recv())
                if message.get("id") == next_id and "method" not in message:
                    if "error" in message:
                        raise RuntimeError(f"{method}: {message['error']}")
                    return message["result"]

        await call(
            "initialize",
            {"clientInfo": {"name": "cross-agent-live-check", "version": "1"}},
        )
        await ws.send(json.dumps({"method": "initialized"}))
        if command == "archive":
            await call("thread/archive", {"threadId": arg})
            return
        thread_id = (await call("thread/start", {"cwd": arg, "sandbox": "read-only"}))[
            "thread"
        ]["id"]
        Path(id_file).write_text(thread_id + "\n")
        try:
            await call(
                "turn/start",
                {
                    "threadId": thread_id,
                    "input": [{"type": "text", "text": "Reply with exactly: ready"}],
                },
            )
            while json.loads(await ws.recv()).get("method") != "turn/completed":
                pass
        except BaseException:
            await call("thread/archive", {"threadId": thread_id})
            raise


if __name__ == "__main__":
    asyncio.run(asyncio.wait_for(main(*sys.argv[1:4]), 300))
