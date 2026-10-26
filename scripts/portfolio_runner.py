#!/usr/bin/env python3
"""Bounded, opt-in GitHub workflow dispatcher for existing repositories.

No repository creation, visibility changes, merge, force push, deploy, or secrets
management. Without --execute, never invokes gh or changes a remote resource.
Requires only Python 3.11+ and optional authenticated GitHub CLI.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, nullcontext
import fcntl
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import time
from typing import Callable, Sequence

REPO = re.compile(r"^(?![-.])[A-Za-z0-9_.-]+/(?![-.])[A-Za-z0-9_.-]+$")
WORKFLOW = re.compile(r"^[A-Za-z0-9_.-]+\.ya?ml$")
REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./-]{0,120}$")
MAX_REPOS = 50
MAX_DISPATCHES = 5
CONFIG_MAX_BYTES = 200_000
DEFAULT_TIMEOUT = 25
MAX_RUNTIME_SECONDS = 600


class ConfigurationError(ValueError):
    """An explicitly configured safety constraint was violated."""


def validate(config: object) -> dict:
    if not isinstance(config, dict) or config.get("version") != 1:
        raise ConfigurationError("Config must be a version 1 JSON object")
    allowed = {"version", "enabled", "repositories", "max_dispatches"}
    if set(config) - allowed:
        raise ConfigurationError("Unknown config keys (fail closed)")
    if type(config.get("enabled")) is not bool:
        raise ConfigurationError("enabled must be true or false")
    repos = config.get("repositories")
    if not isinstance(repos, list) or len(repos) > MAX_REPOS:
        raise ConfigurationError("repositories must be an array of at most 50 entries")
    budget = config.get("max_dispatches", 2)
    if type(budget) is not int or not 1 <= budget <= MAX_DISPATCHES:
        raise ConfigurationError("max_dispatches must be an integer between 1 and 5")
    seen: set[tuple[str, str, str]] = set()
    normalized = []
    for index, row in enumerate(repos):
        if not isinstance(row, dict) or set(row) != {"repository", "workflow", "ref"}:
            raise ConfigurationError(f"Entry {index}: require repository, workflow and ref only")
        repo, workflow, ref = (row["repository"], row["workflow"], row["ref"])
        if not isinstance(repo, str) or not REPO.fullmatch(repo) or any(part in (".", "..") for part in repo.split("/")):
            raise ConfigurationError(f"Entry {index}: invalid repository slug")
        if not isinstance(workflow, str) or not WORKFLOW.fullmatch(workflow):
            raise ConfigurationError(f"Entry {index}: workflow must be a .yml/.yaml filename")
        if not isinstance(ref, str) or not REF.fullmatch(ref) or ".." in ref or "//" in ref:
            raise ConfigurationError(f"Entry {index}: invalid git ref")
        key = (repo.casefold(), workflow, ref)
        if key in seen:
            raise ConfigurationError(f"Entry {index}: duplicated repository/workflow/ref")
        seen.add(key)
        normalized.append({"repository": repo, "workflow": workflow, "ref": ref})
    return {"version": 1, "enabled": config["enabled"], "repositories": normalized, "max_dispatches": budget}


def load_config(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size > CONFIG_MAX_BYTES:
        raise ConfigurationError("Config missing or too large")
    return validate(json.loads(path.read_text(encoding="utf-8")))


def targets_hash(config: dict) -> str:
    """Identify the ordered allowlist so changing it resets the rotation."""
    data = json.dumps(config["repositories"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def load_cursor(path: Path, config: dict) -> int:
    """Return a persisted index; never trust an invalid or oversized state file."""
    if not path.exists():
        return 0
    if not path.is_file() or path.stat().st_size > 8192:
        raise ConfigurationError("Rotation state is invalid or too large")
    state = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state, dict) or set(state) != {"version", "targets_sha256", "next_index"}:
        raise ConfigurationError("Rotation state has an invalid schema")
    if type(state["version"]) is not int or state["version"] != 1:
        raise ConfigurationError("Rotation state version is invalid")
    if not isinstance(state["targets_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", state["targets_sha256"]):
        raise ConfigurationError("Rotation state fingerprint is invalid")
    if state["targets_sha256"] != targets_hash(config):
        return 0
    index = state["next_index"]
    total = len(config["repositories"])
    if type(index) is not int or not (0 <= index < total if total else index == 0):
        raise ConfigurationError("Rotation cursor is out of range")
    return index


def command(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    # NEVER shell=True; no command interpolation, script execution or API token logging.
    return subprocess.run(
        list(args), shell=False, capture_output=True, text=True,
        timeout=DEFAULT_TIMEOUT, check=False,
    )


def call_gh(args: Sequence[str], runner: Callable = command) -> bool:
    try:
        result = runner(["gh", *args])
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def dispatch(config: dict, execute: bool = False, runner: Callable = command, start_index: int = 0) -> dict:
    """Make an auditable report; execution dispatches EXISTING workflows only."""
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    entries = []
    eligible = config["enabled"] and execute
    dispatched = 0
    deadline = time.monotonic() + MAX_RUNTIME_SECONDS
    targets = config["repositories"]
    total = len(targets)
    if type(start_index) is not int or not (0 <= start_index < total if total else start_index == 0):
        raise ConfigurationError("Invalid rotation cursor")
    # Rotate only in real execution; previews keep the configured order.
    ordered = targets[start_index:] + targets[:start_index] if eligible else targets
    next_index = start_index
    for offset, item in enumerate(ordered):
        repo, workflow, ref = (item["repository"], item["workflow"], item["ref"])
        report = {"repository": repo, "workflow": workflow, "ref": ref}
        if time.monotonic() >= deadline:
            report["status"] = "time_budget_exhausted"
        elif not config["enabled"]:
            report["status"] = "disabled"
        elif not execute:
            report["status"] = "dry_run"
        elif dispatched >= config["max_dispatches"]:
            report["status"] = "budget_exhausted"
        else:
            # Check repository archive state before invoking anything. Nothing
            # about the response, token, or private repository is logged.
            try:
                info = runner(["gh", "api", f"repos/{repo}", "--jq", ".archived"])
                is_archived = info.returncode != 0 or info.stdout.strip() != "false"
            except (OSError, subprocess.TimeoutExpired):
                is_archived = True
            if is_archived:
                report["status"] = "archived_or_unavailable"
            elif not call_gh(["api", f"repos/{repo}/actions/workflows/{workflow}"], runner):
                report["status"] = "workflow_unavailable"
            else:
                # A dispatched workflow is NOT a passing CI run or a released product.
                if call_gh(["workflow", "run", workflow, "--repo", repo, "--ref", ref], runner):
                    report["status"] = "dispatched_unverified"
                    dispatched += 1
                    # Next invocation starts after the latest successful dispatch.
                    # Without this, a finite budget starves later repositories.
                    next_index = (start_index + offset + 1) % total
                else:
                    report["status"] = "dispatch_failed"
        entries.append(report)
    return {"generated_at": now, "mode": "execute" if eligible else "dry_run",
            "dispatches": dispatched, "max_dispatches": config["max_dispatches"],
            "next_index": next_index, "results": entries,
            "note": "Workflow dispatch is not completion, test success, deployment or publication."}


@contextmanager
def execution_lock(state_path: Path):
    """Prevent overlapping explicit dispatches from reusing the same cursor."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = state_path.with_name(state_path.name + ".lock")
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(lock_path, flags, 0o600)
    except OSError as error:
        raise ConfigurationError("Unable to open exclusive execution lock") from error
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise ConfigurationError("Execution lock is not a private regular file")
        os.fchmod(fd, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ConfigurationError("Another workflow dispatcher is already running") from error
        yield
    finally:
        os.close(fd)


def write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Random exclusive temp file prevents a predictable .tmp symlink overwrite.
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bounded opt-in GitHub workflow dispatcher")
    parser.add_argument("--config", type=Path, default=Path("config/portfolio.json"))
    parser.add_argument("--output", type=Path, default=Path("reports/portfolio-run.json"))
    parser.add_argument("--execute", action="store_true", help="Dispatch existing workflows (explicit opt-in)")
    parser.add_argument("--state", type=Path, default=Path("reports/portfolio-state.json"),
                        help="Private persisted round-robin cursor (used only with --execute)")
    parser.add_argument("--validate", action="store_true", help="Validate config without accessing GitHub")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        if args.validate:
            print(f"VALID: {len(config['repositories'])} configured targets, enabled={config['enabled']}")
            return 0
        if args.execute and not config["enabled"]:
            raise ConfigurationError("Execution denied: config.enabled must be true")
        # Dry runs never create a lock or touch the cursor. Explicit dispatch
        # holds the lock through cursor read, remote calls and state persistence.
        with (execution_lock(args.state) if args.execute else nullcontext()):
            start_index = load_cursor(args.state, config) if args.execute else 0
            result = dispatch(config, execute=args.execute, start_index=start_index)
            if args.execute:
                write_report(args.state, {"version": 1, "targets_sha256": targets_hash(config),
                                          "next_index": result["next_index"]})
            write_report(args.output, result)
        print(f"{result['mode']}: {len(result['results'])} targets, {result['dispatches']} workflow dispatches")
        if args.execute and any(x["status"].endswith(("failed", "unavailable")) for x in result["results"]):
            return 2
        return 0
    except (ConfigurationError, ValueError, OSError, json.JSONDecodeError) as error:
        print(f"Portfolio runner: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
