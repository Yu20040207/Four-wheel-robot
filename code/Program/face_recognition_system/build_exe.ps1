# OpenMV Web - build exe (PowerShell, UTF-8 safe)
Set-Location $PSScriptRoot

Write-Host "========================================"
Write-Host "  OpenMV Face System - Build EXE"
Write-Host "========================================"
Write-Host ""

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] Python not found. Install Python 3.12 first." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "[1/4] Installing dependencies..."
python -m pip install -r requirements.txt pyinstaller -q
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] pip install failed" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "[2/4] Running PyInstaller (may take 5-15 min)..."
python -m PyInstaller app.spec --clean --noconfirm
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] PyInstaller failed" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "[3/4] Copying runtime files to dist..."
New-Item -ItemType Directory -Force -Path dist | Out-Null
Copy-Item -Force config.ini dist\
if (Test-Path face_data) {
    Copy-Item -Recurse -Force face_data dist\face_data
}
if (Test-Path attendance_data.json) {
    Copy-Item -Force attendance_data.json dist\
}
if (Test-Path garbage.pt) {
    Copy-Item -Force garbage.pt dist\
}
New-Item -ItemType Directory -Force -Path dist\rubbish_photo | Out-Null

Write-Host "[4/4] Done"
Write-Host ""
Write-Host "Output: $PSScriptRoot\dist\OpenMV_FaceSystem.exe"
Write-Host "Edit dist\config.ini for MQTT before deploy."
Write-Host "Browser: http://localhost:5000/login"
Write-Host ""
Read-Host "Press Enter to exit"
