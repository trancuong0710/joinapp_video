@echo off
title Build Video Toolkit Pro
chcp 65001 > nul
cd /d "%~dp0"

echo Dang bat dau build Video Toolkit Pro...
python build_exe.py
pause

