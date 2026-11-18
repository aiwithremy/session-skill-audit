---
name: |-
  session-skill-audit
description: |-
  Audit a completed or ongoing Claude, Codex, Cursor, or other agent session from its full transcript, including pre-compaction history, to identify evidence-backed root causes and minimal improvements to skills or instruction files. Use when the user asks to review what should be learned from a session, improve the skills used, or run a session skill audit. Review-only by default; never edit persistent instructions until the user approves numbered proposals.
---

# Session Skill Audit

Run a first-principles audit of an agent session. The goal is not to preserve every correction. It is to discover the mechanism that made each meaningful correction necessary, then recommend the smallest change at the narrowest canonical owner.

> Never persist a correction until you understand the mechanism that made the correction necessary.

## Two modes

1. **Review mode is the default.** Recover the evidence, diagnose it, and present numbered proposals. Do not edit skills, scripts, references, `CLAUDE.md`, `AGENTS.md`, Cursor rules, or other persistent instructions.
2. **Apply mode starts only after the user explicitly approves proposal numbers.** Apply exactly those proposals, validate them, and complete the owning repository's release/sync workflow.

An instruction to "run the session skill audit" authorizes review mode only. Never interpret it as approval to mutate the files being reviewed.

## 1. Recover the real transcript

Read [references/transcript-recovery.md](references/transcript-recovery.md), then recover the raw session archive before diagnosing anything. Do not rely on the active context, a compaction summary, memory, or the agent's recollection when a local transcript exists.

Use the bundled `scripts/extract_session.py` for Claude Code and Codex archives. It can target the current session, an older session ID, or an explicit transcript path. It also discovers linked Claude subagent logs and Codex child-agent sessions.

For the current session, identify it with a distinctive phrase from one of the user's recent messages rather than trusting file modification time alone. If the helper reports ambiguity, inspect its candidate list and rerun with the exact session ID or path. Never guess which session is the target.

If another harness exposes a task/thread transcript through a read-only tool, use it. Otherwise ask for an exported transcript or local path. If only the visible conversation is available, continue only if the user accepts a partial audit and label the coverage limitation prominently.

Keep transcript artifacts local. Do not upload them to an external service or commit them to a repository.

## 2. Reconstruct what governed the run

Build an evidence-backed inventory before judging the output:

1. Skills the user explicitly invoked.
2. Skills the agent actually loaded or cited.
3. Skills that should reasonably have been selected but were not.
4. Scripts, references, tools, and data sources that materially shaped the result.
5. The inherited instruction stack: harness/system instructions, workspace `AGENTS.md` or `CLAUDE.md`, the closest project instructions, and relevant skill instructions.
6. The exact installed skill snapshot used during the run versus its canonical editable source. A current source file is not proof that the running agent saw that version.

Read every skill or instruction file that could plausibly own a proposed change **in full**. Search the surrounding instruction hierarchy for duplicate, overlapping, stale, or conflicting guidance. Do not diagnose from a quoted fragment alone.

Treat user corrections, rejected drafts, repeated retries, unnecessary questions, workarounds, tool failures, missed assets, stale copies, and post-compaction context loss as evidence. Treat the agent's explanation of its own mistake as a hypothesis, not proof.

## 3. Diagnose from first principles

Read [references/first-principles-diagnosis.md](references/first-principles-diagnosis.md) and apply it to each candidate issue.

Start from the intended outcome and observable facts. Strip away assumptions, identify the failure mechanism, locate the narrowest owner, and test the proposed change against the original failure.

Do not assume every bad result means an instruction was missing. Check whether:

- a clear existing instruction was simply ignored;
- the relevant skill was never selected or never loaded;
- an installed snapshot was stale;
- two instructions conflicted or obscured the priority;
- the skill's reference, helper, or tool mechanics caused the behavior;
- the source material was incomplete or wrong;
- the user was making a one-off creative choice rather than stating a durable preference.

If a clear instruction already governed the case and no structural reason prevented compliance, classify it as an execution miss and recommend **no persistent change**. Repeating the same rule in more places is not a fix.

## 4. Choose the canonical owner

Prefer the narrowest layer that controls the failure mechanism:

1. Incorrect source data or reference material → repair that source or its retrieval step.
2. Deterministic helper or tool behavior → fix the helper or the owning tool instructions.
3. Task-specific behavior → fix the most specific skill that owns the task.
4. Behavior shared by several related skills → fix their common workflow or shared reference.
5. Stable project-only behavior → fix the closest project instruction file.
6. Stable behavior that genuinely applies across unrelated work → propose a root instruction-file change.

The root instruction file is the last resort. A global addition must be stable, cross-workflow, likely to recur, consequential enough to justify permanent context, and impossible to own more narrowly.

Prefer, in order:

1. Correcting an inaccurate existing instruction.
2. Clarifying or consolidating overlapping instructions.
3. Removing a conflicting or obsolete instruction.
4. Adding a new instruction only when no existing instruction can be improved.

Never create one rule per example. The change must prevent the underlying class of failure without constraining unrelated work.

## 5. Deliver the review

Write the report in plain English and make it independently verifiable. Include:

1. **Verdict:** how many changes are worth making, how many findings require no persistent change, and the highest-leverage root cause.
2. **Coverage:** harness, raw transcript path or task ID, main-session and child-session coverage, compaction boundaries found, and anything unavailable or truncated by the original harness.
3. **What the session was trying to achieve:** the intended outcome and important constraints.
4. **Skill and instruction inventory:** invoked, actually loaded, missed, stale, or uncertain.
5. **Numbered proposed changes:** for each, include the observed behavior, exact transcript evidence, first-principles root cause, existing coverage, canonical owner, minimal change, counterfactual test, possible side effects, and confidence.
6. **No-change findings:** meaningful corrections or failures that should not become permanent instructions, with the reason.
7. **Approval line:** ask the user to approve proposal numbers, reject them, or revise the diagnosis.

Quote enough transcript text to prove the finding, and identify its source event or message. Do not dump the transcript into the report. Distinguish confirmed facts from inference.

It is valid—and often correct—for the report to recommend no changes.

## 6. Apply only approved proposals

When the user approves proposal numbers:

1. Re-read every affected canonical source file and its applicable repository instructions in full. Confirm the source has not changed since the review.
2. Re-check that the proposals still address root causes and do not duplicate or conflict with existing guidance.
3. Apply only the approved changes. Consolidate shared fixes rather than scattering duplicate rules.
4. Validate scripts behaviorally and validate each changed skill with the available skill and repository validators.
5. Inspect the diff for accidental instruction growth, private transcript content, secrets, or edits to installed cache snapshots.
6. Commit, push, release, refresh, and verify the installed/model-visible version according to the owning repository's rules. An uncommitted source edit is not a completed skill improvement.
7. Report exactly what changed, what was deliberately left unchanged, the verification performed, and any harness that needs a new session before it can see the update.

Do not write to memory systems as part of this workflow unless the user separately and explicitly requests a memory update.

## Self-Improvement Loop

After each run, evaluate this skill using its own first-principles standard.

- Did transcript recovery omit a harness artifact, child session, or meaningful event?
- Did the diagnostic method misidentify an owner or encourage a symptom-level fix?
- Did the user correct the report structure or the approval boundary in a way that would change future runs?

Propose a one-line update only when it would change a future run or prevent a demonstrated repeat failure. Most runs should propose nothing. Wait for approval; then update the relevant section rather than appending a changelog, and complete the owning repository's release workflow.
