#!/bin/bash
# Build curateur standalone executable for the current platform
#
# Usage:
#   ./build/scripts/build-all.sh
#
# Requirements:
#   - Python 3.8+
#   - pip install pyinstaller
#
# Output:
#   dist/curateur (or dist/curateur.exe on Windows)
#   dist/Curateur.app (macOS only, if building app bundle)

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Detect platform
if [[ "$OSTYPE" == "darwin"* ]]; then
    PLATFORM="macOS"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    PLATFORM="Linux"
elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "win32" ]]; then
    PLATFORM="Windows"
else
    PLATFORM="Unknown"
fi

echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Curateur Standalone Build Script     ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
echo ""
echo -e "Platform: ${GREEN}$PLATFORM${NC}"
echo ""

# Check if PyInstaller is installed
if ! command -v pyinstaller &> /dev/null; then
    echo -e "${RED}✗ PyInstaller not found${NC}"
    echo ""
    echo "Install it with:"
    echo "  pip install pyinstaller"
    echo ""
    exit 1
fi

echo -e "${GREEN}✓ PyInstaller found${NC}"
echo ""

# Get version from pyproject.toml
VERSION=$(grep -E '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
echo -e "Version: ${GREEN}$VERSION${NC}"
echo ""

# Clean previous builds
echo -e "${YELLOW}Cleaning previous builds...${NC}"
rm -rf build/temp dist/ build/*.spec 2>/dev/null || true
echo -e "${GREEN}✓ Cleaned${NC}"
echo ""

# Run PyInstaller
echo -e "${YELLOW}Building with PyInstaller...${NC}"
pyinstaller build/pyinstaller/curateur.spec

if [ $? -ne 0 ]; then
    echo -e "${RED}✗ Build failed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Build complete${NC}"
echo ""

# Show output
echo -e "${BLUE}Output files:${NC}"
if [[ "$PLATFORM" == "Windows" ]]; then
    ls -lh dist/curateur.exe 2>/dev/null || ls -lh dist/
elif [[ "$PLATFORM" == "macOS" ]]; then
    if [ -d "dist/Curateur.app" ]; then
        echo "  Curateur.app (macOS app bundle)"
        du -sh dist/Curateur.app
    fi
    if [ -f "dist/curateur" ]; then
        ls -lh dist/curateur
    fi
else
    ls -lh dist/curateur 2>/dev/null || ls -lh dist/
fi
echo ""

# Test the executable
echo -e "${YELLOW}Testing executable...${NC}"
if [[ "$PLATFORM" == "Windows" ]]; then
    dist/curateur.exe --version 2>/dev/null || dist/curateur.exe --help | head -n 5
elif [[ "$PLATFORM" == "macOS" ]] && [ -f "dist/curateur" ]; then
    dist/curateur --version 2>/dev/null || dist/curateur --help | head -n 5
elif [ -f "dist/curateur" ]; then
    dist/curateur --version 2>/dev/null || dist/curateur --help | head -n 5
fi

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Executable works${NC}"
else
    echo -e "${YELLOW}⚠ Could not test executable (may need --help flag)${NC}"
fi
echo ""

# Platform-specific next steps
echo -e "${BLUE}Next steps:${NC}"
if [[ "$PLATFORM" == "macOS" ]]; then
    echo "  1. Test: ./dist/curateur --help"
    echo "  2. Create DMG: ./build/scripts/create-dmg.sh"
    echo "  3. Code sign (optional): codesign -s 'Developer ID' dist/Curateur.app"
elif [[ "$PLATFORM" == "Windows" ]]; then
    echo "  1. Test: .\\dist\\curateur.exe --help"
    echo "  2. Create installer: iscc build/windows/curateur-setup.iss"
    echo "  3. Sign (optional): signtool sign /f cert.pfx dist/curateur.exe"
else
    echo "  1. Test: ./dist/curateur --help"
    echo "  2. Create AppImage: python-appimage build app curateur"
    echo "  3. Create .deb: ./build/scripts/create-deb.sh"
fi
echo ""

echo -e "${GREEN}════════════════════════════════════════${NC}"
echo -e "${GREEN}Build complete! 🎉${NC}"
echo -e "${GREEN}════════════════════════════════════════${NC}"
