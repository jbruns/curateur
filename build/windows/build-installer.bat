@echo off
REM Build Windows installer for Curateur using Inno Setup
REM
REM Usage:
REM   build\windows\build-installer.bat
REM
REM Requirements:
REM   - Inno Setup 6+ installed (https://jrsoftware.org/isinfo.php)
REM   - curateur.exe already built in dist\ folder
REM
REM Output:
REM   build\installers\Curateur-Setup-1.0.0.exe

echo ========================================
echo  Curateur Windows Installer Builder
echo ========================================
echo.

REM Check if Inno Setup is installed
where iscc >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Inno Setup Compiler not found
    echo.
    echo Please install Inno Setup from:
    echo   https://jrsoftware.org/isinfo.php
    echo.
    echo Or add ISCC.exe to your PATH
    pause
    exit /b 1
)

REM Check if curateur.exe exists
if not exist "dist\curateur.exe" (
    echo [ERROR] dist\curateur.exe not found
    echo.
    echo Build the executable first:
    echo   build\scripts\build-all.bat
    echo.
    pause
    exit /b 1
)

REM Create output directory
if not exist "build\installers" mkdir build\installers

REM Build installer
echo Building installer with Inno Setup...
echo.
iscc build\windows\curateur-setup.iss

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo  Build Complete!
    echo ========================================
    echo.
    dir /B build\installers\*.exe
    echo.
    echo Test the installer:
    echo   build\installers\Curateur-Setup-1.0.0.exe
    echo.
) else (
    echo.
    echo [ERROR] Build failed
    pause
    exit /b 1
)

pause
