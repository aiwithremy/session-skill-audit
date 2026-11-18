# Transcript recovery

Recover the original session evidence before running the retrospective. Auto-compaction changes what remains in active context; it does not normally remove earlier entries from Claude Code or Codex's local JSONL archive.

## Bundled helper

Resolve `scripts/extract_session.py` relative to this skill's own `SKILL.md`. Do not assume a fixed installation path because installed plugins and loose-loaded skills live in different locations.

The helper writes a private temporary audit bundle containing:

- `transcript.md` — normalized visible conversation plus tool calls/results;
- `instructions.md` — developer/system instruction records when requested;
- `inventory.json` — detected skill mentions, instruction-file references, compaction markers, source files, and coverage counts.

It never edits the source archive.

### Current session

Use a distinctive exact phrase from one of the user's recent messages:

```bash
python3 /absolute/path/to/session-skill-audit/scripts/extract_session.py \
  --source auto \
  --cwd "$PWD" \
  --contains "distinctive phrase from the current request"
```

The phrase is used only for local file selection. If more than one transcript contains it, the helper prints the matching candidates and stops. Rerun with a session ID or explicit path.

### Older session by ID

```bash
python3 /absolute/path/to/session-skill-audit/scripts/extract_session.py \
  SESSION_ID_HERE
```

### Explicit archive or exported transcript

```bash
python3 /absolute/path/to/session-skill-audit/scripts/extract_session.py \
  /absolute/path/to/session.jsonl
```

Use `--output-dir` only when a stable local audit folder is genuinely useful. Otherwise accept the automatically created private temporary directory and remove it after the review if appropriate.

Use `--include-instructions` when the cause may depend on harness-level developer/system instructions. It places those large records in `instructions.md` rather than mixing them into the visible conversation.

Use `--max-tool-chars N` to change the per-event tool payload cap. The default preserves enough context for errors and routing while preventing a multi-megabyte API response from swallowing the audit. The inventory records every truncation. A truncated tool result that is material to a finding must be inspected directly in the raw JSONL before making the finding.

## Coverage rules

1. **Claude Code:** inspect `~/.claude/projects/**/*.jsonl`. Include the main transcript and the main session's `subagents/*.jsonl` files. Treat `isCompactSummary` messages as generated summaries, not user instructions; use the original earlier turns.
2. **Codex:** inspect `~/.codex/sessions/**/*.jsonl` and `~/.codex/archived_sessions/*.jsonl`. Follow `session_meta.payload.parent_thread_id` recursively to include child-agent sessions. Do not expose encrypted reasoning records.
3. **Cursor or another harness:** use a read-only task/thread API when one is available. Otherwise accept a JSONL/JSON/Markdown export. The helper can preserve plain-text and common message-shaped JSONL, but unknown schemas may require direct inspection.
4. **Subagents:** report whether full child transcripts were recovered. A parent tool-result summary is not equivalent to the child's full transcript.
5. **Tool output:** distinguish helper truncation from output already truncated by the original harness. The latter cannot be reconstructed from the local transcript unless the tool wrote a separate artifact.
6. **Live sessions:** the archive may grow during extraction. Record the extraction time and, if the final turns are material, rerun after the session is complete.

## Finding the canonical skills

The inventory's skill mentions are candidates, not proof of invocation. Verify them against the transcript and filesystem.

Search, in order:

1. the exact path shown in a skill read or tool call;
2. the active workspace's project skills;
3. the personal and team source repositories;
4. the harness's installed plugin cache.

Compare the installed copy used during the session with the canonical editable source. Recommend changes against the canonical source, and treat a stale installed copy as a release/sync problem rather than a missing-instruction problem.

## Privacy

Session archives can contain private messages, customer data, tool arguments, signed URLs, and credentials. Keep all extraction and analysis local. Do not paste raw tool payloads into the final report, commit the bundle, or send it to an external model/service. Quote only the minimum evidence needed for the user to verify a finding.
