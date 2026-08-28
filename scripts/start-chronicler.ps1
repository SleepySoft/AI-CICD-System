# Chronicler 启动壳（Windows）：行为与直接运行 python -m chronicler serve 完全一致
# （.env 由应用自动加载，ADR-0023）；此脚本仅为加入开机启动项/任务计划提供单一入口。
Set-Location (Split-Path $PSScriptRoot -Parent)   # 仓库根（脚本位置的上一级）
& chronicler\.venv-win\Scripts\python.exe -m chronicler serve
