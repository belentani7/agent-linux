#!/usr/bin/env python3
"""Bounded, opt-in GitHub workflow dispatcher for existing repositories.

No repository creation, visibility changes, merge, force push, deploy, or secrets
management. Without --execute, never invokes gh or changes a remote resource.
Requires only Python 3.11+ and optional authenticated GitHub CLI.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Callable, Sequence

REPO = re.compile(r"^(?![-.])[A-Za-z0-9_.-]+/(?![-.])[A-Za-z0-9_.-]+$")
WORKFLOW = re.compile(r"^[A-Za-z0-9_.-]+\.ya?ml$")
REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./-]{0,120}$")
MAX_REPOS = 500
MAX_DISPATCHES = 5
MAX_PROBES = 15  # No more than 15 remote repository lookups per iteration.
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
        raise ConfigurationError("repositories must be an array of at most 500 entries")
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
    all_items = config["repositories"]
    start_index = start_index % len(all_items) if eligible and all_items else 0
    ordered = all_items[start_index:] + all_items[:start_index]
    examined = 0
    for item in ordered:
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
        elif examined >= MAX_PROBES:
            report["status"] = "probe_budget_exhausted"
        else:
            examined += 1
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
                else:
                    report["status"] = "dispatch_failed"
        entries.append(report)
    next_index = (start_index + examined) % len(all_items) if all_items else 0
    return {"generated_at": now, "mode": "execute" if eligible else "dry_run",
            "dispatches": dispatched, "max_dispatches": config["max_dispatches"],
            "examined": examined, "cursor_before": start_index, "cursor_after": next_index,
            "results": entries,
            "note": "Workflow dispatch is not completion, test success, deployment or publication."}


def config_fingerprint(config: dict) -> str:
    """A cursor only applies to the exact, ordered allowlist that created it."""
    rows = json.dumps(config["repositories"], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(rows.encode("utf-8")).hexdigest()


def read_cursor(path: Path, config: dict) -> int:
    try:
        if not path.is_file() or path.stat().st_size > 4096:
            return 0
        saved = json.loads(path.read_text(encoding="utf-8"))
        if saved.get("fingerprint") != config_fingerprint(config):
            return 0
        value = saved.get("next_index")
        if type(value) is int and 0 <= value < len(config["repositories"]):
            return value
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return 0


def write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Private reports can contain private repository names. Never make world-readable.
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    finally:
        if tmp.exists():
            tmp.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bounded opt-in GitHub workflow dispatcher")
    parser.add_argument("--config", type=Path, default=Path("config/portfolio.json"))
    parser.add_argument("--output", type=Path, default=Path("reports/portfolio-run.json"))
    parser.add_argument("--execute", action="store_true", help="Dispatch existing workflows (explicit opt-in)")
    parser.add_argument("--cursor", type=Path, help="Cursor file; default: next to --output")
    parser.add_argument("--validate", action="store_true", help="Validate config without accessing GitHub")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        if args.validate:
            print(f"VALID: {len(config['repositories'])} configured targets, enabled={config['enabled']}")
            return 0
        if args.execute and not config["enabled"]:
            raise ConfigurationError("Execution denied: config.enabled must be true")
        cursor_path = args.cursor or args.output.with_name("portfolio-cursor.json")
        start_index = read_cursor(cursor_path, config) if args.execute else 0
        result = dispatch(config, execute=args.execute, start_index=start_index)
        write_report(args.output, result)
        if args.execute:
            write_report(cursor_path, {"fingerprint": config_fingerprint(config),
                                       "next_index": result["cursor_after"]})
        print(f"{result['mode']}: {len(result['results'])} targets, {result['dispatches']} workflow dispatches")
        if args.execute and any(x["status"].endswith(("failed", "unavailable")) for x in result["results"]):
            return 2
        return 0
    except (ConfigurationError, ValueError, OSError, json.JSONDecodeError) as error:
        print(f"Portfolio runner: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
