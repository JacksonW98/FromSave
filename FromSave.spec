# -*- mode: python ; coding: utf-8 -*-
import os
import sys

from PyInstaller.utils.hooks import collect_all

datas = [('fromsave.ico', '.')]
binaries = []
hiddenimports = ['PySide6.QtMultimedia']

tmp_ret = collect_all('pynput')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

if sys.platform.startswith('linux'):
    # GL/driver userspace libs must match the host's graphics driver at
    # runtime; shipping the build container's copies breaks GLX elsewhere.
    _gl_libs = (
        'libGL.so', 'libGLX', 'libEGL', 'libOpenGL.so', 'libGLdispatch',
        'libgbm', 'libglapi', 'libdrm',
        # Old toolchain runtimes shadow the host's and break its Mesa driver.
        'libstdc++', 'libgcc_s',
        # X11/xcb client stack and Mesa support libs: the host GL driver
        # links against these, so bundled older copies break GLX init.
        'libX11', 'libxcb-', 'libXext', 'libXrender', 'libXrandr',
        'libXfixes', 'libXcomposite', 'libXdamage', 'libXau', 'libXdmcp',
        'libexpat', 'libz.so', 'libzstd', 'libffi',
    )
    a.binaries = [
        b for b in a.binaries
        if not os.path.basename(b[0]).startswith(_gl_libs)
    ]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='FromSave',
    icon='fromsave.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    Tree('ui', prefix='ui', excludes=['__pycache__', '*.py', '*.pyc']),
    strip=False,
    upx=True,
    upx_exclude=[],
    name='FromSave',
)
