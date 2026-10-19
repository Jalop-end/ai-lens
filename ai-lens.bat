@echo off
if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" -m ai_lens %*
) else (
    where python >nul 2>nul
    if %ERRORLEVEL% EQU 0 (
        python -m ai_lens %*
    ) else (
        py -m ai_lens %*
    )
)
