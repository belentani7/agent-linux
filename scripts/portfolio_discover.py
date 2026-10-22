#!/usr/bin/env python3
"""Prepare a disabled 500-repository workflow allowlist from the owner's GitHub account.

This is configuration generation, not a repository edit or background execution.
Uses the local user's existing GitHub CLI permissions; never reads tokens or
calls user-controlled hooks and never enables the resulting configuration.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

from portfolio_runner import (
    ConfigurationError, MAX_REPOS, REF, WORKFLOW, validate, write_report
)

OWNER = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37})$")
MAX_SOURCE_BYTES = 2_000_000


def build_manifest(lines: str, owner: str, workflow: str, max_dispatches: int = 5) -> tuple[dict, dict]:
    if not OWNER.fullmatch(owner) or not WORKFLOW.fullmatch(workflow):
        raise ConfigurationError("Invalid owner or workflow")
    if len(lines.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise ConfigurationError("GitHub repository listing is unexpectedly large")
    rows: dict[str, tuple[str, str]] = {}
    archived = 0
    item_branch: dict[str, str] = {}
    for index, raw in enumerate(lines.splitlines()):
        if not raw.strip():
            continue
        try:
            item = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ConfigurationError(f"Invalid GitHub listing line {index + 1}") from error
        if not isinstance(item, dict):
            raise ConfigurationError("GitHub listing contains an invalid row")
        full_name = item.get("full_name")
        ref = item.get("default_branch")
        if not isinstance(full_name, str) or not isinstance(ref, str):
            raise ConfigurationError("GitHub listing lacks repository identity or default branch")
        parts = full_name.split("/")
        if len(parts) != 2 or parts[0].casefold() != owner.casefold():
            continue
        if item.get("archived") is True:
            archived += 1
            continue
        if item.get("archived") is not False:
            raise ConfigurationError("Missing archived state; refusing to guess")
        if not REF.fullmatch(ref) or ".." in ref or "//" in ref:
            raise ConfigurationError(f"Unsafe default branch for {full_name}")
        key = full_name.casefold()
        if key in rows:
            raise ConfigurationError(f"Duplicate repository in listing: {full_name}")
        pushed_at = item.get("pushed_at")
        if pushed_at is not None and not isinstance(pushed_at, str):
            raise ConfigurationError("Unexpected push timestamp type")
        rows[key] = (full_name, pushed_at or "")
        # Preserve the exact branch associated with each validated repository.
        item_branch[key] = ref
    ordered = sorted(rows.items(), key=lambda entry: (entry[1][1], entry[0]))
    if len(ordered) > MAX_REPOS:
        raise ConfigurationError(f"More than {MAX_REPOS} active repositories; split allowlists")
    config = validate({
        "version": 1,
        "enabled": False,
        "max_dispatches": max_dispatches,
        "repositories": [
            {"repository": full_name, "workflow": workflow, "ref": item_branch[key]}
            for key, (full_name, _) in ordered
        ],
    })
    return config, {
        "active": len(ordered),
        "archived_excluded": archived,
        "execution_enabled": False,
        "order": "oldest last-push first",
        "notice": "Workflow candidates must be reviewed. No GitHub action was dispatched.",
    }


def fetch_owned_repos() -> str:
    # gh operates under the user's existing authentication; no token is printed.
    # Query the authenticated user's owner repos, including private ones.
    try:
        result = subprocess.run(
            [
                "gh", "api", "--paginate",
                "--jq", ".[] | {full_name, archived, default_branch, pushed_at}",
                "user/repos?per_page=100&affiliation=owner",
            ],
            capture_output=True, text=True, timeout=120, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ConfigurationError("GitHub CLI unavailable or timed out") from error
    if result.returncode != 0:
        raise ConfigurationError("GitHub repository listing failed (verify gh auth and permissions)")
    return result.stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare an inactive GitHub owner allowlist")
    parser.add_argument("--owner", required=True)
    parser.add_argument("--workflow", default="ci.yml")
    parser.add_argument("--output", type=Path, default=Path("config/portfolio.generated.json"))
    parser.add_argument("--replace", action="store_true", help="Overwrite only the explicitly named output file")
    args = parser.parse_args(argv)
    try:
        if args.output.exists() and not args.replace:
            raise ConfigurationError("Output already exists; provide --replace to overwrite")
        config, stats = build_manifest(fetch_owned_repos(), args.owner, args.workflow)
        write_report(args.output, config)
        print(f"Prepared {stats['active']} active repos; excluded {stats['archived_excluded']} archived. "
              f"enabled=false; file={args.output}")
        return 0
    except (ConfigurationError, ValueError, OSError) as error:
        print(f"Discovery refused: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
