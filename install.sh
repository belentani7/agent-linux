#!/usr/bin/env bash
set -Eeuo pipefail

# Agent Linux — instalación idempotente para Ubuntu 24.04/26.04.
# Ejecutar como usuario normal; el script solicita sudo cuando corresponde.

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export DEBIAN_FRONTEND=noninteractive

# Mantener apt totalmente no interactivo: conservar la configuración existente
# ante conflictos de ficheros y reintentar descargas puntuales de red.
APT_OPTS=(-o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold -o Acquire::Retries=3)

log() { printf '\n\033[1;36m[agent-linux]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; exit 1; }

if apt-cache show chromium >/dev/null 2>&1; then
  BROWSER_PACKAGES=(chromium chromium-driver)
else
  BROWSER_PACKAGES=(chromium-browser chromium-driver)
fi

[[ "$EUID" -ne 0 ]] || fail "Ejecuta como usuario normal, no con sudo."
. /etc/os-release
[[ "${ID:-}" == "ubuntu" ]] || fail "Este instalador requiere Ubuntu."
[[ "${VERSION_ID:-}" == "24.04" || "${VERSION_ID:-}" == "26.04" ]] || fail "Ubuntu 24.04 o 26.04 requerido; detectado ${VERSION_ID:-desconocido}."

log "Actualizando paquetes base"
sudo apt-get update
sudo apt-get install -y --no-install-recommends "${APT_OPTS[@]}" \
  apt-transport-https ca-certificates curl wget gnupg lsb-release software-properties-common \
  git git-lfs gh openssh-client gpg build-essential pkg-config libssl-dev \
  zsh tmux vim nano jq yq ripgrep fd-find fzf bat tree unzip zip rsync shellcheck \
  python3 python3-pip python3-venv python-is-python3 \
  "${BROWSER_PACKAGES[@]}" \
  fonts-liberation fonts-noto-color-emoji xdg-utils

git lfs install --skip-repo

log "Instalando PowerShell desde el repositorio oficial de Microsoft"
if ! command -v pwsh >/dev/null 2>&1; then
  tmp_deb="$(mktemp --suffix=.deb)"
  wget -q "https://packages.microsoft.com/config/ubuntu/${VERSION_ID}/packages-microsoft-prod.deb" -O "$tmp_deb"
  sudo dpkg -i "$tmp_deb" || sudo apt-get install -f -y "${APT_OPTS[@]}"
  rm -f "$tmp_deb"
  sudo apt-get update
  sudo apt-get install -y "${APT_OPTS[@]}" powershell
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
# corepack ya provee los shims de pnpm/yarn; evitamos colisiones EEXIST
# instalando el resto de utilidades Node con npm global.
corepack enable || true
npm install --global playwright npm-check-updates prettier eslint typescript tsx

log "Instalando Chromium de Playwright (navegador headless usable en contenedores)"
# El paquete apt `chromium` en Ubuntu es transitional -> snap y no arranca en
# contenedores sin snapd; Playwright provee un Chromium autocontenido y headless.
npx --yes playwright install --with-deps chromium || \
  log "Aviso: no se pudo instalar el Chromium de Playwright; reintenta con 'npx playwright install --with-deps chromium'"

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
