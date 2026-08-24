# 构建全部工具链镜像（Windows PowerShell，需 Docker Desktop 可用）
# 用法: .\scripts\build-images.ps1 [-Images toolchain-cpp,test-python]
param(
    [string[]]$Images = @("toolchain-cpp", "toolchain-android", "toolchain-node", "test-python", "browsers")
)

Set-Location (Join-Path $PSScriptRoot "..")

foreach ($img in $Images) {
    $path = Join-Path "images" $img
    if (Test-Path $path) {
        Write-Host "==> 构建 aisystem/${img}:latest"
        docker build -t "aisystem/${img}:latest" $path
        if ($LASTEXITCODE -ne 0) { Write-Error "构建失败: $img"; exit 1 }
    } else {
        Write-Error "未知镜像: $img"; exit 1
    }
}
Write-Host "==> 完成。查看: docker images | Select-String aisystem"
