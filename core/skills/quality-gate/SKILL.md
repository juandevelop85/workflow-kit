---
name: quality-gate
description: >-
  Run the project's quality gates (format, lint, tests, workflow rules) and return a pass/fail
  report with evidence. Activate before closing a ticket, before a push, or when the user asks
  'run the gates', 'check quality' or 'make sure CI will pass'.
---

# Quality gates

The gates are declared by the project, not by this skill. **No ticket is closed with a gate in
red**, not even one the ticket did not touch.

## 1. Get the gates

```bash
python3 .agents/scripts/workflow_check.py gates
```

prints one `name<TAB>command` per line, resolved from the stack preset plus the project's
overrides. Warnings on stderr tell you about gates the project has switched off: **report each of
them**, a gate that can be silenced without anyone noticing is not a gate.

## 2. Run them

Run every gate in the order given, and stop to read the first failure. Then run the workflow
rules:

```bash
python3 .agents/scripts/workflow_check.py
```

(backlog coherence, honest closing, file sizes; add `--commits N` to check the last N commit
subjects). If the change touches a part of the repository with its own CI job or toolchain, read
that job and use its commands instead of guessing.

## 3. Things that are not a command

Read the project rules (`[project].rules`) and check by hand what no tool checks: comments that
promise more than the code does, new risky constructs the rules forbid, a code-moving refactor
that changed the number of tests.

## 4. Report

A table `gate | result | evidence` (trimmed output, test counts). Distinguish:

- **Red because of this change:** fix it before continuing.
- **Already red** (check against the base branch): do not hide it and do not "fix" it out of scope
  in silence; document it and decide with the user whether to widen the ticket.
- **Not run** (missing toolchain, no network…): say so explicitly. "Not run" is never "passed".

Never skip, disable or silence a test or a lint to get a green result.
