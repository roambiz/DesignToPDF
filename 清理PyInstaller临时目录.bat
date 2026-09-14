@echo off
chcp 65001 >nul
echo 请先关闭所有「设计底稿导出」窗口，再按任意键清理临时解压目录…
pause >nul
taskkill /IM DesignToPDF.exe /F >nul 2>&1
taskkill /IM 设计底稿导出.exe /F >nul 2>&1
powershell -NoProfile -Command "Get-ChildItem -LiteralPath $env:TEMP -Filter '_MEI*' -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue"
echo 已尝试清理 %%TEMP%% 下的 _MEI* 文件夹。请再双击 exe 试一次。
pause
