# Application Icons

This directory should contain application icons for Windows, macOS, and Linux distributions.

## Required Files

### Windows
**File:** `curateur.ico`
- Multi-resolution .ico file
- Recommended sizes: 16x16, 32x32, 48x48, 256x256
- Tools: ImageMagick, GIMP, or online converters

**Create with ImageMagick:**
```bash
# From PNG source
convert curateur-256.png \
  -define icon:auto-resize=16,32,48,256 \
  curateur.ico
```

---

### macOS
**File:** `curateur.icns`
- Apple icon format with multiple resolutions
- Required sizes: 16x16, 32x32, 64x64, 128x128, 256x256, 512x512, 1024x1024
- Each size needs standard and @2x retina version

**Create with iconutil (macOS):**
```bash
# 1. Create iconset directory
mkdir curateur.iconset

# 2. Generate all required sizes
sips -z 16 16     curateur-1024.png --out curateur.iconset/icon_16x16.png
sips -z 32 32     curateur-1024.png --out curateur.iconset/icon_16x16@2x.png
sips -z 32 32     curateur-1024.png --out curateur.iconset/icon_32x32.png
sips -z 64 64     curateur-1024.png --out curateur.iconset/icon_32x32@2x.png
sips -z 128 128   curateur-1024.png --out curateur.iconset/icon_128x128.png
sips -z 256 256   curateur-1024.png --out curateur.iconset/icon_128x128@2x.png
sips -z 256 256   curateur-1024.png --out curateur.iconset/icon_256x256.png
sips -z 512 512   curateur-1024.png --out curateur.iconset/icon_256x256@2x.png
sips -z 512 512   curateur-1024.png --out curateur.iconset/icon_512x512.png
sips -z 1024 1024 curateur-1024.png --out curateur.iconset/icon_512x512@2x.png

# 3. Convert to icns
iconutil -c icns curateur.iconset
```

---

### Linux
**File:** `curateur.png`
- Standard PNG format
- Recommended size: 256x256 or 512x512
- Used for desktop entries and app menus

---

## Design Guidelines

### Icon Design Recommendations
- **Simple and recognizable** at small sizes (16x16)
- **Clear silhouette** - should be identifiable from shape alone
- **Consistent style** - match modern application icon trends
- **Readable text** - avoid small text that becomes illegible
- **Appropriate colors** - consider both light and dark themes

### Curateur Icon Ideas
Since curateur is about curating ROM collections, consider:
- **Collection/Archive theme**: Books, folders, library shelves
- **Retro gaming theme**: Pixel art, classic console controllers
- **Organization theme**: Filing cabinet, sorted boxes
- **Media theme**: Film reel, photo album
- **Combination**: Retro game controller inside a library/catalog icon

### Color Palette Suggestions
- **Primary**: Deep blue or purple (knowledge, organization)
- **Accent**: Bright cyan or orange (energy, retro)
- **Style**: Flat design with subtle gradients
- **Variants**: Consider dark mode compatibility

---

## Tools for Icon Creation

### Free Online Tools
- **Favicon.io**: https://favicon.io/ (simple icon generator)
- **RealFaviconGenerator**: https://realfavicongenerator.net/ (multi-platform)
- **ICO Convert**: https://icoconvert.com/ (format conversion)

### Desktop Software
- **GIMP**: Free, cross-platform image editor
- **Inkscape**: Free, vector graphics editor
- **Affinity Designer**: Paid, professional design tool
- **Adobe Illustrator**: Paid, industry standard

### macOS Built-in
- **Preview**: Can export to .icns from .png
- **iconutil**: Command-line tool (see above)

### Windows Tools
- **IcoFX**: Icon editor for Windows
- **Greenfish Icon Editor Pro**: Free icon editor

---

## Installation

Once you create the icons, update these files:

1. **PyInstaller spec:**
   ```python
   # In build/pyinstaller/curateur.spec
   icon='build/icons/curateur.ico',  # Windows
   icon='build/icons/curateur.icns',  # macOS
   ```

2. **Inno Setup script:**
   ```iss
   ; In build/windows/curateur-setup.iss
   SetupIconFile=build\icons\curateur.ico
   ```

3. **DMG creator:**
   ```bash
   # In build/scripts/create-dmg.sh
   --icon-size 100 \
   --icon "Curateur.app" 175 120
   ```

---

## Testing Icons

### Windows
```batch
REM View in File Explorer
explorer dist\curateur.exe

REM Check properties
start dist\curateur.exe /properties
```

### macOS
```bash
# View app bundle icon
open dist/Curateur.app

# Preview icon file
open build/icons/curateur.icns
```

### Linux
```bash
# View PNG
xdg-open build/icons/curateur.png
```

---

## Icon Checklist

Before releasing:
- [ ] All required formats created (.ico, .icns, .png)
- [ ] Icons look good at all sizes (16x16 to 1024x1024)
- [ ] Colors work on both light and dark backgrounds
- [ ] Icon is visually distinct from other apps
- [ ] Spec files updated with icon paths
- [ ] Test builds include icons
- [ ] Icons display correctly in installers

---

## Example Icon Source

You can start with a simple placeholder:

```bash
# Create a simple colored square placeholder
convert -size 1024x1024 xc:"#4A90E2" \
  -gravity center \
  -pointsize 400 -font Arial-Bold \
  -fill white -annotate +0+0 "C" \
  curateur-1024.png

# Then create all formats from this
convert curateur-1024.png -define icon:auto-resize=16,32,48,256 curateur.ico
```

Replace with a professional design before public release!

---

## Attribution

If you use graphics from external sources:
- Check license compatibility (GPL-3.0)
- Provide attribution if required
- Document sources in this README

---

**TODO**: Create professional icon designs and place files in this directory.
