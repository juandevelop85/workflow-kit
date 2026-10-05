---
description: Set up the workflow in this repository (configuration, rules skeleton, backlog)
argument-hint: [stack: rust | node | python | none]
---

Set up the project layer of the workflow in this repository. The core (skills, agents, commands,
scripts) must already be installed under `.agents/`; if `.agents/scripts/workflow_init.py` does not
exist, tell me to run the kit's `install.py` first and stop.

1. If `.agents/workflow.toml` already exists, say so and stop: this command never overwrites the
   project layer.
2. Ask me, one short question each, only what you cannot infer from the repository: the stack (rust,
   node, python or none; infer it from `Cargo.toml`, `package.json` or `pyproject.toml` when
   present, and ask me to confirm), the project name, the tickets directory (default `docs/tickets`),
   the ticket id prefix (default `T`) and the language policy for identifiers and comments.
3. Run `python3 .agents/scripts/workflow_init.py --stack <stack> --name <name>
   [--tickets-dir …] [--id-prefix …] [--language-policy "…"]`.
4. Run `python3 .agents/scripts/workflow_check.py` and `python3 .agents/scripts/workflow_check.py
   gates`, and show me both outputs.
5. Tell me which two files I must fill in by hand because nobody else can: `.agents/rules/project.md`
   (the architecture and conventions) and `.agents/security-model.md` (the threat model), and which
   globs to add to `[sensitive]` in `.agents/workflow.toml`. Do not invent their content.
