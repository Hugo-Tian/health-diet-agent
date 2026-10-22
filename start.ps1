param([switch]$Lan, [int]$Port=8000)
$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
$pythonPath=Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw '请先运行 setup.ps1 安装依赖。' }
if (-not (Test-Path -LiteralPath 'frontend\dist\index.html')) { throw '请先运行 setup.ps1 构建前端。' }
Set-Location (Join-Path $PSScriptRoot 'backend')
& $pythonPath -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw '数据库迁移失败' }
& $pythonPath -m app.seed
if ($LASTEXITCODE -ne 0) { throw '参考食物库初始化失败' }
$listenAddress=if ($Lan) { '0.0.0.0' } else { '127.0.0.1' }
Write-Host "打开 http://localhost:$Port ，按 Ctrl+C 停止。"
if ($Lan) { Write-Host '局域网模式已启用：仅在可信私有网络测试，手机访问本机局域网 IP 和同一端口。' }
& $pythonPath -m uvicorn app.main:app --host $listenAddress --port $Port --no-access-log
