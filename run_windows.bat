@echo off
setlocal
cd /d %~dp0
title Nexus Scan IP Cam - Servidor

echo ==================================================
echo         NEXUS SCAN - INICIANDO SISTEMA
echo ==================================================
echo.

:: Verifica se o Python está no PATH
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Python nao encontrado! Por favor, instale o Python 3.8+
    pause
    exit /b
)

:: Cria ambiente virtual se não existir
if not exist venv (
    echo [CONFIG] Criando ambiente virtual (venv)...
    python -m venv venv
)

:: Ativa venv e instala requisitos
echo [CONFIG] Ativando ambiente e verificando dependencias...
call venv\Scripts\activate
pip install -r requirements.txt --quiet

:: Abre o navegador
echo [INFO] Abrindo o painel de controle no navegador...
start http://localhost:8000

:: Inicia o servidor
echo [INFO] Servidor rodando em http://localhost:8000
echo [INFO] Nao feche esta janela enquanto estiver usando o sistema.
echo.
python main.py

pause
