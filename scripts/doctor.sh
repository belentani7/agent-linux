#!/usr/bin/env bash
# --strict reports failure when essential coding tools are missing.
set -u
mode=""
if [[ "$#" -gt 0 ]]; then mode="$1"; fi
if [[ "$mode" != "" && "$mode" != "--strict" ]]; then
  echo "Usage: doctor.sh [--strict]" >&2
  exit 2
fi
missing=0
printf '%s\n' "AGENT LINUX / DOCTOR" "===================="
printf 'Account: %s (uid=%s)\n' "$(id -un)" "$(id -u)"

check() {
  local cmd="$1" tier="$2"
  if command -v "$cmd" >/dev/null 2>&1; then
    printf 'OK       %-15s %s\n' "$cmd" "installed"
  else
    printf '%-8s %-15s %s\n' "$tier" "$cmd" "missing"
    if [[ "$tier" == "REQUIRED" ]]; then missing=$((missing + 1)); fi
  fi
}
for cmd in git gh git-lfs python3 node npm jq rg; do check "$cmd" REQUIRED; done
for cmd in mise go rustc pwsh claude openclaw playwright fzf chromium; do check "$cmd" OPTIONAL; done
printf 'Core missing: %s\n' "$missing"
if [[ "$mode" == "--strict" && "$missing" -gt 0 ]]; then
  echo "Strict diagnostic failed: core runtime incomplete" >&2
  exit 1
fi
