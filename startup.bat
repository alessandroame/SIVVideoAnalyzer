@echo off
setlocal
chcp 65001 >nul

title SIV Video Analyzer

:: Posizionati nella directory del progetto
cd /d "%~dp0"

echo ======================================================
echo             SIV Video Analyzer - Avvio
echo ======================================================
echo.

:: Rilevamento automatico dell'interprete Python
set "PYTHON_EXE="

if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
    goto :PYTHON_FOUND
)

if exist "%~dp0venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0venv\Scripts\python.exe"
    goto :PYTHON_FOUND
)

where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set "PYTHON_EXE=python"
    goto :PYTHON_FOUND
)

:PYTHON_NOT_FOUND
echo [ERRORE] Interprete Python non trovato!
echo Assicurati che l'ambiente virtuale sia presente (.venv o venv)
echo oppure che Python sia installato nel sistema.
echo.
echo Per preparare l'ambiente esegui:
echo   python -m venv .venv
echo   .venv\Scripts\pip install -r requirements.txt
echo.
pause
exit /b 1

:PYTHON_FOUND
echo Interprete: %PYTHON_EXE%
echo Avvio dell'applicazione in corso...
echo.

:: Avvia l'applicazione passando eventuali parametri
"%PYTHON_EXE%" "%~dp0main.py" %*
set "APP_EXIT_CODE=%ERRORLEVEL%"

:: Se l'applicazione si e' chiusa con un errore, mantieni aperta la finestra per i dettagli
if %APP_EXIT_CODE% neq 0 (
    echo.
    echo [ATTENZIONE] L'applicazione si e' chiusa con codice di errore: %APP_EXIT_CODE%
    pause
)

exit /b %APP_EXIT_CODE%
