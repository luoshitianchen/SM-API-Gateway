# 本地质量门禁：静态检查 + 编译 + 单测
$ErrorActionPreference = "Stop"
Write-Host "[1/3] ruff 检查"
python -m ruff check app tests
Write-Host "[2/3] 编译检查"
python -m compileall -q app
Write-Host "[3/3] 单元测试"
python -m pytest tests -q
Write-Host "质量门禁通过"
