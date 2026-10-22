$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
New-Item -ItemType Directory -Path work -Force | Out-Null
$testDirectory=Join-Path $PSScriptRoot ('work\pytest-'+[guid]::NewGuid().ToString('N'))
Push-Location backend
try {
    & ..\.venv\Scripts\python.exe -m pytest -q --basetemp=$testDirectory
    if ($LASTEXITCODE -ne 0) { throw '后端测试失败' }
} finally { Pop-Location }
Push-Location frontend
try {
    npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw '前端构建失败' }
} finally { Pop-Location }
