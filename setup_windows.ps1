$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
Set-Location $projectRoot

$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $pythonCommand) {
    Write-Host 'Python is not installed or not in PATH.' -ForegroundColor Red
    Write-Host 'Please install Python 3.10, 3.11, or 3.12 and rerun setup_windows.ps1.' -ForegroundColor Yellow
    exit 1
}

& $pythonCommand.Source --version
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Python is not installed or not in PATH.' -ForegroundColor Red
    Write-Host 'Please install Python 3.10, 3.11, or 3.12 and rerun setup_windows.ps1.' -ForegroundColor Yellow
    exit 1
}

$venvDir = Join-Path $projectRoot '.venv'
$venvPython = Join-Path $venvDir 'Scripts\python.exe'

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host 'Creating project virtual environment...' -ForegroundColor Cyan
    & $pythonCommand.Source -m venv $venvDir
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host 'Upgrading packaging tools...' -ForegroundColor Cyan
& $venvPython -m pip install --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host 'Installing core and visual demo dependencies...' -ForegroundColor Cyan
& $venvPython -m pip install -r (Join-Path $projectRoot 'requirements-visual-demo.txt')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host 'Installing the local project in editable mode...' -ForegroundColor Cyan
& $venvPython -m pip install --no-deps -e $projectRoot
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$env:PYTHONPATH = $projectRoot
Write-Host 'Running import smoke test...' -ForegroundColor Cyan
& $venvPython -c "import routellm; import streamlit; from routellm.hierarchical_controller import HierarchicalController; from routellm.routers.multimodel_router import MultiModelRouter; from routellm.scheduler.resource_scheduler import ResourceAwareScheduler; print('Import smoke test passed.')"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host 'Running unit tests...' -ForegroundColor Cyan
& $venvPython -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ''
Write-Host 'Setup completed successfully.' -ForegroundColor Green
Write-Host 'Run the classroom demo with:' -ForegroundColor Green
Write-Host '.\run_visual_demo.ps1' -ForegroundColor White
