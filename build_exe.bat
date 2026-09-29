@echo off
rem Builds the game as a folder dist\SlarkJump\ (SlarkJump.exe + _internal) and packs it into a ZIP.
rem A folder build triggers antivirus false alarms much less often than a single self-extracting .exe.
rem When releasing a new version, change VERSION here, in common.py and in tools\version_info.txt.
set VERSION=1.1.0
cd /d "%~dp0"
.venv\Scripts\pyinstaller.exe --noconfirm --onedir --windowed --noupx --name SlarkJump ^
  --icon "%~dp0assets\icon.ico" --add-data "%~dp0assets;assets" ^
  --version-file "%~dp0tools\version_info.txt" ^
  --exclude-module numpy ^
  --workpath "%TEMP%\slarkjump_build" --specpath "%TEMP%\slarkjump_build" ^
  --distpath "%~dp0dist" main.py
if errorlevel 1 goto :eof
copy /y allow_firewall.bat dist\SlarkJump\ >nul
powershell -NoProfile -Command "Compress-Archive -Path 'dist\SlarkJump' -DestinationPath 'dist\SlarkJump-v%VERSION%.zip' -Force"
echo.
echo Done: dist\SlarkJump\SlarkJump.exe and dist\SlarkJump-v%VERSION%.zip
pause
