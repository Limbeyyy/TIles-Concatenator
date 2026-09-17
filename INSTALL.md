# Tile Concatenator - Installation Guide

Build and install Tile Concatenator as a desktop application for Windows, macOS, and Linux.

## Quick Start

### Windows
```bash
# Run the build script
build.bat

# Or manually with PyInstaller
pip install pyinstaller
pyinstaller Map-Concatenator.spec
```

Then run the installer or executable from `dist/`.

### Linux
```bash
# Make the build script executable
chmod +x build.sh

# Run the build script
./build.sh
```

This creates an AppImage that can be run directly.

### macOS
```bash
# Run the build script
./build.sh
```

This creates a macOS app bundle.

## Prerequisites

### All Platforms
- Python 3.8 or higher
- pip (Python package manager)

### System Requirements
- Windows: Windows 7 or higher
- macOS: macOS 10.12 or higher
- Linux: Most modern distributions

## Installation Methods

### Method 1: Build Standalone Executable (Recommended)

#### Windows
1. Download and install Python from https://www.python.org/
2. Open Command Prompt and navigate to the project directory
3. Run: `build.bat`
4. Find the installer in the `dist/` folder

#### Linux
1. Install Python: `sudo apt-get install python3 python3-pip`
2. Run: `./build.sh`
3. An AppImage will be created in `dist/`

#### macOS
1. Install Python from https://www.python.org/ or via Homebrew
2. Run: `./build.sh`
3. A .app bundle will be created in `dist/`

### Method 2: Install from Source

```bash
# Install the package in development mode
pip install -e .

# Or install from a wheel
pip install wheel
python setup.py bdist_wheel
pip install dist/Tile_Concatenator-*.whl
```

### Method 3: Run from Source (No Installation)

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
cd src/app
python Map-Concator-App.py
```

## Building Installers

### Windows Installer (.exe)

Requires: [NSIS](https://nsis.sourceforge.io/)

```bash
build.bat
```

This automatically uses NSIS if installed, or creates just the executable.

### Linux AppImage

Requires: [AppImageKit](https://github.com/AppImage/AppImageKit)

```bash
chmod +x build.sh
./build.sh
```

The AppImage can be run directly:
```bash
chmod +x dist/Tile-Concatenator.AppImage
./dist/Tile-Concatenator.AppImage
```

### macOS App Bundle

```bash
./build.sh
```

Double-click `dist/Tile-Concatenator.app` or run:
```bash
open dist/Tile-Concatenator.app
```

## Troubleshooting

### PyInstaller Build Issues

If the build fails, try:
```bash
pip install --upgrade pyinstaller
pip install --upgrade setuptools
```

### Missing Dependencies

Ensure all requirements are installed:
```bash
pip install -r requirements.txt
```

### Permission Denied (Linux/macOS)

Make scripts executable:
```bash
chmod +x build.sh
chmod +x dist/Tile-Concatenator.AppImage  # For AppImage
```

### Windows NSIS Not Found

Either:
1. Install NSIS from https://nsis.sourceforge.io/
2. Or run the .exe directly from `dist/Tile-Concatenator/`

## Distribution

### Creating a Portable Version

The standalone executables in `dist/` are portable and can be:
- Moved to any location
- Copied to a USB drive
- Shared directly with others

No additional installation is needed.

### Creating a Package Distribution

```bash
# Create wheel
python setup.py bdist_wheel

# Create source distribution
python setup.py sdist

# Upload to PyPI (requires account)
pip install twine
twine upload dist/*
```

## System Integration

### Windows
The installer optionally creates:
- Start Menu shortcuts
- Desktop shortcut
- Registry entries for uninstallation

### Linux
After building the AppImage:
```bash
# Make executable
chmod +x dist/Tile-Concatenator.AppImage

# Run
./dist/Tile-Concatenator.AppImage
```

### macOS
After building the app bundle:
```bash
# Run
open dist/Tile-Concatenator.app

# Or from command line
dist/Tile-Concatenator.app/Contents/MacOS/Tile-Concatenator
```

## Support

For issues with building or installation, refer to:
- PyInstaller Documentation: https://pyinstaller.readthedocs.io/
- NSIS Documentation: https://nsis.sourceforge.io/Docs/
- AppImageKit: https://docs.appimage.org/

## License

See LICENSE file in the project root.
