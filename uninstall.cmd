@echo off
rem Removes Vocet. Runs uninstall.ps1; the execution policy bypass applies to this process only.
rem The uninstaller deletes the folder this file is in, so everything happens on the last line:
rem leave that folder, "(goto)" ends this batch file (cmd won't look for it again), then run.
cd /d "%TEMP%" & (goto) 2>nul & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1" %*
