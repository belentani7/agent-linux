#!/usr/bin/env bash
set -Eeuo pipefail

# Agent Linux — instalación idempotente para Ubuntu 24.04/26.04.
# Ejecutar como usuario normal; el script solicita sudo cuando corresponde.

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export DEBIAN_FRONTEND=noninteractive

log() { printf '\n\033[1;36m[agent-linux]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; exit 1; }

[[ "$EUID" -ne 0 ]] || fail "Ejecuta como usuario normal, no con sudo."
. /etc/os-release
[[ "${ID:-}" == "ubuntu" ]] || fail "Este instalador requiere Ubuntu."
[[ "${VERSION_ID:-}" == "24.04" || "${VERSION_ID:-}" == "26.04" ]] || fail "Ubuntu 24.04 o 26.04 requerido; detectado ${VERSION_ID:-desconocido}."

log "Actualizando paquetes base"
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  apt-transport-https ca-certificates curl wget gnupg lsb-release software-properties-common \
  git git-lfs gh openssh-client gpg build-essential pkg-config libssl-dev \
  zsh tmux vim nano jq yq ripgrep fd-find fzf bat tree unzip zip rsync shellcheck \
  python3 python3-pip python3-venv python-is-python3 \
  chromium-browser chromium-driver \
  fonts-liberation fonts-noto-color-emoji xdg-utils

git lfs install --skip-repo

log "Instalando PowerShell desde el repositorio oficial de Microsoft"
if ! command -v pwsh >/dev/null 2>&1; then
  tmp_deb="$(mktemp --suffix=.deb)"
  wget -q "https://packages.microsoft.com/config/ubuntu/${VERSION_ID}/packages-microsoft-prod.deb" -O "$tmp_deb"
  sudo dpkg -i "$tmp_deb"
  rm -f "$tmp_deb"
  sudo apt-get update
  sudo apt-get install -y powershell
fi

log "Instalando mise para runtimes reproducibles"
if ! command -v mise >/dev/null 2>&1; then
  curl https://mise.run | sh
fi
export PATH="$HOME/.local/bin:$PATH"
if ! grep -q 'mise activate' "$HOME/.bashrc" 2>/dev/null; then
  printf '\n# Agent Linux\nexport PATH="$HOME/.local/bin:$PATH"\neval "$(mise activate bash)"\n' >> "$HOME/.bashrc"
fi
if ! grep -q 'mise activate' "$HOME/.zshrc" 2>/dev/null; then
  printf '\n# Agent Linux\nexport PATH="$HOME/.local/bin:$PATH"\neval "$(mise activate zsh)"\n' >> "$HOME/.zshrc"
fi
mise settings set experimental true >/dev/null 2>&1 || true
mise use --global node@lts
mise use --global python@3.13
mise use --global go@latest
mise use --global rust@stable

log "Activando Corepack y herramientas Node"
export PATH="$HOME/.local/share/mise/installs/node/lts/bin:$PATH"
corepack enable || true
npm install --global playwright npm-check-updates prettier eslint typescript tsx pnpm

log "Instalando Claude Code mediante el instalador nativo oficial"
if ! command -v claude >/dev/null 2>&1; then
  curl -fsSL https://claude.ai/install.sh | bash
fi

log "Instalando OpenClaw mediante el instalador oficial, sin onboarding"
if ! command -v openclaw >/dev/null 2>&1; then
  curl -fsSL https://openclaw.ai/install.sh | bash -s -- --no-onboard
fi

log "Configurando helpers locales"
mkdir -p "$HOME/.config/agent-linux" "$HOME/.local/bin"
install -m 0755 "$REPO_ROOT/scripts/agent-status" "$HOME/.local/bin/agent-status"

log "Instalación terminada. Abre una nueva terminal y ejecuta: bash scripts/doctor.sh"
