#!/bin/bash

# Tile Concatenator Build Script
# Builds executable and installers for different platforms

set -e

echo "================================"
echo "Tile Concatenator Build Script"
echo "================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Build directory
BUILD_DIR="build"
DIST_DIR="dist"

# Function to print colored output
print_step() {
    echo -e "${BLUE}▶ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Check Python installation
print_step "Checking Python installation..."
python_version=$(python3 --version 2>&1)
print_success "Found: $python_version"

# Install dependencies
print_step "Installing dependencies..."
pip install -q -r requirements.txt
pip install -q pyinstaller
print_success "Dependencies installed"

# Clean previous builds
print_step "Cleaning previous builds..."
rm -rf "$BUILD_DIR" "$DIST_DIR" build/ dist/ *.spec 2>/dev/null || true
print_success "Clean complete"

# Build with PyInstaller
print_step "Building executable with PyInstaller..."
pyinstaller --distpath "$DIST_DIR" --buildpath "$BUILD_DIR" Map-Concatenator.spec --noconfirm
print_success "Executable built"

# Get OS type
OS_TYPE=$(uname -s)

# Create platform-specific installer
if [ "$OS_TYPE" == "Linux" ]; then
    print_step "Building Linux AppImage..."
    if command -v appimagetool &> /dev/null; then
        # Create AppDir structure
        APPDIR="$DIST_DIR/Tile-Concatenator.AppDir"
        mkdir -p "$APPDIR/usr/bin"
        mkdir -p "$APPDIR/usr/share/applications"
        mkdir -p "$APPDIR/usr/share/pixmaps"

        # Copy executable
        cp "$DIST_DIR/Tile-Concatenator/Tile-Concatenator" "$APPDIR/usr/bin/"

        # Create desktop file
        cat > "$APPDIR/usr/share/applications/tile-concatenator.desktop" << 'EOF'
[Desktop Entry]
Version=1.0
Type=Application
Name=Tile Concatenator
Comment=Map tile capture and stitching tool
Exec=Tile-Concatenator
Icon=tile-concatenator
Categories=Graphics;GIS;
EOF

        # Copy icon
        cp "src/app/media/dev_logo.ico" "$APPDIR/usr/share/pixmaps/tile-concatenator.png"

        # Create AppRun script
        cat > "$APPDIR/AppRun" << 'EOF'
#!/bin/bash
APPDIR="$(dirname "$(readlink -f "$0")")"
export LD_LIBRARY_PATH="$APPDIR/usr/lib:$LD_LIBRARY_PATH"
exec "$APPDIR/usr/bin/Tile-Concatenator" "$@"
EOF
        chmod +x "$APPDIR/AppRun"

        appimagetool "$APPDIR" "$DIST_DIR/Tile-Concatenator.AppImage"
        chmod +x "$DIST_DIR/Tile-Concatenator.AppImage"
        print_success "AppImage created: $DIST_DIR/Tile-Concatenator.AppImage"
    else
        print_warning "appimagetool not found. Install with: wget https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
    fi

elif [ "$OS_TYPE" == "Darwin" ]; then
    print_step "Building macOS App Bundle..."
    BUNDLE_NAME="$DIST_DIR/Tile-Concatenator.app"
    mkdir -p "$BUNDLE_NAME/Contents/MacOS"
    mkdir -p "$BUNDLE_NAME/Contents/Resources"

    # Copy executable
    cp "$DIST_DIR/Tile-Concatenator/Tile-Concatenator" "$BUNDLE_NAME/Contents/MacOS/"

    # Create Info.plist
    cat > "$BUNDLE_NAME/Contents/Info.plist" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleExecutable</key>
    <string>Tile-Concatenator</string>
    <key>CFBundleIdentifier</key>
    <string>com.ramlaxmangroup.tileconcatenator</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>Tile Concatenator</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>0.0.8</string>
    <key>CFBundleVersion</key>
    <string>1</string>
</dict>
</plist>
EOF

    print_success "macOS App Bundle created: $BUNDLE_NAME"

elif [ "$OS_TYPE" == "MINGW64" ] || [ "$OS_TYPE" == "MSYS" ] || [[ "$OS_TYPE" == *"MINGW"* ]]; then
    print_step "Building Windows installer..."
    if command -v makensis &> /dev/null; then
        makensis "src/app/setup.nsi"
        print_success "Windows installer created"
    else
        print_warning "NSIS not found. Install NSIS to create Windows installer"
        print_warning "Windows EXE available at: $DIST_DIR/Tile-Concatenator/Tile-Concatenator.exe"
    fi
fi

echo ""
print_success "Build complete!"
echo ""
print_step "Output location: $DIST_DIR/"
ls -lh "$DIST_DIR/" | tail -5

echo ""
print_step "Installation instructions:"
echo "  Linux:   Double-click the AppImage or run: chmod +x *.AppImage && ./Tile-Concatenator.AppImage"
echo "  macOS:   Double-click the .app bundle or run: open Tile-Concatenator.app"
echo "  Windows: Run the installer .exe or double-click the executable"
echo ""
