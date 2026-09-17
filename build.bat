@echo off
REM Tile Concatenator Build Script for Windows
REM Builds executable and installers

setlocal enabledelayedexpansion

echo ================================
echo Tile Concatenator Build Script
echo ================================
echo.

REM Check Python installation
echo Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python not found. Please install Python 3.8 or higher.
    exit /b 1
)
for /f "tokens=2" %%A in ('python --version 2^>^&1') do set PYTHON_VERSION=%%A
echo Found: Python %PYTHON_VERSION%

REM Install dependencies
echo Installing dependencies...
pip install -q -r requirements.txt
pip install -q pyinstaller
echo Dependencies installed

REM Clean previous builds
echo Cleaning previous builds...
rmdir /s /q build dist 2>nul || true
del /q *.spec 2>nul || true
echo Clean complete

REM Build with PyInstaller
echo Building executable with PyInstaller...
pyinstaller --distpath dist --workpath build Map-Concatenator.spec --noconfirm
if errorlevel 1 (
    echo Error: PyInstaller build failed
    exit /b 1
)
echo Executable built

REM Create Windows installer
echo Building Windows installer...
if exist "%ProgramFiles(x86)%\NSIS\makensis.exe" (
    "%ProgramFiles(x86)%\NSIS\makensis.exe" "src\app\setup.nsi"
    echo Windows installer created
) else if exist "%ProgramFiles%\NSIS\makensis.exe" (
    "%ProgramFiles%\NSIS\makensis.exe" "src\app\setup.nsi"
    echo Windows installer created
) else (
    echo Warning: NSIS not found. Install NSIS from https://nsis.sourceforge.io/
    echo Windows EXE available at: dist\Tile-Concatenator\Tile-Concatenator.exe
)

echo.
echo Build complete!
echo.
echo Output location: dist\
dir /b dist\
echo.
echo Installation instructions:
echo   Windows: Run the installer .exe or double-click dist\Tile-Concatenator\Tile-Concatenator.exe
echo.
pause
