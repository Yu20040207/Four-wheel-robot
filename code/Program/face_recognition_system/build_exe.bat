@echo off
cd /d "%~dp0"

echo ========================================
echo   OpenMV Face System - Build EXE
echo ========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.12 and add to PATH.
    pause
    exit /b 1
)

echo [1/4] Installing dependencies...
python -m pip install -r requirements.txt pyinstaller -q
if errorlevel 1 (
    echo [ERROR] pip install failed
    pause
    exit /b 1
)

echo [2/4] Running PyInstaller (may take 5-15 min)...
python -m PyInstaller app.spec --clean --noconfirm
if errorlevel 1 (
    echo [ERROR] PyInstaller failed
    pause
    exit /b 1
)

echo [3/4] Copying runtime files to dist...
if not exist dist mkdir dist
copy /Y config.ini dist\config.ini >nul
if exist face_data xcopy face_data dist\face_data /E /I /Y >nul
if exist attendance_data.json copy /Y attendance_data.json dist\attendance_data.json >nul
if exist garbage.pt copy /Y garbage.pt dist\garbage.pt >nul
if not exist dist\rubbish_photo mkdir dist\rubbish_photo

echo [4/4] Done
echo.
echo Output: %cd%\dist\OpenMV_FaceSystem.exe
echo Edit dist\config.ini for MQTT before deploy.
echo Open browser: http://localhost:5000/login
echo.
pause
