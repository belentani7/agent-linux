#!/usr/bin/env bash
# Autonomous, bounded, read-only portfolio inspection. No code-generation privileges.
set -Eeuo pipefail
if (( EUID == 0 )); then
  echo "Refusing to run as root" >&2; exit 77
fi
command -v gh >/dev/null || { echo "GitHub CLI (gh) is required" >&2; exit 69; }
command -v python3 >/dev/null || { echo "Python 3 is required" >&2; exit 69; }
command -v flock >/dev/null || { echo "flock is required" >&2; exit 69; }
umask 077
data="${PORTFOLIO_DATA_DIR:-${HOME}/.local/share/belentani-portfolio}"
src="${data}/agent-orchestration-machine"
reports="${data}/reports"
mkdir -p "${data}" "${reports}"
exec 9>"${data}/portfolio.lock"
if ! flock -n 9; then
  echo "A portfolio audit is already running; skipping"
  exit 0
fi
if [[ -z "${PORTFOLIO_AUDIT_TOKEN:-${GH_TOKEN:-${GITHUB_TOKEN:-}}}" ]]; then
  echo "Missing read-only portfolio token; cannot enumerate private repositories" >&2
  exit 78
fi
if [[ ! -d "${src}/.git" ]]; then
  gh repo clone belentani7/agent-orchestration-machine "${src}" -- --depth 1
fi
if [[ -n "$(git -C "${src}" status --porcelain)" ]]; then
  echo "Orchestrator checkout is dirty: manual recovery required" >&2; exit 70
fi
git -C "${src}" pull --ff-only --quiet
if [[ ! -f "${src}/scripts/portfolio_audit.py" ]]; then
  echo "Portfolio auditor missing on main: merge the audited PR before activating" >&2; exit 69
fi
export AUDIT_OUTPUT="${reports}"
export PORTFOLIO_OWNER=belentani7
export MAX_REPOS="${MAX_REPOS:-1000}"
export MAX_CONTENT_CHECKS="${MAX_CONTENT_CHECKS:-120}"
cursor="${data}/next_offset"
offset=0
if [[ -f "${cursor}" ]]; then
  offset="$(cat "${cursor}")"
  [[ "${offset}" =~ ^[0-9]{1,9}$ ]] || { echo "Invalid audit cursor" >&2; exit 65; }
fi
export AUDIT_SCAN_OFFSET="${offset}"
python3 "${src}/scripts/portfolio_audit.py"
# Only advance after a successful scan, so a temporary API outage doesn't skip pages.
printf '%s\n' "$((offset + MAX_CONTENT_CHECKS))" > "${cursor}.tmp"
mv -f "${cursor}.tmp" "${cursor}"
printf 'Audit finished; next scan offset=%s; reports=%s\n' "$(cat "${cursor}")" "${reports}"
