# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['main_gui_pro.py'],
    pathex=[],
    binaries=[],
    datas=[('assets\\mergeguru_pro.qss', 'assets')],
    hiddenimports=['mergeguru_engine'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter'],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='MergeGuru_Pro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=['assets\\MergeGuru_v1.ico'],
)
