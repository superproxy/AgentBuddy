@echo off
chcp 65001 >nul 2>&1
REM AdeBuddy Release: tag + push, triggers GitHub Actions build
REM
REM Usage:
REM   release.cmd              interactive version (auto patch +1)
REM   release.cmd 1.0.0        specify version
REM   release.cmd 1.0.0 -p     skip confirm and push
REM
REM Flow:
REM   1. Check working tree clean
REM   2. Confirm version
REM   3. Create git tag v<version>
REM   4. Push tag to origin
REM   5. GitHub Actions builds macOS + Windows and publishes Release

setlocal enabledelayedexpansion
cd /d "%~dp0"

REM ===== Color (Windows Terminal / ANSI) =====
set "G=[92m"
set "Y=[93m"
set "R=[91m"
set "C=[96m"
set "N=[0m"

echo %C%========================================%N%
echo %C%  AdeBuddy Release%N%
echo %C%========================================%N%

REM ===== Parse args =====
set "VERSION=%~1"
set "AUTO_PUSH=0"
if /i "%~2"=="-p" set "AUTO_PUSH=1"
if /i "%~2"=="--push" set "AUTO_PUSH=1"

REM ===== 1. Check working tree =====
git diff --quiet --exit-code >nul 2>&1
if errorlevel 1 (
    echo %Y%[release]%N% Working tree dirty, commit first:
    git status --short
    echo %R%[release][ERROR]%N% Please git commit before release
    exit /b 1
)
echo %G%[release]%N% Working tree clean

REM ===== 2. Confirm version =====
if not defined VERSION (
    REM Auto infer: latest tag + patch +1
    set "LATEST_TAG="
    for /f "tokens=*" %%t in ('git describe --tags --abbrev=0 2^>nul') do set "LATEST_TAG=%%t"
    if defined LATEST_TAG (
        REM Strip leading v
        set "VER=!LATEST_TAG:v=!"
        for /f "tokens=1,2,3 delims=." %%a in ("!VER!") do (
            set /a "PATCH=%%c+1"
            set "SUGGESTED=%%a.%%b.!PATCH!"
        )
        echo %Y%[release]%N% Previous version: !LATEST_TAG!
        set /p "INPUT=Enter version [!SUGGESTED!]: "
        if "!INPUT!"=="" (
            set "VERSION=!SUGGESTED!"
        ) else (
            set "VERSION=!INPUT!"
        )
    ) else (
        set /p "VERSION=Enter version (e.g. 1.0.0): "
    )
)

if "!VERSION!"=="" (
    echo %R%[release][ERROR]%N% Version cannot be empty
    exit /b 1
)

set "TAG=v!VERSION!"
echo %G%[release]%N% Version: !VERSION!  Tag: !TAG!

REM ===== 3. Check tag exists =====
git rev-parse "!TAG!" >nul 2>&1
if not errorlevel 1 (
    echo %R%[release][ERROR]%N% Tag !TAG! already exists, use another version
    exit /b 1
)

REM ===== 4. Confirm push =====
if "!AUTO_PUSH!"=="0" (
    echo.
    echo %Y%[release]%N% About to:
    echo   1. git tag !TAG!
    echo   2. git push origin !TAG!
    echo   3. GitHub Actions build macOS + Windows
    echo   4. Auto create GitHub Release (.dmg / .zip / .exe)
    echo.
    set /p "CONFIRM=Confirm release? [y/N]: "
    if /i not "!CONFIRM!"=="y" (
        echo %Y%[release]%N% Cancelled
        exit /b 0
    )
)

REM ===== 5. Create and push tag =====
echo %G%[release]%N% Creating tag: !TAG!
git tag "!TAG!"
if errorlevel 1 (
    echo %R%[release][ERROR]%N% Create tag failed
    exit /b 1
)

echo %G%[release]%N% Pushing tag: !TAG!
git push origin "!TAG!"
if errorlevel 1 (
    echo %R%[release][ERROR]%N% Push tag failed, run manually: git push origin !TAG!
    exit /b 1
)

REM ===== 6. Done =====
echo.
echo %G%========================================%N%
echo %G%  Release triggered!%N%
echo %G%========================================%N%
echo.
echo   Tag:        !TAG!
echo   Actions:    Check GitHub Actions page
echo   Releases:   Check GitHub Releases page
echo.
echo   After build, Releases page will show:
echo     - AdeBuddy-!VERSION!-macos.dmg / .zip
echo     - AdeBuddy-Setup-!VERSION!-x64.exe
echo.

endlocal
