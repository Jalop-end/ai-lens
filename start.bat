@echo off
rem Universal start launcher for AI Lens
setlocal
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
if /i "%1"=="with" (
    call "%~dp0ai-lens.bat" start with %2 %3 %4 %5 %6 %7 %8 %9
) else (
    call "%~dp0ai-lens.bat" start %*
)
endlocal
