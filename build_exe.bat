@echo off
rem Builds the game as a folder dist\SlarkJump\ (SlarkJump.exe + _internal) and packs it into a ZIP.
rem A folder build triggers antivirus false alarms much less often than a single self-extracting .exe.
rem When releasing a new version, change VERSION here, in common.py and in tools\version_info.txt.
set VERSION=1.1.1
cd /d "%~dp0"

rem --- Create virtual environment if it doesn't exist ---
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment. Make sure Python is installed.
        pause
        exit /b 1
    )
)

rem --- Install the game requirements and PyInstaller in the venv ---
echo Installing requirements and PyInstaller...
.venv\Scripts\python.exe -m pip install --upgrade pip pyinstaller -r requirements.txt --no-warn-script-location
if errorlevel 1 (
    echo ERROR: Failed to install requirements or PyInstaller.
    pause
    exit /b 1
)

rem --- Build with PyInstaller ---
echo Building executable...
.venv\Scripts\pyinstaller.exe --noconfirm --onedir --windowed --noupx --name SlarkJump ^
  --icon "%~dp0assets\icon.ico" --add-data "%~dp0assets;assets" ^
  --version-file "%~dp0tools\version_info.txt" ^
  --exclude-module numpy ^
  --workpath "%TEMP%\slarkjump_build" --specpath "%~dp0build_temp" ^
  --distpath "%~dp0dist" main.py
if errorlevel 1 goto :clean_fail

rem --- Copy firewall helper ---
copy /y allow_firewall.bat dist\SlarkJump\ >nul

rem --- Pack into ZIP ---
rem tar ships with Windows 10 1803+ and, unlike Compress-Archive, does not choke on locked files.
pushd dist
tar -a -c -f "SlarkJump-v%VERSION%.zip" SlarkJump
set PACKED=%errorlevel%
popd
if not "%PACKED%"=="0" (
    echo ERROR: Failed to pack ZIP.
    goto :clean_fail
)

echo.
echo Done: dist\SlarkJump\SlarkJump.exe and dist\SlarkJump-v%VERSION%.zip
goto :clean

:clean_fail
echo.
echo Build failed. Cleaning up temp files...

:clean
if exist "build_temp" rmdir /s /q "build_temp"
pause
