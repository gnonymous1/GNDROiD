@echo off
setlocal
title GNDROiD — Turnkey System Installer

echo ============================================================
echo   GNDROiD Master Suite — Turnkey Setup
echo   Developed by Ghulam Nabi Kalhoro
echo ============================================================
echo.

set SCRIPT_DIR=%~dp0
set INSTALLER_EXE=%SCRIPT_DIR%installer\GNDROiD-Setup-v2.2.2-Full.exe

if exist "%INSTALLER_EXE%" (
    echo [*] Found Standalone Inno Setup Installer: %INSTALLER_EXE%
    echo [*] Launching GNDROiD Setup Wizard...
    start "" "%INSTALLER_EXE%"
    goto done
)

echo [*] Standalone installer executable not found.
echo [*] Executing automated PowerShell System Deployer...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%installer\install_system.ps1"

:done
echo.
echo [*] Process finished.
endlocal
