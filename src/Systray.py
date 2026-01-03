import logging
import os
import atexit
import sys
from threading import Thread

from PIL import Image
from pystray import MenuItem as Item, Icon, Menu

from src.image_utils import fetch_content_path
from src.image_utils import fetch_content_path
from src.utils import fetch_app_data_path, set_startup, is_startup_enabled

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
        Menu.SEPARATOR,
        Item(
            "Run at Startup",
            toggle_startup,
            checked=lambda item: is_startup_enabled(),
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
