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
reusable agentic AI design patterns, then hand each candidate off to the same
matching/create/update workflow used by `create-pattern`.

## Overview

**Input:** Path to a repomix XML file representing a codebase that implements
(or contains) an agentic AI system.

**Process:**
1. Parse the XML into a file inventory + contents
2. Triage files to find concrete, nameable agentic mechanisms (not generic
   LLM-wrapper boilerplate)
3. Show the candidate mechanisms to the user and get confirmation before
   writing anything — a single codebase can yield many low-value candidates
4. For each confirmed candidate, run `create-pattern`'s Phase 2-6 (extract
   metadata, match against `patterns/*.md`, create or update)
5. Rebuild pattern data and report results

This skill only handles ingestion + triage of the repomix XML. Once a
candidate is confirmed, defer to `create-pattern`'s matching/decision/write
logic rather than duplicating it.

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

Triage what you read into the repo's existing category set so each candidate
maps cleanly onto the catalogue:

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

Do not auto-create patterns for every mechanism found — a single agentic
codebase often surfaces several candidates of wildly different novelty/value,
and the repo's contribution policy requires submissions to be materially
novel and non-repetitive.

---

## Phase 4: Extract, match, write — per confirmed candidate

For each confirmed mechanism, follow `create-pattern`'s existing workflow
rather than re-deriving it:

1. **Phase 3 (match)** — Glob `patterns/*.md`, compare problem/solution/
   category/tags against the candidate, score confidence.
2. **Phase 4 (decision)** — >80% confidence → update existing pattern's
   `based_on`/References/content; <50% → create new; 50-80% → ask the user.
3. **Phase 5a/5b (write)** — use the same front-matter schema, category list,
   and status values as `create-pattern` (title, status, authors, based_on,
   category, source, tags; Problem/Solution/References sections). Set
   `source` to the repo's actual URL if known from the repomix dump (e.g. a
   `package.json`/`README` repository field), otherwise ask the user for it —
   don't fabricate a URL.
4. Remember the CLAUDE.md formatting rule: always put a blank line after a
   header before a bullet list, or Astro won't render it as `<ul><li>`.

---

## Phase 5: Build & report

```bash
cd apps/web && bun run build-data
```

Confirm the JSON files updated under `apps/web/public/patterns/` with no
errors, then summarize for the user:

```
Extracted N pattern(s) from <repomix-file>:
✅ Created: patterns/{slug}.md — {title}
✅ Updated: patterns/{slug}.md — added source to based_on

Skipped candidates (not pursued): {titles}

Next steps:
1. Review the new/updated pattern file(s)
2. cd apps/web && bun run dev
3. git add patterns/{slug}.md
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
