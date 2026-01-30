param(
    [string]$ServiceName,
    [string]$PythonExe,
    [switch]$Start,
    [switch]$Stop,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $RepoRoot

if (-not $ServiceName) {
    $ServiceName = Split-Path $RepoRoot -Leaf
}

if (-not (Get-Command nssm -ErrorAction SilentlyContinue)) {
    throw "nssm not found on PATH."
}

if (-not $PythonExe -and $env:DEMUCS_PYTHON_EXE) {
    $PythonExe = $env:DEMUCS_PYTHON_EXE
}

$pythonCommand = $null
$pythonArgs = @()
$venvPath = "$RepoRoot\.venv"
if (-not $PythonExe -and -not (Test-Path $venvPath)) {
    $resolved = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($resolved -and $resolved.Source) {
        $PythonExe = $resolved.Source
    }
}
if (-not $PythonExe) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $PythonExe = "py"
        $pythonArgs = @("-3")
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $PythonExe = "python"
    }
}
if ($PythonExe) {
    $pythonCommand = $PythonExe
} else {
    throw "Python interpreter not found. Provide -PythonExe or set DEMUCS_PYTHON_EXE."
}

$logsDir = "$RepoRoot\logs"
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

if (!(Test-Path $venvPath)) {
    Write-Host "Creating virtual environment..."
    & $pythonCommand @pythonArgs -m venv $venvPath
}

$demucsBin = $null
$envFile = Join-Path $RepoRoot ".env"
if (Test-Path $envFile) {
    $demucsLine = Get-Content $envFile | Where-Object { $_ -match "^\s*DEMUCS_BIN\s*=" } | Select-Object -First 1
    if ($demucsLine) {
        $demucsBin = $demucsLine.Split("=", 2)[1].Trim()
    }
}
if (-not $demucsBin -and $env:DEMUCS_BIN) {
    $demucsBin = $env:DEMUCS_BIN
}
if (-not $demucsBin) {
    $demucsCmd = Get-Command demucs.exe -ErrorAction SilentlyContinue
    if ($demucsCmd -and $demucsCmd.Source) {
        $demucsBin = $demucsCmd.Source
    }
}

if ($Uninstall) {
    nssm stop $ServiceName 2>$null | Out-Null
    nssm remove $ServiceName confirm | Out-Null
    Write-Host "Removed service $ServiceName."
    exit 0
}

$app = "powershell.exe"
$appArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$RepoRoot\scripts\up.ps1`""
if ($PythonExe -and $PythonExe -ne "powershell.exe") {
    $appArgs += " -PythonExe `"$PythonExe`""
}

if (-not (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue)) {
    nssm install $ServiceName $app $appArgs | Out-Null
} else {
    nssm set $ServiceName Application $app | Out-Null
    nssm set $ServiceName AppParameters $appArgs | Out-Null
}

nssm set $ServiceName AppDirectory $RepoRoot | Out-Null
nssm set $ServiceName AppStdout "$logsDir\service-stdout.log" | Out-Null
nssm set $ServiceName AppStderr "$logsDir\service-stderr.log" | Out-Null

if ($PythonExe -and $PythonExe -ne "powershell.exe") {
    nssm set $ServiceName AppEnvironmentExtra "DEMUCS_PYTHON_EXE=$PythonExe" | Out-Null
}
if ($demucsBin) {
    nssm set $ServiceName AppEnvironmentExtra "DEMUCS_BIN=$demucsBin" | Out-Null
}

if ($Stop) {
    nssm stop $ServiceName | Out-Null
}

if ($Start) {
    $status = nssm status $ServiceName 2>$null
    if ($status -and $status -ne "STOPPED") {
        nssm restart $ServiceName | Out-Null
    } else {
        nssm start $ServiceName | Out-Null
    }
}

Write-Host "Service $ServiceName configured."
