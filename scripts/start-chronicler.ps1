# Windows 侧启动 Chronicler（读 .env 注入环境后常驻）
Set-Location C:\D\code\AI-CICD-System
Get-Content .env | ForEach-Object {
  if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
  $k, $v = $_ -split '=', 2
  [System.Environment]::SetEnvironmentVariable($k.Trim(), $v.Trim())
}
& chronicler\.venv-win\Scripts\python.exe -m chronicler serve *>> C:\D\code\AI-CICD-System\data\chronicler\supervisor.log
