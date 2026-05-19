@echo off
chcp 65001 >nul
echo ========================================
echo   重序 ReOrder - PyInstaller 构建
echo ========================================
echo.

REM Check if PyInstaller is installed
pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Installing PyInstaller...
    pip install pyinstaller
)

echo [BUILD] Starting build with spec file...
pyinstaller --clean --noconfirm ReOrder.spec

if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo   Build successful!
    echo   Output: dist\ReOrder.exe
    echo ========================================
) else (
    echo.
    echo [ERROR] Build failed! Check the output above.
)

pause
