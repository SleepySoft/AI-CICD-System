param(
    [Parameter(Mandatory = $true)][string]$ReleaseDir,
    [Parameter(Mandatory = $true)][string]$InstallDir,
    [string]$ComponentsDir = ""
)
$ErrorActionPreference = "Stop"
$manifestPath = Join-Path $ReleaseDir "manifest.json"
if (-not (Test-Path $manifestPath)) { throw "不是 Chronicler 发行目录：$ReleaseDir" }
$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
if ($manifest.bundle_only) { throw "bundle-only 目录仅用于验证，不能安装" }
if (-not (Test-Path (Join-Path $ReleaseDir "chronicler.exe"))) { throw "发行目录缺少 chronicler.exe" }
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item (Join-Path $ReleaseDir "*") $InstallDir -Recurse -Force
if (-not (Test-Path (Join-Path $InstallDir ".env"))) {
    Copy-Item (Join-Path $InstallDir ".env.example") (Join-Path $InstallDir ".env")
}
New-Item -ItemType Directory -Force -Path (Join-Path $InstallDir "components") | Out-Null
if ($ComponentsDir) {
    if (-not (Test-Path $ComponentsDir)) { throw "外置组件目录不存在：$ComponentsDir" }
    Copy-Item (Join-Path $ComponentsDir "*") (Join-Path $InstallDir "components") -Recurse -Force
}
Write-Host "Installed: $InstallDir"
Write-Host "Next: edit .env, provision external components/ if needed, then run chronicler.exe serve"