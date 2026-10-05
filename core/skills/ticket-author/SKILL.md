---
name: ticket-author
description: >-
  Write a new ticket in the project's ticket directory with the standard structure (description,
  technical scope, verifiable acceptance criteria, test plan) and register it in the backlog.
  Activate when the user wants to create, formalise or break down an idea, an audit finding or a
  bug into a ticket (e.g. 'create a ticket for…', 'formalise this as T2.3').
---

# Ticket author

The ticket is the contract of the work: without verifiable acceptance criteria there is no "done".
This skill produces the ticket; it does **not** implement anything (that is `ticket-runner`).

Where tickets live, how they are numbered and what a status looks like come from
`.agents/workflow.toml` (`[tickets]`). Read it first.

## 1. Context

1. Read the backlog: the last id of the target phase, the dependencies, and whether the idea already
   exists (search before duplicating).
2. Read one or two recent tickets of the same phase to match tone and level of detail.
3. Locate the real code that is affected and cite it with relative links. A ticket that describes
   code nobody read lies; if something could not be checked, say so in the ticket.

## 2. Structure

Start from `.agents/templates/ticket.md.tmpl` (replace the `{{…}}` placeholders). File name: `<id>-<lowercase-slug>.md` inside the tickets
directory. Sections: Description, Technical Scope, Acceptance Criteria, Test Plan, Risks. The
header status line must use the same symbol as the backlog row.

## 3. Quality of a ticket

- **Verifiable:** no "improve", "optimise" or "make robust" without a measure or a test that
  proves it. Each criterion names its test (`test: name`) or the command/inspection.
- **One ticket, one commit:** if the scope needs several independent commits, split it.
- **Honest:** if something is a simulation today, the ticket says so.
- **Sensitive surfaces:** if the change touches a path listed in `[sensitive].globs`, add
  "Requires security review" to the Risks so the review step launches the security reviewer.
- **Do not change the scope of an existing ticket** unless asked: create a new one and link it.

## 4. Register it

1. Add the row at the end of its phase in the backlog, with the same format as the others.
2. Run `python3 .agents/scripts/workflow_check.py` and check the new ticket introduces no error.
3. Do not commit the ticket mixed with code: `docs(tickets): <TID> - <title>`.

## 5. Summary to the user

The id and path created, the acceptance criteria as a short list, the dependencies, and which
decisions are still the user's (priority, doubtful scope).
