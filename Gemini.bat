@echo off
rem AI Lens - Direct Gemini launcher: gemini "<api_key>" [model] [lang] [level]
setlocal
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set PYTHONPATH=%~dp0;%PYTHONPATH%

if "%~1"=="" (
    if "%AI_LENS_ACTIVE%"=="1" (
        exit /b 0
    ) else (
        call "%~dp0ai-lens.bat" start with Gemini
    )
) else (
    call "%~dp0ai-lens.bat" gemini %*
)
endlocal
