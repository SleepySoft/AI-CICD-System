# 把 AISystem 的 *.localhost 子域名固定到 127.0.0.1（Windows hosts）
# 用法：以管理员身份运行 PowerShell，执行 scripts\fix-hosts.ps1
$hostsPath = "$env:SystemRoot\System32\drivers\etc\hosts"
$names = @('app','git','ci','sso','kb','docs','req','vectors','status','browser','llm','term')
$entries = $names | ForEach-Object { "127.0.0.1 $_.localhost" }

$cur = [System.IO.File]::ReadAllText($hostsPath)
$toAdd = $entries | Where-Object { $cur -notmatch [regex]::Escape($_) }
if ($toAdd) {
  # AppendAllLines 以纯追加模式打开，不预读文件（Add-Content 的"流不可读"坑）
  [System.IO.File]::AppendAllText($hostsPath, "`r`n# AISystem local domains`r`n" + ($toAdd -join "`r`n") + "`r`n")
  "added $($toAdd.Count) entries"
} else { "already up to date" }
ipconfig /flushdns | Out-Null
"dns cache flushed. now open http://app.localhost"
