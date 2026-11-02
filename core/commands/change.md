---
description: Make a change with only the process it needs (quick, standard or deep lane)
argument-hint: <what to change>
---

Use the `change` skill for: $ARGUMENTS

Classify the change with `python3 .agents/scripts/workflow_check.py classify`, answer its questions,
never use a lighter lane than the one it prints, and run that lane. Finish with the report of the
skill: what changed, how it was verified, what is pending and the lane used.
