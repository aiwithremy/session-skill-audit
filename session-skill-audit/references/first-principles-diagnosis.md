# First-principles diagnosis

Use this method for every candidate improvement. It is a causal investigation, not a checklist for manufacturing changes.

## 1. Define the required outcome

State the outcome the user was trying to achieve in concrete terms. Separate it from the method the agent happened to use.

Capture:

- the deliverable or decision required;
- the audience or operator;
- the important quality bar;
- explicit constraints and approval boundaries;
- what success would have looked like at that moment in the session.

Do not retroactively treat preferences introduced later as though the agent knew them earlier.

## 2. Establish observable facts

Use the raw transcript, tool events, files, and version metadata. Record what happened without explaining it yet.

Strong evidence includes:

- an exact user correction or rejection;
- the output immediately before that correction;
- a loaded skill path or tool call;
- the canonical source and installed snapshot hashes or versions;
- a repeat of the same behavior after correction;
- a concrete error, retry, workaround, or missing artifact.

Compaction summaries, agent self-explanations, and later recollections are secondary evidence. Use them to locate primary evidence, not as substitutes for it.

## 3. Remove assumptions

List the explanations that are being assumed. Test them separately.

Examples:

- "The skill needs another rule" assumes the skill was loaded and lacked the rule.
- "The tool is broken" assumes its input and permissions were correct.
- "This is a global preference" assumes the correction applies outside this task.
- "The latest source caused the behavior" assumes the session used the latest source rather than a cached snapshot.

Reject any explanation that is not supported by evidence. Mark uncertainty instead of filling gaps with a plausible story.

## 4. Find the failure mechanism

Trace the shortest causal chain from the governing system to the observed behavior.

Ask:

1. Was the needed information available?
2. Was it in the correct canonical source?
3. Was the relevant source or skill selected and loaded?
4. Was the instruction clear, prioritized, and internally consistent?
5. Did a deterministic helper or external tool behave differently than expected?
6. Did the agent comply with the instruction it had?
7. Was the user's correction actually a durable preference, or a local editorial choice?

Stop at the earliest controllable cause. Do not label the final visible symptom as the root cause.

## 5. Decide whether persistence is justified

A permanent change needs more than an undesirable outcome. It should meet all of these tests:

- **Recurrence:** the mechanism is likely to appear again.
- **Control:** the proposed owner can actually influence the behavior.
- **Novelty:** the instruction is not already clear and available at the correct layer.
- **Durability:** the learning is stable rather than tied to a temporary state or one deliverable.
- **Value:** preventing recurrence is worth the added instruction or code complexity.

If it fails a test, recommend no persistent change or a temporary operational action instead.

## 6. Derive the smallest effective intervention

Design the fix from the mechanism, not from the wording of the correction.

Prefer changing the system that creates the behavior:

- a parser over a reminder to inspect every line manually;
- the shared audience definition over repeating "use less jargon" in every writing skill;
- skill routing or discovery over copying the skill's instructions into a root file;
- a corrected reference over an instruction to distrust the reference;
- removing a conflict over adding a third rule to resolve it.

State exactly which existing sentence, section, helper, or reference would change. Avoid vague recommendations such as "make the skill clearer."

## 7. Run the counterfactual test

Ask:

> If this exact change had existed before the session, would a capable agent following the system have avoided the observed failure?

If no, the proposal is not a root-cause fix.

Then test the other direction:

> What unrelated work could this change make worse, slower, or less flexible?

Narrow or reject proposals with meaningful collateral effects.

## 8. Compare against alternatives

Consider at least:

- no persistent change;
- repairing an existing instruction;
- deleting or consolidating conflicting guidance;
- changing a helper, reference, or routing rule;
- adding a new skill-level instruction;
- adding a project instruction;
- adding a global instruction.

Choose the least expansive option that passes the counterfactual test.

## Evidence standard for recommendations

Label each conclusion:

- **Confirmed:** directly supported by transcript and current files/version evidence.
- **Strong inference:** the causal chain is well supported but one link is not directly observable.
- **Tentative:** plausible, but more evidence or another session is needed before changing persistent instructions.

Tentative findings should normally remain watch items, not become changes.
