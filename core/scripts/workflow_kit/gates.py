"""Stack presets and quality gates: resolve them, list them, run them."""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import time
import tomllib

from .config import CACHE_DIR, ConfigError, efficiency, kit_dir, load_config


def load_preset(root: pathlib.Path, name: str) -> dict:
    if name in ("", "none"):
        return {"gate": [], "size": {}}
    path = kit_dir(root) / "presets" / f"{name}.toml"
    if not path.exists():
        raise ConfigError(f"unknown stack preset «{name}» (no {path.relative_to(root)})")
    return tomllib.loads(path.read_text(encoding="utf-8"))


def resolve_gates(root: pathlib.Path, cfg: dict) -> tuple[list[dict], list[str]]:
    """Gates = preset gates, with project overrides, plus project extras."""
    gates_cfg = cfg.get("gates", {})
    preset = load_preset(root, gates_cfg.get("preset", "none"))
    overrides = gates_cfg.get("override", {})
    gates, warnings = [], []
    for gate in preset.get("gate", []):
        name = gate["name"]
        ov = overrides.get(name, {})
        if ov.get("enabled", True) is False:
            warnings.append(f"gate «{name}» is DISABLED in workflow.toml")
            continue
        gates.append({"name": name, "command": ov.get("command", gate["command"])})
    for name in overrides:
        if name not in {g["name"] for g in preset.get("gate", [])}:
            warnings.append(f"workflow.toml: [gates.override.{name}] matches no gate of the preset")
    for extra in gates_cfg.get("extra", []):
        gates.append({"name": extra["name"], "command": extra["command"]})
    return gates, warnings


def run_gates(root: pathlib.Path, as_json: bool) -> int:
    try:
        cfg = load_config(root)
        gates, warnings = resolve_gates(root, cfg)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    if as_json:
        print(json.dumps(gates, indent=2))
    else:
        for g in gates:
            print(f"{g['name']}\t{g['command']}")
    return 0


def run_gates_report(root: pathlib.Path, tail: int | None) -> int:
    """Run every gate; keep the full output on disk, print only what a decision needs."""
    try:
        cfg = load_config(root)
        gates, warnings = resolve_gates(root, cfg)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    eff = efficiency(cfg)
    tail = eff["gate_tail_lines"] if tail is None else tail
    for w in warnings:
        print(f"warning: {w}")
    logs = root / CACHE_DIR
    logs.mkdir(parents=True, exist_ok=True)
    (root / ".agents/.cache/.gitignore").write_text("*\n", encoding="utf-8")
    failed = 0
    for gate in gates:
        log = logs / f"{re.sub(r'[^A-Za-z0-9_.-]', '_', gate['name'])}.log"
        started = time.monotonic()
        try:
            res = subprocess.run(gate["command"], shell=True, cwd=root, capture_output=True, text=True,
                                 errors="replace", timeout=eff["gate_timeout_seconds"])
            code, output = res.returncode, res.stdout + res.stderr
        except subprocess.TimeoutExpired as exc:
            code, output = 124, f"timed out after {eff['gate_timeout_seconds']}s\n{exc.stdout or ''}"
        log.write_text(output if isinstance(output, str) else output.decode(errors="replace"), encoding="utf-8")
        took = time.monotonic() - started
        rel = log.relative_to(root).as_posix()
        if code == 0:
            print(f"PASS {gate['name']} ({took:.1f}s)")
        else:
            failed += 1
            print(f"FAIL {gate['name']} (exit {code}, {took:.1f}s) full output: {rel}")
            for line in output.splitlines()[-tail:] if tail else []:
                print(f"  | {line}")
    print(f"\n{len(gates)} gate(s): {len(gates) - failed} passed, {failed} failed")
    return 1 if failed else 0
