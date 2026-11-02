# A human + AI workflow driven by tickets

> **The human governs, the agent executes, the repository remembers.**

This is a method for building software with AI coding agents without losing control of the result.
It is deliberately small: a few files in the repository, a handful of skills and agents, and one
script that turns written rules into checks.

## 1. The central idea

The person decides **what** is built and **why**. The agent carries out the **how** inside a written,
verifiable contract. That contract does not live in the conversation (which is lost between
sessions) but in the repository: rules, tickets, skills and checks, versioned with the code.

In practice:

- Any new agent session starts with the same context and the same rules.
- "Done" is defined by a verifiable acceptance criterion, not by anyone's impression.
- Every change is traceable: to a ticket and a commit, or, for a quick change, to its commit and
  the request it answered.

## 2. The four layers

| Layer | Where it lives | What it provides |
| :--- | :--- | :--- |
| **1. Memory and rules** | `CLAUDE.md`, `AGENTS.md`, `.agents/rules/` | Permanent context: layout, conventions, limits, the decisions already taken. |
| **2. Specification** | the tickets directory and its backlog | Each unit of work has a goal, a technical scope and acceptance criteria. The backlog is the board. |
| **3. Procedure** | skills in `.agents/skills/` | A repeatable runbook to classify a change, and to author and run a ticket end to end. |
| **4. Quality gates** | commands declared in `.agents/workflow.toml`, plus the checker | Objective verification, independent of the agent's opinion. |

A fifth element runs through all of them: **independent review**. The agent that writes the code does
not approve it. Reviewer agents work with clean context; `reviewer` and `security-reviewer` are
read-only by their tool list (no shell), and `test-auditor`, which must run tests, works in a
disposable worktree and is checked with a content fingerprint before and after.

### The kit: core and project layer

The kit separates what is **method** from what is a **project decision**.

- The **core** (skills, agents, commands, the checker, stack presets, templates) never names a
  product, a language or a directory layout. It reads everything specific from the project.
- The **project layer** (`.agents/workflow.toml`, `.agents/rules/`, the threat model, the size
  baseline, the tickets) holds the decisions: stack, conventions, limits, what is sensitive.

The criterion that decides which side something falls on: **if a second project could not adopt it
unchanged, it is a project decision**. Updating the core never modifies the project layer.

## 3. Roles

**The person** sets the vision and priorities, writes or approves the tickets and their acceptance
criteria, decides what is deferred and what is accepted, and corrects the course when something does
not fit.

**The agent** reads the backlog and the ticket, plans and defines the tests before implementing,
implements, runs the tests, validates each criterion, keeps the backlog and the documentation up to
date, writes detailed commits and audits its own work.

| The person decides | The agent proposes and executes |
| :--- | :--- |
| Vision, strategy and priorities | Technical breakdown and design inside the scope |
| What enters, what is deferred | Implementation, tests and documentation |
| Accepting or rejecting a result | Verification against the criteria and the gates |
| Changing a project rule | Detecting the need for a rule and drafting it |

The agent does not change functional goals on its own, does not close a ticket with a gate in red and
does not rewrite a project decision.

## 4. The cycle

```text
 Intent ──► Ticket ──► Execution ──► Verification ──► Review ──► Close
    ▲                                                              │
    └───────────── New rule / new ticket (learning) ◄──────────────┘
```

1. **Intent.** The person states a goal, or the agent proposes one after an audit. Often it is
   clarified first in a free conversation with the agent. That conversation is a means, not the
   contract: it is lost between sessions, so what was decided must be written into tickets.
2. **Ticket.** It is formalised with a technical scope and verifiable acceptance criteria
   (`ticket-author`). When it comes from a conversation, the agent first summarises what was agreed,
   proposes the breakdown into tickets and waits for the person's approval before writing them; each
   ticket keeps the decisions taken in its "Context and Decisions" section.
3. **Execution** (`ticket-runner`): context first; plan and tests first; implementation; validation
   criterion by criterion with traceability to a test; the quality gates; independent review; backlog
   update; the closing commit; a report to the person.
4. **Review.** The person reviews. If something drifted, fix the **ticket or the rule**, not only the
   code.
5. **Learning.** What was learned is written into the rules so it does not repeat with any agent.

A quick change (section 5) skips the Ticket step, `ticket-runner` and the reviewer subagents; the
gates and the checker always run.

## 5. Proportional ceremony: lanes

The flow above is the same for every change; **how much of it runs depends on the work**. This is the
core idea of Organic Driven Development (ODD): process that does not reduce a real risk is waste, and
a method that charges a typo the price of a feature teaches people to skip it.

| Lane | When | What it takes |
| :--- | :--- | :--- |
| **quick** | Small, localised, well understood, no sensitive surface | No ticket. Read, change, gates, checker, self-review of the diff, a `quick` commit. |
| **standard** | A real behaviour change, or anything sensitive | A ticket (it may be short), tests first, gates, `review-plan`, one commit. |
| **deep** | Large, wide or risky work | A ticket split into steps, an explicit risk section, plan confirmed with the person, full review. |

Who decides, and how it stays honest:

1. **The checker measures** what can be measured and prints a *minimum* lane (`workflow_check.py
   classify`): size and spread of the diff, sensitive paths, code changed without a test change,
   binary files, and changes to the workflow itself (`.agents/`, agent memory). A sensitive path is
   never quick, however small: one line of session settings can be a security change. Moves count
   at both ends, so moving a file into a sensitive path is caught.
2. **The agent judges** what cannot be measured, with four questions: is it well understood? free of
   hidden risk? finishable and reviewable on its own? resumable from the request and the diff? Any
   "no" raises the lane. The agent may raise a lane, never lower it.
3. **The history is audited.** A `quick` commit (`<type>(<area>): quick - <title>`) is checked
   afterwards by `check --commits`: one that exceeded the quick limits, touched a sensitive path, a
   binary or the workflow's own files, or cites a ticket outside the backlog is an error. Written instructions are not enforcement; this check is.

What the audit does **not** catch, by design or not yet: one change split into several quick
commits (each is judged alone); touching any test file switches off the untested-code signal; a
merge commit's own changes are not audited; each commit is judged by the configuration at `HEAD`
(which is why changing that configuration is never quick). These are limits of measurement: the
review of standard work and the person's review of the history cover them.

The gates and the checker run in every lane. What changes is the paperwork and the reviewers, never
the verification. The `change` skill (`/change`) is the single entry point that classifies and then
runs the lane; `ticket-runner` remains the procedure for standard and deep work.

## 6. Principles

1. **The repository is the memory.** The agent does not remember between sessions; the repository
   does.
2. **Contract before code.** Without acceptance criteria there is no "done".
3. **Objective verification.** Tests and checks decide, not confidence.
4. **A criterion without a test is declared, not met.** Traceability from criterion to test is part of
   closing.
5. **Honesty.** Documentation describes current behaviour, never aspirations. If something is a
   simulation, the data says so.
6. **Rules correct themselves.** Each repeated mistake becomes a written rule, with the ticket or
   commit that taught it.
7. **Small, traceable changes.** One ticket, one commit; a quick change, one `quick` commit; moving
   code never mixes with changing behaviour.
8. **One framework, several agents.** `.agents/` is the single source; each tool links to it.
9. **Honest scope.** If a ticket must grow, document it; if it is partial, say so.
10. **A rule that can be silenced unnoticed is not a rule.** Anything the project switches off is
    reported on every run.
11. **Ceremony in proportion to risk.** The flow is the same for every change; how much of it runs
    is measured, judged and audited (section 5). Process that reduces no risk is waste.

## 7. The pieces

| Piece | Role |
| :--- | :--- |
| `change` (skill) | Single entry point: classifies a change and runs only the process its lane needs. |
| `ticket-author` (skill) | Writes a ticket with criteria that name their test and registers it. |
| `ticket-runner` (skill) | Runs a ticket end to end. |
| `quality-gate` (skill) | Runs the declared gates and reports what this change breaks and what was already broken. |
| `reviewer` (agent) | Reviews the diff against the ticket and the rules. Read-only. |
| `test-auditor` (agent) | Checks that each criterion has a test that would fail if the code were wrong, mutating code in a disposable worktree. |
| `security-reviewer` (agent) | Reviews sensitive surfaces with an attacker's mindset, against the project's threat model. Read-only. |
| `workflow_check.py` | Backlog coherence, honest closing, file sizes, commit format (and audit of `quick` commits); lists the gates; finds sensitive changes; `classify` prints the minimum lane; `review-plan --write-diff` hands the diff to the reviewers; `fingerprint` hashes HEAD, the index, the working tree and the untracked files (not ignored files or `.git`) to show an agent changed none of them. |
| Token economy | The skills read a compact `context` brief instead of the whole backlog; `review-plan` skips review subagents for tiny or docs-only diffs; `gates --run` logs gate output to a file and reports one line per gate; the review agents return one line per finding with a cap, and `test-auditor` runs on a cheaper model (`model:` in its frontmatter; change it there). |
| Commands | `/change`, `/ticket-new`, `/ticket-run`, `/ticket-review`, `/quality-gate`, `/ticket-status`, `/workflow-init`. |

## 8. What to add next

The method gives a base; further quality methods are separate decisions, each worth its own ticket,
and none is part of this kit yet: dependency and licence audits, secret scanning in CI, fuzzing of
parsers, automated mutation testing (`test-auditor` only mutates by hand), property-based testing, coverage thresholds, and evaluations of whether a
new agent follows the rules. Add one when a real failure shows you need it, not before.
