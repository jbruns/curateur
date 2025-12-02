#!/bin/bash
# Create macOS DMG installer for Curateur
#
# Usage:
#   ./build/scripts/create-dmg.sh
#
# Requirements:
#   - macOS
#   - Curateur.app built in dist/ (run build-all.sh first)
#   - create-dmg (optional, install with: brew install create-dmg)
#
# Output:
#   dist/Curateur-1.0.0-macOS.dmg

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}Creating macOS DMG installer...${NC}"
echo ""

# Check platform
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo -e "${RED}✗ This script must be run on macOS${NC}"
    exit 1
fi

# Check if Curateur.app exists
if [ ! -d "dist/Curateur.app" ] && [ ! -f "dist/curateur" ]; then
    echo -e "${RED}✗ dist/Curateur.app not found${NC}"
    echo "Run build-all.sh first to create the app bundle"
    exit 1
fi

# Get version
VERSION=$(grep -E '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')

# If we only have the executable, create a minimal app bundle
if [ ! -d "dist/Curateur.app" ] && [ -f "dist/curateur" ]; then
    echo -e "${YELLOW}Creating app bundle from executable...${NC}"

    mkdir -p dist/Curateur.app/Contents/MacOS
    mkdir -p dist/Curateur.app/Contents/Resources

    cp dist/curateur dist/Curateur.app/Contents/MacOS/

    cat > dist/Curateur.app/Contents/Info.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>Curateur</string>
    <key>CFBundleDisplayName</key>
    <string>Curateur</string>
    <key>CFBundleIdentifier</key>
    <string>com.jbruns.curateur</string>
    <key>CFBundleVersion</key>
    <string>$VERSION</string>
    <key>CFBundleShortVersionString</key>
    <string>$VERSION</string>
    <key>CFBundleExecutable</key>
    <string>curateur</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.13</string>
</dict>
</plist>
EOF

    echo -e "${GREEN}✓ App bundle created${NC}"
fi

# Create DMG using create-dmg if available, otherwise use hdiutil
if command -v create-dmg &> /dev/null; then
    echo -e "${YELLOW}Using create-dmg...${NC}"

    create-dmg \
        --volname "Curateur $VERSION" \
        --window-pos 200 120 \
        --window-size 600 400 \
        --icon-size 100 \
        --icon "Curateur.app" 175 120 \
        --hide-extension "Curateur.app" \
        --app-drop-link 425 120 \
        "dist/Curateur-$VERSION-macOS.dmg" \
        "dist/Curateur.app"
else
    echo -e "${YELLOW}Using hdiutil (basic DMG)...${NC}"
    echo -e "${YELLOW}Note: Install create-dmg for prettier DMGs: brew install create-dmg${NC}"
    echo ""

    # Create temporary directory for DMG contents
    DMG_DIR=$(mktemp -d)

    # Copy app bundle
    cp -R "dist/Curateur.app" "$DMG_DIR/"

    # Create Applications symlink
    ln -s /Applications "$DMG_DIR/Applications"

    # Create DMG
    hdiutil create -volname "Curateur $VERSION" \
        -srcfolder "$DMG_DIR" \
        -ov -format UDZO \
        "dist/Curateur-$VERSION-macOS.dmg"

    # Cleanup
    rm -rf "$DMG_DIR"
fi

echo ""
echo -e "${GREEN}✓ DMG created${NC}"
ls -lh "dist/Curateur-$VERSION-macOS.dmg"
echo ""

echo -e "${BLUE}Next steps:${NC}"
echo "  1. Test: open dist/Curateur-$VERSION-macOS.dmg"
echo "  2. Sign (optional): codesign -s 'Developer ID' dist/Curateur-$VERSION-macOS.dmg"
echo "  3. Notarize (for distribution): xcrun notarytool submit ..."
echo ""

echo -e "${GREEN}Done! 🎉${NC}"
