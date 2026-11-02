#!/usr/bin/env python3
"""Workflow checker: turns the rules a project wrote down into checks.

The code lives in the `workflow_kit` package next to this file; `--help` lists the subcommands.
Standard library only (Python 3.11+, for `tomllib`).
"""
import pathlib
import sys

# `python3 -I` (or PYTHONSAFEPATH) leaves the script's directory off sys.path: put it back.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from workflow_kit.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
