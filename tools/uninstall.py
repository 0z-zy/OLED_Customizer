"""
OLED Customizer - Uninstaller
Removes all user data, config files, and startup registry entry.
"""

import os
import shutil
import winreg
import ctypes
import sys

APP_NAME = "OLED Customizer"


def is_admin():
    """Check if running with admin privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def get_app_data_path():
    """Get the app data folder path."""
    return os.path.join(os.environ.get('APPDATA', ''), APP_NAME)


def remove_app_data():
    """Remove the app data folder and all its contents."""
    app_data = get_app_data_path()
    
    if os.path.exists(app_data):
        try:
            shutil.rmtree(app_data)
            print(f"✓ Removed app data folder: {app_data}")
            return True
        except Exception as e:
            print(f"✗ Failed to remove app data: {e}")
            return False
    else:
        print(f"✓ App data folder not found (already clean)")
        return True


def remove_startup_entry():
    """Remove the Windows startup registry entry."""
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
        try:
            winreg.DeleteValue(key, APP_NAME)
            print(f"✓ Removed startup registry entry")
        except FileNotFoundError:
            print(f"✓ Startup entry not found (already clean)")
        winreg.CloseKey(key)
        return True
    except Exception as e:
        print(f"✗ Failed to remove startup entry: {e}")
        return False


def show_completion_message(success):
    """Show a completion message box."""
    if success:
        title = "Uninstall Complete"
        message = f"{APP_NAME} has been successfully uninstalled.\n\nThe following were removed:\n• App data and config files\n• Startup registry entry\n\nYou can now delete the program files manually."
        icon = 0x40  # MB_ICONINFORMATION
    else:
        title = "Uninstall Incomplete"
        message = f"Some items could not be removed.\nPlease check the console output for details."
        icon = 0x30  # MB_ICONWARNING
    
    ctypes.windll.user32.MessageBoxW(0, message, title, icon)


def main():
    print("=" * 50)
    print(f"  {APP_NAME} Uninstaller")
    print("=" * 50)
    print()
    
    # Confirm with user
    result = ctypes.windll.user32.MessageBoxW(
        0,
        f"This will remove all {APP_NAME} data:\n\n• Configuration files\n• Saved credentials\n• Startup entry\n\nThis cannot be undone. Continue?",
        f"Uninstall {APP_NAME}",
        0x04 | 0x30  # MB_YESNO | MB_ICONWARNING
    )
    
    if result != 6:  # IDYES = 6
        print("Uninstall cancelled by user.")
        return
    
    print("Starting uninstall process...")
    print()
    
    success = True
    
    # Remove app data
    if not remove_app_data():
        success = False
    
    # Remove startup entry
    if not remove_startup_entry():
        success = False
    
    print()
    print("=" * 50)
    
    if success:
        print("✓ Uninstall completed successfully!")
    else:
        print("⚠ Uninstall completed with some errors.")
    
    print("=" * 50)
    
    show_completion_message(success)


if __name__ == "__main__":
    main()
