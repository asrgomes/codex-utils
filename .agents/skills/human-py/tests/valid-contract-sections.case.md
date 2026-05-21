---
name: valid-contract-sections
valid: true
---

```humanpy
inputs:
    ticket: issue, document, or thread to review
    audience = "engineering leadership"

defaults:
    tone = "concise and evidence-backed"

constraints:
    Do not invent dates, owners, statuses, source links, or tool results.

outputs:
    summary: markdown update for <audience>

steps:
    summarize_ticket(ticket, audience) as summary
    return <summary>
```
