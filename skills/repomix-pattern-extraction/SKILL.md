---
name: repomix-pattern-extraction
description: Extract agentic AI design patterns from a repomix-generated XML snapshot of a codebase. Use when the user provides a repomix XML file (a packed repo dump) and asks to find, extract, or mine agentic patterns from it.
allowed-tools:
  - Read
  - Write
  - Glob
  - Grep
  - Bash
---

# Repomix Pattern Extraction

Mine a [repomix](https://github.com/yamadashy/repomix) XML dump — a single file
packing an entire repository's directory structure and file contents — for
reusable agentic AI design patterns, and write each one out as a standalone
Markdown pattern file. Self-contained: no other skill or repo is required.

## Overview

**Input:** Path to a repomix XML file representing a codebase that implements
(or contains) an agentic AI system.

**Process:**
1. Parse the XML into a file inventory + contents
2. Triage files to find concrete, nameable agentic mechanisms (not generic
   LLM-wrapper boilerplate)
3. Show the candidate mechanisms to the user and get confirmation before
   writing anything — a single codebase can yield many low-value candidates
4. For each confirmed candidate, check for existing similar patterns and
   either create a new pattern file or update an existing one
5. Report what was written

**Output location:** a `patterns/` folder in the current working directory
(created if it doesn't exist), unless the user specifies otherwise.

---

## Phase 1: Parse the repomix XML

Repomix XML is structured roughly as:

```xml
<directory_structure>
...
</directory_structure>
<files>
<file path="src/agent/orchestrator.ts">
...content...
</file>
<file path="src/memory/store.ts">
...content...
</file>
</files>
```

Exact tag names can vary slightly by repomix version/config — don't assume,
inspect the actual file first.

1. `Read` the first ~100 lines to confirm the wrapper tags in use.
2. If the file is large, don't load it all into context at once:
   - `grep -o '<file path="[^"]*"' the.xml` (via Bash) to build a path
     inventory first.
   - Use the directory_structure block (if present) for a quick architectural
     map.
3. From the inventory, prioritize files whose path or name suggests agentic
   machinery: `agent`, `orchestrat`, `planner`, `tool`, `memory`, `context`,
   `loop`, `eval`, `guard`, `router`, `coordinat`, `retry`, `critic`,
   `reflect`, `sandbox`. Read those files (or the relevant `<file>` blocks)
   in full; skim everything else from the inventory alone.

---

## Phase 2: Identify agentic mechanisms

Triage what you read into a fixed category set so each candidate maps
cleanly onto a catalogue:

- Orchestration & Control
- Context & Memory
- Feedback Loops
- Learning & Adaptation
- Reliability & Eval
- Security & Safety
- Tool Use & Environment
- UX & Collaboration

For each category where you find a concrete, nameable mechanism, record:

- **Working title** — short name for the mechanism
- **Files/functions** — where it lives (path + symbol/line)
- **Problem** — what failure mode or constraint it addresses
- **Solution** — the actual approach/algorithm, in your own words
- **Category** — from the list above

Skip anything that's just a thin LLM API call, a standard prompt template, or
boilerplate retry/logging with no distinguishing design — these aren't
patterns, they're plumbing.

---

## Phase 3: Confirm with the user

Before writing any files, present the candidate list (title, category,
1-line problem/solution) and ask which ones to pursue. Use AskUserQuestion if
there are 2-4 strong candidates and the choice is genuinely the user's; for
longer lists, just present the list in text and ask which to proceed with.

Do not auto-create patterns for every mechanism found — favor materially
novel, non-repetitive candidates over restatements of the same idea.

---

## Phase 4: Match against existing patterns

`Glob patterns/*.md` (create the `patterns/` folder if it's missing — there's
nothing to match against yet). For each existing pattern found, read its
front-matter and compare against the candidate:

- Same problem statement?
- Same solution mechanism?
- Same category?
- Overlapping tags?

Score roughly: 2+ of (problem, solution, category) matching → likely the same
pattern, lean toward updating it instead of creating a duplicate. Otherwise,
create new.

If genuinely unsure, ask the user rather than guessing.

---

## Phase 5: Write the pattern file

### New pattern

Slug the title (lowercase, spaces → hyphens, strip punctuation) and write
`patterns/{slug}.md`:

```markdown
---
title: "Title"
status: emerging
authors: ["Your Name (@yourusername)"]
based_on: ["Repo/Project Name (source URL)"]
category: "Category Name"
source: "https://github.com/org/repo"
tags: [tag1, tag2, tag3]
---

## Problem

[Concrete problem this mechanism solves]

## Solution

[How the mechanism actually works, in the implementation's own terms]

- Key components: [list]
- Mechanism: [describe the control flow / data flow]

## How to use it

[When to reach for this, and how to adapt it]

## Trade-offs

* **Pros:** [benefits]
* **Cons:** [drawbacks]

## References

* [Repo name](source URL)
```

Always put a blank line after a heading before a bullet list — some Markdown
renderers (including static-site generators like Astro) won't turn
`**Header:**\n- Item` into a real `<ul>` without it.

Status values: `proposed`, `emerging`, `established`,
`validated-in-production`, `best-practice`, `experimental-but-awesome`,
`rapidly-improving`. Default to `emerging` unless the codebase shows strong
evidence of production use.

Set `source` to the repo's actual URL if it's discoverable in the repomix
dump (e.g. a `package.json` `repository` field, a README badge/link).
Otherwise ask the user — don't fabricate a URL.

### Updating an existing pattern

Read the matched file, then:
- Append the new source to `based_on` (skip if it's already there)
- Add any genuinely new tags
- Append to `## References`
- If the new source adds real insight (not just another citation), append a
  short attributed addition to `## Solution` / `## Trade-offs` — never delete
  or overwrite existing content

---

## Phase 6: Report

```
Extracted N pattern(s) from <repomix-file>:
✅ Created: patterns/{slug}.md — {title}
✅ Updated: patterns/{slug}.md — added source to based_on

Skipped candidates (not pursued): {titles}
```

---

## Tips

- A repomix dump of a large monorepo can be huge — always inventory paths
  before reading contents, and read selectively.
- Prefer the mechanism's *own* implementation details over generic
  descriptions — the value of a pattern extracted from real code is its
  concrete how, not a restatement of "uses an LLM agent loop."
- If the codebase implements multiple agents/systems, group candidates by
  subsystem in the confirmation step so the user can approve per-subsystem.
- If repomix XML parsing is ambiguous or malformed, say so and ask the user
  rather than guessing at tag structure.
- If you're running this inside a repo that already has its own pattern
  catalogue/conventions (e.g. a different front-matter schema or output
  folder), follow that repo's existing conventions instead of the defaults
  above.
