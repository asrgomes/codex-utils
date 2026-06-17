---
name: handoff
description:
  Compact the current conversation into a handoff document for another agent to pick up. Use when
  the user asks for a handoff, restart note, continuation brief, context summary, or instructions
  for the next session.
---

# Handoff

Write a handoff document summarizing the current conversation so a fresh agent can continue the
work. Save it to the temporary directory of the user's OS, not the current workspace.

Include a "suggested skills" section in the document, which suggests skills that the agent should
invoke.

Do not duplicate content already captured in other artifacts, such as PRDs, plans, ADRs, issues,
commits, or diffs. Reference them by path or URL instead.

Redact sensitive information, such as API keys, passwords, credentials, and personally identifiable
information.

If the user passed arguments, treat them as a description of what the next session will focus on and
tailor the document accordingly.
