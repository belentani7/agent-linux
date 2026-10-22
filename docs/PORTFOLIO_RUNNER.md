# Agent Linux — bounded portfolio runner

The runner safely **verifies and dispatches existing GitHub workflows**. It does **not** autonomously claim a product is finished or publicly deploy anything. Dispatching a workflow is not proof that it passed. Production releases need checked builds, E2E acceptance, real content and preview smoke tests.

## Security design

- Disabled by default. Empty allowlist in `config/portfolio.example.json`.
- Strict JSON schema (v1); at most 50 targets, at most 5 dispatches per invocation, all target identifiers validated.
- Persistent round-robin cursor prevents the first few allowlisted repositories from monopolizing each run. The private state file resets safely when the allowlist changes.
- Repository archive state and selected workflow are verified via GitHub CLI before dispatch.
- No scripts fetched and executed, no `shell=True`, no PR merging, no cloning, no force pushing, no repo creation, no permission or visibility changes.
- Never stores or prints tokens. Reports live on the user's machine with mode `0600`. Keep `reports/` untracked.
- Failed GitHub checks never become automatic success. Results distinguish `dispatched_unverified` from a successful release.
- Designed for periodic local Linux execution under the user's account, never as an unrestricted unattended agent.

## 1. Start locally

```bash
mkdir -p config
cp -n config/portfolio.example.json config/portfolio.json
python3 scripts/portfolio_runner.py --validate
python3 scripts/portfolio_runner.py
python3 -m unittest discover -s tests -p test_portfolio_runner.py -v
```

The default invocation validates and writes a local, private dry-run report. No GitHub request is made. Configure ONLY repositories that you own or are explicitly authorized to manage. The target CI workflows must already exist and be manually reviewed; they must support `workflow_dispatch`.

## 2. Example opt-in

Add existing targets to `config/portfolio.json`:

```json
{
  "version": 1,
  "enabled": true,
  "max_dispatches": 2,
  "repositories": [
    {"repository": "YOUR-OWNER/YOUR-EXISTING-REPO", "workflow": "verify.yml", "ref": "main"}
  ]
}
```

The example is illustrative. Do not use it until the repo and workflow have been verified.

```bash
gh auth login
python3 scripts/portfolio_runner.py --execute --config config/portfolio.json
```

Each execution has bounded work. With multiple targets and a small per-run budget, the successful dispatch cursor rotates between subsequent executions. By default it is stored in `reports/portfolio-state.json`; the systemd timer stores it in `~/.local/state/agent-linux/rotation.json`. Dry runs neither consult nor modify the cursor. Validate status separately with `gh run list --repo OWNER/REPO` and inspect the exact workflow run and deployed URL. Never infer success from a dispatch response.

## 3. Optional Linux user timer

For the user's choice of periodic, bounded verification, use the timer setup described in `scripts/install-user-timer.sh`. It **always runs dry-run checks unless explicitly opted into execution**. The service never runs as root. It can be disabled with `systemctl --user disable --now agent-linux-portfolio.timer`.

## Limitations

The runner is a control-plane trigger, not an AI coder, a secret store, a code executor, a browser tester or a deployment platform. It cannot complete missing course content, repair code, or ensure tests and releases pass automatically; those require purpose-specific implementations and verified CI. A run is always finite.
