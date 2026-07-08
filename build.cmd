@echo off
chcp 65001 >nul 2>&1
REM AgentBuddy Build Script (Frontend + Backend + PyInstaller + Installer)
REM Usage: build.cmd [--windowed] [--clean] [--no-frontend] [--no-verify] [--no-installer] [--version 1.0.0]
setlocal enabledelayedexpansion

cd /d "%~dp0"

echo [build] AgentBuddy Build
echo [build] Platform: Windows
echo.

REM ===== Step 1/5: Frontend Build =====
echo [build] Step 1/5: Frontend build (Vue 3 + Vite)...
if not exist "frontend\node_modules" (
    echo [build]   Installing npm dependencies...
    cd frontend && call npm install && cd ..
)
cd frontend
call npm run build-only
if errorlevel 1 (
    echo [build][ERROR] Frontend build failed
    exit /b 1
)
cd ..
echo [build]   OK: tools\dist-ui\
echo.

REM ===== Step 2/5: Python Dependencies =====
echo [build] Step 2/5: Check Python dependencies...
python -c "import flask, yaml, requests" 2>nul
if errorlevel 1 (
    echo [build]   Installing runtime deps...
    python -m pip install flask pyyaml requests pywebview
)
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo [build]   Installing PyInstaller...
    python -m pip install pyinstaller
)
echo [build]   OK
echo.

REM ===== Step 3/5: PyInstaller =====
echo [build] Step 3/5: PyInstaller packaging...
python build.py %*
if errorlevel 1 (
    echo [build][ERROR] PyInstaller failed
    exit /b 1
)
echo.

REM ===== Step 4/5: Verify Frontend Bundle =====
echo [build] Step 4/5: Verify frontend in bundle...
if exist "dist\AgentBuddy\_internal\tools\dist-ui\index.html" (
    echo [build]   OK: _internal\tools\dist-ui\index.html
) else if exist "dist\AgentBuddy\tools\dist-ui\index.html" (
    echo [build]   OK: tools\dist-ui\index.html
) else (
    echo [build][WARN] Frontend assets not found in bundle
)
echo.

REM ===== Step 5/5: Check Installer =====
echo [build] Step 5/5: Check installer output...
set "INSTALLER_FOUND=0"
if exist "dist\installer\AgentBuddy-Setup-*.exe" (
    for %%f in (dist\installer\AgentBuddy-Setup-*.exe) do (
        echo [build]   Installer: %%f
        set "INSTALLER_FOUND=1"
    )
)
if "!INSTALLER_FOUND!"=="0" (
    echo [build]   No installer generated.
    echo [build]   To enable: install Inno Setup 6 from https://jrsoftware.org/isdl.php
    echo [build]   Or use: build.cmd --no-installer  (skip installer)
)
echo.

REM ===== Summary =====
echo [build] ========================================
echo [build]   Build Complete!
echo [build] ========================================
echo [build]   Output dir:  dist\AgentBuddy\
echo [build]   Executable:  dist\AgentBuddy\AgentBuddy.exe
if "!INSTALLER_FOUND!"=="1" (
    echo [build]   Installer:   dist\installer\AgentBuddy-Setup-*.exe
) else (
    echo [build]   Distribute:  zip dist\AgentBuddy\ or install Inno Setup
)
echo [build]
echo [build]   First run auto-generates config from templates.
echo.

endlocal
