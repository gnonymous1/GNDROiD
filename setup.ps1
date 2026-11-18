# GNDROiD Turnkey Setup Launcher
# Replaces legacy setup.bat with clean PowerShell installer launcher
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  GNDROiD Master Suite v2.5.0 — Turnkey Setup" -ForegroundColor Cyan
Write-Host "  Architected & Developed by Ghulam Nabi Kalhoro" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$InstallerExe = Join-Path $ScriptDir "installer\GNDROiD-Setup-v2.5.0-Full.exe"
if (-not (Test-Path $InstallerExe)) {
    $InstallerExe = Join-Path $ScriptDir "installer\GNDROiD-Setup-v2.2.2-Full.exe"
}

if (Test-Path $InstallerExe) {
    Write-Host "[*] Found Standalone Inno Setup Installer: $InstallerExe" -ForegroundColor Green
    Write-Host "[*] Launching GNDROiD Setup Wizard..." -ForegroundColor Green
    Start-Process -FilePath $InstallerExe
} else {
    Write-Host "[*] Standalone wizard installer executable not found." -ForegroundColor Yellow
    Write-Host "[*] Executing automated native PowerShell System Deployer..." -ForegroundColor Yellow
    $DeployScript = Join-Path $ScriptDir "installer\install_system.ps1"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $DeployScript
}

$GuidePath = Join-Path $ScriptDir "INSTALL_AND_USER_GUIDE.md"
if (Test-Path $GuidePath) {
    Write-Host ""
    Write-Host "[*] User Guide available at: $GuidePath" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "[*] Setup launcher finished." -ForegroundColor Green
