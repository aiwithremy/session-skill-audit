#!/usr/bin/env python3
"""Recover a normalized local transcript bundle from Claude Code or Codex JSONL.

The script is intentionally read-only with respect to source archives. It writes
an audit bundle to a private temporary directory (or --output-dir) and prints the
bundle path. Hidden/encrypted reasoning is never emitted.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SKILL_DOLLAR_RE = re.compile(r"\$([a-z][a-z0-9:-]{1,63})(?![\w-])")
SKILL_PATH_RE = re.compile(
    r"(?:^|[/\\])skills[/\\]([a-z][a-z0-9-]{0,63})[/\\]SKILL\.md",
    re.I,
)
SKILL_BLOCK_RE = re.compile(r"<name>([a-z0-9][a-z0-9:-]{1,63})</name>")
INSTRUCTION_RE = re.compile(
    r"(?:^|[/\\\s])((?:AGENTS|CLAUDE)\.md|SKILL\.md|\.cursorrules|"
    r"\.cursor[/\\]rules[/\\][^\s]+)",
    re.I,
)
SENSITIVE_KEY_RE = re.compile(
    r"(?:authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|password|passwd|"
    r"secret|cookie|private[_-]?key|security[_-]?token)",
    re.I,
)
SIGNED_QUERY_RE = re.compile(
    r"(?i)(X-Amz-(?:Signature|Credential|Security-Token)|token|signature|sig|key)="
    r"[^&\s]+"
)
BEARER_RE = re.compile(r"(?i)Bearer\s+[A-Za-z0-9._~+/-]+=*")
INSTRUCTION_PREFIXES = (
    "<app-context>",
    "<environment_context>",
    "<permissions",
    "<apps_instructions>",
    "<plugins_instructions>",
    "<skills_instructions>",
    "<recommended_plugins>",
    "<in-app-browser-context",
    "<skill>",
    "# AGENTS.md instructions",
    "## Memory\n",
)


@dataclass
class Candidate:
    harness: str
    path: Path
    session_id: str | None
    cwd: str | None
    mtime: float
    is_child: bool = False
    parent_id: str | None = None


@dataclass
class Event:
    sequence: int
    source: str
    harness: str
    kind: str
    timestamp: str | None = None
    role: str | None = None
    name: str | None = None
    event_id: str | None = None
    content: str = ""
    is_error: bool = False
    truncated: bool = False


@dataclass
class Inventory:
    generated_at: str
    harness: str
    main_session_id: str | None
    main_source: str
    source_files: list[str]
    child_session_ids: list[str]
    transcript_event_count: int = 0
    instruction_event_count: int = 0
    instruction_events_exported: int = 0
    tool_call_count: int = 0
    tool_result_count: int = 0
    compaction_markers: list[dict[str, Any]] = field(default_factory=list)
    skill_mentions: dict[str, list[str]] = field(default_factory=dict)
    instruction_references: dict[str, list[str]] = field(default_factory=dict)
    truncated_events: list[dict[str, Any]] = field(default_factory=list)
    parse_warnings: list[str] = field(default_factory=list)
    coverage_notes: list[str] = field(default_factory=list)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recover a normalized audit bundle from a Claude Code or Codex session."
    )
    parser.add_argument("target", nargs="?", help="Session ID or transcript path")
    parser.add_argument(
        "--source", choices=("auto", "claude", "codex", "generic"), default="auto"
    )
    parser.add_argument("--cwd", default=os.getcwd(), help="Working directory used for discovery")
    parser.add_argument("--contains", help="Distinctive exact text used to identify the session")
    parser.add_argument("--output-dir", help="Directory for the generated audit bundle")
    parser.add_argument("--include-instructions", action="store_true")
    parser.add_argument("--no-children", action="store_true")
    parser.add_argument("--max-tool-chars", type=int, default=8000)
    parser.add_argument("--list", action="store_true", help="List recent candidate sessions")
    args = parser.parse_args()
    if args.max_tool_chars < 500:
        parser.error("--max-tool-chars must be at least 500")
    return args


def read_first_json(path: Path, limit: int = 80) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for _, line in zip(range(limit), handle):
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    return value
    except OSError:
        return None
    return None


def inspect_candidate(path: Path, harness_hint: str | None = None) -> Candidate | None:
    first = read_first_json(path)
    if first is None:
        if harness_hint == "generic":
            return Candidate("generic", path, None, None, path.stat().st_mtime)
        return None

    if first.get("type") == "session_meta" and isinstance(first.get("payload"), dict):
        payload = first["payload"]
        source = payload.get("source")
        is_child = payload.get("thread_source") == "subagent" or (
            isinstance(source, dict) and "subagent" in source
        )
        return Candidate(
            "codex",
            path,
            str(payload.get("id") or payload.get("session_id") or "") or None,
            payload.get("cwd"),
            path.stat().st_mtime,
            is_child=is_child,
            parent_id=payload.get("parent_thread_id") or payload.get("forked_from_id"),
        )

    if first.get("sessionId") or first.get("type") in {
        "user",
        "assistant",
        "queue-operation",
        "attachment",
    }:
        session_id = first.get("sessionId")
        cwd = first.get("cwd")
        if not session_id or not cwd:
            try:
                with path.open("r", encoding="utf-8", errors="replace") as handle:
                    for _, line in zip(range(120), handle):
                        try:
                            value = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        session_id = session_id or value.get("sessionId")
                        cwd = cwd or value.get("cwd")
                        if session_id and cwd:
                            break
            except OSError:
                pass
        return Candidate(
            "claude",
            path,
            str(session_id) if session_id else path.stem,
            cwd,
            path.stat().st_mtime,
            is_child="subagents" in path.parts,
        )

    if harness_hint == "generic":
        return Candidate("generic", path, None, None, path.stat().st_mtime)
    return None


def iter_paths(source: str) -> Iterable[tuple[Path, str | None]]:
    home = Path.home()
    if source in {"auto", "codex"}:
        for root in (home / ".codex/sessions", home / ".codex/archived_sessions"):
            if root.is_dir():
                for path in root.rglob("*.jsonl"):
                    yield path, "codex"
    if source in {"auto", "claude"}:
        root = home / ".claude/projects"
        if root.is_dir():
            for path in root.rglob("*.jsonl"):
                yield path, "claude"


def discover(source: str) -> list[Candidate]:
    candidates: list[Candidate] = []
    for path, hint in iter_paths(source):
        try:
            candidate = inspect_candidate(path, hint)
        except OSError:
            continue
        if candidate and (source == "auto" or candidate.harness == source):
            candidates.append(candidate)
    return candidates


def contains_text(path: Path, needle: str) -> bool:
    raw = needle.encode("utf-8")
    overlap = max(len(raw) - 1, 0)
    try:
        with path.open("rb") as handle:
            tail = b""
            while chunk := handle.read(1024 * 1024):
                data = tail + chunk
                if raw in data:
                    return True
                tail = data[-overlap:] if overlap else b""
    except OSError:
        return False
    return False


def print_candidates(candidates: list[Candidate], limit: int = 15) -> None:
    print("HARNESS  MODIFIED_UTC          SESSION_ID                            CWD  PATH")
    for item in sorted(candidates, key=lambda value: value.mtime, reverse=True)[:limit]:
        stamp = datetime.fromtimestamp(item.mtime, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        child = " child" if item.is_child else ""
        print(
            f"{item.harness:<8} {stamp}  {(item.session_id or '-'):<36} "
            f"{item.cwd or '-'}{child}  {item.path}"
        )


def select_candidate(args: argparse.Namespace, candidates: list[Candidate]) -> Candidate:
    target = args.target
    if target:
        path = Path(target).expanduser()
        if path.is_file():
            candidate = inspect_candidate(path, "generic")
            if not candidate:
                raise SystemExit(f"Could not recognize transcript format: {path}")
            if args.source != "auto" and args.source != candidate.harness and args.source != "generic":
                raise SystemExit(
                    f"Transcript looks like {candidate.harness}, not requested source {args.source}."
                )
            return candidate

        matches = [
            item
            for item in candidates
            if item.session_id == target or target in item.path.name
        ]
        if not matches:
            raise SystemExit(f"No local session matched target: {target}")
        main_matches = [item for item in matches if not item.is_child]
        matches = main_matches or matches
        matches.sort(key=lambda value: value.mtime, reverse=True)
        if len({item.session_id for item in matches}) > 1:
            print_candidates(matches)
            raise SystemExit("Target matched multiple sessions; use an exact ID or path.")
        return matches[0]

    eligible = [item for item in candidates if not item.is_child]
    if args.contains:
        eligible = [item for item in eligible if contains_text(item.path, args.contains)]
        if not eligible:
            raise SystemExit("No main session contains the supplied distinctive phrase.")
        session_ids = {item.session_id or str(item.path) for item in eligible}
        if len(session_ids) != 1:
            print_candidates(eligible)
            raise SystemExit(
                "The phrase appears in multiple sessions; rerun with an exact session ID or path."
            )
        eligible.sort(key=lambda value: value.mtime, reverse=True)
        return eligible[0]

    wanted_cwd = str(Path(args.cwd).expanduser().resolve())
    cwd_matches = [
        item
        for item in eligible
        if item.cwd and str(Path(item.cwd).expanduser().resolve()) == wanted_cwd
    ]
    eligible = cwd_matches or eligible
    if not eligible:
        raise SystemExit("No local Claude or Codex sessions were found.")
    eligible.sort(key=lambda value: value.mtime, reverse=True)
    if len(eligible) > 1 and eligible[0].mtime - eligible[1].mtime < 120:
        print_candidates(eligible)
        raise SystemExit(
            "Recent sessions are ambiguous. Use --contains, an exact session ID, or a path."
        )
    return eligible[0]


def child_candidates(main: Candidate, candidates: list[Candidate]) -> list[Candidate]:
    if main.harness == "claude":
        child_dir = main.path.with_suffix("") / "subagents"
        children: list[Candidate] = []
        if child_dir.is_dir():
            for path in sorted(child_dir.glob("*.jsonl")):
                candidate = inspect_candidate(path, "claude")
                if candidate:
                    candidate.is_child = True
                    candidate.parent_id = main.session_id
                    children.append(candidate)
        return children

    if main.harness == "codex" and main.session_id:
        by_parent: dict[str, list[Candidate]] = {}
        for item in candidates:
            if item.harness == "codex" and item.parent_id:
                by_parent.setdefault(item.parent_id, []).append(item)
        found: list[Candidate] = []
        queue = [main.session_id]
        seen_ids = {main.session_id}
        while queue:
            parent = queue.pop(0)
            for item in by_parent.get(parent, []):
                key = item.session_id or str(item.path)
                if key in seen_ids:
                    continue
                seen_ids.add(key)
                found.append(item)
                if item.session_id:
                    queue.append(item.session_id)
        return sorted(found, key=lambda value: value.mtime)

    return []


def redact_value(value: Any, key: str | None = None) -> Any:
    if key and SENSITIVE_KEY_RE.search(key):
        return "[REDACTED CREDENTIAL]"
    if isinstance(value, dict):
        return {str(k): redact_value(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        value = BEARER_RE.sub("Bearer [REDACTED]", value)
        return SIGNED_QUERY_RE.sub(lambda match: match.group(1) + "=[REDACTED]", value)
    return value


def stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(redact_value(value), ensure_ascii=False, indent=2, sort_keys=True)
    except (TypeError, ValueError):
        return str(value)


def cap(text: str, maximum: int) -> tuple[str, bool]:
    if len(text) <= maximum:
        return text, False
    omitted = len(text) - maximum
    return text[:maximum] + f"\n\n[... {omitted} characters omitted by extractor ...]", True


def split_codex_message(role: str | None, text: str) -> list[tuple[str, str]]:
    """Separate harness-injected context from the visible user request."""
    if role in {"developer", "system"}:
        return [("instruction", text)]
    if text.startswith("<in-app-browser-context") and "## My request:" in text:
        context, request = text.split("## My request:", 1)
        pieces = [("instruction", context.rstrip())]
        if request.strip():
            pieces.append(("message", request.strip()))
        return pieces
    if text.startswith(INSTRUCTION_PREFIXES):
        return [("instruction", text)]
    return [("message", text)]


def codex_events(
    candidate: Candidate,
    source_label: str,
    max_tool_chars: int,
    include_instructions: bool,
) -> tuple[list[Event], list[Event], list[dict[str, Any]], list[str]]:
    transcript: list[Event] = []
    instructions: list[Event] = []
    markers: list[dict[str, Any]] = []
    warnings: list[str] = []
    sequence = 0
    try:
        handle = candidate.path.open("r", encoding="utf-8", errors="replace")
    except OSError as exc:
        return [], [], [], [f"Could not read {candidate.path}: {exc}"]

    with handle:
        for line_number, line in enumerate(handle, 1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                warnings.append(f"{source_label}:{line_number}: invalid JSON: {exc}")
                continue
            record_type = record.get("type")
            payload = record.get("payload")
            timestamp = record.get("timestamp")
            if record_type == "compacted" and isinstance(payload, dict):
                marker = {
                    "source": source_label,
                    "line": line_number,
                    "timestamp": timestamp,
                    "kind": "codex_compaction",
                    "window_number": payload.get("window_number"),
                    "window_id": payload.get("window_id"),
                }
                markers.append(marker)
                continue
            if record_type != "response_item" or not isinstance(payload, dict):
                continue

            item_type = payload.get("type")
            if item_type == "message":
                role = payload.get("role")
                blocks = payload.get("content") or []
                if not isinstance(blocks, list):
                    blocks = [blocks]
                for block_index, block in enumerate(blocks, 1):
                    if not isinstance(block, dict):
                        continue
                    text = block.get("text") or block.get("content")
                    if not isinstance(text, str) or not text:
                        continue
                    for piece_index, (destination, piece) in enumerate(
                        split_codex_message(role, text), 1
                    ):
                        sequence += 1
                        event = Event(
                            sequence,
                            source_label,
                            "codex",
                            "message",
                            timestamp=timestamp,
                            role=role,
                            event_id=(
                                f"line-{line_number}-block-{block_index}-piece-{piece_index}"
                            ),
                            content=piece,
                        )
                        if destination == "instruction":
                            instructions.append(event)
                        elif role in {"user", "assistant"}:
                            transcript.append(event)
                continue

            if item_type in {"function_call", "custom_tool_call"}:
                raw = payload.get("arguments") if item_type == "function_call" else payload.get("input")
                text, truncated = cap(stringify(redact_value(raw)), max_tool_chars)
                sequence += 1
                transcript.append(
                    Event(
                        sequence,
                        source_label,
                        "codex",
                        "tool_call",
                        timestamp=timestamp,
                        name=payload.get("name"),
                        event_id=payload.get("call_id") or f"line-{line_number}",
                        content=text,
                        truncated=truncated,
                    )
                )
                continue

            if item_type in {"function_call_output", "custom_tool_call_output"}:
                text, truncated = cap(
                    stringify(redact_value(payload.get("output"))), max_tool_chars
                )
                sequence += 1
                transcript.append(
                    Event(
                        sequence,
                        source_label,
                        "codex",
                        "tool_result",
                        timestamp=timestamp,
                        event_id=payload.get("call_id") or f"line-{line_number}",
                        content=text,
                        is_error=bool(payload.get("is_error")),
                        truncated=truncated,
                    )
                )
    return transcript, instructions, markers, warnings


def claude_events(
    candidate: Candidate,
    source_label: str,
    max_tool_chars: int,
    include_instructions: bool,
) -> tuple[list[Event], list[Event], list[dict[str, Any]], list[str]]:
    del include_instructions  # Export selection happens after inventory extraction.
    transcript: list[Event] = []
    instructions: list[Event] = []
    markers: list[dict[str, Any]] = []
    warnings: list[str] = []
    sequence = 0
    try:
        handle = candidate.path.open("r", encoding="utf-8", errors="replace")
    except OSError as exc:
        return [], [], [], [f"Could not read {candidate.path}: {exc}"]

    with handle:
        for line_number, line in enumerate(handle, 1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                warnings.append(f"{source_label}:{line_number}: invalid JSON: {exc}")
                continue
            timestamp = record.get("timestamp")
            if record.get("type") == "system" and record.get("subtype") == "compact_boundary":
                markers.append(
                    {
                        "source": source_label,
                        "line": line_number,
                        "timestamp": timestamp,
                        "kind": "claude_compact_boundary",
                    }
                )
                continue
            if record.get("isCompactSummary") is True:
                markers.append(
                    {
                        "source": source_label,
                        "line": line_number,
                        "timestamp": timestamp,
                        "kind": "claude_compact_summary",
                    }
                )
                continue
            if record.get("type") not in {"user", "assistant"}:
                continue
            message = record.get("message")
            if not isinstance(message, dict):
                continue
            role = message.get("role") or record.get("type")
            content = message.get("content")
            blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content
            if not isinstance(blocks, list):
                continue
            for block_index, block in enumerate(blocks, 1):
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                event_id = block.get("id") or record.get("uuid") or f"line-{line_number}"
                if block_type == "text" and isinstance(block.get("text"), str):
                    for piece_index, (destination, piece) in enumerate(
                        split_codex_message(role, block["text"]), 1
                    ):
                        sequence += 1
                        event = Event(
                            sequence,
                            source_label,
                            "claude",
                            "message",
                            timestamp=timestamp,
                            role=role,
                            event_id=f"{event_id}-block-{block_index}-piece-{piece_index}",
                            content=piece,
                        )
                        if destination == "instruction":
                            instructions.append(event)
                        else:
                            transcript.append(event)
                elif block_type == "tool_use":
                    text, truncated = cap(
                        stringify(redact_value(block.get("input"))), max_tool_chars
                    )
                    sequence += 1
                    transcript.append(
                        Event(
                            sequence,
                            source_label,
                            "claude",
                            "tool_call",
                            timestamp=timestamp,
                            name=block.get("name"),
                            event_id=event_id,
                            content=text,
                            truncated=truncated,
                        )
                    )
                elif block_type == "tool_result":
                    text, truncated = cap(
                        stringify(redact_value(block.get("content"))), max_tool_chars
                    )
                    sequence += 1
                    transcript.append(
                        Event(
                            sequence,
                            source_label,
                            "claude",
                            "tool_result",
                            timestamp=timestamp,
                            event_id=block.get("tool_use_id") or event_id,
                            content=text,
                            is_error=bool(block.get("is_error")),
                            truncated=truncated,
                        )
                    )
    return transcript, instructions, markers, warnings


def generic_events(
    candidate: Candidate, source_label: str, max_tool_chars: int
) -> tuple[list[Event], list[Event], list[dict[str, Any]], list[str]]:
    transcript: list[Event] = []
    warnings: list[str] = []
    try:
        lines = candidate.path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return [], [], [], [f"Could not read {candidate.path}: {exc}"]
    for line_number, line in enumerate(lines, 1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            text, truncated = cap(line, max_tool_chars)
            transcript.append(
                Event(
                    line_number,
                    source_label,
                    "generic",
                    "message",
                    role="unknown",
                    event_id=f"line-{line_number}",
                    content=text,
                    truncated=truncated,
                )
            )
            continue
        if not isinstance(record, dict):
            continue
        role = record.get("role") or record.get("type") or "unknown"
        content = record.get("content") or record.get("text") or record.get("message")
        text, truncated = cap(stringify(redact_value(content)), max_tool_chars)
        transcript.append(
            Event(
                line_number,
                source_label,
                "generic",
                "message",
                timestamp=record.get("timestamp"),
                role=str(role),
                event_id=str(record.get("id") or f"line-{line_number}"),
                content=text,
                truncated=truncated,
            )
        )
    warnings.append(
        "Generic parsing was used; inspect the raw export before relying on role or tool classification."
    )
    return transcript, [], [], warnings


def add_mentions(
    inventory: Inventory,
    event: Event,
    skill_evidence_limit: int = 8,
    instruction_context: bool = False,
) -> None:
    text = event.content
    evidence = f"{event.source}:{event.event_id or event.sequence}"
    names: set[str] = set()
    if instruction_context:
        if text.startswith("<skill>"):
            names.update(match.group(1) for match in SKILL_BLOCK_RE.finditer(text))
    elif event.kind != "tool_result":
        if event.kind == "message":
            names.update(match.group(1) for match in SKILL_DOLLAR_RE.finditer(text))
        names.update(match.group(1) for match in SKILL_PATH_RE.finditer(text))
        names.update(match.group(1) for match in SKILL_BLOCK_RE.finditer(text))
    for name in sorted(names):
        bucket = inventory.skill_mentions.setdefault(name, [])
        if evidence not in bucket and len(bucket) < skill_evidence_limit:
            bucket.append(evidence)
    if event.kind == "tool_result":
        return
    for match in INSTRUCTION_RE.finditer(text):
        name = match.group(1)
        bucket = inventory.instruction_references.setdefault(name, [])
        if evidence not in bucket and len(bucket) < skill_evidence_limit:
            bucket.append(evidence)


def render_event(event: Event) -> str:
    label = event.kind.replace("_", " ").title()
    if event.role:
        label += f" · {event.role}"
    if event.name:
        label += f" · {event.name}"
    identity = event.event_id or str(event.sequence)
    stamp = f" · {event.timestamp}" if event.timestamp else ""
    flags = []
    if event.is_error:
        flags.append("ERROR")
    if event.truncated:
        flags.append("EXTRACTOR-TRUNCATED")
    flag_text = f" · {', '.join(flags)}" if flags else ""
    content = event.content.rstrip()
    return (
        f"## {label}\n\n"
        f"Source: `{event.source}` · Event: `{identity}`{stamp}{flag_text}\n\n"
        f"{content}\n"
    )


def make_output_dir(value: str | None) -> Path:
    if value:
        output = Path(value).expanduser().resolve()
        output.mkdir(parents=True, exist_ok=True)
    else:
        output = Path(tempfile.mkdtemp(prefix="session-skill-audit-"))
    try:
        output.chmod(stat.S_IRWXU)
    except OSError:
        pass
    return output


def write_bundle(
    output: Path,
    inventory: Inventory,
    transcript: list[Event],
    instructions: list[Event],
) -> None:
    transcript_header = (
        "# Normalized session transcript\n\n"
        "Generated locally for a session skill audit. Hidden/encrypted reasoning is not included. "
        "Tool payloads marked EXTRACTOR-TRUNCATED must be checked in the raw source before supporting "
        "a finding.\n\n"
    )
    transcript_text = transcript_header + "\n".join(render_event(event) for event in transcript)
    (output / "transcript.md").write_text(transcript_text, encoding="utf-8")

    instructions_header = (
        "# Session instruction records\n\n"
        "These are harness-supplied developer/system or recognized instruction-context records. "
        "They are separated from the visible conversation to avoid mistaking them for user messages.\n\n"
    )
    instructions_text = instructions_header + "\n".join(render_event(event) for event in instructions)
    (output / "instructions.md").write_text(instructions_text, encoding="utf-8")

    (output / "inventory.json").write_text(
        json.dumps(asdict(inventory), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for path in output.iterdir():
        try:
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass


def main() -> int:
    args = parse_args()
    explicit_file = bool(args.target and Path(args.target).expanduser().is_file())
    candidates = discover(args.source) if not explicit_file else []
    if args.list:
        print_candidates(candidates)
        return 0

    main_candidate = select_candidate(args, candidates)
    if args.source == "generic" and main_candidate.harness != "generic":
        main_candidate.harness = "generic"
    selected = [main_candidate]
    if not args.no_children:
        if main_candidate.harness == "codex" and not candidates:
            candidates = discover("codex")
        selected.extend(child_candidates(main_candidate, candidates))

    inventory = Inventory(
        generated_at=datetime.now(timezone.utc).isoformat(),
        harness=main_candidate.harness,
        main_session_id=main_candidate.session_id,
        main_source=str(main_candidate.path),
        source_files=[str(item.path) for item in selected],
        child_session_ids=[item.session_id or item.path.stem for item in selected[1:]],
    )
    if not selected[1:]:
        inventory.coverage_notes.append("No linked child-agent transcript was discovered.")
    if main_candidate.harness == "claude":
        inventory.coverage_notes.append(
            "Claude compact summaries were excluded as synthetic user messages; original archived turns were retained."
        )
    elif main_candidate.harness == "codex":
        inventory.coverage_notes.append(
            "Codex encrypted/internal reasoning records were excluded; visible messages and tool events were retained."
        )

    transcript: list[Event] = []
    instructions: list[Event] = []
    for index, candidate in enumerate(selected):
        label = "main" if index == 0 else f"child-{index}-{candidate.session_id or candidate.path.stem}"
        if candidate.harness == "codex":
            events, instruction_events, markers, warnings = codex_events(
                candidate, label, args.max_tool_chars, args.include_instructions
            )
        elif candidate.harness == "claude":
            events, instruction_events, markers, warnings = claude_events(
                candidate, label, args.max_tool_chars, args.include_instructions
            )
        else:
            events, instruction_events, markers, warnings = generic_events(
                candidate, label, args.max_tool_chars
            )
        transcript.extend(events)
        instructions.extend(instruction_events)
        inventory.compaction_markers.extend(markers)
        inventory.parse_warnings.extend(warnings)

    for sequence, event in enumerate(transcript, 1):
        event.sequence = sequence
        add_mentions(inventory, event)
        if event.kind == "tool_call":
            inventory.tool_call_count += 1
        elif event.kind == "tool_result":
            inventory.tool_result_count += 1
        if event.truncated:
            inventory.truncated_events.append(
                {
                    "source": event.source,
                    "event_id": event.event_id,
                    "kind": event.kind,
                    "name": event.name,
                }
            )
    for event in instructions:
        add_mentions(inventory, event, instruction_context=True)

    inventory.transcript_event_count = len(transcript)
    inventory.instruction_event_count = len(instructions)
    exported_instructions = instructions if args.include_instructions else []
    inventory.instruction_events_exported = len(exported_instructions)
    if inventory.truncated_events:
        inventory.coverage_notes.append(
            f"{len(inventory.truncated_events)} tool or generic events were capped by the extractor; inspect raw sources for material findings."
        )
    if not args.include_instructions:
        inventory.coverage_notes.append(
            "Harness developer/system instruction bodies were not exported; rerun with --include-instructions if they may be causal."
        )

    output = make_output_dir(args.output_dir)
    write_bundle(output, inventory, transcript, exported_instructions)
    print(f"Audit bundle: {output}")
    print(f"Harness: {inventory.harness}")
    print(f"Session: {inventory.main_session_id or '-'}")
    print(f"Sources: {len(inventory.source_files)}")
    print(f"Transcript events: {inventory.transcript_event_count}")
    print(
        "Instruction events: "
        f"{inventory.instruction_event_count} detected, "
        f"{inventory.instruction_events_exported} exported"
    )
    print(f"Compaction markers: {len(inventory.compaction_markers)}")
    print(f"Extractor-truncated events: {len(inventory.truncated_events)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
