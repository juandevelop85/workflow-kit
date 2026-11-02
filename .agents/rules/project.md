# workflow-kit · Project rules

These rules are read by every agent before it works on the kit itself.

## Architecture and conventions

- `core/` is the product: what `install.py` copies into other repositories. It never names a
  product, a language or a directory layout (`tests/test_kit_hygiene.py` checks it).
- In this repository `.agents/` holds the project layer of the kit itself; its `agents`, `commands`,
  `scripts`, `presets`, `skills` and `templates` are symlinks to `core/`. Never copy core files into
  `.agents/`: edit them in `core/`.
- Python 3.11+, standard library only, for the scripts and the tests. The tests use `unittest` and
  run the scripts as a user would (subprocess over throwaway repositories built from the fixtures).
- Every security property has a regression test: the installer, the generator and the checker's git
  hardening in `tests/test_security.py`, the review hand-off and the cache in
  `tests/test_read_only.py`, the quick-lane audit in `tests/test_lanes.py`, the review agents' tool
  lists in `tests/test_kit_hygiene.py`.

## Language policy

Identifiers, comments and documentation are written in English. Conversation with the user follows
the user's language.

## Change flow

- Every change starts with the `change` skill: `workflow_check.py classify` prints its minimum lane.
  Quick changes need no ticket (`<type>(<area>): quick - <title>`); anything else is a ticket in
  `docs/tickets/`. Never use a lighter lane than the one printed. `core/skills`, `core/commands` and
  `core/templates` are process files here (`[lanes].process_globs`): changing them is never quick.
- One ticket, one commit, with the format `<type>(<area>): <TID> - <title>`.
- Moving code never mixes with changing behaviour.
- The kit must pass its own checker: `python3 .agents/scripts/workflow_check.py --commits 20`
  (`tests/test_dogfood.py` runs it).

## Rules learned

- A feature is not "in the changelog" until it is committed (T1.1: the token economy was described
  as released while still uncommitted).
