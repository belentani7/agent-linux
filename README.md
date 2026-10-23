# Agent Linux

**Entorno Linux reproducible para editar repositorios con IA, automatización y herramientas de desarrollo.**

Agent Linux se construye sobre **Ubuntu 26.04 LTS** y reúne un entorno listo para trabajar en GitHub:

- Git, GitHub CLI, SSH, GPG, ripgrep, fd, fzf, jq, yq, shellcheck y utilidades de compilación.
- Node.js LTS mediante `mise`, Python 3, Go, Rust y Docker/Podman opcional.
- PowerShell 7 desde el repositorio oficial de Microsoft.
- Claude Code mediante el instalador nativo oficial.
- OpenClaw mediante el instalador oficial, sin onboarding automático.
- Chromium y Playwright para navegación y pruebas web.
- Plantillas de configuración para MCP y skills reutilizables.
- Dev Container y Dockerfile para entornos idénticos en local o CI.

> **Importante:** esto es una capa de desarrollo reproducible sobre Ubuntu; no reemplaza la imagen oficial de Ubuntu ni pretende redistribuir sus binarios. Las credenciales de GitHub, Anthropic, OpenClaw y MCP se configuran localmente y nunca se almacenan en el repositorio.

## Inicio rápido

### Instalación en Ubuntu 24.04/26.04

```bash
git clone https://github.com/belentani7/agent-linux.git
cd agent-linux
bash install.sh
```

Cierra y abre la terminal al terminar. Comprueba el entorno:

```bash
bash scripts/doctor.sh
```

### Dev Container

```bash
code --install-extension ms-vscode-remote.remote-containers
code agent-linux
# Reopen in Container
```

O con Docker/Podman:

```bash
docker build -t agent-linux:latest .
docker run --rm -it -v "$PWD:/workspace" -w /workspace agent-linux:latest
```

## Uso diario

```bash
# Autenticar GitHub de forma segura
gh auth login
ssh-keygen -t ed25519 -C "tu-correo"

# Claude Code (primer uso: login interactivo)
claude

# OpenClaw (onboarding cuando estés preparado)
openclaw onboard
openclaw doctor

# PowerShell
pwsh

# Navegador para Playwright
npx playwright install chromium
```

## MCP y skills

`config/mcp.example.json` es una plantilla sin secretos. Copia únicamente los servidores que quieras usar a la configuración de tu cliente MCP y proporciona sus credenciales mediante variables de entorno o el gestor de secretos del cliente.

`skills/` contiene skills locales pequeñas y auditables. Para usar una skill en Claude Code, copia o enlaza la carpeta a `.claude/skills/` dentro del repositorio que estés editando. No se instalan skills de terceros automáticamente: la selección y auditoría de cada skill evita ejecutar código no confiable.

## Seguridad

1. No ejecutes instaladores remotos sin revisar su origen. Este proyecto usa únicamente URLs oficiales de Ubuntu, Microsoft, Anthropic y OpenClaw.
2. No pongas tokens en `.env`, commits, imágenes ni `config/mcp.json`.
3. Trabaja como usuario normal; `sudo` solo se utiliza durante la instalación del sistema.
4. Revisa los permisos de Claude Code/OpenClaw antes de permitir cambios destructivos.
5. Actualizaciones **opt-in**: ejecuta `bash scripts/update.sh` para previsualizar sin cambios. Solo `bash scripts/update.sh --apply` actualiza paquetes Ubuntu (sin `full-upgrade`); `--apply --with-tools` actualiza también herramientas de desarrollo. Revisa respaldos, espacio disponible y la salida antes de aplicar: **no hay rollback automático**.

## Arquitectura

| Capa | Componentes |
|---|---|
| Sistema | Ubuntu 26.04 LTS, bash, zsh, locales, certificados, SSH |
| Código | Git, GitHub CLI, Node LTS, Python, Go, Rust, build-essential |
| IA | Claude Code, OpenClaw, plantillas MCP y skills locales |
| Web | Chromium, Playwright, curl, HTTPie |
| Contenedores | Docker CLI/Engine opcional, Podman, Compose |
| Calidad | shellcheck, shfmt, pre-commit, jq, yq, ripgrep, fd, fzf |

## Fuentes oficiales

- [Ubuntu Releases](https://releases.ubuntu.com/)
- [Instalar PowerShell en Ubuntu](https://learn.microsoft.com/en-us/powershell/scripting/install/install-ubuntu)
- [Claude Code Quickstart](https://code.claude.com/docs/en/quickstart)
- [OpenClaw Install](https://docs.openclaw.ai/install)
- [GitHub CLI manual](https://cli.github.com/manual/)

## Licencia

MIT para los archivos de este proyecto. Cada herramienta instalada conserva su propia licencia.
