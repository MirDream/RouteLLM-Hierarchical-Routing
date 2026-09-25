param(
    [switch]$NoPause,
    [switch]$Headless
)

$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$env:LITELLM_LOCAL_MODEL_COST_MAP = 'True'
if (-not $env:OPENAI_API_KEY) {
    $env:OPENAI_API_KEY = 'not-used'
}

function Wait-OnError {
    if (-not $NoPause -and $Host.Name -eq 'ConsoleHost') {
        [void](Read-Host 'Press Enter to exit')
    }
}

function Test-PortAvailable {
    param([int]$Port)
    $listener = $null
    try {
        $listener = [System.Net.Sockets.TcpListener]::new(
            [System.Net.IPAddress]::Loopback,
            $Port
        )
        $listener.Start()
        return $true
    }
    catch {
        return $false
    }
    finally {
        if ($null -ne $listener) {
            $listener.Stop()
        }
    }
}

try {
    $projectRoot = $PSScriptRoot
    $python = Join-Path $projectRoot '.venv\Scripts\python.exe'
    $app = Join-Path $projectRoot 'visual_demo.py'

    Set-Location $projectRoot

    if (-not (Test-Path -LiteralPath $python)) {
        throw "Virtual environment not found.`nPlease run:`n.\setup_windows.ps1"
    }
    if (-not (Test-Path -LiteralPath $app)) {
        throw "Visual demo entry point not found: $app"
    }

    & $python -c 'import streamlit' 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Streamlit is not installed.`nPlease run:`n.\setup_windows.ps1"
    }

    $port = 8501
    if (-not (Test-PortAvailable -Port $port)) {
        $port = 8502
        if (-not (Test-PortAvailable -Port $port)) {
            throw 'Ports 8501 and 8502 are both in use. Close the existing process and retry.'
        }
        Write-Host 'Port 8501 is in use; using 8502 instead.' -ForegroundColor Yellow
    }

    $env:PYTHONPATH = $projectRoot
    $headlessValue = if ($Headless) { 'true' } else { 'false' }
    Write-Host 'Starting RouteLLM classroom visual demo...' -ForegroundColor Cyan
    Write-Host "Local URL: http://localhost:$port" -ForegroundColor Green

    & $python -m streamlit run $app `
        --server.port $port `
        --server.headless $headlessValue `
        --server.fileWatcherType none `
        --browser.gatherUsageStats false
    if ($LASTEXITCODE -ne 0) {
        throw "Streamlit exited with code $LASTEXITCODE"
    }
}
catch {
    Write-Host ''
    Write-Host 'Visual demo failed to start.' -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Yellow
    Wait-OnError
    exit 1
}
