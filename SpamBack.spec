# -*- mode: python ; coding: utf-8 -*-
a = Analysis(
    ['app.py'],
    pathex=['src'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'google.genai',
        'google.auth',
        'transformers',
        'torch',
        'numpy',
        'PIL',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludedimports=['tkinter', 'test', 'tests'],
    noarchive=False,
    collect_submodules=['torch', 'transformers', 'google.genai', 'google.auth'],
)
pyz = PYZ(a.pure, a.zipped_data, cipher=None)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SpamBack',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # Enable console to see error messages
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file='entitlements.plist',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='SpamBack',
)
app = BUNDLE(
    coll,
    name='SpamBack.app',
    icon=None,
    bundle_identifier='com.autoelk.spamback',
    info_plist={
        'NSPrincipalClass': 'NSApplication',
        'NSAppleEventsUsageDescription': 'SpamBack needs to send Apple Events to control Messages and Contacts.',
        'NSContactsUsageDescription': 'SpamBack may read Contacts (via Apple Events) to match senders.',
    },
)
