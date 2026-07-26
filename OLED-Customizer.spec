# -*- mode: python ; coding: utf-8 -*-

import os
import glob

block_cipher = None

# Base path for the project
base_path = os.getcwd()

# Dynamically find HardwareMonitor package and DLLs
hw_monitor_dlls = []
hw_monitor_pkg_datas = []

# Paths to search for the HardwareMonitor package (miniconda first - that's where it's installed)
# NOTE: only Python313 paths — the build runs on conda Python 3.13, and
# pulling packages from a Python 3.14 site-packages produces cp314 binaries
# the bundled 3.13 interpreter cannot load.
hw_search_paths = [
    'C:\\ProgramData\\miniconda3\\Lib\\site-packages',
    os.path.expanduser('~\\AppData\\Roaming\\Python\\Python313\\site-packages'),
    os.path.expanduser('~\\AppData\\Local\\Packages\\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\\LocalCache\\local-packages\\Python313\\site-packages'),
]

try:
    import HardwareMonitor
    hw_path = os.path.dirname(HardwareMonitor.__file__)
    dll_pattern = os.path.join(hw_path, 'lib', '*.dll')
    if glob.glob(dll_pattern):
        hw_monitor_dlls = [(dll_pattern, 'HardwareMonitor/lib')]
        print(f"Found HardwareMonitor DLLs at: {dll_pattern}")
except ImportError:
    # HardwareMonitor not in current Python - find it manually
    hw_pkg_found = False
    for sp in hw_search_paths:
        hw_pkg_dir = os.path.join(sp, 'HardwareMonitor')
        if os.path.isdir(hw_pkg_dir):
            print(f"Found HardwareMonitor package at: {hw_pkg_dir}")
            hw_pkg_found = True
            # Collect all files from the package
            for root, dirs, files in os.walk(hw_pkg_dir):
                # Skip __pycache__
                dirs[:] = [d for d in dirs if d != '__pycache__']
                for f in files:
                    if f.endswith('.pyc'): continue
                    full = os.path.join(root, f)
                    rel_dir = os.path.relpath(root, sp)
                    if 'lib' in rel_dir.split(os.sep) and f.endswith('.dll'):
                        hw_monitor_dlls.append((full, rel_dir))
                    else:
                        hw_monitor_pkg_datas.append((full, rel_dir))
            break
    if not hw_pkg_found:
        print("WARNING: HardwareMonitor package not found - hardware monitoring will not work!")

from PyInstaller.utils.hooks import collect_all

def collect_pkg(name):
    try:
        datas, binaries, hiddenimports = collect_all(name)
        return datas, binaries, hiddenimports
    except:
        return [], [], []

# List of problematic packages to collect all data/submodules for
problem_pkgs = [
    'pycaw', 'comtypes', 'OpenSSL', 'cryptography', 
    'pynput', 'winrt', 'winrt.windows.foundation', 
    'winrt.windows.foundation.collections', 'winrt.windows.storage',
    'winrt.windows.media.control',
    'wmi', 'pythonnet', 'psutil',
    'HardwareMonitor'
]

extra_datas = []
extra_binaries = []
extra_hidden = []

for pkg in problem_pkgs:
    d, b, h = collect_pkg(pkg)
    extra_datas += d
    extra_binaries += b
    extra_hidden += h

# Conda stdlib extension modules (_ctypes, _sqlite3, _ssl, _lzma, _bz2,
# _tkinter, ...) link against runtime DLLs in Library\bin which PyInstaller's
# dependency scan misses on this setup, yielding an exe that dies with
# "DLL load failed while importing _xxx". Bundle the whole set explicitly.
import sys as _sys
_conda_lib_bin = os.path.join(_sys.prefix, 'Library', 'bin')
_conda_dll_patterns = [
    'ffi*.dll', 'libffi*.dll',            # _ctypes
    'sqlite3*.dll',                        # _sqlite3
    'libcrypto*.dll', 'libssl*.dll',       # _ssl, _hashlib
    'liblzma*.dll',                        # _lzma
    'libbz2*.dll', 'LIBBZ2*.dll', 'bz2*.dll',  # _bz2
    'libexpat*.dll',                       # pyexpat, _elementtree
    'tcl86*.dll', 'tk86*.dll',             # _tkinter
    'zlib*.dll',                           # tk/zlib users
]
_seen_dlls = set()
for _pat in _conda_dll_patterns:
    for _p in glob.glob(os.path.join(_conda_lib_bin, _pat)):
        _base = os.path.basename(_p).lower()
        if _base not in _seen_dlls:
            _seen_dlls.add(_base)
            extra_binaries.append((_p, '.'))
            print(f"Explicitly bundling {_p}")

# List of assets to include
added_files = [
    ('version.py', '.'),
    ('src/lib/PresentMon.dll', 'src/lib'),
] + hw_monitor_dlls + hw_monitor_pkg_datas + extra_datas

print(f"Collected {len(extra_datas)} extra data files, {len(extra_binaries)} binaries, {len(extra_hidden)} hidden imports")

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

# Aggressively find all potential site-packages locations
extra_paths = [base_path]

# Add standard site.getusersitepackages()
import site
user_site = site.getusersitepackages()
if user_site and os.path.isdir(user_site):
    extra_paths.append(user_site)

# Hard-coded fallbacks for common Windows paths (3.13 only — must match the
# conda interpreter's ABI; see note above)
roaming_base = os.path.expanduser('~\\AppData\\Roaming\\Python')
if os.path.isdir(roaming_base):
    for ver in ['Python313']:
        p = os.path.join(roaming_base, ver, 'site-packages')
        if os.path.isdir(p) and p not in extra_paths:
            extra_paths.append(p)
            print(f"Added hard-coded site-packages: {p}")

# Also check Local AppData (Miniconda / PSF versions)
local_base = os.path.expanduser('~\\AppData\\Local\\Python')
if os.path.isdir(local_base):
    for ver in ['Python313']:
        p = os.path.join(local_base, ver, 'site-packages')
        if os.path.isdir(p) and p not in extra_paths:
            extra_paths.append(p)

print(f"Final PyInstaller Pathex: {extra_paths}")

a = Analysis(
    ['main.py'],
    pathex=extra_paths,
    binaries=extra_binaries,
    datas=added_files,
    hiddenimports=list(set([
        'psutil', 'PIL', 'PIL.Image', 'PIL.ImageDraw', 'PIL.ImageFont',
        'requests', 'win32gui', 'win32api', 'win32con', 'win32process',
        'pystray', 'asyncio', 'winrt', 'winrt.windows.media.control',
        'winrt.windows.foundation', 'winrt.windows.media',
        'winrt.windows.foundation.collections',
        '_winrt_windows_foundation', '_winrt_windows_media_control',
        'HardwareMonitor', 'HardwareMonitor.Hardware',
        'clr', 'pythonnet', 'tkinter', 'pynput', 'pynput.keyboard',
        'pynput.mouse', 'pynput.keyboard._win32', 'pynput.mouse._win32',
        'src.SettingsWindow', 'src.Calculator', 'src.DiscordRPC', 'wmi', 'OpenSSL', 'OpenSSL.crypto',
        'OpenSSL.SSL', 'cryptography', 'pycaw', 'pycaw.pycaw', 'comtypes',
    ] + extra_hidden)),
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
