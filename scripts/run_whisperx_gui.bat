@echo off
setlocal
chcp 65001 >nul 2>nul
set "PYTHONIOENCODING=utf-8"

REM ── Self-contained WhisperX GUI launcher ──
REM Project root = parent of this scripts\ folder.
for %%A in ("%~dp0..") do set "ROOT=%%~fA"

if not exist "%ROOT%\scripts\wisper_launcher.py" (
  echo ERROR: wisper_launcher.py not found at %ROOT%\scripts\
  echo Did you move this .bat out of the scripts\ folder?
  pause
  exit /b 2
)

REM Check venv
set "PY=%ROOT%\venv\Scripts\python.exe"
set "PYW=%ROOT%\venv\Scripts\pythonw.exe"
if not exist "%PY%" (
  echo ERROR: venv not found at %ROOT%\venv
  echo Run the installer first:
  echo   powershell -ExecutionPolicy Bypass -File "%ROOT%\scripts\install_whisperx_windows.ps1"
  pause
  exit /b 2
)
if not exist "%PYW%" set "PYW=%PY%"

REM Put venv Scripts and local ffmpeg on PATH
set "PATH=%ROOT%\venv\Scripts;%ROOT%\tools\ffmpeg\bin;%PATH%"

REM Check ffmpeg (local or system)
where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo ERROR: ffmpeg not found (not in project tools and not in system PATH^).
  echo Re-run the installer or install ffmpeg manually.
  pause
  exit /b 2
)

set "LOG=%ROOT%\_run_whisperx_gui.log"
del "%LOG%" >nul 2>nul

REM Launch the GUI; log output for debugging
"%PYW%" "%ROOT%\scripts\wisper_launcher.py" > "%LOG%" 2>&1
if errorlevel 1 (
  echo.
  echo ERROR: WhisperX launcher failed. Log:
  echo   %LOG%
  echo.
  echo --- last 40 lines ---
  powershell -NoProfile -Command "Get-Content -Path '%LOG%' -Tail 40"
  echo ---------------------
  echo.
  start notepad "%LOG%"
  pause
)

endlocal
