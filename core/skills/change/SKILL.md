---
name: change
description: >-
  Single entry point for any change to the code or docs: measures the change, picks the lightest lane
  that is safe (quick, standard or deep) and runs only the process that lane needs. Activate when the
  user asks to fix, change, add or tweak something without naming a ticket (e.g. 'fix this typo',
  'rename this function', 'add a flag to X'). With a ticket id, use `ticket-runner` instead.
---

# Change

The flow is the same for every change; how much of it runs depends on the work (Organic Driven
Development). Ceremony that does not reduce a real risk is waste: skip it. Ceremony that a risk
needs is never skipped.

## 1. Authorise and understand

1. If the user asked a question or an analysis, answer it **without modifying files** unless they
   ask for the change.
2. Read the code the change touches and the rules in `[project].rules` of `.agents/workflow.toml`.
   Do not change code you have not read.
3. Resolve doubts by reading; ask the user only about product decisions, not about things the code
   can tell you.

## 2. Classify

Make the change (or a first cut of it, for a large one: stop early) and run:

```bash
python3 .agents/scripts/workflow_check.py classify
```

It prints the **minimum lane** from what it can measure (size, spread, sensitive paths, code changed
without tests, binary files, changes to the workflow itself) and four questions it cannot measure. Answer them honestly: **any "no" raises the
lane by one**. You may raise a lane; you may never lower the one the checker prints. When unsure,
raise it.

## 3. Run the lane

- **quick**: no ticket. Finish the change; run `python3 .agents/scripts/workflow_check.py gates --run`
  and `python3 .agents/scripts/workflow_check.py`; re-read the whole diff once as a reviewer would;
  commit as `<type>(<area>): quick - <title>` with a body that says what changed and how it was
  verified. `check --commits` audits later that every `quick` commit really was within the limits.
- **standard**: write a ticket with `ticket-author` (it may be short: a goal, a scope and criteria
  that name their test), then run it with `ticket-runner`.
- **deep**: as standard, but split the work into steps or several tickets, fill in the Risks section
  and confirm the plan with the user before writing code.

If the change grows while you work, classify again: a quick change that stops being quick becomes a
ticket, written before the commit. Never split one change into several quick commits to stay under
the limits: the audit judges each commit alone, and that is exactly the gap it cannot see.

## 4. Report

What changed; what was verified and how (gate lines, tests); what is still pending. Say which lane
you used and why, in one line.
