---
name: repomix-pattern-extraction
description: Run repomix against a codebase (local path or remote git URL) or accept an existing repomix XML dump, mine it for agentic AI design patterns, score each candidate's confidence and match against the existing pattern catalogue, then write or update pattern files. Use when the user gives a repo/URL/XML and asks to find, extract, scan, or mine agentic patterns from it.
allowed-tools:
  - Read
  - Write
  - Glob
  - Grep
  - Bash
---

# Repomix Pattern Extraction

Generate (or accept) a [repomix](https://github.com/yamadashy/repomix) XML
dump — a single file packing an entire repository's directory structure and
file contents — mine it for reusable agentic AI design patterns, score each
candidate against the existing catalogue, and write confirmed ones out as
standalone Markdown pattern files. Self-contained: no other skill or repo is
required.

## Overview

**Input:** one of:
- A local directory (path to a codebase to scan)
- A remote git URL (GitHub/GitLab repo to scan)
- An already-generated repomix XML file path

**Process:**
0. If given a directory or URL (not an XML file), run `repomix` to generate
   the XML dump first
1. Parse the XML into a file inventory + contents
2. Triage files to find concrete, nameable agentic mechanisms (not generic
   LLM-wrapper boilerplate)
3. Score each candidate: confidence it's a genuine pattern (with
   justification) + best-matching existing pattern in the catalogue (with
   match confidence)
4. Show the scored list to the user and get confirmation before writing
   anything — a single codebase can yield many low-value candidates
5. For each confirmed candidate, create a new pattern file or update the
   matched existing one
6. Report what was written

**Output location:** a `patterns/` folder in the current working directory
(created if it doesn't exist), unless the user specifies otherwise.

---

## Phase 0: Generate the repomix XML (skip if already given an XML file)

If the input is a local directory or a remote URL, run repomix via `npx` (no
global install required) and write the output to a temp file:

```bash
# local codebase
npx -y repomix <path-to-codebase> -o /tmp/repomix-<slug>.xml

# remote repo (GitHub/GitLab URL or org/repo shorthand)
npx -y repomix --remote <git-url-or-org/repo> -o /tmp/repomix-<slug>.xml
```

- `<slug>` — derive from the repo/dir name so the temp file is identifiable
  if multiple scans happen in one session.
- If the user wants to scan a *subset* of a large repo (e.g. just `src/agent`),
  pass `--include "<glob>"` rather than scanning the whole tree.
- If `npx repomix` fails (not installed, network blocked, private repo
  without auth), report the exact error to the user and ask how to proceed —
  don't silently fall back to manually walking the repo with `Glob`/`Read`,
  since that defeats the point of using repomix's packing/compression.
- Once generated, proceed to Phase 1 with the resulting XML path.

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

## Phase 3: Score candidates against the existing catalogue

For every candidate from Phase 2, compute two independent scores before
showing anything to the user.

### 3a. Pattern-confidence score — is this actually a pattern?

Rate how confident you are that the candidate is a genuine, reusable agentic
mechanism (not boilerplate, not a restatement of generic LLM usage):

- **High** — concrete, non-trivial mechanism with clear control/data flow,
  visibly built to solve a specific failure mode; would generalize to other
  codebases.
- **Medium** — a real mechanism, but thin, implicit, or only partially
  distinguishing (e.g. a fairly standard retry-with-backoff, a memory store
  with no eviction/ranking logic).
- **Low** — mostly plumbing or a one-off; flag but don't recommend pursuing.

Justification must cite the actual file(s)/function(s) and what specifically
makes it concrete (or thin) — not a generic restatement of the category.

### 3b. Catalogue-match score — does this already exist?

`Glob patterns/*.md` (create the `patterns/` folder if it's missing — there's
nothing to match against yet). For each existing pattern, compare against the
candidate using these signals (mirrors the scoring used by the `create-pattern`
skill, for consistency across the repo):

**Primary signals (30% each):** same problem statement / same solution
mechanism / same category.
**Secondary signals (10% each):** tag overlap / same source-repo or author /
similar title.

```
Score = Σ(matching_signals × weights)
```

- All 3 primary match → **90%+** → near-certain duplicate, update don't create.
- 2 primary + 1+ secondary → **70–90%** → likely duplicate, lean update.
- 1 primary + 2+ secondary → **50–70%** → ambiguous, ask the user.
- 0–1 primary only → **<50%** → new pattern.

Record the top match (slug + score + which signals matched) even when the
score is low, so the user can see what was checked against.

---

## Phase 4: Present the scored list and confirm

Before writing any files, present a table like:

| # | Candidate | Category | Pattern confidence | Justification | Best match | Match score |
|---|-----------|----------|--------------------|----------------|------------|-------------|
| 1 | Title | Category | High/Med/Low | 1-line, file-cited | slug or "none" | NN% |

Then recommend an action per row using Phase 3b's thresholds (create new /
update existing / ask), and ask the user which rows to pursue. Use
AskUserQuestion if there are 2-4 strong candidates and the choice is genuinely
the user's; for longer lists, present the table in text and ask which rows to
proceed with.

Do not auto-write for every row — favor materially novel, non-repetitive,
high pattern-confidence candidates over low-confidence or near-duplicate ones.

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
✅ Created: patterns/{slug}.md — {title} (pattern confidence: High)
✅ Updated: patterns/{slug}.md — added source to based_on (matched at NN%)

Skipped candidates (not pursued): {titles, with pattern-confidence/match score}
```

---

## Tips

- `npx -y repomix` avoids interactive install prompts; pass `-o` explicitly
  so you know exactly where the dump landed.
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
