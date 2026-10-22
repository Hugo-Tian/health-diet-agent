param([ValidateRange(1024,65535)][int]$Port=8000,[switch]$NoBrowser)
$ErrorActionPreference='Stop'
$projectRoot=$PSScriptRoot
$baseUrl="http://127.0.0.1:$Port"
$mutex=New-Object System.Threading.Mutex($false,"Local\HealthDietAgent-$Port")
$locked=$false
function Test-App {
    try {
        $health=Invoke-RestMethod -Uri "$baseUrl/api/v1/health" -TimeoutSec 2
        return ($health.status -eq 'ok' -and $health.application -eq 'health-diet-agent')
    } catch { return $false }
}
try {
    try { $locked=$mutex.WaitOne(30000) } catch [System.Threading.AbandonedMutexException] { $locked=$true }
    if(-not $locked){throw 'Another launch is in progress. Please try again shortly.'}
    if(Test-App){
        Write-Host "Already running: $baseUrl/assistant"
        if(-not $NoBrowser){Start-Process "$baseUrl/assistant"}
        exit 0
    }
    $listener=Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if($listener){throw "Port $Port is occupied by another or unresponsive service. It was not stopped."}
    if(-not (Test-Path -LiteralPath (Join-Path $projectRoot '.venv\Scripts\python.exe'))){throw 'Python environment missing. Run setup.ps1 in the project first.'}
    if(-not (Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\dist\index.html'))){throw 'Frontend build missing. Run setup.ps1 in the project first.'}
    $logDir=Join-Path $projectRoot 'work\logs'
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    $stamp=Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $outLog=Join-Path $logDir "server-$Port-$stamp.out.log"
    $errLog=Join-Path $logDir "server-$Port-$stamp.err.log"
    $startScript=Join-Path $projectRoot 'start.ps1'
    $child=Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$startScript+'"'),'-Port',$Port) -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
    $ready=$false
    for($attempt=0;$attempt -lt 45;$attempt++){
        if(Test-App){$ready=$true;break}
        if($child.HasExited){break}
        Start-Sleep -Seconds 1
    }
    if(-not $ready){throw "Startup did not become ready. See logs: $errLog"}
    Write-Host "Ready: $baseUrl/assistant"
    Write-Host "Logs: $logDir"
    if(-not $NoBrowser){Start-Process "$baseUrl/assistant"}
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
} finally {
    if($locked){$mutex.ReleaseMutex()}
    $mutex.Dispose()
}
