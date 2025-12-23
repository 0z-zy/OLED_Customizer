# -*- mode: python ; coding: utf-8 -*-

import os

block_cipher = None

# Base path for the project
base_path = os.getcwd()

# List of assets to include
added_files = [
    ('version.py', '.'),
    ('C:/Users/super/AppData/Local/Packages/PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0/LocalCache/local-packages/Python313/site-packages/HardwareMonitor/lib/*.dll', 'HardwareMonitor/lib'),
]

# Recursively add everything in 'content' folder
for root, dirs, files in os.walk('content'):
    for filename in files:
        if filename.endswith(".py") or filename.endswith(".pyc"): continue
        file_path = os.path.join(root, filename)
        # Target path inside bundle (preserve structure)
        # e.g. content/fonts/MunroSmall.ttf -> content/fonts
        target_dir = root.replace("\\", "/") 
        added_files.append((file_path, target_dir))

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
        'tkinter',
        'pynput.keyboard._win32',
        'pynput.mouse._win32',
        'src.SettingsWindow',
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
    upx=False,
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
    version='version_info.py',
)
