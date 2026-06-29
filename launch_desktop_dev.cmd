@echo off
setlocal

set "ROOT=%~dp0"
set "DESKTOP_DIR=%ROOT%frontends\desktop"
set "CARGO_BIN=%USERPROFILE%\.cargo\bin"
set "VSDEVCMD=%ProgramFiles(x86)%\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat"

if not exist "%DESKTOP_DIR%\package.json" (
  echo [ERROR] Desktop project not found: "%DESKTOP_DIR%"
  exit /b 1
)

if exist "%CARGO_BIN%\cargo.exe" (
  set "PATH=%CARGO_BIN%;%PATH%"
)

if not exist "%CARGO_BIN%\cargo.exe" (
  echo [ERROR] cargo.exe not found: "%CARGO_BIN%\cargo.exe"
  echo Install Rustup first, then reopen this script.
  exit /b 1
)

if not exist "%VSDEVCMD%" (
  echo [ERROR] Visual Studio Build Tools not found: "%VSDEVCMD%"
  echo Install VS 2022 Build Tools with the C++ workload.
  exit /b 1
)

if not exist "%DESKTOP_DIR%\node_modules" (
  echo [ERROR] node_modules not found.
  echo Run: cd /d "%DESKTOP_DIR%" ^&^& npm install
  exit /b 1
)

call "%VSDEVCMD%" -arch=x64 -host_arch=x64
if errorlevel 1 exit /b %errorlevel%

cd /d "%DESKTOP_DIR%"
npm run tauri -- dev
