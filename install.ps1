#Requires -Version 5.1
<#
.SYNOPSIS
    Installs Vocet (offline dictation for Windows) for the current Windows user.
.DESCRIPTION
    Double-click install.cmd to run this. It copies Vocet to %LOCALAPPDATA%\Programs\Vocet,
    sets up its Python libraries with uv, adds Start menu and Desktop shortcuts and an entry
    in Settings > Apps > Installed apps, then starts Vocet. No administrator rights needed.

    Running it again from a newer download updates Vocet in place. The speech model
    (models\ in the install folder) and your settings and history (%LOCALAPPDATA%\Vocet)
    are kept. The details of every run are written to %LOCALAPPDATA%\Vocet\install.log.

    The Test* parameters are for automated tests only: they install into other folders and
    under another registry name, so a test can never touch a real install. Give all five or none.
#>
[CmdletBinding()]
param(
    [string]$TestInstallDir,
    [string]$TestDataDir,
    [string]$TestProgramsDir,
    [string]$TestDesktopDir,
    [string]$TestRegistryName,
    # Don't start Vocet at the end.
    [switch]$NoLaunch,
    # Never wait for a key press (for automated runs).
    [switch]$NoPause
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Source = $PSScriptRoot
$TotalSteps = 4
$IssuesUrl = 'https://github.com/KMGSL67/vocet/issues'
$script:FriendlyMessage = $null
$script:FriendlyAdvice = $null
$script:LogFile = $null

# --- Helpers -------------------------------------------------------------

function Get-FullPath {
    param([string]$Path)
    return [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
}

function Write-Log {
    param([string]$Text)
    if (-not $script:LogFile) {
        return
    }
    $line = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '  ' + $Text + [Environment]::NewLine
    try {
        [System.IO.File]::AppendAllText($script:LogFile, $line, [System.Text.Encoding]::UTF8)
    }
    catch {
        # Logging must never stop the install.
    }
}

function Say {
    param([string]$Text, [string]$Color)
    if ($Color) {
        Write-Host $Text -ForegroundColor $Color
    }
    else {
        Write-Host $Text
    }
    Write-Log $Text
}

function Write-Step {
    param([int]$Number, [string]$Text)
    Write-Host ''
    Say ('Step ' + $Number + ' of ' + $TotalSteps + ': ' + $Text) 'Cyan'
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

function Stop-Friendly {
    # Stops the install with a plain message for the user. Details go to the log only.
    param([string]$Message, [string]$Advice, [string]$Detail)
    $script:FriendlyMessage = $Message
    $script:FriendlyAdvice = $Advice
    if ($Detail) {
        Write-Log ('Detail: ' + $Detail)
    }
    throw ('Install stopped: ' + $Message)
}

function Test-DiskFullError {
    param($Exception)
    $e = $Exception
    while ($e) {
        # ERROR_DISK_FULL (112) and ERROR_HANDLE_DISK_FULL (39)
        if ($e.HResult -eq -2147024784 -or $e.HResult -eq -2147024857) {
            return $true
        }
        $e = $e.InnerException
    }
    return $false
}

function Test-InsideZip {
    # True when this script runs from inside a ZIP (Windows extracts a single file to a temp folder)
    # instead of from a folder the user extracted.
    param([string]$Dir)
    $d = $Dir.TrimEnd('\') + '\'
    if ($d.IndexOf('.zip\', [StringComparison]::OrdinalIgnoreCase) -ge 0) {
        return $true
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Dir 'vocet') -PathType Container)) {
        return $true
    }
    $temps = @($env:TEMP, $env:TMP, [System.IO.Path]::GetTempPath())
    if ($env:LOCALAPPDATA) {
        $temps += (Join-Path $env:LOCALAPPDATA 'Temp')
    }
    if ($env:SystemRoot) {
        $temps += (Join-Path $env:SystemRoot 'Temp')
    }
    foreach ($t in $temps) {
        if ($t) {
            $prefix = $t.TrimEnd('\') + '\'
            if ($d.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
                return $true
            }
        }
    }
    return $false
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
        Write-Log ('Could not list processes: ' + $_.Exception.Message)
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

function Wait-VocetClosed {
    param([string]$Dir)
    while ($true) {
        $running = @(Get-VocetProcess $Dir)
        if ($running.Count -eq 0) {
            return
        }
        Write-Log ('Vocet is running from the install folder, process id(s): ' + (($running | ForEach-Object { $_.ProcessId }) -join ', '))
        if ($NoPause) {
            Stop-Friendly 'Vocet is open.' 'Quit Vocet (right-click the Vocet icon next to the clock > Quit Vocet), then try again.'
        }
        Write-Host ''
        Write-Host 'Vocet is open. Please quit it first:' -ForegroundColor Yellow
        Write-Host '  right-click the Vocet icon next to the clock (click the ^ arrow if you'
        Write-Host '  don''t see it), then choose "Quit Vocet".'
        Wait-ForKey 'When Vocet is closed, press any key here to continue.'
    }
}

function Find-Uv {
    # Returns the path to uv.exe, or $null if not found.
    $cmd = Get-Command uv -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($cmd) {
        return $cmd.Source
    }
    $candidate = Join-Path $env:USERPROFILE '.local\bin\uv.exe'
    if (Test-Path -LiteralPath $candidate) {
        return $candidate
    }
    return $null
}

function Invoke-Logged {
    # Runs a program with its output going to the log, printing a dot every few seconds
    # so the user can see it's still working. Returns @{ Code; Output }.
    param([string]$FilePath, [string]$Arguments, [string]$WorkingDirectory)
    $out = [System.IO.Path]::GetTempFileName()
    $err = [System.IO.Path]::GetTempFileName()
    try {
        Write-Log ('Running: "' + $FilePath + '" ' + $Arguments)
        $p = Start-Process -FilePath $FilePath -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory `
            -NoNewWindow -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
        $null = $p.Handle   # keeps ExitCode available after the process ends (Windows PowerShell quirk)
        $dots = 0
        while (-not $p.WaitForExit(3000)) {
            Write-Host -NoNewline '.'
            $dots++
            if ($dots % 60 -eq 0) {
                Write-Host ''
            }
        }
        $p.WaitForExit()
        if ($dots -gt 0) {
            Write-Host ''
        }
        $text = ''
        foreach ($f in @($out, $err)) {
            $part = [System.IO.File]::ReadAllText($f, [System.Text.Encoding]::UTF8)
            if ($part) {
                $text += $part
            }
        }
        Write-Log ('Exit code ' + $p.ExitCode + '. Output:' + [Environment]::NewLine + $text)
        return @{ Code = $p.ExitCode; Output = $text }
    }
    finally {
        Remove-Item -LiteralPath $out, $err -Force -ErrorAction SilentlyContinue
    }
}

function Get-ProblemKind {
    # Sorts a failed download or setup into: network, disk, inuse or other.
    param([string]$Text)
    if ($Text -match '(?i)os error 112|not enough space|no space left|disk is full') {
        return 'disk'
    }
    if ($Text -match '(?i)dns error|failed to lookup address|no such host|os error 1100[1-4]|os error 1006[01]|error sending request|could not connect|unable to connect|connection (was )?(refused|reset|closed)|timed out|tcp connect error|failed to fetch|failed to download|network is unreachable|remote name could not be resolved|underlying connection was closed|certificate') {
        return 'network'
    }
    if ($Text -match '(?i)os error 32|os error 5\b|being used by another process|access is denied') {
        return 'inuse'
    }
    return 'other'
}

function Stop-ForProblem {
    param([string]$Kind, [string]$What)
    switch ($Kind) {
        'network' {
            Stop-Friendly ($What + ' because Vocet couldn''t reach the internet.') 'Check that you''re connected to the internet (on a work PC, downloads may be blocked), then double-click install.cmd again.'
        }
        'disk' {
            Stop-Friendly ($What + ' because your PC is out of disk space.') 'Free up at least 2 GB (for example, empty the Recycle Bin or delete old downloads), then double-click install.cmd again.'
        }
        'inuse' {
            Stop-Friendly ($What + ' because some of its files are in use.') 'Quit Vocet if it''s open, restart your PC if needed, then double-click install.cmd again.'
        }
        default {
            Stop-Friendly ($What + '.') ('Please double-click install.cmd again. If it keeps happening, report it at ' + $IssuesUrl + ' and attach the log file.')
        }
    }
}

function New-Shortcut {
    param([string]$Path, [string]$Target, [string]$Arguments, [string]$WorkDir, [string]$Icon)
    $shell = New-Object -ComObject WScript.Shell
    try {
        $lnk = $shell.CreateShortcut($Path)
        $lnk.TargetPath = $Target
        $lnk.Arguments = $Arguments
        $lnk.WorkingDirectory = $WorkDir
        if ($Icon -and (Test-Path -LiteralPath $Icon)) {
            $lnk.IconLocation = $Icon + ',0'
        }
        $lnk.Description = 'Vocet: offline dictation. Hold Ctrl + Win and speak.'
        $lnk.Save()
    }
    finally {
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($shell)
    }
}

function Get-FolderSizeKB {
    param([string]$Dir)
    try {
        $sum = (Get-ChildItem -LiteralPath $Dir -Recurse -File -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
        if (-not $sum) {
            return 0
        }
        return [int][Math]::Min([Math]::Round($sum / 1KB), [int]::MaxValue)
    }
    catch {
        return 0
    }
}

# --- Where things go -------------------------------------------------------

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
    $DisplayName = 'Vocet (test)'
}
else {
    $InstallDir = Join-Path $env:LOCALAPPDATA 'Programs\Vocet'
    $DataDir = Join-Path $env:LOCALAPPDATA 'Vocet'
    $ProgramsDir = [Environment]::GetFolderPath('Programs')
    $DesktopDir = [Environment]::GetFolderPath('Desktop')
    $RegName = 'Vocet'
    $DisplayName = 'Vocet'
}
$UninstallSubKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\' + $RegName
$RunSubKey = 'Software\Microsoft\Windows\CurrentVersion\Run'
$RunValue = $RegName   # the app's "Start with Windows" value (vocet/settings.py RUN_VALUE)
$Entry = Join-Path $InstallDir 'vocet.pyw'
$IconPath = Join-Path $InstallDir 'assets\vocet.ico'

try {
    $Host.UI.RawUI.WindowTitle = 'Vocet installer'
}
catch {
    # Not a console window: no title to set.
}

# --- Run from inside the ZIP? --------------------------------------------

if (Test-InsideZip $Source) {
    Write-Host ''
    Write-Host '  ==============================================================' -ForegroundColor Yellow
    Write-Host ''
    Write-Host '     Please unzip Vocet first.' -ForegroundColor Yellow
    Write-Host ''
    Write-Host '     1. Close this window.'
    Write-Host '     2. Right-click the Vocet ZIP file (in your Downloads folder)'
    Write-Host '        and choose "Extract All", then "Extract".'
    Write-Host '     3. In the new folder, double-click install.cmd.'
    Write-Host ''
    Write-Host '  ==============================================================' -ForegroundColor Yellow
    Wait-ForKey 'Press any key to close this window.'
    exit 2
}

# --- Install ---------------------------------------------------------------

$exitCode = 0
try {
    if (-not (Test-Path -LiteralPath $DataDir)) {
        [void][System.IO.Directory]::CreateDirectory($DataDir)
    }
    $script:LogFile = Join-Path $DataDir 'install.log'
    [System.IO.File]::WriteAllText($script:LogFile, '', [System.Text.Encoding]::UTF8)

    $version = '0.0.0'
    $pyproject = Join-Path $Source 'pyproject.toml'
    if (Test-Path -LiteralPath $pyproject) {
        foreach ($line in [System.IO.File]::ReadAllLines($pyproject)) {
            if ($line -match '^\s*version\s*=\s*"([^"]+)"') {
                $version = $Matches[1]
                break
            }
        }
    }

    Write-Host ''
    Say ('Installing Vocet ' + $version) 'Green'
    Write-Log ('Source: ' + $Source)
    Write-Log ('Install folder: ' + $InstallDir)
    Write-Log ('Data folder: ' + $DataDir)
    Write-Log ('Start menu folder: ' + $ProgramsDir)
    Write-Log ('Desktop folder: ' + $DesktopDir)
    Write-Log ('Registry name: ' + $RegName + $(if ($TestMode) { ' (test mode)' } else { '' }))
    Write-Log ('Windows ' + [Environment]::OSVersion.Version.ToString() + ', PowerShell ' + $PSVersionTable.PSVersion.ToString())

    # --- Step 1: checks ----------------------------------------------------
    Write-Step 1 'Checking your PC...'
    if (-not [Environment]::Is64BitOperatingSystem) {
        Stop-Friendly 'Vocet needs 64-bit Windows, and this PC has 32-bit Windows.' 'Unfortunately Vocet can''t run on this PC.'
    }
    $osVersion = [Environment]::OSVersion.Version
    if ($osVersion.Major -lt 10) {
        Stop-Friendly 'Vocet needs Windows 10 or 11.' 'Unfortunately Vocet can''t run on this version of Windows.'
    }
    foreach ($needed in @('pyproject.toml', 'uv.lock', 'vocet.pyw', 'uninstall.ps1')) {
        if (-not (Test-Path -LiteralPath (Join-Path $Source $needed))) {
            Stop-Friendly ('Part of Vocet is missing from this folder (' + $needed + ').') 'Download Vocet again, unzip it with "Extract All", and double-click install.cmd in the new folder.'
        }
    }

    $hasEnv = Test-Path -LiteralPath (Join-Path $InstallDir '.venv')
    $needGB = 2
    if ($hasEnv) {
        $needGB = 0.5
    }
    try {
        $drive = New-Object System.IO.DriveInfo ([System.IO.Path]::GetPathRoot($InstallDir))
        $freeGB = [Math]::Round($drive.AvailableFreeSpace / 1GB, 1)
        Write-Log ('Free space on ' + $drive.Name + ': ' + $freeGB + ' GB')
    }
    catch {
        $freeGB = $null
        Write-Log ('Could not check free space: ' + $_.Exception.Message)
    }
    if ($null -ne $freeGB -and $freeGB -lt $needGB) {
        Stop-Friendly ('Your PC is almost out of disk space (' + $freeGB + ' GB free; Vocet needs about 2 GB).') 'Free up some space (for example, empty the Recycle Bin or delete old downloads), then double-click install.cmd again.'
    }

    Wait-VocetClosed $InstallDir
    Say '  Everything looks fine.'

    # --- Step 2: copy ------------------------------------------------------
    Write-Step 2 'Copying Vocet to your PC...'
    $sameFolder = [string]::Equals((Get-FullPath $Source), $InstallDir, [StringComparison]::OrdinalIgnoreCase)
    $keep = @('.venv', 'models')                                                  # never deleted on update
    $skip = @('.venv', 'models', '.git', '.pytest_cache', '__pycache__')   # never copied
    try {
        if ($sameFolder) {
            Write-Log 'Running from the install folder itself: nothing to copy.'
        }
        else {
            if (-not (Test-Path -LiteralPath $InstallDir)) {
                [void][System.IO.Directory]::CreateDirectory($InstallDir)
            }
            # Remove the previous version's files (so deleted files don't linger), keeping .venv and models.
            foreach ($old in @(Get-ChildItem -LiteralPath $InstallDir -Force)) {
                if ($keep -notcontains $old.Name) {
                    Remove-Item -LiteralPath $old.FullName -Recurse -Force
                }
            }
            foreach ($item in @(Get-ChildItem -LiteralPath $Source -Force)) {
                if ($skip -notcontains $item.Name) {
                    Copy-Item -LiteralPath $item.FullName -Destination $InstallDir -Recurse -Force
                }
            }
            foreach ($cache in @(Get-ChildItem -LiteralPath (Join-Path $InstallDir 'vocet') -Recurse -Directory -Force -Filter '__pycache__')) {
                Remove-Item -LiteralPath $cache.FullName -Recurse -Force
            }
            # Upgrading from an older Vocet that lived in this folder: reuse its speech model.
            $oldModels = Join-Path $Source 'models'
            $newModels = Join-Path $InstallDir 'models'
            if ((Test-Path -LiteralPath $oldModels -PathType Container) -and -not (Test-Path -LiteralPath $newModels)) {
                Say '  Reusing the speech model you already downloaded...'
                Copy-Item -LiteralPath $oldModels -Destination $InstallDir -Recurse -Force
            }
            Write-Log ('Copied the app files to ' + $InstallDir)
        }
        # Files from a downloaded ZIP carry a "came from the internet" mark; remove it from Vocet's
        # own files so Windows doesn't warn about each of them.
        foreach ($item in @(Get-ChildItem -LiteralPath $InstallDir -Force)) {
            if ($keep -notcontains $item.Name) {
                if ($item.PSIsContainer) {
                    Get-ChildItem -LiteralPath $item.FullName -Recurse -File -Force | Unblock-File
                }
                else {
                    Unblock-File -LiteralPath $item.FullName
                }
            }
        }
    }
    catch {
        Write-Log ('Copy failed: ' + $_.Exception.ToString())
        if (Test-DiskFullError $_.Exception) {
            Stop-ForProblem 'disk' 'Vocet could not be copied'
        }
        if ($_.Exception -is [System.UnauthorizedAccessException] -or $_.Exception -is [System.IO.IOException]) {
            Stop-ForProblem 'inuse' 'Vocet could not be copied'
        }
        throw
    }
    Say ('  Vocet is in ' + $InstallDir)

    # --- Step 3: Python libraries ------------------------------------------
    Write-Step 3 'Downloading Vocet''s parts. This can take a few minutes...'
    $uv = Find-Uv
    if (-not $uv) {
        Say '  Getting a helper tool called uv (one time)...'
        $psExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
        # Astral's documented installer, in its own process so this script's strict mode doesn't apply to it.
        $uvInstall = '-NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor 3072; irm https://astral.sh/uv/install.ps1 | iex"'
        $r = Invoke-Logged $psExe $uvInstall ([System.IO.Path]::GetTempPath())
        $localBin = Join-Path $env:USERPROFILE '.local\bin'
        if (($env:Path -split ';') -notcontains $localBin) {
            $env:Path = $localBin + ';' + $env:Path
        }
        $uv = Find-Uv
        if (-not $uv) {
            Stop-ForProblem (Get-ProblemKind $r.Output) 'A helper tool Vocet needs (uv) could not be installed'
        }
    }
    Write-Log ('Using uv at ' + $uv)

    # Use a Python that uv manages itself, so a Microsoft Store or other Python on the PC can't get in the way.
    $env:UV_PYTHON_PREFERENCE = 'only-managed'
    Remove-Item Env:UV_PROJECT_ENVIRONMENT -ErrorAction SilentlyContinue
    Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue
    $r = Invoke-Logged $uv 'sync --frozen --no-dev' $InstallDir
    if ($r.Code -ne 0) {
        Stop-ForProblem (Get-ProblemKind $r.Output) 'Vocet''s parts could not be downloaded'
    }

    # Python's own windowless pythonw.exe (see vocet.pyw for why not the .venv copy).
    $cfg = Join-Path $InstallDir '.venv\pyvenv.cfg'
    $homeDir = $null
    if (Test-Path -LiteralPath $cfg) {
        foreach ($line in [System.IO.File]::ReadAllLines($cfg)) {
            if ($line -match '^\s*home\s*=\s*(.+?)\s*$') {
                $homeDir = $Matches[1]
                break
            }
        }
    }
    $pythonw = $null
    if ($homeDir) {
        $pythonw = Join-Path $homeDir 'pythonw.exe'
    }
    if (-not $pythonw -or -not (Test-Path -LiteralPath $pythonw)) {
        Stop-Friendly 'Vocet''s parts were downloaded, but Python''s launcher is missing.' ('Please double-click install.cmd again. If it keeps happening, report it at ' + $IssuesUrl + ' and attach the log file.') ('pyvenv.cfg home: ' + $homeDir)
    }
    Write-Log ('pythonw: ' + $pythonw)
    Say '  Done.'

    # --- Step 4: shortcuts and Installed apps ------------------------------
    Write-Step 4 'Adding Vocet to the Start menu, the desktop and Installed apps...'
    $arguments = '"' + $Entry + '"'
    foreach ($dir in @($ProgramsDir, $DesktopDir)) {
        if (-not (Test-Path -LiteralPath $dir)) {
            [void][System.IO.Directory]::CreateDirectory($dir)
        }
        $lnkPath = Join-Path $dir 'Vocet.lnk'
        New-Shortcut -Path $lnkPath -Target $pythonw -Arguments $arguments -WorkDir $InstallDir -Icon $IconPath
        Write-Log ('Shortcut: ' + $lnkPath)
    }

    $psExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $uninstallCmd = '"' + $psExe + '" -NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $InstallDir 'uninstall.ps1') + '"'
    if ($TestMode) {
        $uninstallCmd += ' -TestInstallDir "' + $InstallDir + '" -TestDataDir "' + $DataDir + '" -TestProgramsDir "' + $ProgramsDir +
            '" -TestDesktopDir "' + $DesktopDir + '" -TestRegistryName "' + $RegName + '"'
    }
    $key = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($UninstallSubKey)
    try {
        $sz = [Microsoft.Win32.RegistryValueKind]::String
        $dw = [Microsoft.Win32.RegistryValueKind]::DWord
        $key.SetValue('DisplayName', $DisplayName, $sz)
        $key.SetValue('DisplayVersion', $version, $sz)
        $key.SetValue('Publisher', 'KMGSL67', $sz)
        $key.SetValue('DisplayIcon', $IconPath, $sz)
        $key.SetValue('InstallLocation', $InstallDir, $sz)
        $key.SetValue('UninstallString', $uninstallCmd, $sz)
        $key.SetValue('URLInfoAbout', 'https://github.com/KMGSL67/vocet', $sz)
        $key.SetValue('InstallDate', (Get-Date -Format 'yyyyMMdd'), $sz)
        $key.SetValue('EstimatedSize', (Get-FolderSizeKB $InstallDir), $dw)
        $key.SetValue('NoModify', 1, $dw)
        $key.SetValue('NoRepair', 1, $dw)
    }
    finally {
        $key.Close()
    }
    Write-Log ('Registered HKCU\' + $UninstallSubKey)

    # If "Start with Windows" was on for a Vocet in another folder (an older install), point it here.
    $runKey = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey($RunSubKey, $true)
    if ($runKey) {
        try {
            $current = [string]$runKey.GetValue($RunValue, '')
            $wanted = '"' + $pythonw + '" "' + $Entry + '"'
            if ($current -and $current -match '(?i)vocet\.pyw' -and $current -ne $wanted) {
                $runKey.SetValue($RunValue, $wanted, [Microsoft.Win32.RegistryValueKind]::String)
                Write-Log ('Updated the "Start with Windows" entry from: ' + $current)
            }
        }
        finally {
            $runKey.Close()
        }
    }
    Say '  Done.'

    # --- Done --------------------------------------------------------------
    Write-Host ''
    Say 'Vocet is installed!' 'Green'
    Write-Host ''
    if ($NoLaunch) {
        Say 'Open Vocet from the Start menu or your desktop. Then hold Ctrl + Win and speak.'
    }
    else {
        Start-Process -FilePath $pythonw -ArgumentList $arguments -WorkingDirectory $InstallDir
        Write-Log 'Started Vocet.'
        Say 'Vocet is opening. Hold Ctrl + Win and speak.'
    }
    Say 'The first time, Vocet asks to download its speech model (about 0.8 GB, one time).'
    Say 'Next time, find Vocet in the Start menu or on your desktop.'
    Write-Host ''
    Write-Host 'You can close this window.'
}
catch {
    $exitCode = 1
    Write-Log ('ERROR: ' + $_.Exception.ToString())
    Write-Log ('At: ' + $_.ScriptStackTrace)
    Write-Host ''
    if (-not $script:FriendlyMessage -and (Test-DiskFullError $_.Exception)) {
        $script:FriendlyMessage = 'Vocet could not be installed because your PC is out of disk space.'
        $script:FriendlyAdvice = 'Free up at least 2 GB (for example, empty the Recycle Bin or delete old downloads), then double-click install.cmd again.'
    }
    if ($script:FriendlyMessage) {
        Write-Host $script:FriendlyMessage -ForegroundColor Red
        Write-Host $script:FriendlyAdvice
    }
    else {
        Write-Host 'Vocet could not be installed: something unexpected went wrong.' -ForegroundColor Red
        Write-Host ('(' + $_.Exception.Message + ')')
        Write-Host ('Please double-click install.cmd again. If it keeps happening, report it at ' + $IssuesUrl + ' and attach the log file.')
    }
    if ($script:LogFile) {
        Write-Host ''
        Write-Host ('The details are in this file: ' + $script:LogFile)
    }
}

Wait-ForKey 'Press any key to close this window.'
exit $exitCode
