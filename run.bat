@echo off
title Video Joiner Pro
chcp 65001 > nul
cd /d "%~dp0"

echo Dang khoi dong Video Joiner Pro...
python main.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Da co loi xay ra khi chay ung dung.
    pause
)

