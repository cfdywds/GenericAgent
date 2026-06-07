@echo off
setlocal

set "REPO_ROOT=%~dp0"
set "PWSH=C:\Program Files\PowerShell\7\pwsh.exe"

if not exist "%PWSH%" (
  echo PowerShell 7 not found: %PWSH%
  echo Install PowerShell 7.5.5 or update this launcher.
  pause
  exit /b 1
)

pushd "%REPO_ROOT%" >nul
"%PWSH%" -NoProfile -ExecutionPolicy Bypass -File "%REPO_ROOT%launch_tuiapp_v2.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"
popd >nul

exit /b %EXIT_CODE%
