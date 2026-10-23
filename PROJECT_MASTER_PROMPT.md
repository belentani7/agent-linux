# PROJECT_MASTER_PROMPT — agent-linux

## Identity and source of truth
**Canonical factory index:** #9 of the frozen 490-repository manifest. **Product:** Agent Linux, an opt-in Ubuntu 24.04/26.04 development workstation and local, bounded portfolio CI dispatcher. This is not a public SaaS, remote agent fleet, or a promise that all repositories have been fixed. Source of truth: `README.md`, `install.sh`, `scripts/`, `config/`, `tests/`, `.github/workflows/`, `Dockerfile` and `.devcontainer/`. Preserve the original full workstation image; optional rootless variants must remain separate.

## Intended audience and behavior
A developer can inspect prerequisites, preview package maintenance, deliberately install/update tools, validate the disabled-by-default workflow allowlist, and optionally activate a bounded systemd **user** timer on a trusted Linux machine. The software must never require making private repositories public, installing paid services, or granting unnecessary GitHub scopes. Credential entry stays on the user's device.

## Preservation and security invariants
- Never run apt upgrades, remote installers, workflow dispatch, or privileged commands during dry-run. Any operation that changes the host must require an explicit action and clear warnings.
- No bulk repository merges, force pushes, deletions, automatic deployment or secrets in logs/reports. Preserve archived repositories and require full offsite encrypted backups with tested restore before destructive operations.
- Pin CI actions by commit, use read-only token scopes unless an operation explicitly requires more, and distinguish configured jobs from actually executed jobs.
- Keep `install.sh` and optional rootless containers separate; avoid replacing the original full environment with a simplified scaffold.
- Existing scripts may still fetch and execute third-party installers; review and pin/verify them before claiming full supply-chain security.

## Engineering and acceptance gates
1. Reconstruct actual files, all relevant open PRs, dependencies, Docker/systemd behavior, default-branch SHA, and deployment scope before editing.
2. Implement real code changes in a non-destructive branch, prefer existing relevant PRs, and document exact safety tradeoffs.
3. Verify `bash -n install.sh scripts/doctor.sh scripts/update.sh scripts/install-user-timer.sh` and `python3 -m unittest discover -s tests -v`; execute real Ubuntu clean-install, upgrade, reinstall, uninstall/rollback and container smoke only on an authorized isolated machine.
4. For frontend components, test keyboard, screen reader, reduced motion and responsive widths when applicable; this repository is primarily CLI/infrastructure.
5. Report actual tool versions, runner steps, test commands, privacy/backup evidence, and deployment SHA; mark unexecuted tests and unavailable devices **BLOCKED**, not green.
6. No release or merge without independent diff review, verified CI or a documented approved equivalent, privacy checks and a rollback path.

## Operational instruction for the next agent
Read the canonical inventory and coordinator issue #4. Confirm #9 remains `agent-linux`. Reconcile PRs #2/#3/#5/#6/#7 before integration; do not overwrite concurrent branches. Fix the remaining unsafe `curl | bash` installation paths and test on a disposable Ubuntu 24.04/26.04 machine. Investigate Actions runs with `runner_id=0` and zero steps as infrastructure failures. If the trusted host or encrypted Drive backup is unavailable, record a truthful blocker and continue to the next active repository within #1–#125.
