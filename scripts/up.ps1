param(
    [string]$PythonExe
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $RepoRoot

function Get-EnvValue {
    param(
        [string]$Path,
        [string]$Key,
        [string]$DefaultValue
    )
    if (!(Test-Path $Path)) {
        return $DefaultValue
    }
    $lines = Get-Content $Path
    foreach ($line in $lines) {
        if ($line.Trim().StartsWith("#") -or !$line.Contains("=")) {
            continue
        }
        $pair = $line.Split("=", 2)
        if ($pair[0].Trim() -eq $Key) {
            return $pair[1].Trim()
        }
    }
    return $DefaultValue
}

function Test-PreflightRepo {
    param([string]$Path, [string]$Name)
    $localWarnings = @()
    if (!(Test-Path $Path)) {
        $localWarnings += "$Name not found at $Path"
        return $localWarnings
    }
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        $localWarnings += "git not available; cannot verify $Name state."
        return $localWarnings
    }
    $isGit = git -C $Path rev-parse --is-inside-work-tree 2>$null
    if ($isGit -ne "true") {
        $localWarnings += "$Name is not a git repository."
        return $localWarnings
    }
    $dirty = git -C $Path status --porcelain
    if ($dirty) {
        $localWarnings += "$Name has uncommitted changes."
    }
    $originHead = git -C $Path symbolic-ref refs/remotes/origin/HEAD 2>$null
    if ($originHead) {
        $defaultBranch = $originHead.Split("/")[-1]
        $currentBranch = git -C $Path rev-parse --abbrev-ref HEAD
        if ($currentBranch -ne $defaultBranch) {
            $localWarnings += "$Name is on $currentBranch, expected $defaultBranch."
        }
        $defaultHead = git -C $Path rev-parse "origin/$defaultBranch" 2>$null
        $currentHead = git -C $Path rev-parse HEAD 2>$null
        if ($defaultHead -and $currentHead -and ($defaultHead -ne $currentHead)) {
            $localWarnings += "$Name is not at origin/$defaultBranch HEAD."
        }
    } else {
        $localWarnings += "$Name has no origin/HEAD to verify default branch."
    }
    return $localWarnings
}

function Confirm-Preflight {
    $answer = Read-Host "Preflight checks raised warnings. Continue? (y/N)"
    if ($answer.ToLower() -ne "y") {
        Write-Host "Aborting startup."
        exit 1
    }
}

$warnings = @()
$infraPath = Join-Path $RepoRoot "..\homelab-infra"
$standardsPath = Join-Path $RepoRoot "..\homelab-standards"
$warnings += Test-PreflightRepo -Path $infraPath -Name "homelab-infra"
$warnings += Test-PreflightRepo -Path $standardsPath -Name "homelab-standards"

if ($warnings.Count -gt 0) {
    foreach ($w in $warnings) {
        if ($w) {
            Write-Warning $w
        }
    }
    Confirm-Preflight
}

$port = Get-EnvValue -Path "$RepoRoot\.env" -Key "PORT" -DefaultValue "20033"
$demucsBin = Get-EnvValue -Path "$RepoRoot\.env" -Key "DEMUCS_BIN" -DefaultValue ""
if (-not $demucsBin -and -not $env:DEMUCS_BIN) {
    $demucsCmd = Get-Command demucs.exe -ErrorAction SilentlyContinue
    if ($demucsCmd -and $demucsCmd.Source) {
        $env:DEMUCS_BIN = $demucsCmd.Source
    }
}
$ruleName = "homelab-demucs-$port"
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")

if ($isAdmin) {
    $existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
    if (-not $existing) {
        New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $port -Profile Private | Out-Null
        Write-Host "Created firewall rule $ruleName."
    }
} else {
    $command = "New-NetFirewallRule -DisplayName `"$ruleName`" -Direction Inbound -Action Allow -Protocol TCP -LocalPort $port -Profile Private"
    Write-Warning "Not running elevated; firewall rule may be missing."
    Write-Host "Run elevated PowerShell:"
    Write-Host $command
}

$pythonCommand = $null
$pythonArgs = @()
if (-not $PythonExe) {
    if ($env:DEMUCS_PYTHON_EXE) {
        $PythonExe = $env:DEMUCS_PYTHON_EXE
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        $PythonExe = "py"
        $pythonArgs = @("-3")
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $PythonExe = "python"
    } else {
        throw "Python interpreter not found. Provide -PythonExe."
    }
}
if ($PythonExe -and -not $pythonCommand) {
    $pythonCommand = $PythonExe
}

if (!(Test-Path "$RepoRoot\.venv")) {
    Write-Host "Creating virtual environment..."
    & $pythonCommand @pythonArgs -m venv "$RepoRoot\.venv"
}

$VenvPython = "$RepoRoot\.venv\Scripts\python.exe"
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r "$RepoRoot\requirements.txt"

Write-Host "Starting Demucs service..."
& $VenvPython -m demucs_service.server
