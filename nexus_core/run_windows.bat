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

:: 2. VERIFICA PYTHON VIA LAUNCHER (py.exe - mais confiavel no Windows)
py --version >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Python Launcher detectado ^(py.exe^).
    set "PYTHON_EXE=py"
    goto check_venv
)

:: 3. VERIFICA PYTHON DIRETO NO PATH
python --version >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Python do sistema detectado.
    set "PYTHON_EXE=python"
    goto check_venv
)

:: 4. AUTO-BOOTSTRAP (Baixa Python portátil se não encontrar nada)
echo [!] Python nao encontrado no computador.
echo [INFO] Tentando baixar motor portatil automaticamente...
echo.

if not exist "!PORTABLE_DIR!" mkdir "!PORTABLE_DIR!"

echo [1/3] Baixando Python 3.12 portatil (aguarde)...
powershell -Command "& { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object System.Net.WebClient).DownloadFile('!PYTHON_URL!', 'python_temp.zip') }"

if not exist "python_temp.zip" (
    echo [ERRO] Falha ao baixar o Python. Verifique sua internet.
    echo Se voce estiver offline, instale o Python manualmente em python.org
    pause
    exit /b 1
)

echo [2/3] Extraindo arquivos...
powershell -Command "Expand-Archive -Path 'python_temp.zip' -DestinationPath '!PORTABLE_DIR!' -Force"
del python_temp.zip

echo [3/3] Configurando motor portatil...
:: Habilita site-packages no Python Embeddable (nome do arquivo detectado automaticamente)
for %%f in ("!PORTABLE_DIR!\python*._pth") do (
    findstr /c:"import site" "%%f" >nul 2>&1
    if !errorlevel! neq 0 (
        echo import site >> "%%f"
    )
)

:: Instala pip no Python portátil
echo [INFO] Instalando gerenciador de pacotes...
powershell -Command "(New-Object System.Net.WebClient).DownloadFile('https://bootstrap.pypa.io/get-pip.py', 'get-pip.py')"
"!PYTHON_EXE!" get-pip.py --quiet
if exist get-pip.py del get-pip.py

echo [OK] Motor portatil configurado com sucesso.
echo.

:check_venv
:: 5. VERIFICA O AMBIENTE VIRTUAL
echo [INFO] Verificando integridade do ambiente...

if exist "!VENV_DIR!\Scripts\python.exe" (
    :: Testa se o venv ainda funciona (pode quebrar se a pasta mudou de lugar)
    "!VENV_DIR!\Scripts\python.exe" -c "import fastapi" >nul 2>&1
    if %errorlevel% equ 0 (
        echo [OK] Ambiente pronto. Iniciando...
        goto start_app
    ) else (
        echo [AVISO] Ambiente desatualizado ou corrompido. Recriando...
        rmdir /s /q "!VENV_DIR!"
    )
)

:: 6. CRIAÇÃO DO AMBIENTE VIRTUAL
echo [INFO] Preparando modulos pela primeira vez (aguarde)...

"!PYTHON_EXE!" -m venv "!VENV_DIR!"
if %errorlevel% neq 0 (
    echo [ERRO] Falha ao criar ambiente virtual.
    echo Tente rodar como Administrador ou verifique a versao do Python ^(minimo 3.10^).
    pause
    exit /b 1
)

echo [INFO] Instalando requisitos...
"!VENV_DIR!\Scripts\pip.exe" install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo [ERRO] Falha ao instalar componentes. Verifique internet ou VPN.
    pause
    exit /b 1
)

echo [OK] Ambiente configurado com sucesso.
echo.

:start_app
"!VENV_DIR!\Scripts\python.exe" main.py

:fim
if %errorlevel% neq 0 (
    echo.
    echo [INFO] O sistema foi encerrado com erro ^(%errorlevel%^).
    pause
)
