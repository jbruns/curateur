@echo off
REM Build curateur standalone executable for Windows
REM
REM Usage:
REM   build\scripts\build-all.bat
REM
REM Requirements:
REM   - Python 3.8+
REM   - pip install pyinstaller
REM
REM Output:
REM   dist\curateur.exe

setlocal enabledelayedexpansion

echo ========================================
echo   Curateur Standalone Build Script
echo ========================================
echo.

REM Check if PyInstaller is installed
where pyinstaller >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] PyInstaller not found
    echo.
    echo Install it with:
    echo   pip install pyinstaller
    echo.
    pause
    exit /b 1
)

echo [OK] PyInstaller found
echo.

REM Get version from pyproject.toml
for /f "tokens=2 delims==" %%a in ('findstr /r "^version" pyproject.toml') do (
    set VERSION=%%a
    set VERSION=!VERSION:"=!
    set VERSION=!VERSION: =!
)

echo Version: !VERSION!
echo.

REM Clean previous builds
echo Cleaning previous builds...
if exist dist rmdir /s /q dist
if exist build\temp rmdir /s /q build\temp
echo [OK] Cleaned
echo.

REM Run PyInstaller
echo Building with PyInstaller...
pyinstaller build\pyinstaller\curateur.spec

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Build failed
    pause
    exit /b 1
)

echo [OK] Build complete
echo.

REM Show output
echo Output files:
dir /B dist\curateur.exe 2>nul || dir /B dist\
echo.

REM Test the executable
echo Testing executable...
dist\curateur.exe --help | findstr /C:"curateur" >nul

if %ERRORLEVEL% EQU 0 (
    echo [OK] Executable works
) else (
    echo [WARNING] Could not test executable
)
echo.

REM Next steps
echo Next steps:
echo   1. Test: dist\curateur.exe --help
echo   2. Create installer: build\windows\build-installer.bat
echo   3. Sign (optional): signtool sign /f cert.pfx dist\curateur.exe
echo.

echo ========================================
echo Build complete!
echo ========================================

pause
