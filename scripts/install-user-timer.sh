#!/usr/bin/env bash
# Install a finite systemd USER timer. Nothing runs as root.
set -Eeuo pipefail
usage() {
  echo "Usage: $0 --install-dry-run | --enable-dispatch | --disable | --status"
  echo "  --install-dry-run  Periodic offline config/report validation; no GitHub calls"
  echo "  --enable-dispatch  Explicitly dispatch existing allowlisted CI workflows"
  echo "  --disable          Stop the user timer (preserve config and reports)"
}
action="\${1:-}"
if [[ ! "$action" =~ ^(--install-dry-run|--enable-dispatch|--disable|--status)$ ]]; then usage >&2; exit 2; fi
command -v systemctl >/dev/null || { echo "systemd user service not available" >&2; exit 2; }
if [[ "$EUID" -eq 0 ]]; then echo "Do not use sudo or root" >&2; exit 2; fi
if [[ "$action" == "--status" ]]; then systemctl --user status agent-linux-portfolio.timer --no-pager; exit $?; fi
if [[ "$action" == "--disable" ]]; then systemctl --user disable --now agent-linux-portfolio.timer; exit $?; fi
root="$(cd -- "$(dirname -- "\${BASH_SOURCE[0]}")/.." && pwd)"
app="\${HOME}/.local/share/agent-linux"
conf="\${HOME}/.config/agent-linux"
reports="\${HOME}/.local/state/agent-linux"
units="\${HOME}/.config/systemd/user"
install -d -m 0700 "$app" "$conf" "$reports" "$units"
install -m 0755 "$root/scripts/portfolio_runner.py" "$app/portfolio_runner.py"
if [[ ! -f "$conf/portfolio.json" ]]; then
  install -m 0600 "$root/config/portfolio.example.json" "$conf/portfolio.json"
fi
args=""
if [[ "$action" == "--enable-dispatch" ]]; then
  command -v gh >/dev/null || { echo "gh CLI missing" >&2; exit 2; }
  gh auth status >/dev/null 2>&1 || { echo "GitHub CLI not authenticated" >&2; exit 2; }
  python3 - "$conf/portfolio.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as source:
    config = json.load(source)
if config.get("enabled") is not True or not config.get("repositories"):
    raise SystemExit("Refusing dispatch: set enabled=true and configure reviewed workflows first")
PY
  "$app/portfolio_runner.py" --validate --config "$conf/portfolio.json" || exit 2
  args=" --execute"
fi
cat > "$units/agent-linux-portfolio.service" <<UNIT
[Unit]
Description=Agent Linux finite portfolio CI runner
Documentation=https://github.com/belentani7/agent-linux/blob/main/docs/PORTFOLIO_RUNNER.md
[Service]
Type=oneshot
WorkingDirectory=%h
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
TimeoutStartSec=12min
ExecStart=/usr/bin/python3 %h/.local/share/agent-linux/portfolio_runner.py --config %h/.config/agent-linux/portfolio.json --output %h/.local/state/agent-linux/report.json$args
UNIT
cat > "$units/agent-linux-portfolio.timer" <<'UNIT'
[Unit]
Description=Run a bounded existing-repo CI check every six hours
[Timer]
OnBootSec=15min
OnUnitActiveSec=6h
RandomizedDelaySec=20min
Persistent=true
Unit=agent-linux-portfolio.service
[Install]
WantedBy=timers.target
UNIT
chmod 0600 "$units/agent-linux-portfolio.service" "$units/agent-linux-portfolio.timer"
systemctl --user daemon-reload
systemctl --user enable --now agent-linux-portfolio.timer
echo "Enabled $action timer (six-hour interval); config: $conf/portfolio.json"
echo "Disable: systemctl --user disable --now agent-linux-portfolio.timer"
