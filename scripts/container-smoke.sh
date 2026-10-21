#!/usr/bin/env bash
set -Eeuo pipefail
if [[ "$(id -u)" == "0" ]]; then echo "ERROR: root runtime" >&2; exit 1; fi
for tool in bash git gh python3 node npm jq rg git-lfs; do
  command -v "$tool" >/dev/null 2>&1 || { echo "MISSING required runtime: $tool" >&2; exit 1; }
done
[[ -d "$HOME" && -w "$HOME" ]] || { echo "HOME is not writable" >&2; exit 1; }
printf 'Agent Linux core OK, UID=%s\n' "$(id -u)"
python3 --version
node --version
git --version
