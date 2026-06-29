# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['shadowmen/__main__.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['gi.repository.Gtk', 'gi.repository.Gdk', 'gi.repository.GLib', 'gi.repository.cairo', 'cairo'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='shadowmen',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
