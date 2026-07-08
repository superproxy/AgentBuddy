@echo off
REM AdeBuddy one-shot install entry (Windows)
REM Equivalent to: agentctl setup (generate + sync to all IDEs)
REM
REM Usage:
REM   install.cmd              # full init (generate + sync All)
REM   install.cmd --ide ZCode  # sync specific IDE only
REM   install.cmd --scope mcp  # sync mcp scope only

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ========================================
echo   AdeBuddy Install
echo ========================================
echo.

REM === Check Python ===
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.8+
    echo         https://www.python.org/downloads/
    exit /b 1
)

for /f "tokens=*" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo [INFO] %PY_VER%

REM === Check and install core deps ===
python -c "import flask, yaml, requests" 2>nul
if errorlevel 1 (
    echo [INFO] Installing core dependencies...
    python -m pip install flask pyyaml requests
    if errorlevel 1 (
        echo [ERROR] pip install failed. Run manually: python -m pip install flask pyyaml requests
        exit /b 1
    )
)

REM === Bootstrap config files from templates (first run) ===
echo.
echo [Step 1/3] Init config files
if not exist "config\llm\llm.yaml" (
    if exist "template\llm\llm-env-example.yaml" (
        copy "template\llm\llm-env-example.yaml" "config\llm\llm.yaml" >nul
        echo   [NEW] config\llm\llm.yaml created (fill in your API Key)
    ) else (
        echo   [WARN] template\llm\llm-env-example.yaml not found
    )
) else (
    echo   [OK]  config\llm\llm.yaml exists
)
if not exist "config\mcp\mcp.yaml" (
    if exist "template\mcp\mcp-env-example.yaml" (
        copy "template\mcp\mcp-env-example.yaml" "config\mcp\mcp.yaml" >nul
        echo   [NEW] config\mcp\mcp.yaml created
    ) else (
        echo   [WARN] template\mcp\mcp-env-example.yaml not found
    )
) else (
    echo   [OK]  config\mcp\mcp.yaml exists
)

REM === generate ===
echo.
echo [Step 2/3] Generate runtime configs (mcp.json + IDE templates)
python scripts\agentctl.py generate
if errorlevel 1 (
    echo [ERROR] generate failed
    exit /b 1
)

REM === sync ===
echo.
echo [Step 3/3] Sync to all IDEs
python scripts\agentctl.py sync --ide All --force %*
if errorlevel 1 (
    echo [ERROR] sync failed
    exit /b 1
)

echo.
echo ========================================
echo   Install complete!
echo ========================================
echo.
echo IDE configs synced:
echo   Claude:    %%USERPROFILE%%\.claude\mcp.json
echo   ZCode:     %%USERPROFILE%%\.zcode\cli\config.json
echo   Trae CN:   %%APPDATA%%\Trae CN\User\mcp.json
echo   Codex:     %%USERPROFILE%%\.codex\config.toml
echo   OpenCode:  %%USERPROFILE%%\.config\opencode\opencode.json
echo.
echo Edit config\llm\llm.yaml and config\mcp\mcp.yaml, then re-run install.cmd
echo To start GUI: run.cmd
echo.
endlocal
