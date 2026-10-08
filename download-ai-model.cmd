@echo off
rem Downloads the optional AI formatting model (Phi-4-mini, about 2.4 GB) once, from Hugging Face.
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Vocet is not installed in this folder yet. Run install.cmd first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m vocet.get_ai_model
set RC=%ERRORLEVEL%
pause
exit /b %RC%
