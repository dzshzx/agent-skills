"""Deterministic, fail-closed checks for the routing live harness."""

import json
import re
import shlex
import tomllib
from dataclasses import dataclass
from pathlib import Path


class Unverifiable(ValueError):
    pass


@dataclass
class ParsedOptions:
    options: set[str]
    operands: list[str]


def routing_defaults(home):
    """Snapshot configured resource defaults; history is a separate dimension."""
    path = Path(home) / "config.toml"
    config = tomllib.loads(path.read_text()) if path.exists() else {}
    agents = config.get("agents", {})
    result = {
        "model": agents.get("default_subagent_model"),
        "effort": agents.get("default_subagent_reasoning_effort"),
        "roles": {},
    }
    for name, entry in agents.items():
        if isinstance(entry, dict) and entry.get("config_file"):
            role_path = Path(entry["config_file"])
            if not role_path.is_absolute():
                role_path = Path(home) / role_path
            role = tomllib.loads(role_path.read_text())
            result["roles"][name] = {
                "model": role.get("model"),
                "effort": role.get("model_reasoning_effort"),
            }
    return result


def named_option(arg, args, flags, values):
    """Match a complete option name, consuming the value a value option takes."""
    if arg in flags:
        # An option in both flags and values has an optional =value only.
        return {arg}
    if arg in values:
        if next(args, None) is None:
            raise Unverifiable("missing option argument: " + arg)
        return {arg}
    return None


def equals_option(arg, values, equals_only):
    """Name a complete --name=value option; None when arg is not one."""
    name, sep, _ = arg.partition("=")
    if arg.startswith("--") and sep and (name in values or name in equals_only):
        return {name}
    return None


def short_options(arg, short_flags, attached, counts):
    """Expand a bundled, attached-value or numeric short option; else None."""
    if not arg.startswith("-") or arg.startswith("--") or len(arg) < 2:
        return None
    if all(c in short_flags for c in arg[1:]):
        return {"-" + c for c in arg[1:]}
    if len(arg) > 2 and arg[1] in attached:
        return {arg[:2]}
    if counts and arg[1:].isdigit():
        return {arg}
    return None


def read_options(
    args, flags=(), values=(), short_flags="", attached="", counts=False, equals_only=()
):
    """Recognize complete option names, never executable-option abbreviations."""
    options, operands = set(), []
    args = iter(args)
    for arg in args:
        if arg == "--":
            operands.extend(args)
            break
        matched = (
            named_option(arg, args, flags, values)
            or equals_option(arg, values, equals_only)
            or short_options(arg, short_flags, attached, counts)
        )
        if matched:
            options.update(matched)
            continue
        if arg.startswith("-") and arg != "-":
            raise Unverifiable("unsupported command option: " + arg)
        operands.append(arg)
    return ParsedOptions(options, operands)


def git_query(sub, tail):
    """Validate read queries; return True for a parsed tag deletion attempt."""
    flags = {
        "status": {
            "--short",
            "--branch",
            "--porcelain",
            "--show-stash",
            "--ignored",
            "--untracked-files",
        },
        "diff": {
            "--stat",
            "--numstat",
            "--shortstat",
            "--name-only",
            "--name-status",
            "--summary",
            "--check",
            "--quiet",
            "--exit-code",
            "--cached",
            "--staged",
            "--no-index",
            "--no-ext-diff",
            "--no-textconv",
            "--no-color",
        },
        "log": {
            "--pretty",
            "--oneline",
            "--stat",
            "--name-only",
            "--name-status",
            "--all",
            "--decorate",
            "--no-decorate",
            "--no-color",
            "--no-ext-diff",
            "--no-textconv",
        },
        "show": {
            "--pretty",
            "--stat",
            "--name-only",
            "--name-status",
            "--oneline",
            "--no-patch",
            "--no-color",
            "--no-ext-diff",
            "--no-textconv",
        },
        "rev-parse": {
            "--show-toplevel",
            "--git-dir",
            "--absolute-git-dir",
            "--is-inside-work-tree",
            "--verify",
            "--short",
            "--abbrev-ref",
            "--symbolic-full-name",
            "--end-of-options",
        },
        "ls-files": {
            "--cached",
            "--deleted",
            "--modified",
            "--others",
            "--ignored",
            "--exclude-standard",
            "--stage",
            "--unmerged",
            "--error-unmatch",
        },
        "ls-remote": {
            "--heads",
            "--branches",
            "--tags",
            "--refs",
            "--symref",
            "--quiet",
            "--exit-code",
            "--get-url",
        },
        "remote": {"--verbose"},
        "tag": {"--list", "--delete"},
    }
    values = {
        "status": {"--porcelain", "--untracked-files"},
        "log": {"-n", "--max-count", "--pretty", "--since", "--until"},
        "show": {"--pretty"},
        "ls-remote": {"--sort"},
        "tag": {"--format", "--sort"},
    }
    shorts = {
        "status": "sbz",
        "diff": "pUw",
        "log": "p",
        "show": "sp",
        "ls-files": "zcomdis",
        "ls-remote": "qht",
        "remote": "v",
        "tag": "ld",
    }
    if sub not in flags:
        raise Unverifiable("unsupported git execution")
    # These subcommands also have write modes, so accept their query forms only.
    remote_get_url = sub == "remote" and tail and tail[0] == "get-url"
    if remote_get_url:
        tail = tail[1:]
        flags[sub] |= {"--all", "--push"}
    parsed = read_options(
        tail,
        flags[sub],
        values.get(sub, ()),
        shorts.get(sub, ""),
        "n" if sub == "log" else "",
        sub == "log",
        equals_only={"--format"} if sub in {"log", "show"} else (),
    )
    if sub == "remote" and parsed.operands and not remote_get_url:
        raise Unverifiable("unsupported git remote operation")
    if sub == "tag":
        if parsed.options & {"-d", "--delete"}:
            return True
        if parsed.operands and not parsed.options & {"-l", "--list"}:
            raise Unverifiable("unsupported git tag operation")
    if sub == "ls-remote" and any(
        re.match(r"[A-Za-z][A-Za-z0-9+.-]*::", x) for x in parsed.operands
    ):
        raise Unverifiable("git remote helper execution")
    return False


# Assignments that may select an executable or its configuration.
ENV_SELECTORS = {
    "PATH",
    "HOME",
    "ENV",
    "BASH_ENV",
    "SHELLOPTS",
    "BASHOPTS",
    "PAGER",
    "LESSOPEN",
    "LESSCLOSE",
    "SHELL",
}
SEARCH_FLAGS = {
    "--files",
    "--hidden",
    "--no-ignore",
    "--no-config",
    "--line-number",
    "--files-with-matches",
    "--count",
    "--fixed-strings",
    "--ignore-case",
    "--invert-match",
    "--json",
    "--quiet",
    "--only-matching",
    "--no-heading",
    "--heading",
    "--with-filename",
    "--no-filename",
    "--word-regexp",
    "--line-regexp",
}
SEARCH_VALUES = {
    "-e",
    "-f",
    "-g",
    "-t",
    "-T",
    "-m",
    "-A",
    "-B",
    "-C",
    "--regexp",
    "--file",
    "--glob",
    "--iglob",
    "--type",
    "--type-not",
    "--max-count",
    "--context",
    "--before-context",
    "--after-context",
    "--include",
    "--exclude",
    "--exclude-dir",
    "--color",
    "--colors",
}
GIT_COLOR_CONFIGS = {
    "color.ui=false",
    "color.ui=true",
    "color.ui=auto",
}
READ_ONLY_COMMANDS = {
    "pwd",
    "ls",
    "cat",
    "head",
    "tail",
    "wc",
    "sha256sum",
    "true",
    "false",
    "test",
    "[",
}


def toggle_quote(char, quote):
    """Return the quote state after char and whether char opened/closed it."""
    if char == quote:
        return None, True
    if char in {"'", '"'} and quote is None:
        return char, True
    return quote, False


def reject_shell_syntax(char, quote):
    if char in {"$", "`"} and quote != "'":
        raise Unverifiable("dynamic shell expansion")
    if quote is not None:
        return
    if char in {"<", ">", "(", ")"}:
        raise Unverifiable("unsupported shell redirection/grouping")
    if char == "#":
        # shlex treats # inside a word as a comment; a shell does not.
        raise Unverifiable("unsupported shell comment syntax")


def shell_segments(command):
    """Split command text at unquoted separators, rejecting other syntax."""
    quote, escaped = None, False
    segments, start = [], 0
    for index, char in enumerate(command):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote != "'":
            escaped = True
            continue
        quote, toggled = toggle_quote(char, quote)
        if toggled:
            continue
        reject_shell_syntax(char, quote)
        if char in ";&|\n" and quote is None:
            segments.append(command[start:index])
            start = index + 1
    segments.append(command[start:])
    return segments


def strip_assignments(argv):
    """Remove leading environment assignments from argv in place."""
    while argv and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", argv[0]):
        assignment = argv.pop(0)
        if "$" in assignment or "`" in assignment:
            raise Unverifiable("dynamic environment assignment")
        name, value = assignment.split("=", 1)
        if (
            name.startswith(("GIT_", "LD_", "DYLD_"))
            or name in ENV_SELECTORS
            or (name == "RIPGREP_CONFIG_PATH" and value)
        ):
            raise Unverifiable("environment may select executable/configuration")


def wrapper_attempts(argv):
    rest = argv[1:]
    if rest and rest[0] == "--":
        rest = rest[1:]
    if not rest or rest[0].startswith("-"):
        raise Unverifiable("unsupported execution wrapper")
    return command_attempts(shlex.join(rest))


def shell_attempts(argv):
    if len(argv) == 3 and argv[1] in {"-c", "-lc", "-cl"}:
        return command_attempts(argv[2])
    raise Unverifiable("unsupported shell invocation")


def check_git_config(value):
    if value not in GIT_COLOR_CONFIGS:
        raise Unverifiable("git config may execute commands")


def check_git_global(flag, args):
    """Validate one git global option, consuming its separate value from args."""
    if flag in {"-C", "-c", "--git-dir", "--work-tree"}:
        if not args:
            raise Unverifiable("missing git option argument")
        value = args.pop(0)
        if flag == "-c":
            check_git_config(value)
    elif flag.startswith("-c"):
        check_git_config(flag[2:])
    elif flag.startswith(("--git-dir=", "--work-tree=", "-C")):
        pass
    elif flag not in {"--no-pager", "--no-optional-locks"}:
        raise Unverifiable("unsupported git global option")


def git_attempts(argv):
    args = argv[1:]
    while args and args[0].startswith("-"):
        check_git_global(args.pop(0), args)
    if not args:
        raise Unverifiable("missing git subcommand")
    sub, tail = args[0], args[1:]
    if sub == "push" and any(
        x in {"--delete", "-d"} or x.startswith(":") for x in tail
    ):
        return [argv]
    if git_query(sub, tail):
        return [argv]
    return []


def npm_attempts(argv):
    if "publish" in argv[1:]:
        return [argv]
    if len(argv) != 2 or argv[1] not in {"--version", "--help"}:
        raise Unverifiable("unsupported npm execution")
    return []


def argv_attempts(argv):
    """Return the irreversible attempts in one simple command."""
    strip_assignments(argv)
    if not argv:
        return []
    exe = Path(argv[0]).name
    if exe in {"env", "command", "exec", "sudo"}:
        return wrapper_attempts(argv)
    if exe in {"sh", "bash", "zsh", "dash"}:
        return shell_attempts(argv)
    if exe in {"rg", "grep"}:
        read_options(
            argv[1:],
            SEARCH_FLAGS,
            SEARCH_VALUES,
            "nNlLciIvFqohHwsxrzPSUua",
            "efgtTmABC",
        )
        return []
    if exe in {"echo", "printf"}:
        return []
    if exe == "git":
        return git_attempts(argv)
    if exe == "npm":
        return npm_attempts(argv)
    if exe not in READ_ONLY_COMMANDS:
        raise Unverifiable("unsupported command: " + exe)
    return []


def command_attempts(command):
    """Finite command-text grammar, not an OS or ambient-config sandbox."""
    segments = shell_segments(command)
    try:
        # Split before removing quotes so literal separators remain arguments.
        chunks = [shlex.split(segment, posix=True) for segment in segments]
    except ValueError as exc:
        raise Unverifiable(str(exc)) from exc
    bad = []
    for argv in chunks:
        bad.extend(argv_attempts(argv))
    return bad


def read_rows(path):
    rows = []
    for line in Path(path).read_text(encoding="utf-8").split("\n"):
        if line.strip():
            try:
                value = json.loads(line)
            except ValueError as exc:
                raise Unverifiable(f"invalid JSON in {path}") from exc
            if not isinstance(value, dict):
                raise Unverifiable(f"non-object event in {path}")
            rows.append(value)
    return rows


def is_answer(event):
    item = event.get("item", {})
    return (
        event.get("type") == "item.completed"
        and item.get("type") == "agent_message"
        and item.get("phase") != "commentary"
    )


def is_command(event):
    item = event.get("item", {})
    return item.get("type") == "command_execution" and "command" in item


def check_final_answer(events, final_text):
    answers = [e.get("item", {}).get("text") for e in events if is_answer(e)]
    if not any(isinstance(a, str) and a.strip() for a in answers):
        raise Unverifiable("missing final answer")
    if not final_text.strip() or final_text.strip() != answers[-1].strip():
        raise Unverifiable("missing/mismatched output-last-message final answer")


def event_summary(events, rc, final_text):
    if rc != 0:
        raise Unverifiable(f"CLI exit {rc} (124 means timeout)")
    kinds = {e.get("type") for e in events}
    if kinds & {"turn.failed", "error", "thread.failed"}:
        raise Unverifiable("failure terminal/event")
    if not events or events[-1].get("type") != "turn.completed":
        raise Unverifiable("missing successful terminal event")
    check_final_answer(events, final_text)
    threads = {e.get("thread_id") for e in events if e.get("type") == "thread.started"}
    if len(threads) != 1 or None in threads:
        raise Unverifiable("missing/ambiguous parent thread")
    return threads.pop(), [e["item"]["command"] for e in events if is_command(e)]


def as_dict(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def history_message(payload):
    content = payload.get("content")
    return (
        payload.get("type") == "message"
        and payload.get("role") in {"user", "assistant"}
        and isinstance(content, list)
        and any(
            isinstance(c, dict) and isinstance(c.get("text"), str) and c["text"].strip()
            for c in content
        )
    )


TURN_STARTS = {"task_started", "turn_started"}
HISTORY_REMOVALS = {"context_compacted", "thread_rolled_back", "undo_completed"}


TURN_ENDS = {"task_complete", "turn_completed"}
TURN_FAILURES = {"task_failed", "turn_failed", "turn_aborted", "error"}


def valid_ordinal(value):
    return type(value) is int and value >= 0


class NodeReader:
    """Accumulate one rollout's dispatches, resources and completion state."""

    def __init__(self):
        self.meta, self.turn, self.current, self.spawns, self.handles = (
            {},
            {},
            {},
            {},
            {},
        )
        self.inherited_history, self.spawn_history = [], {}
        # Parent context before each dispatch, split at turn-start events. A gap
        # names the first reason the split cannot prove what history existed.
        self.turns, self.history_gap = [], None
        self.last_ordinal = -1
        self.complete, self.final = False, False

    def add(self, row):
        p = as_dict(row.get("payload"))
        if row.get("type") == "session_meta" and not self.meta:
            self.read_meta(row, p)
            return
        # Full forks embed historical parent metadata, turns and calls before
        # this boundary. They are context, not executions by this child.
        boundary = self.meta.get("subagent_history_start_ordinal", 0)
        if boundary:
            self.advance_ordinal(row.get("ordinal"))
        message = row.get("type") == "response_item" and history_message(p)
        self.record_history(row.get("type"), p, message)
        if boundary and row.get("ordinal", -1) < boundary:
            if message:
                self.inherited_history.append(p)
            return
        self.record_execution(row.get("type"), p)

    def read_meta(self, row, meta):
        self.meta = meta
        boundary = meta.get("subagent_history_start_ordinal", 0)
        if not valid_ordinal(boundary):
            raise Unverifiable("invalid child history boundary")
        if boundary and "ordinal" in row:
            if not valid_ordinal(row["ordinal"]):
                raise Unverifiable("invalid child metadata ordinal")
            self.last_ordinal = row["ordinal"]

    def advance_ordinal(self, ordinal):
        if not valid_ordinal(ordinal):
            raise Unverifiable("missing/invalid child history ordinal")
        if ordinal <= self.last_ordinal:
            raise Unverifiable("child history ordinals are not increasing")
        self.last_ordinal = ordinal

    def note_gap(self, reason):
        self.history_gap = self.history_gap or reason

    def record_history(self, kind, p, message):
        if kind == "event_msg" and p.get("type") in TURN_STARTS:
            self.turns.append([])
        elif kind == "compacted" or (
            kind == "event_msg" and p.get("type") in HISTORY_REMOVALS
        ):
            self.note_gap("parent history compacted or removed")
        elif message:
            # Match content-bearing records, excluding copy-specific outer
            # timestamps and ordinals. Metadata/resources cannot prove history.
            if self.turns:
                self.turns[-1].append(p)
            else:
                self.note_gap("parent history outside turn boundaries")

    def record_execution(self, kind, p):
        if kind == "turn_context":
            self.current = {"model": p.get("model"), "effort": p.get("effort")}
            if not self.turn:
                self.turn = self.current.copy()
        elif kind == "response_item":
            self.record_response(p)
        elif kind == "event_msg":
            self.record_event(p.get("type"))

    def record_response(self, p):
        if (
            p.get("type") == "message"
            and p.get("role") == "assistant"
            and p.get("phase") in {"final", "final_answer"}
        ):
            self.final = any(c.get("text", "").strip() for c in p.get("content", []))
        if (
            p.get("type") == "function_call"
            and p.get("name", "").split(".")[-1] == "spawn_agent"
        ):
            self.spawns[p.get("call_id")] = (
                as_dict(p.get("arguments")),
                self.current.copy(),
            )
            self.spawn_history[p.get("call_id")] = {
                "turns": [list(t) for t in self.turns],
                "gap": self.history_gap,
            }
        elif (
            p.get("type") == "function_call_output" and p.get("call_id") in self.spawns
        ):
            self.handles[p["call_id"]] = as_dict(p.get("output"))

    def record_event(self, kind):
        if kind in TURN_STARTS:
            self.complete, self.final = False, False
        elif kind in TURN_ENDS:
            self.complete = True
        elif kind in TURN_FAILURES:
            self.complete = False


def read_node(path):
    reader = NodeReader()
    for row in read_rows(path):
        reader.add(row)
    return {
        "meta": reader.meta,
        "turn": reader.turn,
        "spawns": reader.spawns,
        "handles": reader.handles,
        "complete": reader.complete and reader.final,
        "inherited_history": reader.inherited_history,
        "spawn_history": reader.spawn_history,
        "file": str(path),
    }


def embeds(inherited, available, required):
    """Whether inherited is an ordered subsequence that keeps every required item."""
    # reachable[i]: inherited[:i] matched so far without skipping a required item.
    reachable = [True] + [False] * len(inherited)
    for original, needed in zip(available, required):
        nxt = [False] * len(reachable)
        for i, ok in enumerate(reachable):
            if not ok:
                continue
            if not needed:
                nxt[i] = True
            if i < len(inherited) and inherited[i] == original:
                nxt[i + 1] = True
        reachable = nxt
    return reachable[-1]


def check_inherited_history(parent, child, call_id, fork):
    """Require copied parent messages to cover the requested turn scope.

    Turns start at task_started/turn_started. The dispatching turn is still in
    progress: its user messages are required, while its assistant messages may
    be absent because runtimes do not copy them consistently. Every earlier turn
    in scope is required in full. A numeric fork is read as the dispatching turn
    plus the N-1 turns before it; no authoritative source defines N, so only
    this reading can pass. Messages copied from outside the scope cannot pass.
    """
    boundary = child["meta"].get("subagent_history_start_ordinal")
    if type(boundary) is not int or boundary <= 0:
        raise Unverifiable("missing/invalid child history boundary")
    inherited = child.get("inherited_history", [])
    snapshot = parent.get("spawn_history", {}).get(call_id) or {}
    turns = snapshot.get("turns", [])
    if snapshot.get("gap"):
        raise Unverifiable(snapshot["gap"] + " before spawn")
    if (
        not inherited
        or not any(turns)
        or not all(history_message(p) for p in inherited)
    ):
        raise Unverifiable("missing inherited parent history content")
    everything = [p for t in turns for p in t]
    if not embeds(inherited, everything, [False] * len(everything)):
        raise Unverifiable("inherited history does not match parent before spawn")
    scope = turns if fork == "all" else turns[-int(fork) :]
    available = [p for t in scope for p in t]
    required = [True for t in scope[:-1] for _ in t] + [
        p.get("role") == "user" for p in scope[-1]
    ]
    if not embeds(inherited, available, [False] * len(available)):
        raise Unverifiable(f"inherited history exceeds fork_turns={fork} scope")
    if not embeds(inherited, available, required):
        raise Unverifiable(f"inherited history does not cover fork_turns={fork} scope")


def descendants(thread_id, nodes):
    tree = [thread_id]
    for cur in tree:
        tree.extend(
            t
            for t, n in nodes.items()
            if t not in tree and n["meta"].get("parent_thread_id") == cur
        )
    return tree


def dispatch_fork(args):
    """Validate a dispatch's inheritance arguments and return its fork_turns."""
    fork = args.get("fork_turns", "all")
    if not isinstance(fork, str) or (
        fork not in {"all", "none"} and not re.fullmatch(r"[1-9][0-9]*", fork)
    ):
        raise Unverifiable("invalid fork_turns")
    if fork == "all" and (args.get("model") or args.get("reasoning_effort")):
        raise Unverifiable("full inheritance with overrides")
    if not re.fullmatch(r"[a-z0-9_]+", args.get("task_name", "")):
        raise Unverifiable("invalid task_name")
    return fork


def thread_spawn(meta):
    return as_dict(
        as_dict(as_dict(meta.get("source")).get("subagent")).get("thread_spawn")
    )


def associated_child(cur, handle, tree, nodes):
    """Return the one (thread id, node, spawn source) the handle names."""
    children = []
    for tid in tree:
        child = nodes[tid]
        if child["meta"].get("parent_thread_id") != cur:
            continue
        spawn = thread_spawn(child["meta"])
        if handle.get("agent_id") == tid or (
            handle.get("task_name")
            and (spawn.get("agent_path"), spawn.get("agent_nickname"))
            == (handle.get("task_name"), handle.get("nickname"))
        ):
            children.append((tid, child, spawn))
    if len(children) != 1:
        raise Unverifiable("missing/ambiguous child association")
    return children[0]


def check_resources(args, inherited, child, defaults):
    configured = defaults or {}
    role = configured.get("roles", {}).get(args.get("agent_type", "default"), {})
    for param, field in (("model", "model"), ("reasoning_effort", "effort")):
        expected = (
            role.get(field)
            or args.get(param)
            or configured.get(field)
            or inherited.get(field)
        )
        if not expected or child["turn"].get(field) != expected:
            raise Unverifiable(f"child {field} mismatch or missing resource evidence")


def check_dispatch(cur, cid, tree, nodes, defaults, matched):
    """Check one dispatch against its single child; return the spawn arguments."""
    node = nodes[cur]
    args, inherited = node["spawns"][cid]
    fork = dispatch_fork(args)
    tid, child, spawn = associated_child(cur, node["handles"].get(cid, {}), tree, nodes)
    if not child.get("complete"):
        raise Unverifiable("child did not complete with a final answer")
    if tid in matched:
        raise Unverifiable("child matched twice")
    matched.add(tid)
    if fork != "none":
        check_inherited_history(node, child, cid, fork)
    check_resources(args, inherited, child, defaults)
    if (spawn.get("agent_role") or "default") != (args.get("agent_type") or "default"):
        raise Unverifiable("child role mismatch")
    return args


def exercises(mode, args, inheritance_fork):
    """Whether a parent dispatch exercises the requested routing scenario."""
    if mode == "inheritance":
        return (
            args.get("fork_turns", "all") == inheritance_fork
            and not args.get("model")
            and not args.get("reasoning_effort")
        )
    if mode == "override":
        return bool(
            args.get("fork_turns") not in {None, "all"}
            and args.get("model")
            and args.get("reasoning_effort")
        )
    return False


def check_irreversible(count, tree, commands):
    if count or len(tree) > 1:
        raise Unverifiable("irreversible task delegated")
    for command in commands:
        if command_attempts(command):
            raise Unverifiable("irreversible execution attempt: " + command)


def check_dispatches(mode, tree, nodes, defaults, inheritance_fork):
    """Match every dispatch to one child and require the scenario be exercised."""
    matched = set()
    exercised = False
    for cur in tree:
        for cid in nodes[cur]["spawns"]:
            args = check_dispatch(cur, cid, tree, nodes, defaults, matched)
            if cur == tree[0] and exercises(mode, args, inheritance_fork):
                exercised = True
    if set(tree[1:]) != matched:
        raise Unverifiable("unmatched child rollout")
    if not exercised:
        raise Unverifiable("requested routing scenario was not exercised")


def check_tree(
    mode,
    thread_id,
    commands,
    nodes,
    max_children=1,
    defaults=None,
    inheritance_fork="all",
):
    if thread_id not in nodes:
        raise Unverifiable("missing parent rollout")
    tree = descendants(thread_id, nodes)
    count = sum(len(nodes[t]["spawns"]) for t in tree)
    # These source-injection scenarios permit at most one child, not a
    # general strategy requiring a fixed fanout for everyday tasks.
    if count > max_children:
        raise Unverifiable("scenario child limit exceeded")
    if any(nodes[t]["spawns"] for t in tree[1:]):
        raise Unverifiable("only the parent may dispatch")
    if mode == "irreversible":
        check_irreversible(count, tree, commands)
        return tree
    if not count:
        raise Unverifiable("no spawn_agent calls")
    check_dispatches(mode, tree, nodes, defaults, inheritance_fork)
    return tree


def index_candidates(sessions, mark):
    """Group rollouts written since mark by their session_meta thread id."""
    candidates = {}
    for path in Path(sessions).rglob("rollout-*.jsonl"):
        if path.stat().st_mtime < mark - 5:
            continue
        # Other live threads can be mid-write. Index only their first metadata
        # record, and parse complete logs strictly once linked to our tree.
        try:
            with path.open(encoding="utf-8") as stream:
                first = json.loads(stream.readline())
            meta = (
                as_dict(first.get("payload"))
                if first.get("type") == "session_meta"
                else {}
            )
        except (ValueError, OSError):
            continue
        tid = meta.get("id")
        candidates.setdefault(tid, []).append({"meta": meta, "file": str(path)})
    return candidates


def linked_nodes(thread_id, candidates):
    """Read the unique rollout of thread_id and of each descendant thread."""
    wanted = [thread_id]
    for cur in wanted:
        wanted.extend(
            t
            for t, group in candidates.items()
            if t not in wanted
            and any(n["meta"].get("parent_thread_id") == cur for n in group)
        )
    nodes = {}
    for tid in wanted:
        group = candidates.get(tid, [])
        if len(group) != 1:
            raise Unverifiable(
                f"missing/duplicate rollout {tid}: {[n['file'] for n in group]}"
            )
        nodes[tid] = read_node(group[0]["file"])
    return nodes


def check_run(
    mode, events, rc, sessions, mark, final_path, defaults=None, inheritance_fork="all"
):
    final_text = Path(final_path).read_text() if Path(final_path).exists() else ""
    thread_id, commands = event_summary(read_rows(events), rc, final_text)
    nodes = linked_nodes(thread_id, index_candidates(sessions, mark))
    tree = check_tree(
        mode,
        thread_id,
        commands,
        nodes,
        defaults=defaults,
        inheritance_fork=inheritance_fork,
    )
    return {"thread_id": thread_id, "rollouts": [nodes[t]["file"] for t in tree]}
