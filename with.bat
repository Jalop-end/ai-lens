@echo off
rem Helper for `start with Gemini` command in Windows Command Prompt
setlocal
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
call "%~dp0ai-lens.bat" start with %*
endlocal
