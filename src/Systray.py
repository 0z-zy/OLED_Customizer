import logging
import os
import atexit
import sys
from threading import Thread

from PIL import Image
from pystray import MenuItem as Item, Icon, Menu

from src.image_utils import fetch_content_path
from src.utils import fetch_app_data_path, set_startup, is_startup_enabled
from src.debug_utils import toggle_debug_logging, is_debug_enabled
from src.updater import is_update_available, start_update_process
from src import ProfileBackup

logger = logging.getLogger("Systray")
systray_thread = None


def exit_app(icon):
    icon.stop()

    # Remove lock file on exit
    lock_file_path = fetch_app_data_path('.lock')
    if os.path.exists(lock_file_path):
        os.unlink(lock_file_path)

    logger.info("Disabled systray")
    os._exit(0)


def toggle_enabled(icon):
    icon.manager.enabled = not icon.manager.enabled
    icon.update_menu()


def toggle_clock(icon):
    if not icon.manager.user_preferences.valid:
        return

    # Exclusive logic: if enabling clock, disable hw monitor
    was_on = icon.manager.display_clock
    if not was_on:
        icon.manager.display_hw_monitor = False
        icon.manager.user_preferences.preferences["display_hw_monitor"] = False
    
    icon.manager.display_clock = not was_on
    icon.manager.user_preferences.preferences["display_timer"] = icon.manager.display_clock
    icon.manager.user_preferences.save_preferences()
    icon.update_menu()


def toggle_player(icon):
    if not icon.manager.user_preferences.valid:
        return

    icon.manager.display_player = not icon.manager.display_player
    icon.manager.user_preferences.preferences["display_player"] = icon.manager.display_player
    icon.manager.user_preferences.save_preferences()
    icon.update_menu()


def open_config(icon):
    os.startfile(icon.manager.user_preferences.config_path)


def toggle_hw_monitor(icon):
    if not icon.manager.user_preferences.valid:
        return

    # Exclusive logic: if enabling hw monitor, disable clock
    was_on = icon.manager.display_hw_monitor
    if not was_on:
        icon.manager.display_clock = False
        icon.manager.user_preferences.preferences["display_timer"] = False

    icon.manager.display_hw_monitor = not was_on
    icon.manager.user_preferences.preferences["display_hw_monitor"] = icon.manager.display_hw_monitor
    icon.manager.user_preferences.save_preferences()
    icon.manager.update_preferences()
    icon.update_menu()

def toggle_fps(icon):
    if not icon.manager.user_preferences.valid:
        return
    current = icon.manager.user_preferences.preferences.get("show_game_fps", False)
    icon.manager.user_preferences.preferences["show_game_fps"] = not current
    icon.manager.user_preferences.save_preferences()
    icon.manager.update_preferences()
    icon.update_menu()



def set_clock_style(icon, style):
    if not icon.manager.user_preferences.valid:
        return
    
    icon.manager.user_preferences.preferences["clock_style"] = style
    icon.manager.user_preferences.save_preferences()
    icon.manager.update_preferences()
    icon.update_menu()

def set_player_style(icon, style):
    if not icon.manager.user_preferences.valid:
        return
    
    icon.manager.user_preferences.preferences["player_style"] = style
    icon.manager.user_preferences.save_preferences()
    icon.manager.update_preferences()
    icon.update_menu()


def open_install_folder(icon):
    path_to_open = os.getcwd()
    if getattr(sys, 'frozen', False):
        path_to_open = os.path.dirname(sys.executable)
    elif __file__:
        path_to_open = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    os.startfile(path_to_open)

def toggle_startup(icon):
    current_state = is_startup_enabled()
    set_startup(not current_state)
    # No need to save to UserPreferences as this is a registry state, but we could sync them if we wanted.
    # The checkmark will query the registry freshly.
    pass # Menu update happens automatically? No, pystray dynamic menu needs a callback or reload
    # Pystray menus are often static unless updated.
    # But usage of checked=lambda calls the function every time the menu is shown.
    pass
    
def self_update_logic():
    available, latest = is_update_available()
    if available:
        start_update_process()
    else:
        logger.info("Update check: Already up to date!")

def toggle_debug(icon):
    enable = not is_debug_enabled()
    toggle_debug_logging(enable)
    
    # Save to preferences
    if hasattr(icon, "manager"):
        icon.manager.user_preferences.preferences["debug_enabled"] = enable
        icon.manager.user_preferences.save_preferences()
    
    icon.update_menu()

def get_update_label(item):
    if not hasattr(get_update_label, "_cached_label"):
        get_update_label._cached_label = "✨ Check updates"
    return get_update_label._cached_label

# ============ Profile Backup Functions ============

def do_backup_profiles(icon):
    """Backup SteelSeries profiles."""
    result = ProfileBackup.backup_profiles()
    if result:
        logger.info(f"Backup successful: {result}")
    else:
        logger.error("Backup failed!")

def do_restore_profiles(icon, backup_path):
    """
    Restore SteelSeries profiles from backup.
    SAFE VERSION: Requires user to manually close GG first.
    """
    import time
    import ctypes
    logger.info(f"do_restore_profiles called with path: {backup_path}")
    from src.utils import is_process_running
    
    # MessageBox constants
    MB_OK = 0x00
    MB_OKCANCEL = 0x01
    MB_YESNO = 0x04
    MB_ICONWARNING = 0x30
    MB_ICONERROR = 0x10
    MB_ICONINFO = 0x40
    IDOK = 1
    IDCANCEL = 2
    IDYES = 6
    IDNO = 7
    
    gg_processes = ["SteelSeriesGG.exe", "SteelSeriesGGClient.exe", "SteelSeriesEngine3.exe", 
                    "SteelSeriesEngine.exe", "SteelSeriesPrism.exe", "SteelSeriesSonar.exe"]
    
    # Step 1: Check if GG is running - if so, ask user to close it
    if is_process_running(gg_processes):
        result = ctypes.windll.user32.MessageBoxW(
            0,
            "SteelSeries GG must be COMPLETELY closed before restoring.\n\n"
            "Please:\n"
            "1. Right-click SteelSeries GG in system tray\n"
            "2. Click 'Quit SteelSeries GG'\n"
            "3. Wait a few seconds\n"
            "4. Try restore again\n\n"
            "Click OK after you've closed SteelSeries GG.",
            "Close SteelSeries GG First",
            MB_OKCANCEL | MB_ICONWARNING
        )
        if result != IDOK:
            logger.info("User cancelled restore")
            return
        
        # Check again after user says OK
        time.sleep(2)
        if is_process_running(gg_processes):
            ctypes.windll.user32.MessageBoxW(
                0,
                "SteelSeries GG is still running!\n\n"
                "Make sure to quit it completely from the system tray.\n"
                "Restore cancelled.",
                "Still Running",
                MB_OK | MB_ICONERROR
            )
            logger.error("GG still running after user prompt, aborting restore")
            return
    
    # Step 2: Confirm restore
    result = ctypes.windll.user32.MessageBoxW(
        0,
        f"Ready to restore from:\n{backup_path}\n\n"
        "A safety backup of your current settings will be created first.\n\n"
        "Proceed with restore?",
        "Confirm Restore",
        MB_YESNO | MB_ICONWARNING
    )
    if result != IDYES:
        logger.info("User cancelled restore confirmation")
        return
    
    # Step 3: Perform the restore
    if ProfileBackup.restore_profiles(backup_path):
        logger.info("Restore complete!")
        ctypes.windll.user32.MessageBoxW(
            0,
            "Restore complete!\n\n"
            "You can now start SteelSeries GG.\n"
            "(It will NOT auto-start to ensure clean database load)",
            "Restore Successful",
            MB_OK | MB_ICONINFO
        )
    else:
        logger.error("Restore failed!")
        ctypes.windll.user32.MessageBoxW(
            0,
            "Restore failed!\n\n"
            "Check the logs for details.\n"
            "Your original settings were backed up before the attempt.",
            "Restore Failed",
            MB_OK | MB_ICONERROR
        )

def do_vacuum_databases(icon):
    """Compact SteelSeries databases."""
    from src.utils import is_process_running
    if is_process_running(["SteelSeriesGG.exe", "SteelSeriesEngine3.exe"]):
        logger.error("Close SteelSeries GG before compacting!")
        return
    
    before, after = ProfileBackup.vacuum_databases()
    saved = before - after
    logger.info(f"Compacted databases: {before:.1f}MB -> {after:.1f}MB (saved {saved:.1f}MB)")

def build_restore_menu():
    """Build dynamic restore submenu with available backups."""
    logger.debug("Building restore menu...")
    backups = ProfileBackup.list_backups()
    logger.debug(f"Found {len(backups)} backups")
    if not backups:
        return [Item("No backups available", None, enabled=False)]
    
    items = []
    for name, path, count, mtime in backups[:10]:  # Limit to 10
        # Make label prettier
        display_name = name
        if name.startswith("pre_restore_"):
            display_name = "🛡️ Safety: " + name.replace("pre_restore_", "")
        
        label = f"{display_name} ({count} files)"
        logger.debug(f"Adding restore option: {label} -> {path}")
        # Create a closure to capture path correctly
        def make_restore_action(backup_path):
            def action(icon, item):
                logger.info(f"Restore action triggered for: {backup_path}")
                Thread(target=do_restore_profiles, args=(icon, backup_path), daemon=True).start()
            return action
        items.append(Item(label, make_restore_action(path)))
    return items

def run_systray_async(display_manager):
    global systray_thread
    if systray_thread:
        return

    menu = (
        Item(
            "Enable OLED Customizer",
            toggle_enabled,
            checked=lambda item: display_manager.enabled,
        ),
        Item(
            "Clock",
            Menu(
                Item(
                    "Show Clock",
                    toggle_clock,
                    checked=lambda item: display_manager.display_clock,
                ),
                Menu.SEPARATOR,
                Item(
                    "Standard",
                    lambda icon, item: set_clock_style(icon, "Standard"),
                    radio=True,
                    checked=lambda item: display_manager.user_preferences.get_preference("clock_style") == "Standard"
                ),
                Item(
                    "Big Timer",
                    lambda icon, item: set_clock_style(icon, "Big Timer"),
                    radio=True,
                    checked=lambda item: display_manager.user_preferences.get_preference("clock_style") == "Big Timer"
                ),
                Item(
                    "Date Focused",
                    lambda icon, item: set_clock_style(icon, "Date Focused"),
                    radio=True,
                    checked=lambda item: display_manager.user_preferences.get_preference("clock_style") == "Date Focused"
                ),
                Item(
                    "Analog",
                    lambda icon, item: set_clock_style(icon, "Analog"),
                    radio=True,
                    checked=lambda item: display_manager.user_preferences.get_preference("clock_style") == "Analog"
                ),
            ),
            enabled=lambda item: display_manager.enabled,
        ),
        Item(
            "Player",
            Menu(
                Item(
                    "Show Player",
                    toggle_player,
                    checked=lambda item: display_manager.display_player,
                ),
                Menu.SEPARATOR,
                Item(
                    "Standard",
                    lambda icon, item: set_player_style(icon, "Standard"),
                    radio=True,
                    checked=lambda item: display_manager.user_preferences.get_preference("player_style") == "Standard"
                ),
                Item(
                    "Compact",
                    lambda icon, item: set_player_style(icon, "Compact"),
                    radio=True,
                    checked=lambda item: display_manager.user_preferences.get_preference("player_style") == "Compact"
                ),
                Item(
                    "Centered",
                    lambda icon, item: set_player_style(icon, "Centered"),
                    radio=True,
                    checked=lambda item: display_manager.user_preferences.get_preference("player_style") == "Centered"
                ),
                Item(
                    "Ticker",
                    lambda icon, item: set_player_style(icon, "Ticker"),
                    radio=True,
                    checked=lambda item: display_manager.user_preferences.get_preference("player_style") == "Ticker"
                ),
                Item(
                    "Minimal",
                    lambda icon, item: set_player_style(icon, "Minimal"),
                    radio=True,
                    checked=lambda item: display_manager.user_preferences.get_preference("player_style") == "Minimal"
                ),
            ),
            enabled=lambda item: display_manager.enabled,
        ),
        Item(
            "Display HW Monitor",
            toggle_hw_monitor,
            checked=lambda item: display_manager.display_hw_monitor,
            enabled=lambda item: display_manager.enabled,
        ),
        Item(
            "   Show Game FPS (RTSS)",
            toggle_fps,
            checked=lambda item: display_manager.user_preferences.preferences.get("show_game_fps", False),
            enabled=lambda item: display_manager.enabled,
        ),
        Menu.SEPARATOR,
        Item(
            "Run at Startup",
            toggle_startup,
            checked=lambda item: is_startup_enabled(),
        ),
        Item(
            "Enable Debug Logging",
            toggle_debug,
            checked=lambda item: display_manager.user_preferences.preferences.get("debug_enabled", False),
        ),
        Menu.SEPARATOR,
        Item(
            "⚙️ Settings...",
            lambda icon, item: __import__("threading").Thread(
                target=__import__("src.SettingsWindow", fromlist=["open_settings"]).open_settings,
                args=(display_manager.user_preferences, display_manager.update_preferences),
                daemon=True
            ).start()
        ),
        Item(
            get_update_label,
            lambda icon: __import__("threading").Thread(target=self_update_logic, daemon=True).start()
        ),
        Item(
            "💾 SteelSeries Profiles",
            Menu(
                Item(
                    "Backup Now",
                    lambda icon, item: Thread(target=do_backup_profiles, args=(icon,), daemon=True).start()
                ),
                Item(
                    "Restore...",
                    Menu(lambda: build_restore_menu())
                ),
                Menu.SEPARATOR,
                Item(
                    "Compact Databases",
                    lambda icon, item: Thread(target=do_vacuum_databases, args=(icon,), daemon=True).start()
                ),
            )
        ),
        Menu.SEPARATOR,
        Item("Exit", exit_app),
    )

    # Systray ikonunu yükle: yoksa fallback oluştur
    try:
        icon_path = fetch_content_path("assets/icons/icon.png")
        icon_image = Image.open(icon_path)
    except Exception:
        # icon.png yoksa basit 16x16 siyah kare kullan
        icon_image = Image.new("1", (16, 16), 0)

    icon = Icon("OLED_Customizer", icon_image, "OLED Customizer", menu)
    icon.manager = display_manager

    logger.info("Enabled systray")
    systray_thread = Thread(target=icon.run, daemon=True)
    systray_thread.start()

    atexit.register(lambda: exit_app(icon))
