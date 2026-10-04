@echo off
rem Builds the game twice:
rem   1) folder build  -> dist\SlarkJump\  (SlarkJump.exe + _internal), packed into a ZIP.
rem      The folder build triggers antivirus false alarms much less often than a self-extracting .exe,
rem      so this is the one to share. IMPORTANT: SlarkJump.exe only works together with the whole
rem      SlarkJump folder - copying the .exe alone breaks it (pygame lives in _internal).
rem   2) single build -> dist\SlarkJump-1file.exe
rem      Everything (pygame included) is inside one file that runs from anywhere. Handy for quick
rem      testing and for running from a flash drive, but it unpacks to %TEMP% on every launch
rem      and gets flagged by antivirus more often.
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

rem --- Sanity check: pygame must really be in the venv. Without this check PyInstaller happily
rem --- builds an exe that dies on startup with "No module named pygame", with no build error.
.venv\Scripts\python.exe -c "import pygame" >nul 2>&1
if errorlevel 1 (
    echo ERROR: pygame is missing from .venv, the exe would not find it.
    echo Run: .venv\Scripts\python.exe -m pip install -r requirements.txt
    goto :clean_fail
)

rem --- Build with PyInstaller: folder flavour ---
echo Building folder build (dist\SlarkJump)...
.venv\Scripts\pyinstaller.exe --noconfirm --onedir --windowed --noupx --name SlarkJump ^
  --icon "%~dp0assets\icon.ico" --add-data "%~dp0assets;assets" ^
  --version-file "%~dp0tools\version_info.txt" ^
  --exclude-module numpy ^
  --workpath "%TEMP%\slarkjump_build" --specpath "%~dp0build_temp" ^
  --distpath "%~dp0dist" main.py
if errorlevel 1 goto :clean_fail

rem --- Copy firewall helper ---
copy /y allow_firewall.bat dist\SlarkJump\ >nul

rem --- Build with PyInstaller: single-file flavour (own workpath so it does not mix with the folder build) ---
echo Building single-file exe (dist\SlarkJump-1file.exe)...
.venv\Scripts\pyinstaller.exe --noconfirm --onefile --windowed --noupx --name SlarkJump-1file ^
  --icon "%~dp0assets\icon.ico" --add-data "%~dp0assets;assets" ^
  --version-file "%~dp0tools\version_info.txt" ^
  --exclude-module numpy ^
  --workpath "%TEMP%\slarkjump_build_1file" --specpath "%~dp0build_temp" ^
  --distpath "%~dp0dist" main.py
if errorlevel 1 goto :clean_fail

rem --- Pack folder build into ZIP ---
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
echo Done:
echo   dist\SlarkJump\SlarkJump.exe          ^(run together with the SlarkJump folder^)
echo   dist\SlarkJump-v%VERSION%.zip         ^(share this one^)
echo   dist\SlarkJump-1file.exe              ^(single file, runs anywhere^)
goto :clean

:clean_fail
echo.
echo Build failed. Cleaning up temp files...

:clean
if exist "build_temp" rmdir /s /q "build_temp"
pause
