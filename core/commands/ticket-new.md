---
description: Create ticket(s) from an idea, bug, finding or the conversation so far
argument-hint: [description of the idea | empty = use the conversation] [phase]
---

Use the `ticket-author` skill to formalise this work as a ticket: $ARGUMENTS

Follow its full protocol (read the backlog, read the affected code, write criteria that name their
test, register it in the backlog, run `python3 .agents/scripts/workflow_check.py`). If $ARGUMENTS is empty or refers to the discussion so far, work from the conversation: follow the
"From a conversation" section of the skill (summarise what was agreed, propose the breakdown, wait
for approval, then write the tickets). Do not implement
anything. Finish by asking the decisions that are mine (priority, doubtful scope).
