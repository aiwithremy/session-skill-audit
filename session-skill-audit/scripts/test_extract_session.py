#!/usr/bin/env python3
"""Behavioral tests for extract_session.py using synthetic private-free archives."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).with_name("extract_session.py")


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(item) + "\n" for item in records), encoding="utf-8")


def run_extract(source: Path, output: Path, *extra: str) -> tuple[str, dict, str, str]:
    process = subprocess.run(
        [sys.executable, str(SCRIPT), str(source), "--output-dir", str(output), *extra],
        check=False,
        capture_output=True,
        text=True,
    )
    if process.returncode != 0:
        raise AssertionError(process.stderr or process.stdout)
    inventory = json.loads((output / "inventory.json").read_text(encoding="utf-8"))
    transcript = (output / "transcript.md").read_text(encoding="utf-8")
    instructions = (output / "instructions.md").read_text(encoding="utf-8")
    return process.stdout, inventory, transcript, instructions


def test_codex(root: Path) -> None:
    source = root / "codex.jsonl"
    output = root / "codex-output"
    records = [
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "type": "session_meta",
            "payload": {"id": "codex-test", "cwd": "/tmp/project", "source": "cli"},
        },
        {
            "timestamp": "2026-01-01T00:00:01Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "developer",
                "content": [{"type": "input_text", "text": "Internal instruction"}],
            },
        },
        {
            "timestamp": "2026-01-01T00:00:02Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Use $newsletter:newsletter-edit and fix it."}
                ],
            },
        },
        {
            "timestamp": "2026-01-01T00:00:02Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "<skill>\n<name>loaded-skill</name>\nSkill body\n</skill>",
                    }
                ],
            },
        },
        {
            "timestamp": "2026-01-01T00:00:03Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call",
                "name": "exec",
                "call_id": "call-1",
                "input": {"cmd": "read /repo/skills/newsletter-edit/SKILL.md", "api_key": "secret"},
            },
        },
        {
            "timestamp": "2026-01-01T00:00:04Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call_output",
                "call_id": "call-1",
                "output": "ERROR: example failure",
            },
        },
        {
            "timestamp": "2026-01-01T00:00:05Z",
            "type": "compacted",
            "payload": {"window_number": 2, "window_id": "window-2"},
        },
    ]
    write_jsonl(source, records)
    _, inventory, transcript, instructions = run_extract(
        source, output, "--include-instructions"
    )
    assert inventory["harness"] == "codex"
    assert inventory["compaction_markers"][0]["kind"] == "codex_compaction"
    assert "newsletter:newsletter-edit" in inventory["skill_mentions"]
    assert "newsletter-edit" in inventory["skill_mentions"]
    assert "loaded-skill" in inventory["skill_mentions"]
    assert "[REDACTED CREDENTIAL]" in transcript
    assert "secret" not in transcript
    assert "ERROR: example failure" in transcript
    assert "Internal instruction" in instructions
    assert "api" not in inventory["skill_mentions"]


def test_claude(root: Path) -> None:
    source = root / "claude.jsonl"
    output = root / "claude-output"
    records = [
        {
            "type": "user",
            "sessionId": "claude-test",
            "cwd": "/tmp/project",
            "uuid": "user-1",
            "timestamp": "2026-01-01T00:00:00Z",
            "message": {"role": "user", "content": "Please run /session-skill-audit."},
        },
        {
            "type": "assistant",
            "sessionId": "claude-test",
            "cwd": "/tmp/project",
            "uuid": "assistant-1",
            "timestamp": "2026-01-01T00:00:01Z",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Read",
                        "id": "tool-1",
                        "input": {"file_path": "/repo/skills/session-skill-audit/SKILL.md"},
                    }
                ],
            },
        },
        {
            "type": "user",
            "sessionId": "claude-test",
            "cwd": "/tmp/project",
            "uuid": "ambient-1",
            "timestamp": "2026-01-01T00:00:01Z",
            "message": {
                "role": "user",
                "content": "<in-app-browser-context>ambient</in-app-browser-context>\n\n## My request:\nKeep this request",
            },
        },
        {
            "type": "user",
            "sessionId": "claude-test",
            "cwd": "/tmp/project",
            "uuid": "user-2",
            "timestamp": "2026-01-01T00:00:02Z",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tool-1",
                        "is_error": False,
                        "content": "skill contents",
                    }
                ],
            },
        },
        {
            "type": "system",
            "subtype": "compact_boundary",
            "sessionId": "claude-test",
            "content": "Conversation compacted",
            "timestamp": "2026-01-01T00:00:03Z",
        },
        {
            "type": "user",
            "isCompactSummary": True,
            "sessionId": "claude-test",
            "uuid": "summary-1",
            "timestamp": "2026-01-01T00:00:04Z",
            "message": {"role": "user", "content": "Synthetic summary must not look like user evidence"},
        },
    ]
    write_jsonl(source, records)
    _, inventory, transcript, _ = run_extract(source, output)
    assert inventory["harness"] == "claude"
    assert len(inventory["compaction_markers"]) == 2
    assert "session-skill-audit" in inventory["skill_mentions"]
    assert "Synthetic summary" not in transcript
    assert "Please run /session-skill-audit" in transcript
    assert "Keep this request" in transcript
    assert "ambient</in-app-browser-context>" not in transcript


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="test-session-skill-audit-") as temp:
        root = Path(temp)
        test_codex(root)
        test_claude(root)
    print("extract_session.py behavioral tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
