$ErrorActionPreference = "Stop"

$DefaultServiceName = "homelab-demucs"

$RepoRoot = Split-Path -Parent $PSScriptRoot

function Get-DotEnvValue {
    param([string]$Path, [string]$Key, [string]$Default)
    if (-not (Test-Path $Path)) { return $Default }
    foreach ($line in Get-Content $Path) {
        if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
        $parts = $line -split '=', 2
        if ($parts[0].Trim() -eq $Key) { return $parts[1].Trim() }
    }
    return $Default
}

if (-not (Get-Command nssm -ErrorAction SilentlyContinue)) {
    throw "nssm not found in PATH."
}

$serviceName = Get-DotEnvValue (Join-Path $RepoRoot ".env") "NSSM_SERVICE_NAME" $DefaultServiceName

$svc = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if ($null -eq $svc) {
    Write-Host "Service '$serviceName' not installed; nothing to do."
    return
}

& nssm stop $serviceName 2>$null | Out-Null
& nssm remove $serviceName confirm | Out-Null
Write-Host "Service '$serviceName' removed."
