#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["websockets>=17.2"]
# ///
"""Start a turn on a Codex thread held by the local app-server daemon, or steer the running one.

Exit codes: 0 sent (with --wait: turn completed, final answer on stdout);
1 error or failed turn (with --steer, also a thread with no running turn: nothing is started); 3 no daemon, or it does not hold the thread (use exec resume);
4 the thread is busy (without --steer); 5 the turn sent a request this script cannot answer, such as
an approval; 124 --wait timed out (the turn keeps running).
"""

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

from websockets.asyncio.client import unix_connect
from websockets.exceptions import ConnectionClosed

APPROVALS = {
    "applyPatchApproval",
    "execCommandApproval",
    "item/commandExecution/requestApproval",
    "item/fileChange/requestApproval",
    "item/permissions/requestApproval",
}


def control_socket(codex_home):
    home = Path(codex_home or os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    return (home / "app-server-control" / "app-server-control.sock").resolve()


class Connection:
    def __init__(self, ws):
        self.ws = ws
        self.next_id = 0
        self.events = []

    async def call(self, method, params):
        self.next_id += 1
        request_id = self.next_id
        await self.ws.send(
            json.dumps({"id": request_id, "method": method, "params": params})
        )
        while True:
            message = json.loads(await self.ws.recv())
            if message.get("id") == request_id and "method" not in message:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message["result"]
            self.events.append(message)

    async def next_event(self):
        if self.events:
            return self.events.pop(0)
        return json.loads(await self.ws.recv())


async def wait_for_turn(conn, turn_id):
    final = None
    while True:
        message = await conn.next_event()
        method = message.get("method")
        params = message.get("params") or {}
        if "id" in message and method:
            kind = "an approval" if method in APPROVALS else "a request"
            print(
                f"turn {turn_id} sent {kind} ({method}) this script cannot answer;"
                " answer it in the Codex app",
                file=sys.stderr,
            )
            return 5, None
        if method == "item/completed":
            item = params.get("item") or {}
            if item.get("type") == "agentMessage" and item.get("phase") != "commentary":
                final = item.get("text")
        elif (
            method == "turn/completed"
            and (params.get("turn") or {}).get("id") == turn_id
        ):
            turn = params["turn"]
            if turn.get("status") != "completed":
                print(
                    f"turn {turn_id} ended {turn.get('status')}: {turn.get('error')}",
                    file=sys.stderr,
                )
                return 1, final
            if not final:
                print(
                    f"turn {turn_id} completed without a final answer", file=sys.stderr
                )
                return 1, None
            return 0, final


async def run(args):
    text = Path(args.brief).read_text(encoding="utf-8")
    if not text.strip():
        print("brief is empty", file=sys.stderr)
        return 1
    sock = control_socket(args.codex_home)
    try:
        connection = await unix_connect(str(sock), uri="ws://localhost/", max_size=None)
    except (FileNotFoundError, ConnectionRefusedError):
        print(f"no app-server daemon at {sock}; use exec resume", file=sys.stderr)
        return 3
    async with connection as ws:
        conn = Connection(ws)
        await conn.call(
            "initialize",
            {"clientInfo": {"name": "cross-agent-delegation", "version": "1"}},
        )
        await ws.send(json.dumps({"method": "initialized"}))
        loaded = await conn.call("thread/loaded/list", {})
        if args.thread_id not in loaded.get("data", []):
            print(
                "the daemon does not hold this thread; use exec resume", file=sys.stderr
            )
            return 3
        thread = (await conn.call("thread/read", {"threadId": args.thread_id}))[
            "thread"
        ]
        status = (thread.get("status") or {}).get("type")
        if status == "systemError":
            print(
                "thread is in systemError; check it in the Codex app", file=sys.stderr
            )
            return 1
        if args.steer:
            if status != "active":
                print(
                    f"thread status is {status}; --steer needs a running turn",
                    file=sys.stderr,
                )
                return 1
            full = (
                await conn.call(
                    "thread/read", {"threadId": args.thread_id, "includeTurns": True}
                )
            )["thread"]
            running = [
                t for t in full.get("turns", []) if t.get("status") == "inProgress"
            ]
            if not running:
                print("no in-progress turn found to steer", file=sys.stderr)
                return 1
            turn_id = running[-1]["id"]
            if args.wait:
                await conn.call(
                    "thread/resume", {"threadId": args.thread_id, "excludeTurns": True}
                )
            steered = await conn.call(
                "turn/steer",
                {
                    "threadId": args.thread_id,
                    "expectedTurnId": turn_id,
                    "input": [{"type": "text", "text": text}],
                },
            )
            turn_id = steered["turnId"]
            print(
                json.dumps(
                    {"thread_id": args.thread_id, "turn_id": turn_id, "steered": True}
                ),
                file=sys.stderr,
            )
            return await finish(conn, turn_id, args)
        if status != "idle":
            print(
                f"thread status is {status}; send only to an idle thread",
                file=sys.stderr,
            )
            return 4
        if args.wait:
            # turn/start alone does not subscribe this connection to the thread's events.
            await conn.call(
                "thread/resume", {"threadId": args.thread_id, "excludeTurns": True}
            )
        started = await conn.call(
            "turn/start",
            {"threadId": args.thread_id, "input": [{"type": "text", "text": text}]},
        )
        turn_id = started["turn"]["id"]
        print(
            json.dumps({"thread_id": args.thread_id, "turn_id": turn_id}),
            file=sys.stderr,
        )
        return await finish(conn, turn_id, args)


async def finish(conn, turn_id, args):
    if not args.wait:
        return 0
    try:
        code, final = await asyncio.wait_for(wait_for_turn(conn, turn_id), args.timeout)
    except TimeoutError:
        print(f"turn {turn_id} still running after {args.timeout}s", file=sys.stderr)
        return 124
    if final:
        print(final)
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("thread_id")
    parser.add_argument("brief", help="file holding the brief")
    parser.add_argument(
        "--wait", action="store_true", help="stay connected and print the final answer"
    )
    parser.add_argument(
        "--steer",
        action="store_true",
        help="insert the brief into the thread's running turn (turn/steer); exit 1 if none",
    )
    parser.add_argument(
        "--timeout", type=float, default=1800, help="seconds to wait with --wait"
    )
    parser.add_argument("--codex-home", help="defaults to $CODEX_HOME or ~/.codex")
    try:
        return asyncio.run(run(parser.parse_args()))
    except (OSError, RuntimeError, ConnectionClosed) as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
