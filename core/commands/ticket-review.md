---
description: Independent review of a ticket or diff (reviewer, test auditor and, if it applies, security)
argument-hint: [ticket id | branch | empty for the current diff]
---

Review $ARGUMENTS (if empty, the current diff against the base branch) with independent reviewers,
launched in parallel as subagents. First run `python3 .agents/scripts/workflow_check.py review-plan
--write-diff` (add `--base <ref>` for a branch): the reviewers have no shell and read the diff from
`.agents/.cache/review/diff.patch`.

1. `reviewer`: correctness, scope, project rules.
2. `test-auditor`: criterion → test traceability and quality of the tests. It can run code: compare
   `python3 .agents/scripts/workflow_check.py fingerprint` before and after it; a different hash
   voids its report.
3. `security-reviewer`: when the diff touches a sensitive surface (`review-plan` lists it).

Launch at least the ones `review-plan` prints; this command may add the others on request.

Consolidate the reports into one, without duplicates, ordered by severity and separating BLOCKING from
OPTIONAL. Do not fix anything until I confirm, unless this command was invoked from `/ticket-run`.
