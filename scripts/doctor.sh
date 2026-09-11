#!/usr/bin/env bash
set -u
printf '%s\n' 'Agent Linux doctor'
printf '%s\n' '================='
check() {
  if command -v "$1" >/dev/null 2>&1; then
    case "$1" in
      go) ver="$(go version 2>/dev/null)" ;;
      *)  ver="$($1 --version 2>/dev/null | head -n1)" ;;
    esac
    printf 'OK   %-14s %s\n' "$1" "$ver"
  else
    printf 'MISS %-14s %s\n' "$1" 'instala ejecutando ./install.sh'
  fi
}
for cmd in git gh pwsh node npm python3 go rustc claude openclaw mise jq rg fzf; do check "$cmd"; done

# Chromium usable: el paquete apt es snap-only; Playwright provee uno headless.
if command -v playwright >/dev/null 2>&1 && ls "${HOME}/.cache/ms-playwright/"chromium* >/dev/null 2>&1; then
  printf 'OK   %-14s %s\n' 'chromium' 'Playwright headless (~/.cache/ms-playwright)'
elif command -v chromium >/dev/null 2>&1; then
  printf 'OK   %-14s %s\n' 'chromium' "$(chromium --version 2>/dev/null | head -n1)"
else
  printf 'MISS %-14s %s\n' 'chromium' 'ejecuta: npx playwright install --with-deps chromium'
fi
printf '\nConsejos:\n'
printf '%s\n' '  gh auth status        # comprobar GitHub'
printf '%s\n' '  claude                # login de Claude Code en primer uso'
printf '%s\n' '  openclaw doctor       # comprobar OpenClaw'
printf '%s\n' '  npx playwright install chromium'
