$ErrorActionPreference = 'Stop'
$backendRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $backendRoot

$pythonPath = Join-Path $backendRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $pythonPath)) {
    throw 'backend/.venv is missing. Create it with a supported Python interpreter first.'
}

& $pythonPath -c 'import fastapi, uvicorn' 2>$null
if ($LASTEXITCODE -ne 0) {
    throw 'FastAPI/Uvicorn dependencies are not installed in backend/.venv.'
}

$bindHost = if ($env:HOST) { $env:HOST } else { '0.0.0.0' }
$port = if ($env:PORT) { [int]$env:PORT } else { 8000 }

& $pythonPath -m uvicorn app.main:app --host $bindHost --port $port
