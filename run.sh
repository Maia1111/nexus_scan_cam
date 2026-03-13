#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# Cria venv se não existir
if [[ ! -d ".venv" ]]; then
  echo "Criando ambiente virtual..."
  python3 -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
  echo "Dependências instaladas."
fi

echo "Iniciando Scanner de Câmeras IP em http://localhost:8000"
.venv/bin/python main.py
