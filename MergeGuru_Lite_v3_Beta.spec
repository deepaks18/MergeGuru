# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['main_gui_lite_v3.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'mergeguru_engine',
        'mergeguru_lite_v3.app',
        'mergeguru_lite_v3.filter_dialog',
        'mergeguru_lite_v3.preferences',
        'mergeguru_lite_v3.reports',
        'mergeguru_lite_v3.state',
        'prototypes.lite_redesign.brand',
        'prototypes.lite_redesign.category_picker',
        'prototypes.lite_redesign.selection',
        'prototypes.lite_redesign.theme',
        'prototypes.lite_redesign.workspace',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6', 'shiboken6'],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)
splash = Splash(
    'assets\\MergeGuru_Lite_v3_Beta_splash.png',
    binaries=a.binaries,
    datas=a.datas,
    text_pos=None,
    minify_script=True,
    always_on_top=True,
)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    splash,
    splash.binaries,
    [],
    name='MergeGuru_Lite_v3_Beta',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=['assets\\MergeGuru_Lite_v3_Beta.ico'],
)
