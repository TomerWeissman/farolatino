# Build FaroAI for Windows.
#
# Usage (PowerShell):
#   .\packaging\build_windows.ps1
#
# Output:
#   dist\FaroAI\        — onedir PyInstaller bundle (uncompressed)
#   dist\FaroAI-Setup-vX.Y.Z.exe — NSIS installer wrapping the bundle
#
# Prerequisites (the GitHub Actions Windows runner has these via choco):
#   - Python 3.12 on PATH
#   - NSIS (makensis on PATH or at C:\Program Files (x86)\NSIS\makensis.exe)
#   - Node.js (for the frontend build)
#
# Local Windows builds: install via
#   choco install python312 nsis nodejs

$ErrorActionPreference = "Stop"

# Project root = parent of this script's directory.
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$BuildVenv = Join-Path $Root "venv-py312"

# 1. Build venv (Python 3.12). Created idempotently so subsequent
#    builds skip the install step. Same pattern as build_mac.sh.
if (-not (Test-Path $BuildVenv)) {
    Write-Host "==> Creating $BuildVenv (one-time setup)..."
    python -m venv $BuildVenv
    & "$BuildVenv\Scripts\python.exe" -m pip install --quiet --upgrade pip
    & "$BuildVenv\Scripts\pip.exe" install --quiet -r requirements.txt
    & "$BuildVenv\Scripts\pip.exe" install --quiet pyinstaller
}

# 2. Frontend must be built first — the bundled .exe references
#    web\out\ from its data directory.
if (-not (Test-Path "web\out\index.html")) {
    Write-Host "==> Building frontend (web\out)..."
    Push-Location web
    npm run build
    Pop-Location
}

# 3. Read version from core/__init__.py — single source of truth, same
#    one setup_py2app.py reads. Looks for _BUNDLED_VERSION since the
#    runtime __version__ is now a function call, not a literal.
$initText = Get-Content "core\__init__.py" -Raw
$Version = "0.0.0"
if ($initText -match '_BUNDLED_VERSION\s*=\s*[''"]([^''"]+)[''"]') {
    $Version = $Matches[1]
} else {
    # Fail loudly — silently shipping the wrong version is worse than
    # blocking the build. The fallback above is only reached when a
    # future refactor breaks this regex.
    Write-Error "could not parse _BUNDLED_VERSION from core/__init__.py"
    exit 1
}
Write-Host "==> Building FaroAI v$Version"

# 4. Clean previous build artifacts.
Remove-Item -Recurse -Force build -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "dist\FaroAI" -ErrorAction SilentlyContinue
Remove-Item -Force "dist\FaroAI-Setup-v*.exe" -ErrorAction SilentlyContinue

# 5. Run PyInstaller via the spec file. ~3-5 min on a fresh CI runner.
Write-Host "==> Running PyInstaller..."
& "$BuildVenv\Scripts\pyinstaller.exe" `
    --noconfirm `
    --clean `
    "packaging\farolatino.spec"

if (-not (Test-Path "dist\FaroAI\FaroAI.exe")) {
    Write-Host "==> BUILD FAILED — dist\FaroAI\FaroAI.exe not produced"
    exit 1
}

# 6. Wrap in NSIS installer. Writes to dist\FaroAI-Setup-vX.Y.Z.exe.
Write-Host "==> Building NSIS installer..."
$Makensis = Get-Command makensis -ErrorAction SilentlyContinue
if (-not $Makensis) {
    $Makensis = "C:\Program Files (x86)\NSIS\makensis.exe"
    if (-not (Test-Path $Makensis)) {
        Write-Host "==> NSIS not found. Install via 'choco install nsis' or download from https://nsis.sourceforge.io/"
        exit 1
    }
} else {
    $Makensis = $Makensis.Source
}
& $Makensis "/DVERSION=$Version" "packaging\installer.nsi"

# 7. Report.
$ExeBundle = "dist\FaroAI\FaroAI.exe"
$Installer = "dist\FaroAI-Setup-v$Version.exe"
if (Test-Path $Installer) {
    $InstallerSize = (Get-Item $Installer).Length / 1MB
    $BundleSize = (Get-ChildItem -Recurse "dist\FaroAI" | Measure-Object -Property Length -Sum).Sum / 1MB
    Write-Host ""
    Write-Host "==> Built $Installer ($([Math]::Round($InstallerSize)) MB compressed)"
    Write-Host "    Bundle on disk after install: ~$([Math]::Round($BundleSize)) MB"
    Write-Host "    Test:    .\$ExeBundle"
    Write-Host "    First launch: SmartScreen warns 'unrecognized app' (unsigned)."
    Write-Host "    Click 'More info' -> 'Run anyway' -> install proceeds."
} else {
    Write-Host "==> NSIS BUILD FAILED — $Installer not produced"
    exit 1
}
