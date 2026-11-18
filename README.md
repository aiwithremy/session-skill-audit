# Session Skill Audit

A Claude skill that improves your other skills by finding what actually caused each mistake, instead of piling on new rules.

Most agents improve a skill by adding things. Something goes wrong, they add a rule. Something else goes wrong, they add another. A month later the skill is twice as long and somehow worse. This one works the other way. Run it at the end of a session and it reads the full transcript (even if the conversation has been compacted), reasons from first principles about what caused each correction, and gives you a short, numbered list of proposed fixes. Often the fix is deleting something. Nothing changes until you approve it.

Made by [Remy Gaskell](https://www.instagram.com/aiwithremy).

## Install

**The easy way:** paste this repo's link into Claude Code (or any AI agent that can install skills) and say:

> Install this skill for me: https://github.com/aiwithremy/session-skill-audit

**Claude Code, by hand:** copy the `session-skill-audit` folder into `~/.claude/skills/`.

**Claude.ai or the Claude app:** download this repo as a ZIP (green **Code** button, then **Download ZIP**), then go to Settings, then Capabilities, and upload it as a skill.

## Use it

At the end of a session, say "run a session skill audit". You'll get a report with numbered proposals. Approve the numbers you want ("apply 1 and 3") and it makes only those changes.

It works best in Claude Code and Codex, where it can read the full session file on your computer. In other tools, paste or export the transcript.

## More

I send a weekly newsletter on practical AI for business: [aiwithremy.com](https://www.aiwithremy.com)
