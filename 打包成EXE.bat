@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PY=.venv38\Scripts\python.exe"
if exist "%PY%" goto :ready

echo 正在创建 Python 3.8 虚拟环境 .venv38 ...
set "PY38="
for /f "delims=" %%P in ('where python 2^>nul') do (
  "%%P" -c "import sys; raise SystemExit(0 if sys.version_info[:2]==(3,8) else 1)" 2>nul && set "PY38=%%P" && goto :have_py38
)
:have_py38
if not defined PY38 (
  echo 未找到 Python 3.8。Win7-Win11 通用包必须用 3.8 打包。
  pause
  exit /b 1
)
"%PY38%" -m venv ".venv38"
set "PY=.venv38\Scripts\python.exe"

:ready
echo 正在结束已运行的程序，避免 EXE 被占用...
taskkill /IM DesignToPDF.exe /F >nul 2>&1
taskkill /IM 设计底稿导出.exe /F >nul 2>&1

echo 使用 Python 3.8 安装依赖并打包（兼容 Windows 7 至 11）...
"%PY%" -m pip install -r requirements-win7.txt
if errorlevel 1 (
  echo 依赖安装失败。
  pause
  exit /b 1
)

"%PY%" -m PyInstaller DesignToPDF.spec --noconfirm --clean --distpath "发布"
if errorlevel 1 (
  echo 打包失败。
  pause
  exit /b 1
)

if exist "发布\设计底稿导出-1.1.0" rmdir /s /q "发布\设计底稿导出-1.1.0"
mkdir "发布\设计底稿导出-1.1.0"
copy /y "发布\DesignToPDF.exe" "发布\设计底稿导出-1.1.0\设计底稿导出.exe" >nul
del /f /q "发布\DesignToPDF.exe" >nul 2>&1
del /f /q "发布\设计底稿导出.exe" >nul 2>&1

echo.
echo 打包完成（Win7-Win11 通用）：
echo   发布\设计底稿导出-1.1.0\设计底稿导出.exe
echo 发给别人前请先保存到桌面再打开。不要在微信里直接点开。
echo.
pause
