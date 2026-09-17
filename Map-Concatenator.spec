# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for Tile Concatenator

import os
import sys

block_cipher = None

a = Analysis(
    [os.path.join('src', 'app', 'Map-Concator-App.py')],
    pathex=[os.path.join(os.getcwd(), 'src', 'app')],
    binaries=[],
    datas=[
        (os.path.join('src', 'app', 'media'), 'media'),
        (os.path.join('src', 'app', 'core'), 'core'),
        (os.path.join('src', 'app', 'utils'), 'utils'),
        (os.path.join('src', 'app', 'kataho'), 'kataho'),
    ],
    hiddenimports=[
        'selenium',
        'PIL',
        'numpy',
        'scipy',
        'cv2',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludedimports=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    name='Tile-Concatenator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Tile-Concatenator',
)
