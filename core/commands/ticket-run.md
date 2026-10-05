---
description: Run a ticket end to end with the ticket-runner protocol
argument-hint: <ticket id, e.g. T1.1>
---

Run ticket $ARGUMENTS with the `ticket-runner` skill.

Respect the whole protocol: context first, plan and tests first, implementation, criterion-by-criterion
validation with traceability to tests, the gates (`quality-gate`), independent review (`reviewer`, and
`security-reviewer` if the diff touches a sensitive surface), backlog update and the closing commit in
the project's format. If a gate fails, do not close the ticket. Finish with the summary of step 7 of
the skill.
