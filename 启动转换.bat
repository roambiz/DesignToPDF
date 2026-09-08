@echo off
chcp 65001 >nul
cd /d "%~dp0"

if exist "发布\设计底稿导出-1.1.0\设计底稿导出.exe" (
  start "" "发布\设计底稿导出-1.1.0\设计底稿导出.exe"
  exit /b 0
)

if exist "发布\设计底稿导出-1.0.0\设计底稿导出.exe" (
  start "" "发布\设计底稿导出-1.0.0\设计底稿导出.exe"
  exit /b 0
)

set "PY="
if exist ".venv38\Scripts\python.exe" set "PY=.venv38\Scripts\python.exe"
if not defined PY if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY set "PY=python"

"%PY%" -c "import app" 2>nul
if errorlevel 1 (
  echo 正在安装依赖，请稍等...
  if exist ".venv38\Scripts\python.exe" (
    ".venv38\Scripts\python.exe" -m pip install -r requirements-win7.txt
  ) else (
    "%PY%" -m pip install -r requirements.txt
  )
  if errorlevel 1 (
    echo.
    echo 安装失败。请先运行「打包成EXE.bat」生成可双击的程序。
    pause
    exit /b 1
  )
)

"%PY%" app.py
if errorlevel 1 pause
