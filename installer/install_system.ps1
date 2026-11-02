# ======================================================================
# GNDROiD System-Wide Automated Installer & Deployer
# Installs GNDROiD Suite into the Windows operating system
# Author: Ghulam Nabi Kalhoro
# ======================================================================

[CmdletBinding()]
param(
    [string]$TargetDir = "",
    [switch]$AllUsers,
    [switch]$NoShortcuts,
    [switch]$AssociateApk,
    [switch]$Silent
)

$ErrorActionPreference = "Stop"
$AppName = "GNDROiD"
$AppVersion = "2.2.2"
$AppPublisher = "Ghulam Nabi Kalhoro"
$AppDescription = "GNDROiD - High-Performance Android Virtual Machine and Physical Phone Suite"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  GNDROiD v$AppVersion - Automated System Installer            " -ForegroundColor Green -BackgroundColor Black
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Determine Administrative Elevation
$IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $TargetDir) {
    if ($IsAdmin -or $AllUsers) {
        $TargetDir = Join-Path $env:ProgramFiles $AppName
    } else {
        $TargetDir = Join-Path (Join-Path $env:LOCALAPPDATA "Programs") $AppName
    }
}

Write-Host "[+] Target Installation Directory: $TargetDir" -ForegroundColor Yellow
Write-Host "[+] Elevated (Administrator): $IsAdmin" -ForegroundColor Yellow

# 2. Stop Any Active Instances
Write-Host "[*] Terminating active GNDROiD and ADB processes..." -ForegroundColor Gray
try { & adb kill-server 2>$null } catch {}
Get-Process gndroid, scrcpy, adb -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500

# 3. Resolve Workspace Source Files
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
if (-not (Test-Path (Join-Path $ProjectRoot "gndroid.pyw"))) {
    $ProjectRoot = (Get-Location).Path
}

Write-Host "[*] Source Root: $ProjectRoot" -ForegroundColor Gray

# 4. Create Target Directory Structure
New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $TargetDir "nexus") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $TargetDir "_internal") -Force | Out-Null

# 5. Copy Core Binaries and Assets
Write-Host "[*] Copying application assets..." -ForegroundColor Cyan

$FilesToCopy = @(
    "gndroid.pyw",
    "gndroid_app_launcher.py",
    "gndroid_cli_entry.py",
    "gndroid.exe",
    "gndroid.ico",
    "gndroid.png",
    "README.md"
)

foreach ($f in $FilesToCopy) {
    $src = Join-Path $ProjectRoot $f
    if (Test-Path $src) {
        Copy-Item -Path $src -Destination $TargetDir -Force
    }
}

# Copy nexus directory
$nexusSrc = Join-Path $ProjectRoot "nexus"
if (Test-Path $nexusSrc) {
    Copy-Item -Path "$nexusSrc\*" -Destination (Join-Path $TargetDir "nexus") -Recurse -Force
}

# Copy bundled tools (adb, scrcpy, DLLs)
$toolsSrc = Join-Path $ProjectRoot "tools"
if (Test-Path $toolsSrc) {
    Copy-Item -Path "$toolsSrc\*" -Destination $TargetDir -Recurse -Force
    New-Item -ItemType Directory -Path (Join-Path $TargetDir "tools") -Force | Out-Null
    Copy-Item -Path "$toolsSrc\*" -Destination (Join-Path $TargetDir "tools") -Recurse -Force
    Write-Host "[OK] Bundled runtime tools (ADB, Scrcpy, FFmpeg, SDL3) deployed" -ForegroundColor Green
}

# Copy compiled dist binaries if present
$distDir = Join-Path $ProjectRoot "dist\gndroid"
if (Test-Path $distDir) {
    Copy-Item -Path "$distDir\*" -Destination $TargetDir -Recurse -Force
}

# 6. Setup Shell Script / Native CLI Launcher
# If gndroid.exe doesn't exist, create a lightweight runner stub
$gndroidExe = Join-Path $TargetDir "gndroid.exe"
if (-not (Test-Path $gndroidExe)) {
    # Generate batch wrapper as fallback if binary hasn't compiled yet
    $launcherBat = Join-Path $TargetDir "gndroid.cmd"
    $batContent = "@echo off`r`nstart `"`" `"%~dp0gndroid.pyw`" %*"
    Set-Content -Path $launcherBat -Value $batContent -Encoding Ascii
}

# 7. Create Start Menu Shortcuts
if (-not $NoShortcuts) {
    Write-Host "[*] Generating Start Menu & Desktop Shortcuts..." -ForegroundColor Cyan
    $WshShell = New-Object -ComObject WScript.Shell

    if ($IsAdmin -or $AllUsers) {
        $StartMenuDir = Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs\$AppName"
        $DesktopDir = [Environment]::GetFolderPath([Environment+SpecialFolder]::CommonDesktopDirectory)
    } else {
        $StartMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\$AppName"
        $DesktopDir = [Environment]::GetFolderPath([Environment+SpecialFolder]::Desktop)
    }

    New-Item -ItemType Directory -Path $StartMenuDir -Force | Out-Null

    $ExeTarget = if (Test-Path $gndroidExe) { $gndroidExe } else { Join-Path $TargetDir "gndroid.pyw" }
    $IconPath = Join-Path $TargetDir "gndroid.ico"

    $Shortcuts = @(
        @{ Name = "$AppName Master Suite"; Args = ""; Desc = "GNDROiD Master Suite & Virtual Machine" },
        @{ Name = "$AppName Mirror"; Args = "mirror"; Desc = "High-Speed USB & Wireless Phone Mirroring" },
        @{ Name = "$AppName Multi-Instance Manager"; Args = "multi"; Desc = "Multi-Instance Parallel Android Clones" },
        @{ Name = "$AppName Wireless LAN Mode"; Args = "lan"; Desc = "Wireless Wi-Fi Streaming & Subnet Radar" },
        @{ Name = "$AppName ADB Doctor"; Args = "fix"; Desc = "ADB Doctor & Troubleshooting Suite" },
        @{ Name = "$AppName 1-Click OS Downloader"; Args = "download"; Desc = "1-Click Download Official Google Android Images" }
    )

    foreach ($s in $Shortcuts) {
        $lnkPath = Join-Path $StartMenuDir "$($s.Name).lnk"
        $shortcut = $WshShell.CreateShortcut($lnkPath)
        $shortcut.TargetPath = $ExeTarget
        $shortcut.Arguments = $s.Args
        $shortcut.WorkingDirectory = $TargetDir
        $shortcut.Description = $s.Desc
        if (Test-Path $IconPath) { $shortcut.IconLocation = "$IconPath,0" }
        $shortcut.Save()
    }

    # Desktop shortcuts for key suites
    $DesktopShortcuts = @(
        @{ Name = "GNDROiD.lnk"; Args = ""; Desc = "GNDROiD Master Suite" },
        @{ Name = "GNDROiD Mirror.lnk"; Args = "mirror"; Desc = "GNDROiD Phone Mirroring" },
        @{ Name = "GNDROiD Multi-Instance.lnk"; Args = "multi"; Desc = "GNDROiD Multi-Instance Manager" },
        @{ Name = "GNDROiD Wireless LAN.lnk"; Args = "lan"; Desc = "GNDROiD Wireless LAN Mode" },
        @{ Name = "GNDROiD ADB Doctor.lnk"; Args = "fix"; Desc = "GNDROiD ADB Doctor" }
    )
    foreach ($ds in $DesktopShortcuts) {
        $desktopLnk = Join-Path $DesktopDir $ds.Name
        $dShortcut = $WshShell.CreateShortcut($desktopLnk)
        $dShortcut.TargetPath = $ExeTarget
        $dShortcut.Arguments = $ds.Args
        $dShortcut.WorkingDirectory = $TargetDir
        $dShortcut.Description = $ds.Desc
        if (Test-Path $IconPath) { $dShortcut.IconLocation = "$IconPath,0" }
        $dShortcut.Save()
    }

    Write-Host "[OK] Start Menu shortcuts created at: $StartMenuDir" -ForegroundColor Green
    Write-Host "[OK] All 5 Desktop shortcuts created at: $DesktopDir" -ForegroundColor Green
}

# 8. Add to System / User PATH
Write-Host "[*] Configuring PATH Environment Variable..." -ForegroundColor Cyan
$RegScope = if ($IsAdmin -or $AllUsers) { "Machine" } else { "User" }
$OldPath = [Environment]::GetEnvironmentVariable("Path", $RegScope)
if ($OldPath -notlike "*$TargetDir*") {
    $NewPath = "$OldPath;$TargetDir"
    [Environment]::SetEnvironmentVariable("Path", $NewPath, $RegScope)
    Write-Host "[OK] Added '$TargetDir' to $RegScope PATH" -ForegroundColor Green
} else {
    Write-Host "[OK] '$TargetDir' already present in $RegScope PATH" -ForegroundColor Green
}

# 9. Optional APK File Association
Write-Host "[*] Registering .apk File Association..." -ForegroundColor Cyan
$AdbPath = Join-Path $TargetDir "adb.exe"
$RegRoot = if ($IsAdmin) { "HKLM:\Software\Classes" } else { "HKCU:\Software\Classes" }

New-Item -Path "$RegRoot\.apk" -Value "GNDROiD.APKPackage" -Force | Out-Null
New-Item -Path "$RegRoot\GNDROiD.APKPackage" -Value "Android Package File (Install via GNDROiD)" -Force | Out-Null
if (Test-Path (Join-Path $TargetDir "gndroid.ico")) {
    New-Item -Path "$RegRoot\GNDROiD.APKPackage\DefaultIcon" -Value "$TargetDir\gndroid.ico,0" -Force | Out-Null
}
New-Item -Path "$RegRoot\GNDROiD.APKPackage\shell\open\command" -Value "`"$AdbPath`" install -r `"%1`"" -Force | Out-Null
Write-Host "[OK] .apk association registered with GNDROiD ADB" -ForegroundColor Green

# 10. Register in Windows Programs & Features (Add/Remove Programs)
Write-Host "[*] Registering Uninstaller in Windows Registry..." -ForegroundColor Cyan
$UninstallKeyPath = if ($IsAdmin) {
    "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$AppName"
} else {
    "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$AppName"
}

New-Item -Path $UninstallKeyPath -Force | Out-Null
Set-ItemProperty -Path $UninstallKeyPath -Name "DisplayName" -Value "$AppName v$AppVersion - High-Performance Android Suite" -Force
Set-ItemProperty -Path $UninstallKeyPath -Name "DisplayVersion" -Value $AppVersion -Force
Set-ItemProperty -Path $UninstallKeyPath -Name "Publisher" -Value $AppPublisher -Force
Set-ItemProperty -Path $UninstallKeyPath -Name "InstallLocation" -Value $TargetDir -Force
Set-ItemProperty -Path $UninstallKeyPath -Name "DisplayIcon" -Value (Join-Path $TargetDir "gndroid.ico") -Force
Set-ItemProperty -Path $UninstallKeyPath -Name "UninstallString" -Value "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$TargetDir\uninstall_system.ps1`"" -Force
Set-ItemProperty -Path $UninstallKeyPath -Name "NoModify" -Value 1 -Force
Set-ItemProperty -Path $UninstallKeyPath -Name "NoRepair" -Value 1 -Force

# Copy uninstall script to target
$UninstallScriptSrc = Join-Path $ScriptDir "uninstall_system.ps1"
if (Test-Path $UninstallScriptSrc) {
    Copy-Item -Path $UninstallScriptSrc -Destination $TargetDir -Force
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  GNDROiD v$AppVersion has been successfully installed in system! " -ForegroundColor Green -BackgroundColor Black
Write-Host "  Location: $TargetDir" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Cyan
