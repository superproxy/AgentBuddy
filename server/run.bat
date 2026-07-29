@echo off
REM AgentBuddy Server 一键构建和运行脚本 (Windows)
REM 用法：
REM   run.bat          REM 前台运行
REM   run.bat -d       REM 后台运行
REM   run.bat stop     REM 停止后台进程
REM   run.bat restart  REM 重启
REM   run.bat status   REM 查看状态
setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

set VENV_DIR=.venv
set PID_FILE=.server.pid
set LOG_FILE=server.log
set HOST=%AGENTBUDDY_SERVER_HOST%
if "%HOST%"=="" set HOST=0.0.0.0
set PORT=%AGENTBUDDY_SERVER_PORT%
if "%PORT%"=="" set PORT=5001

REM === 检查 Python ===
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] 未找到 Python，请先安装 Python 3.8+
    exit /b 1
)

for /f "tokens=*" %%i in ('python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}'"') do set PYVER=%%i
echo [INFO] Python: %PYVER%

REM === 创建虚拟环境 + 安装依赖 ===
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [INFO] 创建虚拟环境 %VENV_DIR% ...
    python -m venv "%VENV_DIR%"
)

call "%VENV_DIR%\Scripts\activate.bat"

REM 检查依赖
python -c "import flask" >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] 安装依赖...
    pip install --upgrade pip -q
    pip install -r requirements.txt -q
    echo [INFO] 依赖安装完成
) else (
    echo [INFO] 依赖已就绪
)

REM === 主逻辑 ===
if "%~1"=="" goto start
if "%~1"=="-d" goto start_daemon
if "%~1"=="stop" goto stop
if "%~1"=="restart" goto restart
if "%~1"=="status" goto status
goto start

:start
echo [INFO] 启动 AgentBuddy Server ...
echo [INFO]   监听: %HOST%:%PORT%
python app.py
goto :eof

:start_daemon
REM 检查是否已在运行
if exist "%PID_FILE%" (
    for /f "tokens=*" %%i in (%PID_FILE%) do set PID=%%i
    tasklist /FI "PID eq !PID!" 2>nul | find "!PID!" >nul
    if !errorlevel! equ 0 (
        echo [WARN] Server 已在运行 ^(PID: !PID!^)
        exit /b 0
    )
    del "%PID_FILE%" 2>nul
)

echo [INFO] 后台启动 AgentBuddy Server ...
echo [INFO]   监听: %HOST%:%PORT%
echo [INFO]   日志: %LOG_FILE%

start /b "" "%VENV_DIR%\Scripts\python.exe" app.py > "%LOG_FILE%" 2>&1

REM 获取后台进程 PID
for /f "tokens=2" %%i in ('tasklist /FI "IMAGENAME eq python.exe" /FO CSV /NH ^| findstr /N "." ^| findstr "^1:"') do set PID=%%i
echo !PID!> "%PID_FILE%"

timeout /t 2 /nobreak >nul
echo [INFO] Server 已启动
echo [INFO]   查看日志: type %LOG_FILE%
echo [INFO]   健康检查: curl http://%HOST%:%PORT%/api/health
goto :eof

:stop
if not exist "%PID_FILE%" (
    echo [WARN] Server 未在运行
    exit /b 0
)
for /f "tokens=*" %%i in (%PID_FILE%) do set PID=%%i
tasklist /FI "PID eq !PID!" 2>nul | find "!PID!" >nul
if !errorlevel! equ 0 (
    taskkill /PID !PID! /F
    echo [INFO] Server 已停止 ^(PID: !PID!^)
) else (
    echo [WARN] 进程 !PID! 不存在，清理 PID 文件
)
del "%PID_FILE%" 2>nul
goto :eof

:restart
call :stop
timeout /t 1 /nobreak >nul
call :start_daemon
goto :eof

:status
if exist "%PID_FILE%" (
    for /f "tokens=*" %%i in (%PID_FILE%) do set PID=%%i
    tasklist /FI "PID eq !PID!" 2>nul | find "!PID!" >nul
    if !errorlevel! equ 0 (
        echo [INFO] Server 运行中 ^(PID: !PID!^)
        exit /b 0
    )
)
echo [WARN] Server 未运行
exit /b 1
