---
description: Independent review of a ticket or diff (reviewer, test auditor and, if it applies, security)
argument-hint: [ticket id | branch | empty for the current diff]
---

Review $ARGUMENTS (if empty, the current diff against the base branch) with independent reviewers,
launched in parallel as subagents:

1. `reviewer`: correctness, scope, project rules.
2. `test-auditor`: criterion → test traceability and quality of the tests.
3. `security-reviewer`: only if `python3 .agents/scripts/workflow_check.py sensitive` lists changed
   files for this diff.

Consolidate the reports into one, without duplicates, ordered by severity and separating BLOCKING from
OPTIONAL. Do not fix anything until I confirm, unless this command was invoked from `/ticket-run`.
