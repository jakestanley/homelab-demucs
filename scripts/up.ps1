param(
    [switch]$Restart
)

$ErrorActionPreference = "Stop"

# --- per-repo config ---
$DefaultServiceName = "homelab-demucs"
$DefaultDisplayName = "homelab-demucs separation API"
$DefaultDescription = "Host-run Demucs separation HTTP service"
$PythonExeEnvKey    = "DEMUCS_PYTHON_EXE"
$PortEnvKey         = "PORT"
$DefaultPort        = "20033"
$AppParameters      = "-m demucs_service.server"
# -----------------------

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

function Get-DotEnvLines {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return @() }
    return @(Get-Content $Path | Where-Object {
        $_ -and ($_ -notmatch '^\s*#') -and ($_ -match '=')
    })
}

function Get-DotEnvValue {
    param([string]$Path, [string]$Key, [string]$Default)
    foreach ($line in (Get-DotEnvLines $Path)) {
        $parts = $line -split '=', 2
        if ($parts.Count -eq 2 -and $parts[0].Trim() -eq $Key) {
            return $parts[1].Trim()
        }
    }
    return $Default
}

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    return ([Security.Principal.WindowsPrincipal]::new($id)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Ensure-FirewallRule {
    param([string]$Port, [string]$RuleName)
    if (-not $Port) { return }
    if (-not (Test-IsAdmin)) {
        Write-Warning "Not elevated; firewall rule for TCP $Port may be missing."
        Write-Host "Run elevated: New-NetFirewallRule -DisplayName `"$RuleName`" -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -Profile Private"
        return
    }
    $existing = Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue
    if (-not $existing) {
        New-NetFirewallRule -DisplayName $RuleName -Direction Inbound -Action Allow `
            -Protocol TCP -LocalPort $Port -Profile Private | Out-Null
    }
}

function Resolve-BootstrapPython {
    param([string]$EnvFile, [string]$EnvKey)
    $candidate = Get-DotEnvValue $EnvFile $EnvKey $null
    if (-not $candidate -and $EnvKey) { $candidate = (Get-Item "Env:$EnvKey" -ErrorAction SilentlyContinue).Value }
    if ($candidate -and (Test-Path $candidate)) { return $candidate }
    $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) { return $py.Source }
    throw "Python interpreter not found. Set $EnvKey in .env to a full path."
}

# --- main ---
$envFile = Join-Path $RepoRoot ".env"
if (-not (Test-Path $envFile)) {
    Write-Warning "Missing .env; copy .env.example to .env and edit before running."
}

$serviceName = Get-DotEnvValue $envFile "NSSM_SERVICE_NAME" $DefaultServiceName
$displayName = Get-DotEnvValue $envFile "NSSM_DISPLAY_NAME" $DefaultDisplayName
$description = Get-DotEnvValue $envFile "NSSM_DESCRIPTION" $DefaultDescription

if (-not (Get-Command nssm -ErrorAction SilentlyContinue)) {
    throw "nssm not found in PATH. Install NSSM and retry."
}

$venvPath   = Join-Path $RepoRoot ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    $bootstrap = Resolve-BootstrapPython -EnvFile $envFile -EnvKey $PythonExeEnvKey
    Write-Host "Creating venv with $bootstrap"
    if ($bootstrap -match 'py(\.exe)?$') {
        & $bootstrap -3 -m venv $venvPath
    } else {
        & $bootstrap -m venv $venvPath
    }
    if (-not (Test-Path $venvPython)) { throw "venv creation failed at $venvPath" }
}

& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
& $venvPython -m pip install -r (Join-Path $RepoRoot "requirements.txt")
& $venvPython -m pip install demucs

$port = Get-DotEnvValue $envFile $PortEnvKey $DefaultPort
Ensure-FirewallRule -Port $port -RuleName "$serviceName ($port)"

$logsDir = Join-Path $RepoRoot "logs"
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

$svc = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if (-not $svc) {
    & nssm install $serviceName $venvPython $AppParameters | Out-Null
}

& nssm set $serviceName Application $venvPython | Out-Null
& nssm set $serviceName AppParameters $AppParameters | Out-Null
& nssm set $serviceName AppDirectory $RepoRoot | Out-Null
& nssm set $serviceName DisplayName $displayName | Out-Null
& nssm set $serviceName Description $description | Out-Null
& nssm set $serviceName AppStdout (Join-Path $logsDir "$serviceName-stdout.log") | Out-Null
& nssm set $serviceName AppStderr (Join-Path $logsDir "$serviceName-stderr.log") | Out-Null

$appEnvLines = @(Get-DotEnvLines $envFile | Where-Object { $_ -notmatch '^\s*NSSM_' })

$venvDemucs = Join-Path (Split-Path $venvPython -Parent) "demucs.exe"
if (Test-Path $venvDemucs) {
    $appEnvLines = @($appEnvLines | Where-Object { $_ -notmatch '^\s*DEMUCS_BIN\s*=' })
    $appEnvLines += "DEMUCS_BIN=$venvDemucs"
}

if ($appEnvLines.Count -gt 0) {
    & nssm set $serviceName AppEnvironmentExtra $appEnvLines | Out-Null
} else {
    & nssm reset $serviceName AppEnvironmentExtra 2>$null | Out-Null
}

$status = (& nssm status $serviceName).Trim()
if ($status -eq "SERVICE_RUNNING") {
    if ($Restart) {
        & nssm restart $serviceName | Out-Null
    }
} else {
    & nssm start $serviceName | Out-Null
}

Write-Host "Service '$serviceName' applied. Status: $((& nssm status $serviceName).Trim())"
