# Build Infrastructure

This directory contains all the files needed to build standalone executables and installers for curateur.

## Quick Start

### Build for your current platform

```bash
# Install PyInstaller
pip install pyinstaller

# Build executable
./build/scripts/build-all.sh
# On Windows: build\scripts\build-all.bat

# Output: dist/curateur or dist/curateur.exe
```

### Test the executable

```bash
./dist/curateur --help
# On Windows: dist\curateur.exe --help
```

---

## Directory Structure

```
build/
├── pyinstaller/
│   └── curateur.spec          # PyInstaller build configuration
├── scripts/
│   ├── build-all.sh           # Main build script (cross-platform)
│   └── create-dmg.sh          # macOS DMG creator
├── windows/
│   ├── curateur-setup.iss     # Inno Setup installer config
│   └── build-installer.bat    # Windows installer builder
├── icons/                      # Application icons (TODO)
│   ├── curateur.ico           # Windows icon
│   ├── curateur.icns          # macOS icon
│   └── curateur.png           # Linux icon
└── README.md                  # This file
```

---

## Platform-Specific Instructions

### Windows

**Requirements:**
- Python 3.8+
- PyInstaller: `pip install pyinstaller`
- Inno Setup 6+ (for installer): https://jrsoftware.org/isinfo.php

**Build executable:**
```batch
build\scripts\build-all.bat
```

**Create installer:**
```batch
build\windows\build-installer.bat
```

**Output:**
- `dist/curateur.exe` - Standalone executable (~45-60MB)
- `build/installers/Curateur-Setup-1.0.0.exe` - Installer (~50MB)

**Sign executable (optional):**
```batch
signtool sign /f your-cert.pfx /p password /t http://timestamp.digicert.com dist\curateur.exe
```

---

### macOS

**Requirements:**
- Python 3.8+
- PyInstaller: `pip install pyinstaller`
- create-dmg (optional): `brew install create-dmg`

**Build executable:**
```bash
./build/scripts/build-all.sh
```

**Create DMG:**
```bash
./build/scripts/create-dmg.sh
```

**Output:**
- `dist/curateur` - Standalone executable (~40-55MB)
- `dist/Curateur.app` - App bundle (if built)
- `dist/Curateur-1.0.0-macOS.dmg` - DMG installer (~50MB)

**Code sign (optional):**
```bash
# Sign app
codesign --deep --force --verify --verbose \
  --sign "Developer ID Application: Your Name (TEAM_ID)" \
  --options runtime \
  dist/Curateur.app

# Sign DMG
codesign --force --verify --verbose \
  --sign "Developer ID Application: Your Name (TEAM_ID)" \
  dist/Curateur-1.0.0-macOS.dmg
```

**Notarize for Gatekeeper:**
```bash
# Submit for notarization
xcrun notarytool submit dist/Curateur-1.0.0-macOS.dmg \
  --apple-id your-apple-id@example.com \
  --team-id TEAM_ID \
  --wait

# Staple notarization ticket
xcrun stapler staple dist/Curateur-1.0.0-macOS.dmg
```

---

### Linux

**Requirements:**
- Python 3.8+
- PyInstaller: `pip install pyinstaller`

**Build executable:**
```bash
./build/scripts/build-all.sh
```

**Output:**
- `dist/curateur` - Standalone executable (~40-55MB)

**Create AppImage (optional):**
```bash
# Install python-appimage
pip install python-appimage

# Build AppImage
python-appimage build app -l manylinux2014_x86_64 curateur

# Output: curateur-x86_64.AppImage
```

**Create .deb package (Debian/Ubuntu):**
```bash
# Install build tools
sudo apt-get install dh-make devscripts

# Create package
# (TODO: Add debian/ directory with control files)
```

---

## PyInstaller Configuration

The `pyinstaller/curateur.spec` file controls how the executable is built:

**Key settings:**
- **One-file mode**: All dependencies bundled into single executable
- **Console app**: Keeps terminal window (required for CLI)
- **UPX compression**: Enabled to reduce file size
- **Hidden imports**: Explicitly includes all curateur modules
- **Excluded modules**: Removes test dependencies to reduce size

**Customization:**
Edit `build/pyinstaller/curateur.spec` to:
- Add application icon (uncomment `icon=` lines)
- Change output name
- Include additional data files
- Adjust compression settings

---

## Application Icons

**TODO**: Create application icons in `build/icons/`

Required formats:
- **Windows**: `curateur.ico` (multi-resolution .ico file)
  - Recommended sizes: 16x16, 32x32, 48x48, 256x256
  - Create with: https://www.imagemagick.org/ or GIMP

- **macOS**: `curateur.icns` (Apple icon format)
  - Recommended sizes: 16x16 to 1024x1024 (multiple resolutions)
  - Create with: `iconutil` (built into macOS) or third-party tools

- **Linux**: `curateur.png` (standard PNG)
  - Recommended size: 256x256 or 512x512
  - Standard PNG format

Once icons are created, update:
1. `pyinstaller/curateur.spec` - Uncomment icon lines
2. `windows/curateur-setup.iss` - Update icon paths

---

## GitHub Actions Automated Builds

The `.github/workflows/release.yml` workflow automatically builds executables for all platforms when you push a git tag:

**Trigger a release:**
```bash
# Tag a version
git tag -a v1.0.0 -m "Release version 1.0.0"
git push origin v1.0.0

# GitHub Actions will automatically:
# 1. Build Windows .exe
# 2. Build macOS executable and .dmg
# 3. Build Linux executable
# 4. Publish to PyPI
# 5. Create GitHub Release with all artifacts
```

**Manual workflow dispatch:**
You can also trigger builds manually from the GitHub Actions tab.

---

## Testing Builds

**Smoke test checklist:**

```bash
# Test basic functionality
./dist/curateur --help
./dist/curateur --version

# Test with dry-run
./dist/curateur --dry-run --systems nes

# Test configuration loading
./dist/curateur --config config.yaml.example --dry-run --systems nes

# Check file size (should be 40-60MB)
ls -lh dist/curateur*
```

**Common issues:**

1. **Missing modules**: Add to `hiddenimports` in curateur.spec
2. **Runtime errors**: Check PyInstaller warnings during build
3. **Large file size**: Review excluded modules, enable UPX
4. **Import errors**: Verify all dependencies in requirements.txt

---

## Distribution Checklist

Before distributing executables:

- [ ] Test on clean system (no Python installed)
- [ ] Verify all features work in standalone mode
- [ ] Check file size is reasonable (<100MB)
- [ ] Sign executables (Windows/macOS)
- [ ] Scan for malware (optional, for peace of mind)
- [ ] Test installation process
- [ ] Verify uninstaller works (Windows)
- [ ] Update CHANGELOG.md with version notes
- [ ] Create release notes

---

## Troubleshooting

### Windows: "Missing DLL" errors
- Rebuild with PyInstaller in clean venv
- Check excluded modules aren't removing needed DLLs

### macOS: "App is damaged" warning
- App needs to be code signed or user must allow in Security preferences
- For distribution, proper code signing is required

### Linux: "Permission denied"
- Make executable: `chmod +x dist/curateur`

### All platforms: Import errors
- Check PyInstaller console output for warnings
- Add missing modules to `hiddenimports` in spec file

---

## Advanced: Cross-Platform Builds

**Building for other platforms requires:**

- **Windows from Linux/Mac**: Use Wine or VM
- **macOS from Windows/Linux**: Requires macOS VM (Hackintosh or cloud)
- **Linux from Windows/Mac**: Use Docker or VM

**GitHub Actions handles this automatically** - just push a tag!

---

## File Size Optimization

Current executable sizes:
- Windows: ~45-60MB
- macOS: ~40-55MB
- Linux: ~40-55MB

**Reduction strategies:**
1. Enable UPX compression (already enabled)
2. Exclude unused dependencies (check requirements.txt)
3. Remove unnecessary data files
4. Use `--strip` flag (may cause issues on some platforms)

**Trade-offs:**
- Smaller = slower startup time (decompression)
- Larger = faster startup, easier debugging

---

## Additional Resources

- PyInstaller documentation: https://pyinstaller.org/
- Inno Setup documentation: https://jrsoftware.org/ishelp/
- create-dmg: https://github.com/create-dmg/create-dmg
- Code signing guide: https://developer.apple.com/support/code-signing/
- Windows signing: https://docs.microsoft.com/en-us/windows/win32/seccrypto/signtool
