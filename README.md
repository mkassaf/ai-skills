# ai-skills

A collection of [Claude Code](https://claude.com/claude-code) skills, plus tips
and notes on how to use them.

Each skill lives in its own folder under [`skills/`](skills/) as a
`SKILL.md` file with YAML front-matter (`name`, `description`,
`allowed-tools`) followed by the skill's workflow instructions.

## Skills

| Skill | What it does |
|---|---|
| [`repomix-pattern-extraction`](skills/repomix-pattern-extraction/SKILL.md) | Extracts agentic AI design patterns from a [repomix](https://github.com/yamadashy/repomix) XML dump of a codebase: parses the packed repo, triages files for concrete agentic mechanisms, confirms candidates with the user, then matches/creates/updates pattern entries. |

## How to use these skills

Claude Code skills are invoked with a slash command matching their folder
name (e.g. `/repomix-pattern-extraction`). To make a skill available in a
project:

1. Copy the skill's folder into that project's `.claude/skills/` directory:
   ```bash
   cp -r skills/<skill-name> /path/to/your/project/.claude/skills/
   ```
2. Restart or reload Claude Code in that project so it picks up the new
   skill, or run `/skills` to refresh.
3. Invoke it with `/<skill-name> <args>` — check the skill's `SKILL.md` for
   what arguments it expects.

Skills are plain Markdown + YAML, so they're easy to read before trusting
them — open the `SKILL.md` to see exactly what tools it's allowed to use
(`allowed-tools`) and what workflow it follows before copying it into a
project.

## Tips

- Keep `allowed-tools` as narrow as the skill actually needs — it's the
  first thing to check when reviewing a skill you didn't write yourself.
- A skill that writes files should describe its output format and any
  user-confirmation checkpoints explicitly in its `SKILL.md` — don't assume
  the model will pause to ask unless the instructions say so.
- Skills that delegate to other skills (rather than re-implementing their
  logic) age better — when the underlying skill changes, the delegating one
  doesn't need to be rewritten.
- Large or unbounded inputs (log dumps, packed-repo XML, etc.) should be
  inventoried/skimmed before being read in full — say so in the skill so it
  doesn't blow out the context window on big inputs.

## Contributing

Add a new skill by creating `skills/<skill-name>/SKILL.md` and adding a row
to the table above.
