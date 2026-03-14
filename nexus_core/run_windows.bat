@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title Nexus Scan IP Cam

echo ==================================================
echo         NEXUS SCAN - INICIANDO SISTEMA
echo ==================================================
echo.

:: 1. Tenta usar o ambiente virtual local se ele ja existir
if exist ".venv\Scripts\python.exe" (
    echo [OK] Ambiente configurado detectado.
    echo [INFO] Abrindo o sistema...
    echo.
    ".venv\Scripts\python.exe" main.py
    goto fim
)

:: 2. Se nao tem .venv, precisamos do Python para criar um
echo [INFO] Preparando o sistema para o primeiro uso...
echo [INFO] Verificando requisitos de software...

set "PYTHON_EXE="

:: Procura 'python' no PATH
python --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_EXE=python"
    goto found_python
)

:: Procura pelo Launcher 'py'
py --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_EXE=py"
    goto found_python
)

:: Procura em caminhos comuns do Windows (AppData)
for /d %%d in ("%USERPROFILE%\AppData\Local\Programs\Python\Python*") do (
    if exist "%%d\python.exe" (
        set "PYTHON_EXE=%%d\python.exe"
        goto found_python
    )
)

:: Procura em C:\Python
for /d %%d in ("C:\Python*") do (
    if exist "%%d\python.exe" (
        set "PYTHON_EXE=%%d\python.exe"
        goto found_python
    )
)

:: Procura em Program Files
for /d %%d in ("C:\Program Files\Python*") do (
    if exist "%%d\python.exe" (
        set "PYTHON_EXE=%%d\python.exe"
        goto found_python
    )
)

:not_found
echo.
echo [!] OPS! O PYTHON NÃO FOI ENCONTRADO.
echo.
echo Para o Nexus Scan funcionar, voce precisa do Python instalado.
echo.
echo COMO RESOLVER:
echo 1. Baixe o instalador aqui: https://www.python.org/ftp/python/3.12.2/python-3.12.2-amd64.exe
echo 2. Ao instalar, marque a caixa: [X] Add Python to PATH
echo 3. Apos instalar, feche esta janela e abra o Nexus Scan novamente.
echo.
pause
exit /b 1

:found_python
echo [OK] Motor do sistema localizado.
echo [INFO] Instalando componentes necessarios (isso ocorre apenas uma vez)...

"!PYTHON_EXE!" -m venv .venv >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Falha ao criar a base do sistema. Tente rodar como Administrador.
    pause
    exit /b 1
)

echo [INFO] Configurando modulos de camera...
".venv\Scripts\pip.exe" install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo [ERRO] Falha ao baixar componentes. Verifique sua internet.
    pause
    exit /b 1
)

echo [OK] Tudo pronto!
echo [INFO] Criando atalhos na Area de Trabalho e na pasta do projeto...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\Configurar_Nexus_Scan.ps1"
echo.
echo [OK] Iniciando o Nexus Scan...
echo.
".venv\Scripts\python.exe" main.py

:fim
if %errorlevel% neq 0 (
    echo.
    echo [INFO] O sistema foi encerrado.
    pause
)
