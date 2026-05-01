@echo off
REM Quick launcher: runs the QML GUI from the bundled venv.
REM The QML entry point is "python -m ui".

setlocal
set "VENV_PY=%~dp0venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
    echo [run] venv missing at "%VENV_PY%".
    echo [run] Run install.bat first to set it up.
    pause
    exit /b 1
)

pushd "%~dp0"
"%VENV_PY%" -m ui %*
set "EXITCODE=%ERRORLEVEL%"
popd
endlocal ^& exit /b %EXITCODE%
