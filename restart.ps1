# restart.ps1 - restart frontend (5190) and backend (8000)
param(
  [switch]$InitModels
)

$ErrorActionPreference = "SilentlyContinue"

function Stop-Port([int]$Port) {
  Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
}

function Wait-PortFree([int]$Port) {
  $tries = 0
  while ($tries -lt 10) {
    $listening = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $listening) { return $true }
    Start-Sleep -Milliseconds 500
    $tries++
  }
  return $false
}

Write-Host "== Stop existing servers ==" -ForegroundColor Cyan
Stop-Port 5190
Stop-Port 8000
Wait-PortFree 5190 | Out-Null
Wait-PortFree 8000 | Out-Null
Start-Sleep -Seconds 1

# fallback: taskkill the tree since Stop-Process lacks -T
foreach ($p in 8000, 5190) {
  $owning = (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1).OwningProcess
  if ($owning) { taskkill //F //PID $owning //T > $null 2>&1 }
}

Start-Sleep -Seconds 1
if (Get-NetTCPConnection -LocalPort 5190 -State Listen -ErrorAction SilentlyContinue) { throw "port 5190 still busy" }
if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) { throw "port 8000 still busy" }

Write-Host "== Start backend 8000 ==" -ForegroundColor Cyan
$backend = Start-Process -PassThru -WindowStyle Hidden -FilePath "python" `
  -ArgumentList "-m","uvicorn","app.main:app","--host","0.0.0.0","--port","8000" `
  -WorkingDirectory "E:\bchao-test\backend"
Write-Host "backend PID: $($backend.Id)"

$tries = 0
$backendUp = $false
while ($tries -lt 20) {
  try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/docs" -UseBasicParsing -TimeoutSec 2
    if ($r.StatusCode -eq 200) { $backendUp = $true; break }
  } catch {}
  Start-Sleep -Milliseconds 500; $tries++
}
if ($backendUp) { Write-Host "backend 8000 OK" -ForegroundColor Green }
else { throw "backend start timeout" }

if ($InitModels) {
  Write-Host "init default models..." -ForegroundColor Cyan
  curl.exe -X POST "http://127.0.0.1:8000/api/model/init-defaults"
  Write-Host ""
}

Write-Host "== Start frontend 5190 ==" -ForegroundColor Cyan
$frontend = Start-Process -PassThru -WindowStyle Hidden -FilePath "node" `
  -ArgumentList "E:\bchao-test\frontend\node_modules\vite\bin\vite.js","--port","5190","--strict-port","--host","0.0.0.0" `
  -WorkingDirectory "E:\bchao-test\frontend"
Write-Host "frontend PID: $($frontend.Id)"

$tries = 0
$frontendUp = $false
while ($tries -lt 20) {
  try {
    $r = Invoke-WebRequest -Uri "http://localhost:5190/" -UseBasicParsing -TimeoutSec 2
    if ($r.StatusCode -eq 200) { $frontendUp = $true; break }
  } catch {}
  Start-Sleep -Milliseconds 500; $tries++
}
if ($frontendUp) { Write-Host "frontend 5190 OK" -ForegroundColor Green }
else { throw "frontend start timeout" }

Write-Host ""
Write-Host "== Done ==" -ForegroundColor Cyan
Write-Host "frontend : http://localhost:5190"
Write-Host "backend  : http://127.0.0.1:8000"
Write-Host "backend PID : $($backend.Id)"
Write-Host "frontend PID: $($frontend.Id)"
