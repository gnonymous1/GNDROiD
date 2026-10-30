# ======================================================================
# GNDROiD System-Wide Automated Uninstaller
# Author: Ghulam Nabi Kalhoro
# ======================================================================

[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$Silent
)

$ErrorActionPreference = "SilentlyContinue"
$AppName = "GNDROiD"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Uninstalling GNDROiD Suite from System...                 " -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Terminate running processes
Write-Host "[*] Terminating GNDROiD and emulator processes..." -ForegroundColor Gray
Get-Process gndroid, scrcpy -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

# 2. Remove Shortcuts
Write-Host "[*] Removing Start Menu and Desktop shortcuts..." -ForegroundColor Gray
$StartMenuPaths = @(
    Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs\$AppName",
    Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\$AppName"
)
foreach ($p in $StartMenuPaths) {
    if (Test-Path $p) { Remove-Item -Path $p -Recurse -Force }
}

$DesktopDirs = @(
    [Environment]::GetFolderPath([Environment+SpecialFolder]::CommonDesktopDirectory),
    [Environment]::GetFolderPath([Environment+SpecialFolder]::Desktop)
)
$ShortcutNames = @(
    "GNDROiD.lnk",
    "GNDROiD Mirror.lnk",
    "GNDROiD Multi-Instance.lnk",
    "GNDROiD Wireless LAN.lnk",
    "GNDROiD ADB Doctor.lnk"
)
foreach ($dir in $DesktopDirs) {
    foreach ($name in $ShortcutNames) {
        $d = Join-Path $dir $name
        if (Test-Path $d) { Remove-Item -Path $d -Force }
    }
}

# 3. Remove Registry associations & Uninstall entries
Write-Host "[*] Removing Registry keys..." -ForegroundColor Gray
$RegUninstallKeys = @(
    "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$AppName",
    "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$AppName"
)
foreach ($k in $RegUninstallKeys) {
    if (Test-Path $k) { Remove-Item -Path $k -Recurse -Force }
}

$RegClasses = @("HKLM:\Software\Classes", "HKCU:\Software\Classes")
foreach ($rc in $RegClasses) {
    if (Test-Path "$rc\GNDROiD.APKPackage") { Remove-Item -Path "$rc\GNDROiD.APKPackage" -Recurse -Force }
}

# 4. Remove from PATH
Write-Host "[*] Cleaning PATH environment variable..." -ForegroundColor Gray
foreach ($Scope in @("Machine", "User")) {
    $p = [Environment]::GetEnvironmentVariable("Path", $Scope)
    if ($p -like "*$AppName*") {
        $clean = ($p -split ';' | Where-Object { $_ -notlike "*$AppName*" }) -join ';'
        [Environment]::SetEnvironmentVariable("Path", $clean, $Scope)
    }
}

# 5. Remove Installation Directory
$InstallDirs = @(
    Join-Path $env:ProgramFiles $AppName,
    Join-Path (Join-Path $env:LOCALAPPDATA "Programs") $AppName
)

foreach ($dir in $InstallDirs) {
    if (Test-Path $dir) {
        Write-Host "[*] Removing files from: $dir" -ForegroundColor Gray
        Remove-Item -Path $dir -Recurse -Force
    }
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  GNDROiD has been cleanly removed from the system.         " -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
