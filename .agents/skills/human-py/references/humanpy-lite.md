# HumanPy Lite Workflows

HumanPy Lite is a lightweight convention for writing structured workflows inside Markdown. Treat it as Python-shaped English, not executable Python. Its purpose is to give normal instructions a little structure: variables, placeholders, reusable blocks, loops, conditions, and returns, while keeping plain English valid everywhere.

Use this skill to interpret, write, revise, normalize, or explain HumanPy Lite workflows. Do not run HumanPy Lite as code. Do not convert it into an executable script unless the user explicitly asks for executable code.

## Fast reader map

- Start with **Design principle**, **Recognized forms**, and **Structure validation gate** when validating syntax.
- Use **Optional workflow contract sections** when a workflow needs stable inputs, outputs, defaults, constraints, or step grouping.
- Use **Variables**, **Placeholders**, **Functions**, **Conditions**, **Loops**, and **Returns** when authoring reusable workflow blocks.
- Use **Agent integration contract**, **Safeguards**, and **Normalization rules** when embedding HumanPy Lite in another skill.

## Design principle

Plain English is the default. A line has special workflow meaning only when it clearly starts with a recognized HumanPy Lite form.

When HumanPy Lite appears inside Markdown bullets or numbered lists, ignore the list marker (`-`, `*`, `+`, or `1.`) and surrounding whitespace before checking whether the content starts with a recognized form. Preserve the list structure as presentation.

Users may declare HumanPy Lite snippets with fenced code blocks marked as `humanpy` or `human-py`:

````markdown
```humanpy
# Readable comment
audience = "leadership"
return a concise update for <audience>
```
````

````markdown
```human-py
# Readable comment
audience = "leadership"
return a concise update for <audience>
```
````

Inside `humanpy` and `human-py` fenced blocks, comments start with `#`. Treat lines whose first non-whitespace character is `#` as comments, not workflow instructions. Outside those fenced blocks, Markdown headings and prose keep their normal Markdown meaning.

Recognized forms:

```text
set name = value
name = value
def name(args):
if condition:
elif condition:
else:
for item in collection:
for each item in collection:
function(args)
function(args) as result
call function(args) as result
return value
add value to collection
use value as name
inputs:
outputs:
defaults:
constraints:
preconditions:
postconditions:
steps:
notes:
```

Everything else is plain English instruction only when it clearly reads as
English or Markdown prose, even when it appears inside an indented block.

Simple section labels such as `inputs:` and `outputs:` are presentation aids
for workflow contracts. They may have indented lines beneath them, but they do
not create a variable scope by themselves. Use only the listed labels inside a
`humanpy`/`human-py` fenced block; use normal Markdown headings outside fenced
blocks when you need arbitrary section names.

## Extension policy

Keep HumanPy Lite small. Add a new recognized form only when all are true:

- Plain English or an existing form would be materially less clear.
- The form improves reuse, validation, placeholder resolution, or workflow
  handoff between agents/skills.
- The form still reads like instructions, not executable Python.
- The validation script and at least one unit-test fixture are updated with the
  documentation change.

Prefer documenting an idiomatic prose pattern before adding syntax. For
example, write "The ticket summaries are independent; process in parallel only
if the active runtime allows it" instead of adding a dedicated `parallel`
keyword.

## Structure validation gate

When a `humanpy` or `human-py` fenced block, standalone HumanPy Lite script,
or Python-shaped English workflow is detected, validate the structure before
interpreting, normalizing, converting, or embedding it.

For each line, first ignore Markdown list markers (`-`, `*`, `+`, or `1.`)
and surrounding whitespace when deciding whether the line starts with a
HumanPy Lite form. Then classify each line as exactly one of:

- `comment/blank`: empty lines and, inside `humanpy` or `human-py` fenced
  blocks, lines whose first non-whitespace character is `#`.
- `python-like`: a recognized HumanPy Lite structure with the required visible
  shape, such as `set name = value`, `name = value`, `def name(args):`,
  `if condition:`, `elif condition:`, `else:`, `for item in collection:`,
  `for each item in collection:`, `function(args)`,
  `function(args) as result`, `return value`, `add value to collection`, or
  `use value as name`, or a listed section label such as `inputs:` or
  `outputs:`. Treat `call function(args) as result` as a valid legacy form,
  but prefer the bare function-call form when writing new workflows.
- `english-like`: natural-language instruction, prose, or Markdown text that
  does not pretend to be malformed HumanPy Lite structure. It may contain
  `<placeholders>` for dynamic values.

If a line does not look like a Python-like construct but its intent is clear,
classify it as `english-like` and accept it. Do not require a line to use
recognized HumanPy Lite syntax just because the snippet is inside a `humanpy`
or `human-py` block.

Examples of valid `english-like` lines:

```text
Review <ticket> and identify blockers.
Keep only the findings that are backed by evidence.
Group the results by owner, then by risk.
Use the latest available status when the source is clear.
```

Report a validation error when a meaningful line cannot be classified clearly.
Common validation errors include:

- A recognized keyword is malformed, such as `set name value`, `def name(args)`
  without `:`, `if condition` without `:`, `else condition:`,
  `for item collection:`, `call fn(args)` without `as result`,
  `add value collection`, or `use value name`.
- A function invocation is malformed, such as `func args)`, `func(arg`, or
  `func arg as result`.
- A line looks like executable Python rather than HumanPy Lite, such as
  `import`, `class`, `try`, `except`, decorators, type annotations,
  function signatures with `->`, augmented assignment, multi-target
  assignment, field or item mutation such as `ticket.status = "blocked"`, or
  complex expressions whose intent is not clear.
- Indentation implies a nested block but no preceding `def`, `if`, `elif`,
  `else`, `for`, or `for each` line opened that block.
- The line is too fragmentary or symbol-heavy to read confidently as either
  plain English or a recognized HumanPy Lite form.

Use this reporting shape:

```text
Validation error: line <number>: <reason>
```

If any validation error is present, do not treat the script as structurally
valid. Ask for a correction, or, when the user wants best-effort help, clearly
separate the validation errors from any inferred interpretation.

## Mental model

HumanPy Lite has two modes:

1. Structured mode: lines look like lightweight pseudocode. Use bare identifiers such as `ticket`, `audience`, or `summary`.
2. Prose mode: lines are normal English. Use angle brackets such as `<ticket>`, `<audience>`, or `<latest_status>` to mark dynamic references.

Example:

```text
audience = "leadership"
priority_order = ["customer impact", "deadline", "blocker"]

def summarize_ticket(ticket):
    Read <ticket> and summarize it for <audience>.
    Use <priority_order> to decide what matters most.

    if <ticket> looks blocked, stale, or high-impact:
        Mention the risk early.

    return summary
```

In structured lines, `ticket` and `audience` can be bare identifiers. In prose, `<ticket>` and `<audience>` make it clear that these are dynamic values and not just ordinary words.

## Optional workflow contract sections

Use compact section labels when a workflow should be reusable across skills,
prompts, or agents and the inputs/outputs matter.

```text
inputs:
    ticket: issue, document, or thread to review
    audience = "engineering leadership"

defaults:
    tone = "concise and evidence-backed"
    ask_policy = Ask one focused question only when missing information changes the result.

constraints:
    Do not invent dates, owners, statuses, source links, or tool results.
    Follow active system, developer, safety, and tool-use instructions first.

outputs:
    summary: markdown update for <audience>
    risks: explicit list of material blockers, or "No material risks found"

steps:
    summarize_ticket(ticket, audience) as summary
    extract_risks(ticket) as risks
    return <summary> with <risks>
```

Guidelines:

- Skip section labels for small one-off workflows.
- Use `inputs:` for values the caller must provide or the agent may infer from
  context.
- Use `defaults:` for overridable variables.
- Use `constraints:` for safety, sourcing, style, and tool-use boundaries.
- Use `outputs:` to name conceptual artifacts that later steps or callers can
  reference.
- Use `steps:` only when it improves scanability; ordinary ordered prose is
  still valid.

## Variables

Use either `name = value` or `set name = value` to define a variable. They are
equivalent. Prefer the shorter `name = value` form unless `set` makes a
prose-heavy workflow easier to scan.

```text
set number = 10
audience = "Oracle coworkers"
priority_order = ["blockers", "deadlines", "customer impact", "next actions"]
output_rules = {tone: "concise", format: "markdown", ask_when_missing: false}
fallback_behavior = Ask one focused question only if the missing detail changes the result.
```

Guidelines:

- Prefer `snake_case` variable names: `ticket_summary`, `customer_impact`, `priority_order`.
- A bare assignment variable name should be a simple identifier, not a dotted
  field, indexed item, destructuring pattern, or expression.
- Values may be strings, numbers, booleans, lists, maps, object-like values, or plain English.
- Do not require a type system.
- Treat values as guidance unless the workflow explicitly says they are exact text.
- Variables remain available in the current block and nested blocks.
- A variable defined inside a `def`, `if`, or `for` block should not be assumed available globally unless the workflow clearly returns it or promotes it.

## Aliases

Use `use value as name` to give an existing value, selected source, or inferred context a local alias.

```text
use the active Jira issue as issue
use latest_email_thread as email_thread
use the current reviewer comments as review_notes
```

Treat this as: for the current scope, refer to `value` as `name`. It is useful when the source is long, contextual, or awkward to repeat. Do not treat it as a type cast, executable assignment, or global promotion unless the workflow explicitly says so.

## Lists and maps

Lists use square brackets. Maps use Python-like or YAML-like object notation. Keep both flexible.

```text
set labels = ["high", "medium", "low"]
set stakeholders = ["engineering", "support", "leadership"]

set style = {
    tone: "concise",
    confidence: "realistic",
    format: "markdown"
}
```

Interpret unquoted map keys as labels, not as unresolved variables, unless the context strongly implies otherwise.

## Placeholders

Use angle brackets to refer to variables, arguments, object fields, simple expressions, or inferred context inside prose.

```text
Write the update for <audience>.
Use <priority_order> when deciding what matters most.
Mention <ticket.owner> if ownership matters.
Include <timestamp> only if useful.
```

Placeholder resolution order:

1. Local variables and function arguments.
2. Variables in parent scopes.
3. Global variables.
4. Object fields or properties, such as `<ticket.owner>`.
5. Simple expressions that can be resolved from available context, such as `<tickets[0]>` or `<len(tickets)>`, if obvious.
6. Contextual values that are commonly inferred, such as `<current_date>`, `<timestamp>`, `<user_name>`, `<latest_status>`, or `<source>`.
7. If still unresolved, infer only when the meaning is obvious and low risk.
8. Ask a focused clarification question only when the unresolved placeholder materially changes the result.

Use placeholders in prose mode. Do not require placeholders in structured mode.

Good:

```text
summarize_ticket(ticket, audience) as summary
Write the final update for <audience> using <summary>.
```

Also good:

```text
if ticket.status == "blocked":
    return "high"

if <ticket> appears stale or has unclear ownership:
    return "medium"
```

Avoid excessive placeholders when the line is already structured:

```text
summarize_ticket(<ticket>, <audience>) as <summary>
```

Prefer:

```text
summarize_ticket(ticket, audience) as summary
```

## Literal angle brackets

If angle brackets are literal text, wrap them in backticks or quotes.

```text
Use the exact text "<insert name here>" as a visible placeholder in the template.
Mention the XML tag `<title>` only as an example.
```

If a line contains angle brackets that look like code, XML, HTML, or generics, do not automatically treat them as HumanPy Lite placeholders. Use surrounding context.

## Functions

Use `def name(args):` to define a reusable workflow unit.

```text
def classify_risk(ticket):
    if ticket.status == "blocked":
        return "high"

    if <ticket> has customer impact, stale progress, or unclear ownership:
        return "medium"

    return "low"
```

Guidelines:

- A `def` defines reusable instructions, not executable code.
- Arguments are names available inside the block.
- Function bodies may freely mix structured lines and prose.
- Return values are conceptual outputs, not necessarily concrete objects.
- If a function says `return summary`, produce or pass along the conceptual summary.
- Do not invent hidden implementation details beyond what is needed to follow the workflow.
- Default or named-style arguments may be used when they improve readability,
  such as `def summarize(ticket, audience="leadership"):` or
  `summarize(ticket, audience="support") as summary`. Treat these as readable
  binding hints, not as a typed function signature.

## Calling functions

Use `name(args)` to invoke a reusable workflow unit. Use `name(args) as result`
when the workflow wants to store the conceptual result. The older
`call name(args) as result` form is valid for compatibility, but do not require
it and do not introduce it in new examples.

```text
def summarize_ticket(ticket):
    classify_risk(ticket) as risk

    Write one concise paragraph for <ticket>.
    Mention <risk> only if it is medium or high.

    return summary
```

If a call references an undefined function, first look for a nearby `def` with a similar name. If none exists, infer the function's intent from its name and arguments when obvious.

Example:

```text
extract_customer_impact(ticket) as impact
```

If no `extract_customer_impact` function is defined, interpret it as: identify customer impact from `<ticket>` and store it as `impact`.

Ask only if the undefined function is central to the task and cannot be inferred safely.

## Conditions

Conditions after `if` and `elif` may be Python-like or plain English.

Python-like condition:

```text
if ticket.status == "blocked":
    return "high"
```

English-like condition:

```text
if <ticket> looks blocked, stale, or urgent:
    Treat it as a risk.
```

Guidelines:

- If the condition is Python-like, use bare identifiers.
- If the condition is English-like, use placeholders for dynamic values.
- Conditions are judgment rules, not strict boolean expressions, unless written in a clearly code-like way.
- Prefer the most natural interpretation that follows nearby instructions.
- If two conditions conflict, prefer the more specific condition over the general one.
- If the workflow gives an explicit priority order, use that order to resolve conflicts.

## Else and otherwise

Both `else:` and plain English alternatives are allowed.

```text
if <email> asks for a commitment:
    Do not overpromise.
    State what can be done and when.
else:
    Keep the reply brief.
```

Also valid:

```text
if <email> asks for a commitment:
    Do not overpromise.

Otherwise, keep the reply brief.
```

Treat `Otherwise, ...` as an informal `else` only when the surrounding block makes that meaning clear.

## Loops

Use either Python-like or English-like loops.

```text
for ticket in tickets:
    summarize_ticket(ticket) as summary
    add summary to summaries
```

```text
for each ticket in <tickets>:
    Summarize <ticket> for <audience>.
    Add the result to <summaries>.
```

Guidelines:

- `for item in collection:` is structured mode.
- `for each item in <collection>:` is a fluid HumanPy Lite form.
- Inside a loop, the loop variable is available in nested lines.
- If the collection is missing but obvious from context, infer it.
- If the collection is missing and not obvious, ask only if the task cannot proceed.

## Adding to collections

Use `add value to collection` for simple accumulation.

```text
set summaries = []

for ticket in tickets:
    summarize_ticket(ticket) as summary
    add summary to summaries
```

In prose, placeholders are welcome:

```text
Add <summary> to <summaries>.
```

Treat both as the same intention.

For reusable workflows, name accumulators explicitly before loops when the
result is used later. If loop iterations are independent, say so in prose
rather than inventing concurrency syntax. Any actual parallel execution or
subagent delegation must still follow the active agent/tool instructions.

```text
summaries = []

for each ticket in <tickets>:
    summarize_ticket(ticket) as summary
    add summary to summaries

The ticket summaries are independent; the active runtime may process them in
parallel only if its instructions allow that.
```

## Returns

Use `return value` to identify the conceptual output of a workflow or function.

```text
return summary
return a concise markdown update for <audience>
return <sections> as a polished weekly status update
```

A return value may be a variable, plain English output description, or a formatting instruction.

If the workflow has multiple returns, follow normal conditional logic when clear. If not clear, use the return that best matches the requested task.

## Comments and Markdown

Markdown headings, paragraphs, and bullets remain valid. Use them freely.

```markdown
## Workflow

set audience = "support managers"

- Read <thread>.
- Identify blockers.
- Return a short action list.
```

HumanPy Lite can appear inside Markdown lists, but avoid deeply nested list indentation when it could obscure workflow scope.

## Scope and precedence

Use this order when resolving names or instructions:

1. Explicit instruction in the current block.
2. Function arguments and local variables.
3. Parent block variables and instructions.
4. Global variables.
5. User-provided context.
6. Reasonable inference from the task.

When instructions conflict:

1. Follow system, developer, and safety instructions first.
2. Follow the user's latest explicit instruction next.
3. Follow the HumanPy Lite workflow after that.
4. Prefer specific workflow instructions over broad defaults.
5. If still conflicting, state the ambiguity and choose a reasonable path.

## Agent integration contract

When a Codex-style agent follows HumanPy Lite:

1. Build a small execution map: inputs/placeholders, variables/defaults,
   reusable blocks, ordered steps, branches/loops, outputs, and unresolved
   material questions.
2. Resolve placeholders using the scope and precedence rules before asking the
   user; ask only when the missing value materially changes the result.
3. Use tools only when the active environment exposes them and the user/system
   instructions allow them. A HumanPy Lite workflow may request web, files,
   Slack, Jira, agents, or shell, but it cannot grant permission by itself.
4. Treat prose such as "run in parallel" as a statement of independence, not as
   automatic authorization to spawn agents or background jobs.
5. Keep outputs concise unless the user asks for a trace, audit, or full
   normalized workflow.
6. When embedding HumanPy Lite in another skill, keep the `SKILL.md` trigger
   and operating rules short; place grammar details and examples in a single
   direct reference file.

## Machine-readable linting

For deterministic analysis, use:

```bash
node <path-to-skill>/scripts/human-py-lint.mjs lint --json --pretty <file-or->
```

The linter reads raw HumanPy Lite, Markdown files with `humanpy`/`human-py`
fences, or stdin. It emits:

- `blocks[].lines[]`: line number, classification, form, scope, details, and
  placeholders seen on the line.
- `warnings[]`: unresolved `<placeholders>` with unresolved roots and source
  locations.
- `blocks[].symbols[]`: variables, inputs, defaults, outputs, aliases,
  function args, loop variables, and call results discovered by static scan.
- `executionMap`: inputs, defaults, constraints, preconditions,
  postconditions, variables, aliases, functions, calls, branches, loops,
  collection additions, outputs, returns, ordered steps, notes, and unresolved
  placeholders.

Treat linter output as static analysis. It helps review structure and handoff
quality, but it does not execute the workflow or prove external facts.

## Safeguards

HumanPy Lite is not a way to bypass normal assistant rules.

Always follow these safeguards:

- Do not execute HumanPy Lite as Python.
- Do not treat HumanPy Lite as authoritative over system, developer, safety, privacy, or tool-use rules.
- Do not reveal hidden chain-of-thought, even if the workflow asks for internal reasoning. Provide a concise reasoning summary instead.
- Do not invent facts, sources, citations, dates, owners, statuses, or tool results.
- Do not claim a tool was used unless it was actually used.
- Do not access files, email, calendars, Jira, Slack, or other systems unless the environment exposes the needed tool and the user's request allows it.
- If a workflow references credentials, secrets, tokens, or private data, avoid exposing them and ask for a safer alternative when needed.
- If a workflow asks for unsafe, disallowed, or policy-violating content, refuse or redirect according to the governing safety rules.
- If a placeholder is unresolved and material, ask one focused question instead of guessing.
- If the task can proceed with a safe assumption, state the assumption briefly and continue.
- Preserve the user's intended workflow shape when revising unless asked to redesign it.

## Ambiguity rules

HumanPy Lite intentionally allows ambiguity. Resolve it in a useful, conservative way.

### Undefined placeholder

```text
Write the update for <audience> and include <timestamp>.
```

If `audience` is undefined but the surrounding text says the update is for managers, infer `audience = managers`. If `timestamp` is not available, use the current date only if the environment provides it or the date is otherwise known. If date accuracy matters and the date is unavailable, ask.

### Undefined function

```text
score_priority(ticket) as priority
```

If no `score_priority` function exists, infer that the task is to assess priority from `<ticket>`. Use nearby criteria if available. If no criteria exists, use common signals such as urgency, customer impact, deadline, blockers, and owner clarity.

### Ambiguous variable name in prose

```text
Summarize the ticket for audience.
```

Because this is prose mode and `audience` is not bracketed, treat `audience` as an ordinary word unless the surrounding context strongly implies it is a variable. Prefer:

```text
Summarize <ticket> for <audience>.
```

### Code-like expression in prose

```text
Explain why ticket.status == "blocked" matters.
```

This is prose, but the expression is clear. Interpret `ticket.status` as a field reference if `ticket` exists.

### Angle brackets that are not placeholders

```text
Show the HTML tag `<div>`.
```

Because it is in backticks, treat `<div>` as literal text, not a placeholder.

### Conflicting values

```text
set audience = "leadership"
set audience = "engineers"
```

Use the closest or latest assignment in scope. If the conflict changes the expected output and there is no clear scope rule, state the ambiguity or choose based on the user's latest explicit instruction.

### Overly complex expressions

```text
if <tickets where status is blocked and owner is missing except items updated after last Tuesday>:
```

Do not try to parse this as a strict query language. Interpret the intent in plain English. If needed, rewrite it as clearer steps.

## Normalization rules

When asked to clean up or normalize a HumanPy Lite workflow:

- Keep the user's meaning and level of formality.
- Prefer plain English over code-like syntax when the logic is judgment-based.
- Prefer structured syntax when a variable, loop, or reusable step improves clarity.
- Use `<placeholders>` in prose for dynamic values.
- Use bare identifiers in structured lines.
- Reduce unnecessary keywords.
- Avoid turning the workflow into real Python.
- Add only the smallest missing structure needed to make the workflow reusable.

## Good style

Prefer:

```text
set audience = "leadership"

def write_update(ticket):
    Read <ticket> and identify the main change since the last update.

    if <ticket> has a blocker or customer impact:
        Mention the risk in the first sentence.

    return a concise markdown update for <audience>
```

Avoid:

```text
def write_update(ticket: JiraTicket) -> MarkdownSummary:
    return render(template=ExecutiveUpdateTemplate(ticket=ticket, audience=audience))
```

The second example looks too much like executable code and introduces unnecessary types and implementation details.

## Example: email reply workflow

```text
set default_tone = "polite, concise, confident"
set ask_policy = Ask one focused question only when missing information changes the reply.

def draft_reply(email_thread):
    Read <email_thread> and identify what the sender wants from the user.

    if <email_thread> asks for a decision:
        State the decision clearly, then give only the necessary context.

    if <email_thread> asks for a commitment:
        Do not overpromise.
        Offer a realistic next step or timeline.

    if key information is missing:
        Follow <ask_policy>.

    return a plain-text email draft in <default_tone>
```

## Example: Jira-style risk workflow

```text
set risk_signals = ["blocker", "missed deadline", "customer impact", "unclear owner", "stale update"]
set audience = "engineering leadership"

def classify_risk(issue):
    if issue.status == "Blocked":
        return "high"

    if <issue> has any signal in <risk_signals>:
        return "medium or high based on severity"

    return "low"


def summarize_issue(issue):
    classify_risk(issue) as risk

    Write 2 to 4 bullets for <audience>.
    Include impact, current status, next action, and <risk>.
    Do not invent missing dates or owners.

    return summary
```

## Example: weekly update workflow

```text
set sections = ["Done", "In progress", "Risks", "Next"]
set tone = "concise and realistic"

def weekly_update(items):
    set summaries = []

    for each item in <items>:
        Summarize <item> in one bullet.
        Focus on outcome, current state, and next action.
        add summary to summaries

    Group <summaries> into <sections>.

    if there are no risks:
        Say "No major risks identified" instead of inventing risks.

    return a markdown weekly update in <tone>
```

## Example: converting loose bullets to HumanPy Lite

Input:

```text
Review the customer notes, find themes, then write a short product summary. If there are blockers, call them out. Keep it concise.
```

Output:

```text
tone = "concise"

def product_summary(customer_notes):
    Review <customer_notes> and identify recurring themes.

    if <customer_notes> mention blockers:
        Call out the blockers clearly.

    return a short product summary in <tone>
```

## Using HumanPy Lite from another skill

Other skills can opt into this convention by including a short instruction like this in their `SKILL.md`:

```markdown
This skill may use HumanPy Lite workflow notation. Interpret HumanPy Lite as structured Markdown, not executable code. Plain English is valid by default. Treat simple assignments such as `audience = "leadership"`, optional `set` assignments such as `set audience = "leadership"`, lines beginning with `def`, `if`, `elif`, `else`, `for`, `for each`, `add`, `use`, or `return`, plus bare function calls such as `summarize(ticket)` and `summarize(ticket) as summary`, as lightweight workflow structure. In prose, resolve `<placeholders>` as variables, arguments, object fields, simple expressions, or contextually inferred values. Use bare identifiers in structured lines. Ask only when an unresolved placeholder or ambiguous instruction materially changes the result.
```

For a shorter reference:

```markdown
Use HumanPy Lite: plain English by default, optional Python-shaped workflow lines, indentation for scope, `name = value` or `set name = value` for variables, `def` for reusable steps, `if` and `for` for flow, `func(args)` and `func(args) as result` for reusable operations, `return` for output, and `<placeholders>` for dynamic values inside prose. Do not execute it as code.
```

## Response behavior when using this skill

When the user asks for help writing HumanPy Lite:

- Produce the workflow directly.
- Keep it readable and fluid.
- Avoid over-formal grammar unless requested.
- Include a short note only when a convention matters.

When the user asks for review:

- Identify unclear variables, placeholders, scope issues, and unsafe assumptions.
- Suggest minimal edits.
- Do not rewrite the whole workflow unless asked.

When the user asks to interpret a workflow:

- Explain what it does in plain English.
- Mention any inferred values or ambiguous parts.
- Do not pretend that the workflow has been executed.

When the user asks to convert it into a Skill:

- Keep HumanPy Lite conventions in the Skill instructions or a single reference file, according to the user's packaging preference.
- If the user asks for a single-file Skill, put all grammar, examples, corner cases, and safeguards in `SKILL.md`.
