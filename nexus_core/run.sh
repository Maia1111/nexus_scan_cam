#!/usr/bin/env bash
# Nexus Scan — Launcher Linux
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo ""
echo "========================================"
echo "   NEXUS SCAN - INICIANDO SISTEMA"
echo "========================================"
echo ""

# Usa .venv incluido no pacote, ou cria um novo
if [[ -f ".venv/bin/python" ]]; then
    echo "[OK] Ambiente virtual encontrado."
    PYTHON=".venv/bin/python"
else
    echo "[CONFIG] Primeira execucao — configurando ambiente..."

    if ! command -v python3 &>/dev/null; then
        echo "[ERRO] Python3 nao encontrado. Instale com:"
        echo "       sudo apt install python3 python3-venv  (Debian/Ubuntu)"
        echo "       sudo dnf install python3               (Fedora)"
        exit 1
    fi

    python3 -m venv .venv
    .venv/bin/pip install -q --upgrade pip
    .venv/bin/pip install -q -r requirements.txt
    echo "[OK] Dependencias instaladas."
    PYTHON=".venv/bin/python"
fi

echo "[INFO] Iniciando servidor... o navegador abrira automaticamente."
echo "[INFO] Pressione Ctrl+C para encerrar."
echo ""

exec "$PYTHON" main.py
