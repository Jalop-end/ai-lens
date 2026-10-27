@echo off
setlocal
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set PYTHONPATH=%~dp0;%PYTHONPATH%
if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" -m ai_lens %*
) else if exist "%~dp0..\ai-lens\.venv\Scripts\python.exe" (
    "%~dp0..\ai-lens\.venv\Scripts\python.exe" -m ai_lens %*
) else if exist "%USERPROFILE%\Desktop\ai-lens-main\.venv\Scripts\python.exe" (
    "%USERPROFILE%\Desktop\ai-lens-main\.venv\Scripts\python.exe" -m ai_lens %*
) else (
    where python >nul 2>nul
    if %ERRORLEVEL% EQU 0 (
        python -m ai_lens %*
    ) else (
        py -m ai_lens %*
    )
)
endlocal
