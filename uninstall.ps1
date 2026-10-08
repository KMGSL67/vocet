#Requires -Version 5.1
<#
.SYNOPSIS
    Removes Vocet from this Windows account.
.DESCRIPTION
    Runs from Settings > Apps > Installed apps > Vocet > Uninstall, or from uninstall.cmd.
    Removes the Start menu and Desktop shortcuts, the "Start with Windows" entry, the
    Installed apps entry and the install folder (%LOCALAPPDATA%\Programs\Vocet, including
    its Python environment and the speech model). Then it asks before deleting your
    settings and history in %LOCALAPPDATA%\Vocet. uv is left installed.

    The script lives in the folder it deletes, so it first copies itself to %TEMP% and
    runs from there.

    The Test* parameters are for automated tests only (see install.ps1). Give all five or none.
.PARAMETER KeepData
    Keep the settings and history without asking.
.PARAMETER RemoveData
    Delete the settings and history without asking.
#>
[CmdletBinding()]
param(
    [switch]$KeepData,
    [switch]$RemoveData,
    [string]$TestInstallDir,
    [string]$TestDataDir,
    [string]$TestProgramsDir,
    [string]$TestDesktopDir,
    [string]$TestRegistryName,
    # Never wait for a key press (for automated runs).
    [switch]$NoPause,
    # Internal: set on the copy running from %TEMP%.
    [switch]$Relaunched,
    [string]$StartedFrom
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Get-FullPath {
    param([string]$Path)
    return [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
}

function Wait-ForKey {
    param([string]$Prompt)
    if ($NoPause) {
        return
    }
    Write-Host ''
    Write-Host $Prompt
    if ([Console]::IsInputRedirected) {
        # No keyboard to wait for (input comes from a file or pipe): read a line instead.
        try {
            [void][Console]::In.ReadLine()
        }
        catch {
            # Nothing to read: just go on.
        }
        return
    }
    try {
        $Host.UI.RawUI.FlushInputBuffer()
        [void]$Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
    }
    catch {
        try {
            [void](Read-Host)
        }
        catch {
            # No console to read from: just go on.
        }
    }
}

function Get-VocetProcess {
    # Python processes running Vocet from the given folder (vocet.pyw, or the folder's own .venv).
    param([string]$Dir)
    $script = (Join-Path $Dir 'vocet.pyw')
    $prefix = $Dir.TrimEnd('\') + '\'
    try {
        $all = @(Get-CimInstance -ClassName Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -ErrorAction Stop)
    }
    catch {
        return @()
    }
    $found = @()
    foreach ($p in $all) {
        $cmd = [string]$p.CommandLine
        $exe = [string]$p.ExecutablePath
        if (($cmd -and $cmd.IndexOf($script, [StringComparison]::OrdinalIgnoreCase) -ge 0) -or
            ($exe -and $exe.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase))) {
            $found += $p
        }
    }
    return $found
}

function Remove-Shortcut {
    param([string]$Path, [string]$Where)
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Force
        Write-Host ('  Removed the ' + $Where + ' shortcut.')
    }
}

# --- Where things are ----------------------------------------------------

$testValues = @($TestInstallDir, $TestDataDir, $TestProgramsDir, $TestDesktopDir, $TestRegistryName)
$TestMode = @($testValues | Where-Object { $_ }).Count -gt 0
if ($TestMode -and @($testValues | Where-Object { -not $_ }).Count -gt 0) {
    Write-Host 'Test mode needs all of -TestInstallDir, -TestDataDir, -TestProgramsDir, -TestDesktopDir and -TestRegistryName.' -ForegroundColor Red
    exit 1
}
if ($TestMode) {
    $InstallDir = Get-FullPath $TestInstallDir
    $DataDir = Get-FullPath $TestDataDir
    $ProgramsDir = Get-FullPath $TestProgramsDir
    $DesktopDir = Get-FullPath $TestDesktopDir
    $RegName = $TestRegistryName
}
else {
    $InstallDir = Join-Path $env:LOCALAPPDATA 'Programs\Vocet'
    $DataDir = Join-Path $env:LOCALAPPDATA 'Vocet'
    $ProgramsDir = [Environment]::GetFolderPath('Programs')
    $DesktopDir = [Environment]::GetFolderPath('Desktop')
    $RegName = 'Vocet'
}
$UninstallSubKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\' + $RegName
$RunSubKey = 'Software\Microsoft\Windows\CurrentVersion\Run'
$RunValue = $RegName   # the app's "Start with Windows" value (vocet/settings.py RUN_VALUE)
$tempDir = [System.IO.Path]::GetTempPath()

try {
    $Host.UI.RawUI.WindowTitle = 'Uninstall Vocet'
}
catch {
    # Not a console window: no title to set.
}

# --- Run from a copy in %TEMP%, so the install folder can be deleted -------

if (-not $Relaunched) {
    $copy = $null
    try {
        $copy = Join-Path $tempDir ('vocet-uninstall-' + [guid]::NewGuid().ToString('N') + '.ps1')
        Copy-Item -LiteralPath $PSCommandPath -Destination $copy -Force
    }
    catch {
        $copy = $null   # carry on from here; deleting the folder may then leave this file behind
    }
    if ($copy) {
        # Nothing of this process may stay inside the install folder, not even the working directory.
        Set-Location -LiteralPath $tempDir
        [Environment]::CurrentDirectory = $tempDir
        $psExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
        $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $copy, '-Relaunched', '-StartedFrom', $PSScriptRoot)
        foreach ($name in @('KeepData', 'RemoveData', 'NoPause')) {
            if ($PSBoundParameters.ContainsKey($name) -and $PSBoundParameters[$name]) {
                $argList += ('-' + $name)
            }
        }
        if ($TestMode) {
            $argList += @('-TestInstallDir', $InstallDir, '-TestDataDir', $DataDir, '-TestProgramsDir', $ProgramsDir,
                '-TestDesktopDir', $DesktopDir, '-TestRegistryName', $RegName)
        }
        & $psExe @argList
        exit $LASTEXITCODE
    }
}
if (-not $StartedFrom) {
    $StartedFrom = $PSScriptRoot
}
Set-Location -LiteralPath $tempDir
[Environment]::CurrentDirectory = $tempDir

# --- Uninstall -------------------------------------------------------------

$exitCode = 0
try {
    if ($KeepData -and $RemoveData) {
        throw 'Use either -KeepData or -RemoveData, not both.'
    }

    Write-Host ''
    Write-Host 'Uninstalling Vocet' -ForegroundColor Green

    # Vocet must be closed: its files can't be deleted while it runs. It's never closed for you.
    while ($true) {
        $running = @(Get-VocetProcess $InstallDir)
        if ($running.Count -eq 0) {
            break
        }
        if ($NoPause) {
            throw 'Vocet is open. Quit it (right-click the Vocet icon next to the clock > Quit Vocet), then try again.'
        }
        Write-Host ''
        Write-Host 'Vocet is open. Please quit it first:' -ForegroundColor Yellow
        Write-Host '  right-click the Vocet icon next to the clock (click the ^ arrow if you'
        Write-Host '  don''t see it), then choose "Quit Vocet".'
        Wait-ForKey 'When Vocet is closed, press any key here to continue.'
    }

    # --- Shortcuts --------------------------------------------------------
    Remove-Shortcut (Join-Path $ProgramsDir 'Vocet.lnk') 'Start menu'
    Remove-Shortcut (Join-Path $DesktopDir 'Vocet.lnk') 'Desktop'

    # --- "Start with Windows" entry written by the app --------------------
    $runKey = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey($RunSubKey, $true)
    if ($runKey) {
        try {
            if ($null -ne $runKey.GetValue($RunValue, $null)) {
                $runKey.DeleteValue($RunValue, $false)
                Write-Host '  Removed the "Start with Windows" entry.'
            }
        }
        finally {
            $runKey.Close()
        }
    }

    # --- Installed apps entry ---------------------------------------------
    $appKey = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey($UninstallSubKey)
    if ($appKey) {
        $appKey.Close()
        [Microsoft.Win32.Registry]::CurrentUser.DeleteSubKeyTree($UninstallSubKey, $false)
        Write-Host '  Removed Vocet from Installed apps.'
    }

    # --- Install folder ---------------------------------------------------
    if (Test-Path -LiteralPath $InstallDir) {
        if ((Split-Path -Leaf $InstallDir) -ne 'Vocet') {
            throw ('Refusing to delete an unexpected folder: ' + $InstallDir)
        }
        Write-Host '  Removing Vocet''s files and speech model (this can take a moment)...'
        try {
            Remove-Item -LiteralPath $InstallDir -Recurse -Force
        }
        catch {
            # Second try with cmd's rd, which copes better with deep folders and slow virus scanners.
            Start-Sleep -Seconds 2
            & cmd.exe /d /c rd /s /q ('"' + $InstallDir + '"') 2>$null
        }
        if (Test-Path -LiteralPath $InstallDir) {
            $exitCode = 1
            Write-Host ''
            Write-Host 'Some of Vocet''s files could not be removed.' -ForegroundColor Yellow
            Write-Host 'Restart your PC, then delete this folder by hand:'
            Write-Host ('  ' + $InstallDir)
        }
        else {
            Write-Host '  Removed Vocet''s files.'
        }
    }

    # --- Settings and history ---------------------------------------------
    if (Test-Path -LiteralPath $DataDir) {
        $delete = $false
        if ($RemoveData) {
            $delete = $true
        }
        elseif (-not $KeepData -and -not $NoPause) {
            Write-Host ''
            $answer = Read-Host 'Also delete your Vocet settings, dictionary, snippets and history? Type Y for yes or N for no, then press Enter [N]'
            if ($answer -match '^\s*(y|yes)\s*$') {
                $delete = $true
            }
        }
        if ($delete) {
            Remove-Item -LiteralPath $DataDir -Recurse -Force
            Write-Host '  Deleted your settings and history.'
        }
        else {
            Write-Host ('  Kept your settings and history in ' + $DataDir)
        }
    }

    Write-Host ''
    if ($exitCode -eq 0) {
        Write-Host 'Vocet is uninstalled.' -ForegroundColor Green
    }
    $started = $StartedFrom.TrimEnd('\')
    if ($started -and -not [string]::Equals($started, $InstallDir, [StringComparison]::OrdinalIgnoreCase) -and
        (Test-Path -LiteralPath (Join-Path $started 'vocet.pyw'))) {
        Write-Host ('You can also delete the Vocet folder you ran this from: ' + $started)
    }
    Write-Host 'A helper tool called uv was left installed. To remove it too, run: uv self uninstall'
}
catch {
    $exitCode = 1
    Write-Host ''
    Write-Host ('Vocet could not be fully uninstalled: ' + $_.Exception.Message) -ForegroundColor Red
}
finally {
    if ($Relaunched) {
        Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue
    }
}

Wait-ForKey 'Press any key to close this window.'
exit $exitCode
