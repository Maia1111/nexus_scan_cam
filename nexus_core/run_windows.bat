@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title Nexus Scan IP Cam

echo ==================================================
echo         NEXUS SCAN - INICIANDO SISTEMA
echo ==================================================
echo.

:: Usa o .venv ja incluido no pacote (zero configuracao)
if exist ".venv\Scripts\python.exe" (
    echo [OK] Ambiente virtual encontrado.
    echo [INFO] Iniciando servidor... o navegador abrira automaticamente.
    echo [INFO] NAO feche esta janela enquanto estiver usando o sistema.
    echo.
    ".venv\Scripts\python.exe" main.py
    goto fim
)

:: Fallback: .venv nao encontrado, cria um novo
echo [CONFIG] Primeira execucao - configurando ambiente...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [ERRO] Python nao encontrado no sistema!
    echo.
    echo Instale o Python 3.10+ em: https://www.python.org/downloads/
    echo IMPORTANTE: marque a opcao "Add Python to PATH" durante a instalacao.
    echo.
    pause
    exit /b 1
)

echo [CONFIG] Criando ambiente virtual (.venv)...
python -m venv .venv
if %errorlevel% neq 0 (
    echo [ERRO] Falha ao criar ambiente virtual.
    pause
    exit /b 1
)

echo [CONFIG] Instalando dependencias (pode demorar alguns minutos)...
".venv\Scripts\pip.exe" install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo [ERRO] Falha ao instalar dependencias.
    pause
    exit /b 1
)

echo [OK] Configuracao concluida!
echo [INFO] Iniciando servidor... o navegador abrira automaticamente.
echo [INFO] NAO feche esta janela enquanto estiver usando o sistema.
echo.
".venv\Scripts\python.exe" main.py

:fim
pause
