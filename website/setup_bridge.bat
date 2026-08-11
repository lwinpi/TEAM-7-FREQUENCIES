@echo off
cd /d "%~dp0"
py -m pip install -r bridge\requirements.txt
echo.
echo Bridge setup finished.
pause
