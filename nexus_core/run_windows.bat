@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title Nexus Scan IP Cam - Launcher

echo ==================================================
echo         NEXUS SCAN - INICIANDO SISTEMA
echo ==================================================
echo.

:: --- CONFIGURAÇÃO ---
set "PORTABLE_DIR=%~dp0python_bin"
set "PYTHON_EXE=%PORTABLE_DIR%\python.exe"
set "VENV_DIR=%~dp0.venv"
set "PYTHON_URL=https://www.python.org/ftp/python/3.12.7/python-3.12.7-embed-amd64.zip"

:: 1. VERIFICA SE EXISTE PYTHON PORTÁTIL (Prioridade Máxima)
if exist "!PYTHON_EXE!" (
    echo [OK] Motor portatil detectado em !PORTABLE_DIR!
    goto check_venv
)

:: 2. VERIFICA SE EXISTE PYTHON NO SISTEMA
python --version >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Python do sistema detectado.
    set "PYTHON_EXE=python"
    goto check_venv
)

:: 3. AUTO-BOOTSTRAP (Baixa Python se não encontrar nada)
echo [!] Python nao encontrado no computador.
echo [INFO] Tentando baixar motor portatil automaticamente...
echo.

if not exist "!PORTABLE_DIR!" mkdir "!PORTABLE_DIR!"

echo [1/3] Baixando Python (aguarde)...
powershell -Command "& { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object System.Net.WebClient).DownloadFile('!PYTHON_URL!', 'python_temp.zip') }"

if not exist "python_temp.zip" (
    echo [ERRO] Falha ao baixar o Python. Verifique sua internet.
    echo Se voce estiver offline, copie a pasta 'python_bin' de outro computador.
    pause
    exit /b 1
)

echo [2/3] Extraindo arquivos...
powershell -Command "Expand-Archive -Path 'python_temp.zip' -DestinationPath '!PORTABLE_DIR!' -Force"
del python_temp.zip

echo [3/3] Configurando motor...
:: Habilita o carregamento de bibliotecas externas no Python Embeddable
set "PTH_FILE="
for %%f in ("!PORTABLE_DIR!\python*._pth") do set "PTH_FILE=%%f"
if defined PTH_FILE (
    echo. >> "!PORTABLE_DIR!\python312._pth"
    echo import site >> "!PORTABLE_DIR!\python312._pth"
)

:: Baixa get-pip para o novo Python
echo [INFO] Instalando gerenciador de pacotes...
powershell -Command "(New-Object System.Net.WebClient).DownloadFile('https://bootstrap.pypa.io/get-pip.py', 'get-pip.py')"
"!PYTHON_EXE!" get-pip.py --quiet
del get-pip.py

echo [OK] Motor portatil configurado com sucesso.
echo.

:check_venv
:: 4. VERIFICA O AMBIENTE VIRTUAL
echo [INFO] Verificando integridade do ambiente...

:: Se o .venv existe, verificamos se o caminho bate (evita erro de mudança de pasta)
if exist "!VENV_DIR!\Scripts\python.exe" (
    :: Tenta rodar um comando simples. Se falhar, o .venv está quebrado (ex: mudou de pasta)
    "!VENV_DIR!\Scripts\python.exe" -c "import os" >nul 2>&1
    if %errorlevel% equ 0 (
        echo [OK] Ambiente pronto. Iniciando...
        "!VENV_DIR!\Scripts\python.exe" main.py
        goto fim
    ) else (
        echo [AVISO] Pasta do projeto mudou de lugar. Atualizando ambiente...
        rmdir /s /q "!VENV_DIR!"
    )
)

:: 5. CRIAÇÃO/ATUALIZAÇÃO DO AMBIENTE
echo [INFO] Preparando módulos (isso ocorre apenas na primeira vez)...

"!PYTHON_EXE!" -m venv "!VENV_DIR!"
if %errorlevel% neq 0 (
    echo [ERRO] Falha ao criar ambiente virtual. Tente rodar como Administrador.
    pause
    exit /b 1
)

echo [INFO] Instalando requisitos...
"!VENV_DIR!\Scripts\pip.exe" install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo [ERRO] Falha ao instalar componentes. Verifique sua internet ou VPN.
    pause
    exit /b 1
)

echo [OK] Sistema atualizado.
echo.
"!VENV_DIR!\Scripts\python.exe" main.py

:fim
if %errorlevel% neq 0 (
    echo.
    echo [INFO] O sistema foi encerrado com erro (%errorlevel%).
    pause
)
