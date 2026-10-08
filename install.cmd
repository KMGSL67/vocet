@echo off
rem Vocet installer: double-click this file after unzipping Vocet.
rem It runs install.ps1; the execution policy bypass applies to this process only.
setlocal
set "HERE=%~dp0"
rem Run from inside the ZIP, Windows extracts only this file to a temp folder: install.ps1 and
rem the vocet folder are then missing, and the path usually contains ".zip\".
if not exist "%HERE%install.ps1" goto notunzipped
if not exist "%HERE%vocet\" goto notunzipped
if /i not "%HERE:.zip\=%"=="%HERE%" goto notunzipped
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%HERE%install.ps1" %*
exit /b %ERRORLEVEL%

:notunzipped
echo.
echo   ==============================================================
echo.
echo      Please unzip Vocet first.
echo.
echo      1. Close this window.
echo      2. Right-click the Vocet ZIP file (in your Downloads folder)
echo         and choose "Extract All", then "Extract".
echo      3. In the new folder, double-click install.cmd.
echo.
echo   ==============================================================
echo.
pause
exit /b 1
