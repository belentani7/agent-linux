#!/usr/bin/env bash
# Install non-root systemd --user timer for periodic portfolio auditing.
set -Eeuo pipefail
if (( EUID == 0 )); then
  echo "Do not install as root. Use an unprivileged Linux user." >&2; exit 77
fi
base="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bin_dir="${HOME}/.local/bin"
unit_dir="${HOME}/.config/systemd/user"
mkdir -p "${bin_dir}" "${unit_dir}" "${HOME}/.config/belentani" "${HOME}/.local/share/belentani-portfolio"
install -m 0755 "${base}/scripts/portfolio-cycle.sh" "${bin_dir}/belentani-portfolio-cycle"
install -m 0644 "${base}/systemd/belentani-portfolio.service" "${unit_dir}/belentani-portfolio.service"
install -m 0644 "${base}/systemd/belentani-portfolio.timer" "${unit_dir}/belentani-portfolio.timer"
if [[ ! -f "${HOME}/.config/belentani/portfolio.env" ]]; then
  ( umask 077; cat > "${HOME}/.config/belentani/portfolio.env" <<'EOF'
# Supply a fine-grained read-only GitHub token with access to intended repos.
# PORTFOLIO_AUDIT_TOKEN=github_pat_REPLACE_ME
MAX_CONTENT_CHECKS=120
EOF
  )
fi
chmod 600 "${HOME}/.config/belentani/portfolio.env"
systemctl --user daemon-reload
case "${1:-}" in
  --enable)
    systemctl --user enable --now belentani-portfolio.timer
    echo "Timer enabled; check with: systemctl --user list-timers belentani-portfolio.timer"
    ;;
  "")
    echo "Installed, not enabled. Set read-only token in ~/.config/belentani/portfolio.env"
    echo "Then: systemctl --user enable --now belentani-portfolio.timer"
    ;;
  *)
    echo "Usage: bash scripts/install-portfolio-runner.sh [--enable]" >&2
    exit 64
    ;;
esac
