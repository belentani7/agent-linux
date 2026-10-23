#!/usr/bin/env bash
set -Eeuo pipefail

# Opt-in Ubuntu maintenance. No package operations occur without --apply.
usage() {
  cat <<'EOF'
Usage: bash scripts/update.sh [--dry-run | --apply [--with-tools]]
  --dry-run     Show the update plan without sudo, downloads or writes (default).
  --apply       Update Ubuntu package lists and upgrade installed packages.
  --with-tools  With --apply, also update mise/npm/Claude/OpenClaw when installed.
  --help        Show this help.

This script never performs apt full-upgrade or removes packages intentionally.
Review backups and available disk space before --apply; rollback is not automatic.
EOF
}

mode=dry-run
with_tools=false
mode_seen=false
for arg in "$@"; do
  case "$arg" in
    --dry-run|--apply)
      if [[ "$mode_seen" == true ]]; then
        printf 'Choose exactly one of --dry-run and --apply.\n' >&2
        exit 2
      fi
      mode_seen=true
      mode="${arg#--}"
      ;;
    --with-tools) with_tools=true ;;
    --help|-h) usage; exit 0 ;;
    *) printf 'Unknown argument: %s\n' "$arg" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ "$with_tools" == true && "$mode" != apply ]]; then
  printf '%s\n' '--with-tools requires --apply.' >&2
  exit 2
fi

if [[ "$mode" == dry-run ]]; then
  printf '%s\n' '[dry-run] Ubuntu maintenance plan (nothing executed):' \
    '  sudo apt-get update' \
    '  sudo apt-get upgrade -y (preserve installed packages; no full-upgrade)' \
    '  Optional tool updates: skipped (use --apply --with-tools).' \
    '  No files, packages, credentials or timers were modified.'
  exit 0
fi

if [[ "$EUID" -eq 0 ]]; then
  printf '%s\n' 'Run as a regular user, without sudo.' >&2
  exit 2
fi
if [[ ! -r /etc/os-release ]]; then
  printf '%s\n' 'Cannot identify the operating system.' >&2
  exit 2
fi
# shellcheck disable=SC1091
. /etc/os-release
if [[ "${ID:-}" != ubuntu || ( "${VERSION_ID:-}" != 24.04 && "${VERSION_ID:-}" != 26.04 ) ]]; then
  printf 'Unsupported OS: %s %s (Ubuntu 24.04/26.04 required).\n' "${ID:-unknown}" "${VERSION_ID:-unknown}" >&2
  exit 2
fi
if ! command -v sudo >/dev/null 2>&1; then
  printf '%s\n' 'sudo is required for --apply.' >&2
  exit 2
fi

export DEBIAN_FRONTEND=noninteractive
APT_OPTS=(-o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold -o Acquire::Retries=3)
sudo -v
sudo apt-get update
sudo apt-get upgrade -y "${APT_OPTS[@]}"

if [[ "$with_tools" == true ]]; then
  if command -v mise >/dev/null 2>&1; then mise upgrade; fi
  if command -v npm >/dev/null 2>&1; then npm update --global; fi
  if command -v claude >/dev/null 2>&1; then claude update; fi
  if command -v openclaw >/dev/null 2>&1; then openclaw update --channel stable; fi
fi
printf '%s\n' 'Update commands completed. Run bash scripts/doctor.sh and inspect any held packages.'
