# -*- mode: python ; coding: utf-8 -*-

import os

block_cipher = None

# Base path for the project
base_path = os.getcwd()

# List of assets to include
added_files = [
    ('content/fonts/*.ttf', 'content/fonts'),
    ('content/assets/icons/*.png', 'content/assets/icons'),
    ('content/assets/icons/*.ico', 'content/assets/icons'),
    ('version.py', '.'),
    ('C:/Users/super/AppData/Local/Packages/PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0/LocalCache/local-packages/Python313/site-packages/HardwareMonitor/lib/*.dll', 'HardwareMonitor/lib'),
]

a = Analysis(
    ['main.py'],
    pathex=[base_path],
    binaries=[],
    datas=added_files,
    hiddenimports=[
        'psutil',
        'PIL',
        'requests',
        'win32gui',
        'win32api',
        'win32con',
        'pystray',
        'pysnmp',
        'asyncio',
        'comtypes',
        'winrt',
        'winrt.windows.media.control',
        'winrt.windows.foundation',
        'HardwareMonitor',
        'HardwareMonitor.Hardware',
        'clr',
        'pythonnet',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='OLED-Customizer',
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
    icon=['content/assets/icons/icon.ico'],
    uac_admin=True,
)
