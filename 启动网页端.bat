@echo off
cd /d "%~dp0"

rem Use the dedicated virtualenv that has flask/cv2/pynbs/etc. installed.
rem (Bare "python" on this machine resolves to the managed base interpreter
rem  without these deps, which would break the server.)
set "PYTHON=C:\Users\LZH\.workbuddy\binaries\python\envs\nbs-viz\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo [Error] 找不到虚拟环境（依赖未安装）：
    echo   %PYTHON%
    echo 请先创建 venv 并安装依赖后再运行本脚本。
    pause
    exit /b 1
)

echo ============================================
echo   NBS Visualizer - Web Server
echo ============================================

rem Check and install dependencies if needed (into the venv)
echo   Checking dependencies...
"%PYTHON%" -c "import flask" 2>nul
if errorlevel 1 (
    echo   Installing flask...
    "%PYTHON%" -m pip install flask --quiet
)
"%PYTHON%" -c "import cv2" 2>nul
if errorlevel 1 (
    echo   Installing opencv-python...
    "%PYTHON%" -m pip install opencv-python --quiet
)
"%PYTHON%" -c "import PIL" 2>nul
if errorlevel 1 (
    echo   Installing pillow...
    "%PYTHON%" -m pip install pillow --quiet
)
"%PYTHON%" -c "import pynbs" 2>nul
if errorlevel 1 (
    echo   Installing pynbs...
    "%PYTHON%" -m pip install pynbs --quiet
)
"%PYTHON%" -c "import imageio_ffmpeg" 2>nul
if errorlevel 1 (
    echo   Installing imageio-ffmpeg...
    "%PYTHON%" -m pip install imageio-ffmpeg --quiet
)
echo   Dependencies ready.

rem --- Find a free port starting from 5000 (avoids "address already in use") ---
set PORT=5000
:portcheck
netstat -ano 2>nul | findstr ":%PORT% " >nul
if not errorlevel 1 (
    set /a PORT=PORT+1
    if %PORT% gtr 5020 (
        echo [Error] 端口 5000-5020 均被占用，请先关闭其它 NBS 服务器或占用程序。
        pause
        exit /b 1
    )
    goto portcheck
)

echo.
echo   Starting server...
echo   URL: http://127.0.0.1:%PORT%
echo   Press Ctrl+C to stop
echo ============================================
echo.

rem Wait a few seconds for the server to import & bind, then open the browser.
ping -n 6 127.0.0.1 >nul
start "" "http://127.0.0.1:%PORT%"

set "NBS_PORT=%PORT%"
"%PYTHON%" app.py --port %PORT%
if errorlevel 1 (
    echo.
    echo   [Error] 服务器启动失败。请查看上方红色报错信息。
    echo   常见原因：端口仍被占用、依赖缺失、或 app.py 有语法错误。
    pause
)
