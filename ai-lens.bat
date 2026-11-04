@echo off
setlocal
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set PYTHONSAFEPATH=1
set PYTHONPATH=%~dp0;%PYTHONPATH%

set "AI_LENS_PY="
if exist "%~dp0.venv\Scripts\python.exe" (
    set "AI_LENS_PY=%~dp0.venv\Scripts\python.exe"
) else if exist "%USERPROFILE%\Desktop\aiforscreen\.venv\Scripts\python.exe" (
    set "AI_LENS_PY=%USERPROFILE%\Desktop\aiforscreen\.venv\Scripts\python.exe"
) else if exist "%USERPROFILE%\Desktop\ai-lens-main\.venv\Scripts\python.exe" (
    set "AI_LENS_PY=%USERPROFILE%\Desktop\ai-lens-main\.venv\Scripts\python.exe"
) else if exist "%USERPROFILE%\Desktop\ai-lens-main3\.venv\Scripts\python.exe" (
    set "AI_LENS_PY=%USERPROFILE%\Desktop\ai-lens-main3\.venv\Scripts\python.exe"
) else if exist "%~dp0..\ai-lens\.venv\Scripts\python.exe" (
    set "AI_LENS_PY=%~dp0..\ai-lens\.venv\Scripts\python.exe"
)

:run_app
if defined AI_LENS_PY (
    "%AI_LENS_PY%" -m ai_lens %*
) else (
    where python >nul 2>nul
    if not errorlevel 1 (
        python -m ai_lens %*
    ) else (
        py -m ai_lens %*
    )
)
set APP_EXIT_CODE=%ERRORLEVEL%
rem If Python exited cleanly (code 0) or with a standard error, terminate immediately.
rem Only resume if interrupted by Ctrl+C (-1073741510 / 130) and user answered 'N' to Terminate batch job (Y/N)?
if %APP_EXIT_CODE% EQU -1073741510 goto :resume_app
if %APP_EXIT_CODE% EQU 130 goto :resume_app
goto :clean_exit

:resume_app
echo.
echo [AI Lens] Navrat zpet do aplikace...
goto run_app

:clean_exit
endlocal
