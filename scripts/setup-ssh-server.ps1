# Windows OpenSSH Server provisioning for the Web Terminal target (P0, ADR-0031)
# Usage (elevated):  powershell -ExecutionPolicy Bypass -File scripts\setup-ssh-server.ps1
# Idempotent: safe to re-run; only adds, never overwrites existing settings.
$ErrorActionPreference = "Stop"

# 0. Require elevation
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "Please run this script as Administrator (right-click PowerShell -> Run as administrator)."
    exit 1
}

# 1. Install OpenSSH Server (optional feature, Windows 10 1809+ / Server 2019+)
if (-not (Test-Path "$env:WINDIR\System32\OpenSSH\sshd.exe")) {
    Write-Host "==> Installing OpenSSH.Server optional feature (requires network)..."
    Add-WindowsCapability -Online -Name "OpenSSH.Server~~~~0.0.1.0" | Out-Null
} else {
    Write-Host "==> OpenSSH Server already installed"
}

# 2. Service autostart + start
Set-Service -Name sshd -StartupType Automatic
if ((Get-Service sshd).Status -ne "Running") { Start-Service sshd }
Write-Host "==> sshd service: $((Get-Service sshd).Status) / start type $((Get-Service sshd).StartType)"

# 3. Firewall rule for port 22 (usually created by the capability install; ensure anyway)
if (-not (Get-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -DisplayName "OpenSSH Server (sshd)" -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 | Out-Null
    Write-Host "==> Created firewall rule OpenSSH-Server-In-TCP"
}

# 4. Backend keypair (for SSHwifty / future Human Terminal); public key goes to authorized_keys
$repoRoot = Split-Path $PSScriptRoot -Parent
$keyDir = Join-Path $repoRoot "data\private\sshwifty\ssh"
$keyPath = Join-Path $keyDir "id_ed25519"
New-Item -ItemType Directory -Force -Path $keyDir | Out-Null
if (-not (Test-Path $keyPath)) {
    ssh-keygen -t ed25519 -N '""' -f $keyPath | Out-Null
    Write-Host "==> Generated backend key: $keyPath"
} else {
    Write-Host "==> Backend key already exists: $keyPath"
}
$pubLine = (Get-Content "$keyPath.pub" -Raw).Trim()

# 5. Install public key (admin -> administrators_authorized_keys with strict ACL; else %USERPROFILE%\.ssh)
if ($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $authKeys = "C:\ProgramData\ssh\administrators_authorized_keys"
    New-Item -ItemType Directory -Force -Path (Split-Path $authKeys) | Out-Null
    if (-not (Test-Path $authKeys)) { New-Item -ItemType File -Path $authKeys | Out-Null }
    if ((Get-Content $authKeys -Raw -ErrorAction SilentlyContinue) -notmatch [regex]::Escape($pubLine)) {
        Add-Content -Path $authKeys -Value $pubLine
        icacls $authKeys /inheritance:r /grant "SYSTEM:F" /grant "Administrators:F" | Out-Null
        Write-Host "==> Public key added to administrators_authorized_keys (ACL: SYSTEM/Administrators only)"
    } else {
        Write-Host "==> Public key already in administrators_authorized_keys"
    }
} else {
    $authKeys = Join-Path $env:USERPROFILE ".ssh\authorized_keys"
    New-Item -ItemType Directory -Force -Path (Split-Path $authKeys) | Out-Null
    if (-not (Test-Path $authKeys)) { New-Item -ItemType File -Path $authKeys | Out-Null }
    if ((Get-Content $authKeys -Raw -ErrorAction SilentlyContinue) -notmatch [regex]::Escape($pubLine)) {
        Add-Content -Path $authKeys -Value $pubLine
        Write-Host "==> Public key added to $authKeys"
    } else {
        Write-Host "==> Public key already in $authKeys"
    }
}

# 6. Default shell (PowerShell; same environment as the supervisor, agent CLIs on PATH)
$defaultShell = "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
New-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShell -Value $defaultShell -PropertyType String -Force | Out-Null
Write-Host "==> Default shell: $defaultShell"

Write-Host ""
Write-Host "Done. Verify: ssh $env:USERNAME@localhost"
Write-Host "Browser entry: http://ssh.localhost (SharedKey in .env -> SSHWIFTY_SHAREDKEY)"
Write-Host "Backend private key (paste into SSHwifty Private Key field): $keyPath"
