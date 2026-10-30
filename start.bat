@echo off
rem Universal start launcher for AI Lens
setlocal
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
if /i "%1"=="status" (
    "%~dp0ai-lens.bat" status %2 %3 %4 %5 %6 %7 %8 %9
) else if /i "%1"=="stop" (
    "%~dp0ai-lens.bat" stop %2 %3 %4 %5 %6 %7 %8 %9
) else if /i "%1"=="diag" (
    "%~dp0ai-lens.bat" diag %2 %3 %4 %5 %6 %7 %8 %9
) else if /i "%1"=="diagnostika" (
    "%~dp0ai-lens.bat" diag %2 %3 %4 %5 %6 %7 %8 %9
) else if /i "%1"=="languages" (
    "%~dp0ai-lens.bat" languages %2 %3 %4 %5 %6 %7 %8 %9
) else if /i "%1"=="levels" (
    "%~dp0ai-lens.bat" levels %2 %3 %4 %5 %6 %7 %8 %9
) else (
    "%~dp0ai-lens.bat" start %*
)
