param(
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$Output = "dist",
    [string]$Python = "",
    [switch]$BundleOnly
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$python = $Python
if (-not $python) { $python = Join-Path $repo "build\chronicler\venv311\Scripts\python.exe" }
if (-not (Test-Path $python)) { throw "缺少 CPython 3.11 构建环境；见 docs/runbooks/build-sealed-chronicler.md" }
$argsList = @((Join-Path $PSScriptRoot "build-chronicler.py"), "--version", $Version, "--output", $Output)
if ($BundleOnly) { $argsList += "--bundle-only" }
& $python @argsList
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }