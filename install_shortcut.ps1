# Script para criar o atalho visual com ícone de câmera
$shell = New-Object -ComObject WScript.Shell
$desktop = [System.Environment]::GetFolderPath("Desktop")
$currentDir = Get-Location
$targetPath = Join-Path $currentDir "run_windows.bat"
$iconPath = Join-Path $currentDir "camera_icon.png"

# Função para criar atalho
function Create-NexusShortcut {
    param($path)
    $shortcut = $shell.CreateShortcut($path)
    $shortcut.TargetPath = "cmd.exe"
    $shortcut.Arguments = "/c `"$targetPath`""
    $shortcut.IconLocation = "$iconPath,0"
    $shortcut.WorkingDirectory = $currentDir
    $shortcut.WindowStyle = 7 # Minimizado para não poluir
    $shortcut.Description = "Nexus Scan IP Cam"
    $shortcut.Save()
}

Write-Host "--- Configurando ícone do Nexus Scan ---" -ForegroundColor Cyan

# Atalho na Área de Trabalho
Create-NexusShortcut (Join-Path $desktop "Nexus Scan.lnk")
Write-Host "[OK] Ícone de câmera criado na Área de Trabalho." -ForegroundColor Green

# Atalho na pasta raiz do projeto
Create-NexusShortcut (Join-Path $currentDir "Nexus Scan.lnk")
Write-Host "[OK] Ícone de câmera criado na pasta do projeto." -ForegroundColor Green

Write-Host "`nPronto! Agora você pode usar apenas o ícone de câmera para abrir o sistema." -ForegroundColor Yellow
Write-Host "Pressione qualquer tecla para sair..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
