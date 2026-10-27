@echo off
rem Direct launcher for AI Lens with Google Gemini API
setlocal
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
call "%~dp0ai-lens.bat" start with Gemini
endlocal
