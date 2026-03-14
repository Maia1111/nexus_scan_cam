@echo off
title Configurar Nexus Scan - Criar Atalho
echo ========================================
echo   NEXUS SCAN - Criando Atalhos...
echo ========================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Configurar_Nexus_Scan.ps1"

if %ERRORLEVEL% equ 0 (
    echo.
    echo [SUCESSO] Atalhos criados com novo icone profissional!
) else (
    echo.
    echo [ERRO] Ocorreu um problema ao criar os atalhos.
)

pause
