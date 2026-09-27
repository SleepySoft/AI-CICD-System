param([string]$ProfilePath = $PROFILE.CurrentUserAllHosts)
$ErrorActionPreference = 'Stop'
$target = [IO.Path]::GetFullPath($ProfilePath)
$begin = '# BEGIN Chronicler UTF-8'
$end = '# END Chronicler UTF-8'
$utf8 = New-Object Text.UTF8Encoding($false, $true)
$text = ''
if (Test-Path -LiteralPath $target) {
    $bytes = [IO.File]::ReadAllBytes($target)
    try { $text = $utf8.GetString($bytes).TrimStart([char]0xFEFF) }
    catch { $text = [Text.Encoding]::Default.GetString($bytes) }
}
$block = @'
# BEGIN Chronicler UTF-8
$global:OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
if ($null -eq $global:PSDefaultParameterValues) { $global:PSDefaultParameterValues = @{} }
$global:PSDefaultParameterValues['Get-Content:Encoding'] = 'utf8'
$global:PSDefaultParameterValues['Set-Content:Encoding'] = 'utf8'
$global:PSDefaultParameterValues['Add-Content:Encoding'] = 'utf8'
$global:PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'
# END Chronicler UTF-8
'@
if ($text.Contains($begin) -xor $text.Contains($end)) { throw 'Incomplete UTF-8 profile block; inspect profile before retrying.' }
$pattern = '(?s)' + [regex]::Escape($begin) + '.*?' + [regex]::Escape($end)
$updated = if ($text.Contains($begin)) { [regex]::Replace($text, $pattern, [Text.RegularExpressions.MatchEvaluator]{ param($m) $block }) }
           else { $text.TrimEnd() + "`n`n" + $block + "`n" }
if ($updated -eq $text) { Write-Output "UTF-8 profile already configured: $target"; exit 0 }
[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target)) | Out-Null
if (Test-Path -LiteralPath $target) {
    $backup = $target + '.before-chronicler-utf8-' + [DateTime]::Now.ToString('yyyyMMdd-HHmmss-fff')
    Copy-Item -LiteralPath $target -Destination $backup
    Write-Output "Profile backup: $backup"
}
# BOM ensures Windows PowerShell 5.1 can parse an existing profile containing Unicode.
[IO.File]::WriteAllText($target, ($updated -replace "`r`n", "`n"), (New-Object Text.UTF8Encoding($true)))
Write-Output "UTF-8 profile configured: $target"
