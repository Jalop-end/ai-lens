@echo off
rem Universal start launcher for AI Lens
setlocal
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
call "%~dp0ai-lens.bat" start %*
endlocal
