@echo off
cd /d "%~dp0"
py bridge\airfret_bridge.py %*
pause
