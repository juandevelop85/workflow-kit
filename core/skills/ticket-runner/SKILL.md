---
name: ticket-runner
description: >-
  Standard protocol to plan, implement, verify, review, commit and close a ticket from the
  project's backlog. Activate when the user wants to resolve, continue or audit a ticket
  (e.g. 'run ticket T1.1', 'implement T1.2').
---

This is the procedure of the **standard** and **deep** lanes. A change without a ticket starts with
the `change` skill, which classifies it first; a quick change never needs this protocol.

# Ticket runner

Project-specific facts (ticket directory and format, quality gates, size limits, commit format,
rules) live in `.agents/workflow.toml` and the files it lists under `[project].rules`. **Read them
first; do not assume them.**

## 1. Context before touching code

1. Run `python3 .agents/scripts/workflow_check.py context <TID>`. It prints the status of the
   ticket and of its dependencies (flagging any that is not done), the rules files to read, and the
   description, scope and acceptance criteria. If a dependency is not done, say so before starting.
   Read the full backlog or ticket file only if that brief is not enough.
2. Read `.agents/workflow.toml` only if you need a setting the brief does not show, and every file
   in `[project].rules`.
3. Identify the ticket's **description, technical scope and acceptance criteria**. If the criteria
   are not verifiable, stop and ask the user to fix the ticket: without a verifiable criterion there
   is no "done".
4. Read the code the ticket will touch. Do not describe or change code you have not read.

## 2. Plan and tests first

1. List the modules the change affects and the order of work.
2. For each acceptance criterion, decide the test that will prove it **before** writing the code.
   A criterion that cannot be automated needs a documented inspection (a command and what to look
   for).
3. Write the tests first when the behaviour is new; see them fail for the right reason.

## 3. Implement

- Follow the project rules. Keep the change inside the ticket's scope; if the scope must grow to
  keep the gates green, **document the extension in the ticket**, do not slip it in silently.
- Small, traceable steps. Moving code never mixes with changing behaviour: do it in its own commit,
  with the same number of tests before and after.
- Never skip, disable or silence a test or a lint to get a green result.

## 4. Validate

1. **Criterion → test traceability.** Walk the acceptance criteria one by one and point at the test
   (or documented inspection) that covers each. A criterion without a test is declared, not met.
2. **Gates.** Run the `quality-gate` skill. No gate may be red.
3. **Independent review.** Before the commit, run
   `python3 .agents/scripts/workflow_check.py review-plan --ticket <TID>`. It measures the diff and
   prints which of `reviewer`, `test-auditor` and `security-reviewer` to launch, and why. Launch
   exactly those. When it prints `launch: none`, do a written self-review of the diff against the
   ticket and the rules instead of spending a subagent; a sensitive surface always gets the
   `security-reviewer`. The one who implements is not the one who approves: fix the blocking
   findings, or justify in writing why not.

## 5. Update the backlog

Set the status of the ticket (its header line and its row in the backlog) to done **only** when
every criterion is verified and every gate is green. If the work is partial, say it: leave it in
progress and list what is missing in the ticket. Then run
`python3 .agents/scripts/workflow_check.py`.

## 6. Closing commit

One commit per ticket, using the project's format (`[commits].format_hint`).

- Title: `<type>(<area>): <TID> - <short title>`.
- Body: the goal of the ticket; the files and modules created or changed; the tests added or run and
  their result; the state of each acceptance criterion; anything left pending.

## 7. Report to the user

A concise summary: commit hash and message; files and modules changed; tests run and their result;
findings of the review and what was done about them; what is still pending; the suggested next
ticket respecting dependencies.
