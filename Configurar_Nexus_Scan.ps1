# ============================================================
#  Nexus Scan - Configuracao de Atalhos (execute 1 vez)
#  Cria icone na Area de Trabalho e na pasta do projeto.
# ============================================================
$ErrorActionPreference = "Continue"

$rootDir   = $PSScriptRoot
$batPath   = Join-Path $rootDir "Iniciar_Nexus_Scan.bat"
$pngPath   = Join-Path $rootDir "nexus_core\camera_icon.png"
$icoPath   = Join-Path $rootDir "nexus_core\camera_icon.ico"
$desktop   = [System.Environment]::GetFolderPath("Desktop")

Write-Host ""
Write-Host "========================================"
Write-Host "   NEXUS SCAN - Configuracao de Atalhos"
Write-Host "========================================"
Write-Host ""

# 1. Caminho do Icone
if (Test-Path $icoPath) {
    Write-Host "[OK] Icone profissional detectado." -ForegroundColor Green
} else {
    Write-Host "[AVISO] camera_icon.ico nao encontrado. O atalho usara o icone padrao do Windows." -ForegroundColor Yellow
}

# 2. Funcao para criar atalho
function New-NexusShortcut {
    param([string]$ShortcutPath)

    try {
        $shell    = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($ShortcutPath)
        $shortcut.TargetPath       = "cmd.exe"
        $shortcut.Arguments        = "/c `"$batPath`""
        $shortcut.WorkingDirectory = $rootDir
        $shortcut.WindowStyle      = 7
        $shortcut.Description      = "Nexus Scan IP Cam"

        if ($icoPath -and (Test-Path $icoPath)) {
            $shortcut.IconLocation = "$icoPath,0"
        }

        $shortcut.Save()
        return $true
    } catch {
        return $false
    }
}

# 3. Criar atalhos
$desktopLnk = Join-Path $desktop "Nexus Scan.lnk"
if (New-NexusShortcut $desktopLnk) {
    Write-Host "[OK] Atalho criado na Area de Trabalho." -ForegroundColor Green
}

$rootLnk = Join-Path $rootDir "Nexus Scan.lnk"
if (New-NexusShortcut $rootLnk) {
    Write-Host "[OK] Atalho criado na pasta do projeto." -ForegroundColor Green
}

Write-Host ""
Write-Host "Pronto! Use o atalho na sua Area de Trabalho para iniciar." -ForegroundColor Yellow
Write-Host ""
Write-Host "Pressione qualquer tecla para sair..."
Write-Host "(Se a janela nao fechar, voce pode fechar no X)"
