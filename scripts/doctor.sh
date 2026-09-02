#!/usr/bin/env bash
set -u
printf '%s\n' 'Agent Linux doctor'
printf '%s\n' '================='
check() { if command -v "$1" >/dev/null 2>&1; then printf 'OK   %-14s %s\n' "$1" "$($1 --version 2>/dev/null | head -n1)"; else printf 'MISS %-14s %s\n' "$1" 'instala ejecutando ./install.sh'; fi; }
for cmd in git gh pwsh node npm python3 go rustc claude openclaw chromium mise jq rg fzf; do check "$cmd"; done
printf '\nConsejos:\n'
printf '%s\n' '  gh auth status        # comprobar GitHub'
printf '%s\n' '  claude                # login de Claude Code en primer uso'
printf '%s\n' '  openclaw doctor       # comprobar OpenClaw'
printf '%s\n' '  npx playwright install chromium'
