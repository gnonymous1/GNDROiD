# GNDROiD Turnkey Setup Launcher
# Replaces legacy setup.bat with clean PowerShell installer launcher
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  GNDROiD Master Suite — Turnkey Setup" -ForegroundColor Cyan
Write-Host "  Developed by Ghulam Nabi Kalhoro" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$InstallerExe = Join-Path $ScriptDir "installer\GNDROiD-Setup-v2.2.2-Full.exe"

if (Test-Path $InstallerExe) {
    Write-Host "[*] Found Standalone Inno Setup Installer: $InstallerExe" -ForegroundColor Green
    Write-Host "[*] Launching GNDROiD Setup Wizard..." -ForegroundColor Green
    Start-Process -FilePath $InstallerExe
} else {
    Write-Host "[*] Standalone installer executable not found." -ForegroundColor Yellow
    Write-Host "[*] Executing automated PowerShell System Deployer..." -ForegroundColor Yellow
    $DeployScript = Join-Path $ScriptDir "installer\install_system.ps1"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $DeployScript
}

Write-Host ""
Write-Host "[*] Process finished." -ForegroundColor Green
