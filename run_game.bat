@echo off
rem Starts the game with this folder's own Python environment.
cd /d "%~dp0"
.venv\Scripts\python.exe main.py
stop