# -*- mode: python ; coding: utf-8 -*-

import os
import glob

block_cipher = None

# Base path for the project
base_path = os.getcwd()

# Dynamically find HardwareMonitor DLLs
hw_monitor_dlls = []
try:
    import HardwareMonitor
    hw_path = os.path.dirname(HardwareMonitor.__file__)
    dll_pattern = os.path.join(hw_path, 'lib', '*.dll')
    if glob.glob(dll_pattern):
        hw_monitor_dlls = [(dll_pattern, 'HardwareMonitor/lib')]
        print(f"Found HardwareMonitor DLLs at: {dll_pattern}")
except ImportError:
    # Try common fallback locations
    fallback_paths = [
        os.path.expanduser('~\\AppData\\Local\\Packages\\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\\LocalCache\\local-packages\\Python313\\site-packages\\HardwareMonitor\\lib\\*.dll'),
        os.path.expanduser('~\\AppData\\Roaming\\Python\\Python314\\site-packages\\HardwareMonitor\\lib\\*.dll'),
        os.path.expanduser('~\\AppData\\Roaming\\Python\\Python313\\site-packages\\HardwareMonitor\\lib\\*.dll'),
    ]
    for path in fallback_paths:
        if glob.glob(path):
            hw_monitor_dlls = [(path, 'HardwareMonitor/lib')]
            print(f"Found HardwareMonitor DLLs at fallback: {path}")
            break
    if not hw_monitor_dlls:
        print("WARNING: HardwareMonitor DLLs not found - hardware monitoring may not work!")

# List of assets to include
added_files = [
    ('version.py', '.'),
] + hw_monitor_dlls

# Recursively add everything in 'content' folder
content_path = os.path.abspath('content')
print(f"Collecting assets from: {content_path}")

if not os.path.exists(content_path):
    print("WARNING: 'content' directory NOT found!")

for root, dirs, files in os.walk(content_path):
    for filename in files:
        if filename.endswith(".py") or filename.endswith(".pyc"): continue
        
        file_path = os.path.join(root, filename)
        
        # Calculate relative path from content root to keep structure
        # e.g. C:\...\content\fonts\Munro.ttf -> fonts
        rel_dir = os.path.relpath(root, content_path)
        
        if rel_dir == ".":
            target_dir = "content"
        else:
            target_dir = os.path.join("content", rel_dir)
            
        print(f"Adding {filename} -> {target_dir}")
        added_files.append((file_path, target_dir))

a = Analysis(
    ['main.py'],
    pathex=[base_path],
    binaries=[],
    datas=added_files,
    hiddenimports=[
        'psutil',
        'PIL',
        'PIL.Image',
        'PIL.ImageDraw',
        'PIL.ImageFont',
        'requests',
        'win32gui',
        'win32api',
        'win32con',
        'pystray',
        'asyncio',
        'winrt',
        'winrt.windows.media.control',
        'winrt.windows.foundation',
        'winrt.windows.media',
        'HardwareMonitor',
        'HardwareMonitor.Hardware',
        'clr',
        'pythonnet',
        'tkinter',
        'pynput',
        'pynput.keyboard',
        'pynput.mouse',
        'pynput.keyboard._win32',
        'pynput.mouse._win32',
        'src.SettingsWindow',
        'wmi',
        'OpenSSL',
        'cryptography',
        'pycaw',
        'pycaw.pycaw',
        'comtypes',
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
