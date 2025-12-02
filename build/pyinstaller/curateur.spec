# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for building curateur standalone executable.

Usage:
    pyinstaller build/pyinstaller/curateur.spec

This creates a single executable in dist/ that bundles:
- Python runtime
- All dependencies (httpx, lxml, Pillow, rich, PyYAML, psutil)
- curateur source code
- Configuration example and documentation

Output:
    dist/curateur       (Linux/macOS)
    dist/curateur.exe   (Windows)
"""

import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect data files for lxml (includes XML parsing libraries)
datas = collect_data_files('lxml')

# Add bundled files that should be included
datas += [
    ('config.yaml.example', '.'),
    ('README.md', '.'),
    ('LICENSE', '.'),
]

# Collect all curateur submodules to ensure they're included
hiddenimports = collect_submodules('curateur')

# Add additional hidden imports that PyInstaller might miss
hiddenimports += [
    'curateur.api.client',
    'curateur.api.cache',
    'curateur.api.throttle',
    'curateur.api.error_handler',
    'curateur.api.response_parser',
    'curateur.api.credentials',
    'curateur.api.system_map',
    'curateur.api.connection_pool',
    'curateur.api.match_scorer',
    'curateur.api.name_verifier',
    'curateur.config.loader',
    'curateur.config.validator',
    'curateur.config.es_systems',
    'curateur.scanner.rom_scanner',
    'curateur.scanner.hash_calculator',
    'curateur.scanner.rom_types',
    'curateur.scanner.disc_handler',
    'curateur.scanner.m3u_parser',
    'curateur.media.downloader',
    'curateur.media.media_downloader',
    'curateur.media.media_types',
    'curateur.media.organizer',
    'curateur.media.region_selector',
    'curateur.media.url_selector',
    'curateur.gamelist.parser',
    'curateur.gamelist.generator',
    'curateur.gamelist.xml_writer',
    'curateur.gamelist.game_entry',
    'curateur.gamelist.metadata_merger',
    'curateur.gamelist.integrity_validator',
    'curateur.gamelist.path_handler',
    'curateur.workflow.orchestrator',
    'curateur.workflow.thread_pool',
    'curateur.workflow.work_queue',
    'curateur.workflow.evaluator',
    'curateur.workflow.progress',
    'curateur.workflow.performance',
    'curateur.ui.console_ui',
    'curateur.ui.prompts',
    'curateur.ui.keyboard_listener',
]

a = Analysis(
    ['../../curateur/cli.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude test dependencies
        'pytest',
        'pytest-cov',
        'pytest-asyncio',
        'pytest-mock',
        'respx',
        # Exclude unnecessary modules to reduce size
        'tkinter',
        'test',
        'unittest',
        'distutils',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='curateur',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # Enable UPX compression to reduce file size
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Keep console window for CLI tool
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # TODO: Add icon files when available
    # icon='build/icons/curateur.ico',  # Windows
    # icon='build/icons/curateur.icns',  # macOS
)

# For macOS, create an app bundle (optional)
if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='Curateur.app',
        icon=None,  # TODO: Add 'build/icons/curateur.icns'
        bundle_identifier='com.jbruns.curateur',
        info_plist={
            'CFBundleName': 'Curateur',
            'CFBundleDisplayName': 'Curateur',
            'CFBundleVersion': '1.0.0',
            'CFBundleShortVersionString': '1.0.0',
            'NSHighResolutionCapable': 'True',
            'LSMinimumSystemVersion': '10.13.0',
        },
    )
