@echo off
setlocal
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set PYTHONSAFEPATH=1
set PYTHONPATH=%~dp0;%PYTHONPATH%

:run_app
if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" -m ai_lens %*
) else if exist "%USERPROFILE%\Desktop\ai-lens-main\.venv\Scripts\python.exe" (
    "%USERPROFILE%\Desktop\ai-lens-main\.venv\Scripts\python.exe" -m ai_lens %*
) else if exist "%USERPROFILE%\Desktop\ai-lens-main3\.venv\Scripts\python.exe" (
    "%USERPROFILE%\Desktop\ai-lens-main3\.venv\Scripts\python.exe" -m ai_lens %*
) else if exist "%~dp0..\ai-lens\.venv\Scripts\python.exe" (
    "%~dp0..\ai-lens\.venv\Scripts\python.exe" -m ai_lens %*
) else (
    where python >nul 2>nul
    if %ERRORLEVEL% EQU 0 (
        python -m ai_lens %*
    ) else (
        py -m ai_lens %*
    )
)
set APP_EXIT_CODE=%ERRORLEVEL%
rem If Python exited cleanly (code 0) or user chose stop, terminate immediately:
if %APP_EXIT_CODE% EQU 0 goto :clean_exit

rem If user typed 'N' to 'Terminate batch job (Y/N)?' in CMD, the batch continues here!
rem Resumes AI Lens cleanly so user is NOT dropped:
echo.
echo [AI Lens] Navrat zpet do aplikace...
goto run_app

:clean_exit
endlocal
