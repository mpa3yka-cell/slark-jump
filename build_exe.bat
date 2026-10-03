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

rem --- Install/upgrade PyInstaller in the venv ---
echo Installing PyInstaller...
.venv\Scripts\python.exe -m pip install --upgrade pip pyinstaller --no-warn-script-location
if errorlevel 1 (
    echo ERROR: Failed to install PyInstaller.
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

rem --- Copy pygame into the bundle ---
rem Tests, docs, examples and caches add ~8 MB and are useless at runtime, so skip them.
echo Copying pygame...
set PYGAME_DIR=%~dp0.venv\Lib\site-packages\pygame
if exist "%PYGAME_DIR%" (
    xcopy /E /I /Y /XD tests docs examples __pycache__ /XF *.pyc *.pyi "%PYGAME_DIR%" "dist\SlarkJump\_internal\pygame" >nul
    echo pygame copied successfully
) else (
    echo WARNING: pygame directory not found at %PYGAME_DIR%
)

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
