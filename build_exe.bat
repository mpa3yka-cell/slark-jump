@echo off
rem Builds dist\SlarkJump.exe. Double-click this file after changing the game.
cd /d "%~dp0"
.venv\Scripts\pyinstaller.exe --noconfirm --onefile --windowed --name SlarkJump ^
  --icon "%~dp0assets\icon.ico" --add-data "%~dp0assets;assets" ^
  --exclude-module numpy ^
  --workpath "%TEMP%\slarkjump_build" --specpath "%TEMP%\slarkjump_build" ^
  --distpath "%~dp0dist" main.py
echo.
echo Done: dist\SlarkJump.exe
pause
