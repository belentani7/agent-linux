# Portfolio Worker — Ubuntu, non-root

This feature adds a **persistent, scheduled read-only controller** to the existing `agent-linux` repository. It is not yet an AI coding agent and does not deploy websites or change GitHub repositories. It calls the inventory script in `belentani7/agent-orchestration-machine` once that script has been merged to `main`. Each cycle inspects a bounded batch of repository root files, rotating the offset after success, and persists JSON/Markdown reports.

## Activation (Ubuntu systemd user)

```bash
# As an ordinary user (never sudo):
bash scripts/install-portfolio-runner.sh
gh auth login
# Edit ~/.config/belentani/portfolio.env and configure
# PORTFOLIO_AUDIT_TOKEN=<read-only fine-grained GitHub token>
systemctl --user enable --now belentani-portfolio.timer
systemctl --user start belentani-portfolio.service
systemctl --user status belentani-portfolio.service
journalctl --user -u belentani-portfolio.service -n 100
```

A read-only personal access token is needed for the private owner repositories. Scope it to *Contents: Read* and metadata on only the intended repos. Keep the env file mode 0600; do not put tokens in Git, log outputs or command arguments. With the GitHub CLI credential helper configured, authenticated clone and fast-forward pulls can work. **Do not enable the timer until the pending orchestration PR has been merged.**

For execution after logout on a dedicated server, an administrator may enable user lingering after assessing server security: `sudo loginctl enable-linger "$USER"`. No systemd service is created under root. Running untrusted repository code or models with filesystem/secret access remains forbidden in this phase.

## Safety and behavior

- One-shot task with a 1h upper bound; systemd timer, *not* an unbounded shell loop.
- A `flock` guard prevents concurrent runs.
- Runs without root privilege; systemd read-only home/system protection with limited state writes.
- Outputs live at `~/.local/share/belentani-portfolio/reports`.
- `next_offset` rotates batch coverage, keeping previous offset when audit fails.
- Never executes code from the inventoried projects.
- Does not declare projects complete, change visibility, create/merge PRs, edit DNS, or deploy.
- This component is phase 1, an actual durable Linux scheduling adapter; phase 2 requires a restricted coding worker, reliable CI, preview environments, budgets and verified release gates.

## Validation

```bash
bash -n scripts/portfolio-cycle.sh scripts/install-portfolio-runner.sh
command -v shellcheck && shellcheck scripts/portfolio-cycle.sh scripts/install-portfolio-runner.sh
```

## Troubleshooting

- `Missing read-only portfolio token`: set the env file securely.
- `Portfolio auditor missing on main`: the upstream PR is not merged.
- GitHub Actions stalled in `queued`: this local scheduler avoids dependence on hosted runners **once a Linux device is connected**, but it is not hosted or running simply because these files exist.
