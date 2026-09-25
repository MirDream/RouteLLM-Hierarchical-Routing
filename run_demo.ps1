$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$projectRoot = $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python)) {
    throw "Virtual environment not found.`nPlease run:`n.\setup_windows.ps1"
}

$env:PYTHONPATH = $projectRoot
Push-Location $projectRoot
try {
    & $python (Join-Path $projectRoot 'examples\hierarchical_demo.py')
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
