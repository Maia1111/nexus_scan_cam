# ============================================================
#  Nexus Scan — Configuracao de Atalhos (execute 1 vez)
#  Cria icone na Area de Trabalho e na pasta do projeto.
# ============================================================
$ErrorActionPreference = "Stop"

$rootDir   = $PSScriptRoot
$batPath   = Join-Path $rootDir "Iniciar_Nexus_Scan.bat"
$pngPath   = Join-Path $rootDir "nexus_core\camera_icon.png"
$icoPath   = Join-Path $rootDir "nexus_core\camera_icon.ico"
$desktop   = [System.Environment]::GetFolderPath("Desktop")

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   NEXUS SCAN - Configuracao de Atalhos" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. Converte PNG para ICO (necessario para atalhos Windows) ────────────────
if (Test-Path $pngPath) {
    try {
        Add-Type -AssemblyName System.Drawing
        $bmp   = [System.Drawing.Bitmap]::new($pngPath)
        $hIcon = $bmp.GetHicon()
        $icon  = [System.Drawing.Icon]::FromHandle($hIcon)

        $fs = [System.IO.FileStream]::new($icoPath, [System.IO.FileMode]::Create)
        $icon.Save($fs)
        $fs.Close()
        $icon.Dispose()
        $bmp.Dispose()
        Write-Host "[OK] Icone convertido para .ico" -ForegroundColor Green
    } catch {
        Write-Host "[AVISO] Nao foi possivel converter o icone: $_" -ForegroundColor Yellow
        $icoPath = $null
    }
} else {
    Write-Host "[AVISO] camera_icon.png nao encontrado — atalho sem icone personalizado." -ForegroundColor Yellow
    $icoPath = $null
}

# ── 2. Funcao auxiliar para criar atalho .lnk ────────────────────────────────
function New-NexusShortcut {
    param([string]$ShortcutPath)

    $shell    = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($ShortcutPath)
    $shortcut.TargetPath       = "cmd.exe"
    $shortcut.Arguments        = "/c `"$batPath`""
    $shortcut.WorkingDirectory = $rootDir
    $shortcut.WindowStyle      = 7   # Minimizado (janela do cmd fica na barra)
    $shortcut.Description      = "Nexus Scan IP Cam"

    if ($icoPath -and (Test-Path $icoPath)) {
        $shortcut.IconLocation = "$icoPath,0"
    }

    $shortcut.Save()
}

# ── 3. Atalho na Area de Trabalho ─────────────────────────────────────────────
$desktopLnk = Join-Path $desktop "Nexus Scan.lnk"
New-NexusShortcut $desktopLnk
Write-Host "[OK] Atalho criado na Area de Trabalho: $desktopLnk" -ForegroundColor Green

# ── 4. Atalho na pasta raiz do projeto ───────────────────────────────────────
$rootLnk = Join-Path $rootDir "Nexus Scan.lnk"
New-NexusShortcut $rootLnk
Write-Host "[OK] Atalho criado na pasta do projeto: $rootLnk" -ForegroundColor Green

Write-Host ""
Write-Host "Pronto! Use qualquer um dos atalhos para iniciar o sistema." -ForegroundColor Yellow
Write-Host "(Voce tambem pode clicar direto em 'Iniciar_Nexus_Scan.bat')" -ForegroundColor Gray
Write-Host ""
Write-Host "Pressione qualquer tecla para sair..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
