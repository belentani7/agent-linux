#!/usr/bin/env bash
set -Eeuo pipefail
export DEBIAN_FRONTEND=noninteractive
APT_OPTS=(-o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold -o Acquire::Retries=3)
sudo apt-get update
sudo apt-get full-upgrade -y "${APT_OPTS[@]}"
if command -v mise >/dev/null 2>&1; then
  mise upgrade || true
fi
if command -v npm >/dev/null 2>&1; then
  npm update --global || true
fi
if command -v claude >/dev/null 2>&1; then claude update || true; fi
if command -v openclaw >/dev/null 2>&1; then openclaw update --channel stable || true; fi
printf '\nActualización terminada. Ejecuta scripts/doctor.sh para comprobar el entorno.\n'
