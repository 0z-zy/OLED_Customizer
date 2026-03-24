"""
OLED Customizer - Settings GUI
Frameless window, sidebar navigation, custom widgets, clean aesthetics.
"""

import tkinter as tk
from tkinter import ttk, colorchooser, messagebox
import os
import logging
import shutil
import ctypes
from datetime import datetime
from threading import Thread

logger = logging.getLogger("OLED Customizer.Settings")
from src.UserPreferences import UserPreferences
from src.utils import set_startup, is_startup_enabled
from src.updater import is_update_available, start_update_process

# --- THEME CONSTANTS ---
class Colors:
    BG_ROOT = "#2b2b2b"       # Dark Gray background
    SIDEBAR = "#1f1f1f"       # Darker sidebar
    CONTENT = "#2b2b2b"       # Main content bg
    
    ACCENT_PRIMARY = "#ffffff" # White for enabled state
    ACCENT_HOVER   = "#e0e0e0"
    ACCENT_DIM     = "#888888"
    
    TEXT_MAIN  = "#ffffff"
    TEXT_DIM   = "#aaaaaa"
    
    CARD_BG    = "#383838"    # Lighter gray for cards
    CARD_HOVER = "#424242"
    BORDER     = "#444444"
    
    INPUT_BG   = "#1a1a1a"
    INPUT_FG   = "#eeeeee"
    
    DANGER     = "#e74c3c"

FONT_HEADER = ("Segoe UI", 16, "bold")
FONT_SUBHEADER = ("Segoe UI", 11, "bold")
FONT_BODY = ("Segoe UI", 10)
FONT_SMALL = ("Segoe UI", 9)


class CustomTitleBar(tk.Frame):
    def __init__(self, parent, title="OLED Customizer"):
        super().__init__(parent, bg=Colors.SIDEBAR, height=32)
        self.parent = parent
        self.pack_propagate(False)
        self.pack(fill="x", side="top")
        
        # Dragging logic
        self.bind("<Button-1>", self._start_move)
        self.bind("<B1-Motion>", self._move_window)
        
        # Title
        tk.Label(self, text=title, font=("Segoe UI", 10, "bold"), 
                 bg=Colors.SIDEBAR, fg=Colors.TEXT_MAIN).pack(side="left", padx=15)
        
        # Window controls
        close_btn = tk.Label(self, text="×", font=("Arial", 14), 
                             bg=Colors.SIDEBAR, fg=Colors.TEXT_DIM, width=4)
        close_btn.pack(side="right")
        close_btn.bind("<Button-1>", lambda e: parent.destroy())
        close_btn.bind("<Enter>", lambda e: close_btn.configure(bg=Colors.DANGER, fg="white"))
        close_btn.bind("<Leave>", lambda e: close_btn.configure(bg=Colors.SIDEBAR, fg=Colors.TEXT_DIM))
        
        min_btn = tk.Label(self, text="−", font=("Arial", 14), 
                           bg=Colors.SIDEBAR, fg=Colors.TEXT_DIM, width=4)
        min_btn.pack(side="right")
        min_btn.bind("<Button-1>", lambda e: parent.iconify())
        min_btn.bind("<Enter>", lambda e: min_btn.configure(bg=Colors.CARD_HOVER, fg="white"))
        min_btn.bind("<Leave>", lambda e: min_btn.configure(bg=Colors.SIDEBAR, fg=Colors.TEXT_DIM))

    def _start_move(self, event):
        self.x = event.x
        self.y = event.y

    def _move_window(self, event):
        deltax = event.x - self.x
        deltay = event.y - self.y
        x = self.parent.winfo_x() + deltax
        y = self.parent.winfo_y() + deltay
        self.parent.geometry(f"+{x}+{y}")


class SidebarButton(tk.Frame):
    def __init__(self, parent, text, icon, command, is_selected=False):
        super().__init__(parent, bg=Colors.SIDEBAR, height=45, cursor="hand2")
        self.pack_propagate(False)
        self.command = command
        self.is_selected = is_selected
        
        self.indicator = tk.Frame(self, bg=Colors.ACCENT_PRIMARY if is_selected else Colors.SIDEBAR, width=4)
        self.indicator.pack(side="left", fill="y")
        
        self.lbl = tk.Label(self, text=f"{icon}  {text}", font=FONT_BODY,
                            bg=Colors.SIDEBAR, fg=Colors.TEXT_MAIN if is_selected else Colors.TEXT_DIM)
        self.lbl.pack(side="left", padx=15)
        
        self.bind("<Button-1>", lambda e: command())
        self.lbl.bind("<Button-1>", lambda e: command())
        
        self.bind("<Enter>", self._on_hover)
        self.bind("<Leave>", self._on_leave)
        
    def _on_hover(self, e):
        if not self.is_selected:
            self.configure(bg=Colors.CARD_HOVER)
            self.lbl.configure(bg=Colors.CARD_HOVER, fg=Colors.TEXT_MAIN)
            
    def _on_leave(self, e):
        if not self.is_selected:
            self.configure(bg=Colors.SIDEBAR)
            self.lbl.configure(bg=Colors.SIDEBAR, fg=Colors.TEXT_DIM)

    def set_selected(self, selected):
        self.is_selected = selected
        self.indicator.configure(bg=Colors.ACCENT_PRIMARY if selected else Colors.SIDEBAR)
        self.lbl.configure(fg=Colors.TEXT_MAIN if selected else Colors.TEXT_DIM)
        self.configure(bg=Colors.SIDEBAR) # Reset bg
        self.lbl.configure(bg=Colors.SIDEBAR)


class ToggleSwitch(tk.Canvas):
    def __init__(self, parent, variable, command=None, width=44, height=22):
        super().__init__(parent, width=width, height=height, bg=Colors.CARD_BG, highlightthickness=0, cursor="hand2")
        self.variable = variable
        self.command = command
        self.width = width
        self.height = height
        self.bind("<Button-1>", self._toggle)
        self._draw()
        
    def _toggle(self, event):
        self.variable.set(not self.variable.get())
        self._draw()
        if self.command: self.command()
        
    def _draw(self):
        self.delete("all")
        # bg_color = Colors.ACCENT_PRIMARY if self.variable.get() else "#444444"
        bg_color = Colors.ACCENT_PRIMARY if self.variable.get() else "#555555"
        
        # Draw pill
        self.create_oval(0, 0, self.height, self.height, fill=bg_color, outline="")
        self.create_oval(self.width-self.height, 0, self.width, self.height, fill=bg_color, outline="")
        self.create_rectangle(self.height/2, 0, self.width-self.height/2, self.height, fill=bg_color, outline="")
        
        # Draw knob
        knob_color = "black" if self.variable.get() else "white"
        knob_x = self.width - self.height + 2 if self.variable.get() else 2
        self.create_oval(knob_x, 2, knob_x + self.height - 4, self.height - 2, fill=knob_color, outline="")


class SettingsGUI:
    def __init__(self, prefs, on_save=None):
        self.prefs = prefs
        self.on_save = on_save
        self.root = None
        self.vars = {}
        self.rgb = list(prefs.get_preference("rgb_color") or [0, 212, 170])
        self.current_page = None
        self.pages = {}
        self.nav_buttons = {}

    def show(self):
        if self.root:
            try: self.root.lift(); return
            except Exception: pass

        self.root = tk.Tk()
        self.current_page = None # CRITICAL: Ensure first page logic triggers
        self.root.overrideredirect(True) # Frameless
        self.root.geometry("640x600")
        self.root.configure(bg=Colors.BG_ROOT)
        
        # Center
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - 640) // 2
        y = (self.root.winfo_screenheight() - 600) // 2
        self.root.geometry(f"+{x}+{y}")
        
        # FIX: Force taskbar icon for frameless window
        
        def set_appwindow(root):
            GWL_EXSTYLE = -20
            WS_EX_APPWINDOW = 0x00040000
            WS_EX_TOOLWINDOW = 0x00000080
            hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style = style & ~WS_EX_TOOLWINDOW
            style = style | WS_EX_APPWINDOW
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            # Re-assert frame
            root.wm_withdraw()
            root.after(10, lambda: root.wm_deiconify())

        self.root.after(10, lambda: set_appwindow(self.root))

        # Styles
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TCombobox", fieldbackground=Colors.INPUT_BG, background=Colors.INPUT_BG, foreground=Colors.INPUT_FG, arrowcolor=Colors.TEXT_DIM, borderwidth=0)
        style.map("TCombobox", fieldbackground=[("readonly", Colors.INPUT_BG)], selectbackground=[("readonly", Colors.INPUT_BG)], selectforeground=[("readonly", Colors.INPUT_FG)])

        self._build_layout()
        self.root.mainloop()

    def _build_layout(self):
        # 1. Custom Title Bar
        CustomTitleBar(self.root, "OLED Customizer").pack(side="top", fill="x")
        
        # 2. Main Container (Sidebar + Content)
        container = tk.Frame(self.root, bg=Colors.BG_ROOT)
        container.pack(fill="both", expand=True)

        # === SIDEBAR ===
        sidebar = tk.Frame(container, bg=Colors.SIDEBAR, width=180)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        
        # Nav Items
        nav_items = [
            ("General", "⚙️"),
            ("Display", "📺"),
            ("Spotify", "🎵"),
            ("Hotkeys", "⌨️"),
            ("Lighting", "🌈"),
            ("Advanced", "🔧"),
            ("Backups", "💾"),
            ("Logs", "📄")
        ]
        
        for name, icon in nav_items:
            btn = SidebarButton(sidebar, name, icon, lambda n=name: self._switch_page(n), is_selected=(name=="General"))
            btn.pack(fill="x")
            self.nav_buttons[name] = btn
            
        # Save Button at bottom of sidebar
        spacer = tk.Frame(sidebar, bg=Colors.SIDEBAR)
        spacer.pack(fill="both", expand=True)
        
        save_btn = tk.Button(sidebar, text="SAVE", font=FONT_SUBHEADER,
                             bg=Colors.ACCENT_PRIMARY, fg="#000000",
                             activebackground=Colors.ACCENT_HOVER, activeforeground="#000000",
                             relief="flat", cursor="hand2", command=self._save_all)
        save_btn.pack(fill="x", padx=15, pady=20)

        # === CONTENT AREA (Scrollable) ===
        self.content_container = tk.Frame(container, bg=Colors.CONTENT)
        self.content_container.pack(side="right", fill="both", expand=True)
        
        self.canvas = tk.Canvas(self.content_container, bg=Colors.CONTENT, highlightthickness=0)
        self.scrollbar = tk.Scrollbar(self.content_container, orient="vertical", command=self.canvas.yview, 
                                      bg=Colors.SIDEBAR, troughcolor=Colors.BG_ROOT, width=10)
        
        self.content_area = tk.Frame(self.canvas, bg=Colors.CONTENT)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.content_area, anchor="nw")
        
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        
        # Only show scrollbar when needed
        def update_scroll(e=None):
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            if self.canvas.bbox("all")[3] > self.canvas.winfo_height():
                self.scrollbar.pack(side="right", fill="y")
            else:
                self.scrollbar.pack_forget()

        self.content_area.bind("<Configure>", update_scroll)
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width))
        
        # Mouse wheel support
        def _on_mousewheel(event):
            self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        self.root.bind("<MouseWheel>", _on_mousewheel)
        
        # Initialize Pages
        self._init_variables()
        self._create_pages()
        self.root.update() # Ensure dimensions are calculated
        self._switch_page("General")

    def _init_variables(self):
        # Create Tk variables for all prefs
        # General
        self.vars["clock_style"] = tk.StringVar(value=self.prefs.get_preference("clock_style") or "Standard")
        self.vars["display_seconds"] = tk.BooleanVar(value=bool(self.prefs.get_preference("display_seconds")))
        self.vars["use_turkish_days"] = tk.BooleanVar(value=bool(self.prefs.get_preference("use_turkish_days")))
        
        # System
        self.vars["run_on_start"] = tk.BooleanVar(value=is_startup_enabled())

        self.vars["date_format"] = tk.BooleanVar(value=(str(self.prefs.get_preference("date_format")) == "24"))
        self.vars["player_style"] = tk.StringVar(value=self.prefs.get_preference("player_style") or "Standard")
        # Display
        self.vars["display_timer"] = tk.BooleanVar(value=bool(self.prefs.get_preference("display_timer")))
        self.vars["display_player"] = tk.BooleanVar(value=bool(self.prefs.get_preference("display_player")))
        self.vars["display_hw_monitor"] = tk.BooleanVar(value=bool(self.prefs.get_preference("display_hw_monitor")))
        # Spotify
        self.vars["spotify_enabled"] = tk.BooleanVar(value=bool(self.prefs.get_preference("spotify_enabled")))
        self.vars["spotify_client_id"] = tk.StringVar(value=self.prefs.get_preference("spotify_client_id") or "")
        self.vars["spotify_client_secret"] = tk.StringVar(value=self.prefs.get_preference("spotify_client_secret") or "")
        self.vars["spotify_redirect_uri"] = tk.StringVar(value=self.prefs.get_preference("spotify_redirect_uri") or "")
        self.vars["local_port"] = tk.StringVar(value=str(self.prefs.get_preference("local_port") or "2408"))
        self.vars["discord_local_port"] = tk.StringVar(value=str(self.prefs.get_preference("discord_local_port") or "8888"))
        # Hotkeys
        self.vars["hotkey_monitor"] = tk.StringVar(value=self.prefs.get_preference("hotkey_monitor") or "")
        self.vars["hotkey_mute"] = tk.StringVar(value=self.prefs.get_preference("hotkey_mute") or "")
        self.vars["hotkey_mute_2"] = tk.StringVar(value=self.prefs.get_preference("hotkey_mute_2") or "")
        self.vars["hotkey_calculator"] = tk.StringVar(value=self.prefs.get_preference("hotkey_calculator") or "")
        # RGB
        self.vars["rgb_enabled"] = tk.BooleanVar(value=bool(self.prefs.get_preference("rgb_enabled")))
        # Advanced
        self.vars["scrollbar_padding"] = tk.StringVar(value=str(self.prefs.get_preference("scrollbar_padding") or "2"))
        self.vars["text_padding_left"] = tk.StringVar(value=str(self.prefs.get_preference("text_padding_left") or "30"))
        self.vars["auto_launch_gg"] = tk.BooleanVar(value=bool(self.prefs.get_preference("auto_launch_gg")))
        
        # HW Monitoring
        self.vars["hw_polling_interval"] = tk.StringVar(value=str(self.prefs.get_preference("hw_polling_interval") or "1000"))
        self.vars["show_game_fps"] = tk.BooleanVar(value=bool(self.prefs.get_preference("show_game_fps")))
        self.vars["selected_gpu"] = tk.StringVar(value=self.prefs.get_preference("selected_gpu") or "Auto")
        self.vars["spotify_fetch_delay"] = tk.StringVar(value=str(self.prefs.get_preference("spotify_fetch_delay") or "2"))
        # Discord
        self.vars["discord_client_id"] = tk.StringVar(value=self.prefs.get_preference("discord_client_id") or "")
        self.vars["discord_client_secret"] = tk.StringVar(value=self.prefs.get_preference("discord_client_secret") or "")
        self.vars["headset_hid_sync_enabled"] = tk.BooleanVar(
            value=bool(self.prefs.get_preference("headset_hid_sync_enabled"))
        )

    def _create_pages(self):
        # -- GENERAL PAGE --
        p_gen = tk.Frame(self.content_area, bg=Colors.CONTENT)
        self._header(p_gen, "⚙️ General Settings")
        self._dropdown_row(p_gen, "Clock Design", self.vars["clock_style"], ["Standard", "Big Timer", "Date Focused", "Analog"])
        self._toggle_row(p_gen, "Use 24-Hour Format", self.vars["date_format"])
        self._toggle_row(p_gen, "Show Seconds", self.vars["display_seconds"])
        self._toggle_row(p_gen, "Use Turkish Language", self.vars["use_turkish_days"])
        
        # System
        tk.Frame(p_gen, bg=Colors.CONTENT, height=10).pack()
        self._toggle_row(p_gen, "Run on Start", self.vars["run_on_start"])

        # Update Section
        tk.Frame(p_gen, bg=Colors.CONTENT, height=20).pack()
        self._header(p_gen, "✨ Software Update")
        
        self.update_btn_text = tk.StringVar(value="Check for Updates")
        self.update_btn = tk.Button(p_gen, textvariable=self.update_btn_text, font=FONT_SUBHEADER,
                                    bg=Colors.CARD_BG, fg=Colors.TEXT_MAIN,
                                    activebackground=Colors.CARD_HOVER, activeforeground=Colors.TEXT_MAIN,
                                    relief="flat", cursor="hand2", padx=20, pady=5,
                                    command=self._check_updates)
        self.update_btn.pack(anchor="w", padx=5)
        
        self.pages["General"] = p_gen
        
        # -- DISPLAY PAGE --
        p_disp = tk.Frame(self.content_area, bg=Colors.CONTENT)
        self._header(p_disp, "📺 Display Features")
        self._toggle_row(p_disp, "Enable Clock", self.vars["display_timer"], 
                          command=lambda: self._exclusive_toggle("display_timer", "display_hw_monitor"))
        self._toggle_row(p_disp, "Enable Music Info", self.vars["display_player"])
        self._dropdown_row(p_disp, "Player Style", self.vars["player_style"], ["Standard", "Compact", "Centered", "Ticker", "Minimal"], command=self._quick_save)
        self._toggle_row(p_disp, "Always Show System Stats", self.vars["display_hw_monitor"],
                          command=lambda: self._exclusive_toggle("display_hw_monitor", "display_timer"))
        
        tk.Frame(p_disp, bg=Colors.CONTENT, height=10).pack()
        self._toggle_row(p_disp, "Show Game FPS", self.vars["show_game_fps"])
        
        # GPU Selection
        from src.HardwareMonitor import HardwareMonitor
        # We need an instance to get GPUs or just call the worker method if accessible
        from src.HardwareMonitor import _lhm_worker
        available_gpus = ["Auto"] + _lhm_worker.get_available_gpus()
        self._dropdown_row(p_disp, "Selected GPU", self.vars["selected_gpu"], available_gpus)
        
        polling_options = {"500ms": "500", "1s (Default)": "1000", "2s": "2000", "5s": "5000"}
        self._dropdown_row(p_disp, "HW Polling Rate", self.vars["hw_polling_interval"], 
                          list(polling_options.keys()), 
                          # Map back to value on save handled in _save_all
                          display_to_val=polling_options)
        
        self.pages["Display"] = p_disp
        
        # -- SPOTIFY PAGE --
        p_spotify = tk.Frame(self.content_area, bg=Colors.CONTENT)
        self._header(p_spotify, "🎵 Spotify Configuration")
        self._toggle_row(p_spotify, "Enable Spotify Integration", self.vars["spotify_enabled"])
        self._entry_row(p_spotify, "Spotify Client ID", self.vars["spotify_client_id"], width=25)
        self._entry_row(p_spotify, "Spotify Client Secret", self.vars["spotify_client_secret"], width=25, show="*")
        self._entry_row(p_spotify, "Redirect URI", self.vars["spotify_redirect_uri"], width=25)
        self._entry_row(p_spotify, "Connection Port", self.vars["local_port"])
        
        spotify_poll_options = {"1s (Fast)": "1", "2s (Default)": "2", "3s": "3", "5s": "5", "10s (Slow)": "10"}
        self._dropdown_row(p_spotify, "Spotify Polling Rate", self.vars["spotify_fetch_delay"], 
                          list(spotify_poll_options.keys()), 
                          display_to_val=spotify_poll_options)
        
        # Add a help label
        help_frame = tk.Frame(p_spotify, bg=Colors.CONTENT)
        help_frame.pack(fill="x", pady=20, padx=5)
        tk.Label(help_frame, text="* Changes require app restart.", 
                 font=FONT_SMALL, fg=Colors.DANGER, bg=Colors.CONTENT).pack(anchor="w")
        
        self.pages["Spotify"] = p_spotify
        
        # -- HOTKEYS PAGE --
        p_hot = tk.Frame(self.content_area, bg=Colors.CONTENT)
        self._header(p_hot, "⌨️ Keyboard Shortcuts")
        self._hotkey_row(p_hot, "Show System Stats Key", self.vars["hotkey_monitor"])
        self._hotkey_row(p_hot, "Mute Microphone Key (Primary)", self.vars["hotkey_mute"])
        self._hotkey_row(p_hot, "Mute Microphone Key (Optional)", self.vars["hotkey_mute_2"])
        tk.Frame(p_hot, bg=Colors.CONTENT, height=10).pack()
        self._header(p_hot, "🖩 Calculator")
        self._hotkey_row(p_hot, "Toggle Calculator (hold Ctrl +)", self.vars["hotkey_calculator"])
        tk.Label(p_hot, text="   Default: Ctrl + Insert. Press Esc inside to exit.",
                 font=FONT_SMALL, fg=Colors.TEXT_DIM, bg=Colors.CONTENT).pack(anchor="w", pady=(0, 5))
        self.pages["Hotkeys"] = p_hot
        
        # -- LIGHTING PAGE --
        p_rgb = tk.Frame(self.content_area, bg=Colors.CONTENT)
        self._header(p_rgb, "🌈 Ambiance Lighting")
        self._toggle_row(p_rgb, "Match Keyboard Color", self.vars["rgb_enabled"])
        self._color_picker_row(p_rgb)
        self.pages["Lighting"] = p_rgb
        
        # -- ADVANCED PAGE --
        p_adv = tk.Frame(self.content_area, bg=Colors.CONTENT)
        self._header(p_adv, "🔧 Layout Adjustments")
        self._entry_row(p_adv, "Scrollbar Margin (px)", self.vars["scrollbar_padding"])
        tk.Label(p_adv, text="   Controls progress bar width and side padding.", 
                 font=FONT_SMALL, fg=Colors.TEXT_DIM, bg=Colors.CONTENT).pack(anchor="w", pady=(0, 10))
                 
        self._entry_row(p_adv, "Text Indentation (px)", self.vars["text_padding_left"])
        tk.Label(p_adv, text="   Shifts titles to the right to avoid overlapping app icons.", 
                 font=FONT_SMALL, fg=Colors.TEXT_DIM, bg=Colors.CONTENT).pack(anchor="w", pady=(0, 10))
        
        self._toggle_row(p_adv, "Auto-Launch SteelSeries GG", self.vars["auto_launch_gg"])
        tk.Label(p_adv, text="   Automatically starts SteelSeries GG if not running.", 
                 font=FONT_SMALL, fg=Colors.TEXT_DIM, bg=Colors.CONTENT).pack(anchor="w", pady=(0, 10))

        # Discord Section
        tk.Frame(p_adv, bg=Colors.CONTENT, height=10).pack()
        self._header(p_adv, "🎙️ Discord Mic Detection")
        self._toggle_row(
            p_adv,
            "Enable Headset HID Sync (Experimental)",
            self.vars["headset_hid_sync_enabled"],
        )
        tk.Label(
            p_adv,
            text="   Off by default. Turn on only if your headset button/LED sync is supported.",
            font=FONT_SMALL,
            fg=Colors.TEXT_DIM,
            bg=Colors.CONTENT,
        ).pack(anchor="w", pady=(0, 10))
        self._entry_row(p_adv, "Discord Application ID", self.vars["discord_client_id"], width=25)
        self._entry_row(p_adv, "Discord Client Secret", self.vars["discord_client_secret"], width=25, show="*")
        tk.Label(p_adv, text="   Required for mic detection authorization.", 
                 font=FONT_SMALL, fg=Colors.TEXT_DIM, bg=Colors.CONTENT).pack(anchor="w", pady=(0, 10))

        self._entry_row(p_adv, "Discord Listener Port", self.vars["discord_local_port"], width=25)
        tk.Label(p_adv, text="   Matches 'Redirect URI' in Discord Portal (default 8888).", 
                 font=FONT_SMALL, fg=Colors.TEXT_DIM, bg=Colors.CONTENT).pack(anchor="w", pady=(0, 10))

        # Connect Button
        btn_frame = tk.Frame(p_adv, bg=Colors.CONTENT)
        btn_frame.pack(fill="x", padx=5, pady=10)
        
        self.discord_btn = tk.Button(btn_frame, text="🔗 Connect Discord", font=FONT_SUBHEADER,
                                     bg=Colors.CARD_BG, fg=Colors.TEXT_MAIN,
                                     activebackground=Colors.CARD_HOVER, activeforeground=Colors.TEXT_MAIN,
                                     relief="flat", cursor="hand2", padx=20, pady=5,
                                     command=self._authorize_discord_action)
        self.discord_btn.pack(side="left")

        # Status Label
        token = self.prefs.get_preference("discord_access_token")
        status_text = "✅ Connected" if token else "❌ Not Authorized"
        status_color = "#4CAF50" if token else Colors.DANGER
        self.discord_status_lbl = tk.Label(btn_frame, text=status_text, font=FONT_SMALL,
                                           fg=status_color, bg=Colors.CONTENT)
        self.discord_status_lbl.pack(side="left", padx=15)

        self.pages["Advanced"] = p_adv

        # -- BACKUPS PAGE --
        p_backups = tk.Frame(self.content_area, bg=Colors.CONTENT)
        self._create_backups_page(p_backups)
        self.pages["Backups"] = p_backups

        # -- LOGS PAGE --
        p_logs = tk.Frame(self.content_area, bg=Colors.CONTENT)
        self._header(p_logs, "📄 Application Logs")
        
        # Tools Frame (Refresh, Open Folder)
        tools_frame = tk.Frame(p_logs, bg=Colors.CONTENT)
        tools_frame.pack(fill="x", pady=(0, 10))
        
        refresh_btn = tk.Button(tools_frame, text="🔄 Refresh Logs", font=FONT_SMALL,
                                bg=Colors.CARD_BG, fg=Colors.TEXT_MAIN,
                                activebackground=Colors.CARD_HOVER, activeforeground=Colors.TEXT_MAIN,
                                relief="flat", cursor="hand2", padx=10, pady=2,
                                command=self._refresh_logs)
        refresh_btn.pack(side="left", padx=(0, 10))
        
        open_folder_btn = tk.Button(tools_frame, text="📂 Open Log Folder", font=FONT_SMALL,
                                    bg=Colors.CARD_BG, fg=Colors.TEXT_MAIN,
                                    activebackground=Colors.CARD_HOVER, activeforeground=Colors.TEXT_MAIN,
                                    relief="flat", cursor="hand2", padx=10, pady=2,
                                    command=self._open_log_folder)
        open_folder_btn.pack(side="left")
        
        # Log Text Area
        log_frame = tk.Frame(p_logs, bg=Colors.INPUT_BG, highlightthickness=1, highlightbackground=Colors.BORDER)
        log_frame.pack(fill="both", expand=True)
        
        self.log_text = tk.Text(log_frame, bg=Colors.INPUT_BG, fg=Colors.TEXT_MAIN, 
                                font=("Consolas", 9), wrap="word", state="disabled", 
                                relief="flat", padx=10, pady=10)
        self.log_text.pack(side="left", fill="both", expand=True)
        
        # Use proper style for scrollbar to fit dark theme if possible, standard as fallback
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        log_scroll.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=log_scroll.set)
        
        self.pages["Logs"] = p_logs

    def _create_backups_page(self, parent):
        self._header(parent, "💾 SteelSeries Backups")
        
        # Tools Frame (Refresh, Backup Now)
        tools_frame = tk.Frame(parent, bg=Colors.CONTENT)
        tools_frame.pack(fill="x", pady=(0, 15))
        
        tk.Button(tools_frame, text="🔄 Refresh List", font=FONT_SMALL,
                  bg=Colors.CARD_BG, fg=Colors.TEXT_MAIN,
                  activebackground=Colors.CARD_HOVER, activeforeground=Colors.TEXT_MAIN,
                  relief="flat", cursor="hand2", padx=10, pady=2,
                  command=self._refresh_backups_list).pack(side="left", padx=(0, 10))
        
        tk.Button(tools_frame, text="🛡️ Backup Now", font=FONT_SMALL,
                  bg=Colors.CARD_BG, fg=Colors.TEXT_MAIN,
                  activebackground=Colors.CARD_HOVER, activeforeground=Colors.TEXT_MAIN,
                  relief="flat", cursor="hand2", padx=10, pady=2,
                  command=self._do_manual_backup).pack(side="left")

        # Backups List Area
        list_container = tk.Frame(parent, bg=Colors.INPUT_BG, highlightthickness=1, highlightbackground=Colors.BORDER)
        list_container.pack(fill="both", expand=True)

        self.backups_canvas = tk.Canvas(list_container, bg=Colors.INPUT_BG, highlightthickness=0)
        self.backups_scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=self.backups_canvas.yview)
        self.backups_scrollable_frame = tk.Frame(self.backups_canvas, bg=Colors.INPUT_BG)

        self.backups_scrollable_frame.bind(
            "<Configure>",
            lambda e: self.backups_canvas.configure(scrollregion=self.backups_canvas.bbox("all"))
        )

        self.backups_window = self.backups_canvas.create_window((0, 0), window=self.backups_scrollable_frame, anchor="nw")
        self.backups_canvas.configure(yscrollcommand=self.backups_scrollbar.set)

        # Sync width
        self.backups_canvas.bind("<Configure>", lambda e: self.backups_canvas.itemconfig(self.backups_window, width=e.width))

        self.backups_canvas.pack(side="left", fill="both", expand=True)
        self.backups_scrollbar.pack(side="right", fill="y")
        
        # Support mouse wheel - Scoped efficiently
        def _on_mousewheel(event):
            self.backups_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        self.backups_canvas.bind("<Enter>", lambda e: self.backups_canvas.bind_all("<MouseWheel>", _on_mousewheel))
        self.backups_canvas.bind("<Leave>", lambda e: self.backups_canvas.unbind_all("<MouseWheel>"))
        
        # Initial population
        self.root.after(100, self._refresh_backups_list)

    def _refresh_backups_list(self):
        from src import ProfileBackup
        # Clear child widgets
        for widget in self.backups_scrollable_frame.winfo_children():
            widget.destroy()

        # Reset scroll position to avoid hit-testing offsets
        self.backups_canvas.yview_moveto(0)

        backups = ProfileBackup.list_backups()
        if not backups:
            tk.Label(self.backups_scrollable_frame, text="No backups found.", 
                     bg=Colors.INPUT_BG, fg=Colors.TEXT_DIM, font=FONT_BODY).pack(pady=20)
            return

        for name, p, count, mtime in backups:
            # Row Container
            row = tk.Frame(self.backups_scrollable_frame, bg=Colors.CARD_BG)
            row.pack(fill="x", pady=2, padx=5)

            # Actions Container
            actions_frame = tk.Frame(row, bg=Colors.CARD_BG)
            actions_frame.pack(side="right", padx=(10, 20))
            
            # Duplicate Button
            dup_btn = tk.Button(actions_frame, text="📑", font=("Segoe UI Emoji", 11),
                                bg=Colors.CARD_BG, fg=Colors.TEXT_DIM, relief="flat", cursor="hand2",
                                activebackground=Colors.CARD_HOVER, activeforeground=Colors.TEXT_MAIN,
                                borderwidth=0, highlightthickness=0,
                                command=lambda path=p: self._duplicate_backup_action(path))
            dup_btn.pack(side="left", padx=5, pady=8)
            
            # Delete Button
            del_btn = tk.Button(actions_frame, text="🗑️", font=("Segoe UI Emoji", 11),
                                bg=Colors.CARD_BG, fg=Colors.TEXT_DIM, relief="flat", cursor="hand2",
                                activebackground=Colors.CARD_HOVER, activeforeground=Colors.DANGER,
                                borderwidth=0, highlightthickness=0,
                                command=lambda path=p: self._delete_backup_action(path))
            del_btn.pack(side="left", padx=5, pady=8)
            
            # Info
            timestamp = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            display_name = name
            if name.startswith("pre_restore_"):
                display_name = "🛡️ Safety: " + name.replace("pre_restore_", "")
            
            info_frame = tk.Frame(row, bg=Colors.CARD_BG)
            info_frame.pack(side="left", padx=10, fill="x", expand=True)
            
            tk.Label(info_frame, text=display_name, font=FONT_SUBHEADER, fg=Colors.TEXT_MAIN, bg=Colors.CARD_BG).pack(anchor="w", pady=(5, 0))
            tk.Label(info_frame, text=f"{timestamp} • {count} databases", font=FONT_SMALL, fg=Colors.TEXT_DIM, bg=Colors.CARD_BG).pack(anchor="w", pady=(0, 5))

        # FORCE layout update and scrollregion sync to fix hit-detection offsets
        self.root.update() 
        self.backups_canvas.configure(scrollregion=self.backups_canvas.bbox("all"))

    def _do_manual_backup(self):
        from src import ProfileBackup
        if ProfileBackup.backup_profiles():
            messagebox.showinfo("Success", "Backup created successfully!", parent=self.root)
            self._refresh_backups_list()
        else:
            messagebox.showerror("Error", "Failed to create backup.", parent=self.root)

    def _delete_backup_action(self, path):
        from src import ProfileBackup
        name = os.path.basename(path)
        logger.info(f"Delete requested for backup: {name}")
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to permanently delete backup:\n{name}?", parent=self.root):
            if ProfileBackup.delete_backup(path):
                logger.info(f"Successfully deleted backup: {name}")
                self._refresh_backups_list()
            else:
                messagebox.showerror("Error", "Failed to delete backup.", parent=self.root)

    def _authorize_discord_action(self):
        """Action for 'Connect Discord' button"""
        import webbrowser
        
        # Save current ID/Secret first
        self.prefs.preferences["discord_client_id"] = self.vars["discord_client_id"].get()
        self.prefs.preferences["discord_client_secret"] = self.vars["discord_client_secret"].get()
        self.prefs.save_preferences()
        
        cid = self.vars["discord_client_id"].get()
        if not cid:
            messagebox.showerror("Error", "Please enter a Discord Application ID first.", parent=self.root)
            return
            
        # ExtensionReceiver runs on discord_local_port
        port = self.vars["discord_local_port"].get()
        redirect_uri = f"http://127.0.0.1:{port}"
        
        # Open browser for OAuth
        url = f"https://discord.com/api/oauth2/authorize?client_id={cid}&redirect_uri={redirect_uri}&response_type=code&scope=rpc%20rpc.voice.read%20rpc.voice.write"
        logger.info("Opening browser for Discord Auth flow on localhost redirect port %s", port)
        webbrowser.open(url)
        
        messagebox.showinfo("Authorization", "Please check your browser to authorize Discord, then wait for the 'Connected' status in this window.", parent=self.root)

    def _duplicate_backup_action(self, path):
        from src import ProfileBackup
        logger.info(f"Duplicate requested for backup: {os.path.basename(path)}")
        if ProfileBackup.duplicate_backup(path):
            self._refresh_backups_list()
        else:
            messagebox.showerror("Error", "Failed to duplicate backup.", parent=self.root)

    def _switch_page(self, page_name):
        if self.current_page == page_name and page_name not in ["Logs", "Backups"]:
            return

        # Hide all pages
        for p in self.pages.values():
            p.pack_forget()
        
        # Show selected
        if page_name in self.pages:
            self.pages[page_name].pack(fill="both", expand=True, padx=30, pady=20)
            # Reset scroll for the new page
            self.canvas.yview_moveto(0)
            self.root.update_idletasks()
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            
        # Update Nav
        for name, btn in self.nav_buttons.items():
            btn.set_selected(name == page_name)
        
        self.current_page = page_name

        # Refresh AFTER packing to ensure UI is ready
        if page_name == "Logs":
            self._refresh_logs()
        elif page_name == "Backups":
            self._refresh_backups_list()

    def _refresh_logs(self):
        """Reads the last 200 lines of debug.log and populates the text widget."""
        import os
        from src.utils import fetch_app_data_path
        
        self.log_text.config(state="normal")
        self.log_text.delete(1.0, tk.END)
        
        app_data_path = fetch_app_data_path()
        log_file = os.path.join(app_data_path, "debug.log")
        
        if os.path.exists(log_file):
            try:
                with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                    # Read all lines and keep only the last N (prevent lagging UI)
                    lines = f.readlines()
                    max_lines = 200
                    display_lines = lines[-max_lines:] if len(lines) > max_lines else lines
                    
                    if len(lines) > max_lines:
                        self.log_text.insert(tk.END, f"... {len(lines) - max_lines} older lines omitted ...\n\n")
                    
                    self.log_text.insert(tk.END, "".join(display_lines))
            except Exception as e:
                self.log_text.insert(tk.END, f"Error reading log file: {e}")
        else:
            self.log_text.insert(tk.END, "Log file not found. It will be created when events occur.")
            
        self.log_text.config(state="disabled")
        # Scroll to bottom
        self.log_text.yview_moveto(1.0)

    def _open_log_folder(self):
        """Opens the app data folder natively."""
        import os
        import subprocess
        from src.utils import fetch_app_data_path
        
        app_data_path = fetch_app_data_path()
        if os.path.exists(app_data_path):
            try:
                os.startfile(app_data_path)
            except AttributeError: # Non-Windows fallback
                subprocess.call(["explorer", app_data_path])

    def _exclusive_toggle(self, updated_key, other_key):
        """Ensures that if one is enabled, the other is disabled."""
        if self.vars[updated_key].get():
            self.vars[other_key].set(False)
        # Redraw switches since they are canvas based
        for widget in self.pages["Display"].winfo_children():
            for child in widget.winfo_children():
                if isinstance(child, ToggleSwitch):
                    child._draw()
    
    def _quick_save(self):
        """Silent save without closing the window - for auto-save dropdowns."""
        try:
            for k, v in self.vars.items():
                val = v.get()
                if k in ["scrollbar_padding", "text_padding_left", "local_port", "spotify_fetch_delay"]:
                    try: val = int(val)
                    except Exception: val = 0
                elif k == "date_format":
                    val = 24 if val else 12
                elif k == "hw_polling_interval":
                    try: val = int(val)
                    except Exception: val = 1000
                self.prefs.preferences[k] = val
            
            self.prefs.preferences["rgb_color"] = self.rgb
            self.prefs.save_preferences()
            
            # Trigger callback silently
            if self.on_save:
                try: self.on_save()
                except Exception: pass
        except Exception as e:
            logger.error(f"Quick save failed: {e}")

    # --- UI COMPONENTS ---
    def _header(self, parent, text):
        tk.Label(parent, text=text, font=FONT_HEADER, fg=Colors.TEXT_MAIN, bg=Colors.CONTENT).pack(anchor="w", pady=(0, 20))

    def _row_frame(self, parent):
        f = tk.Frame(parent, bg=Colors.CARD_BG, height=50) # Taller rows
        f.pack(fill="x", pady=5)
        f.pack_propagate(False)
        return f

    def _toggle_row(self, parent, label, var, command=None):
        f = self._row_frame(parent)
        tk.Label(f, text=label, font=FONT_BODY, fg=Colors.TEXT_MAIN, bg=Colors.CARD_BG).pack(side="left", padx=15)
        switch = ToggleSwitch(f, var, command=command)
        switch.pack(side="right", padx=15)

    def _dropdown_row(self, parent, label, var, options, command=None, display_to_val=None):
        f = self._row_frame(parent)
        tk.Label(f, text=label, font=FONT_BODY, fg=Colors.TEXT_MAIN, bg=Colors.CARD_BG).pack(side="left", padx=15)
        
        # If display_to_val is provided, 'var' holds the value but we show the label
        if display_to_val:
            # Find current label for the value
            current_val = var.get()
            current_label = next((l for l, v in display_to_val.items() if v == current_val), options[0])
            display_var = tk.StringVar(value=current_label)
            
            def on_select(e):
                val = display_to_val[display_var.get()]
                var.set(val)
                if command: command()
                
            cb = ttk.Combobox(f, textvariable=display_var, values=options, state="readonly", width=15)
            cb.bind("<<ComboboxSelected>>", on_select)
        else:
            cb = ttk.Combobox(f, textvariable=var, values=options, state="readonly", width=15)
            if command:
                cb.bind("<<ComboboxSelected>>", lambda e: command())
                
        cb.pack(side="right", padx=15)

    def _entry_row(self, parent, label, var, width=10, show=None):
        f = self._row_frame(parent)
        tk.Label(f, text=label, font=FONT_BODY, fg=Colors.TEXT_MAIN, bg=Colors.CARD_BG).pack(side="left", padx=15)
        e = tk.Entry(f, textvariable=var, font=FONT_BODY, bg=Colors.INPUT_BG, fg=Colors.INPUT_FG, 
                     insertbackground=Colors.ACCENT_PRIMARY, relief="flat", width=width, show=show)
        e.pack(side="right", padx=15, ipady=3)

    def _hotkey_row(self, parent, label, var):
        f = self._row_frame(parent)
        tk.Label(f, text=label, font=FONT_BODY, fg=Colors.TEXT_MAIN, bg=Colors.CARD_BG).pack(side="left", padx=15)
        
        btn = tk.Button(f, text="SET KEY", font=FONT_SMALL,
                        bg=Colors.INPUT_BG, fg=Colors.ACCENT_PRIMARY,
                        activebackground=Colors.CARD_HOVER, activeforeground=Colors.ACCENT_PRIMARY,
                        relief="flat", cursor="hand2")
        btn.pack(side="right", padx=15)
        
        lbl = tk.Label(f, textvariable=var, font=("Consolas", 10), fg=Colors.TEXT_DIM, bg=Colors.CARD_BG)
        lbl.pack(side="right", padx=10)

        def capture():
            popup = tk.Toplevel(self.root)
            popup.overrideredirect(True)
            popup.geometry("300x120")
            popup.configure(bg=Colors.BG_ROOT, highlightthickness=2, highlightbackground=Colors.ACCENT_PRIMARY)
            
            # Center popup
            x = self.root.winfo_x() + (self.root.winfo_width()//2) - 150
            y = self.root.winfo_y() + (self.root.winfo_height()//2) - 60
            popup.geometry(f"+{x}+{y}")
            
            tk.Label(popup, text="Press any key...", font=FONT_SUBHEADER, fg=Colors.ACCENT_PRIMARY, bg=Colors.BG_ROOT).pack(pady=30)
            tk.Label(popup, text="(Esc to cancel)", font=FONT_SMALL, fg=Colors.TEXT_DIM, bg=Colors.BG_ROOT).pack()
            
            def on_key(e):
                if e.keysym == "Escape":
                    popup.destroy()
                    return
                key_str = f"Key.{e.keysym.lower()}"
                var.set(key_str)
                popup.destroy()
                
            def on_mouse(e):
                # Button 1: Left, 2: Middle, 3: Right
                # Many mice map XButtons to 4 (Back) and 5 (Forward) in Tkinter on Windows
                if e.num == 4:
                    var.set("Key.mouse_4")
                    popup.destroy()
                elif e.num == 5:
                    var.set("Key.mouse_5")
                    popup.destroy()
                
            popup.bind("<Key>", on_key)
            popup.bind("<Button>", on_mouse)
            popup.focus_set()
            
        btn.config(command=capture)

    def _color_picker_row(self, parent):
        f = self._row_frame(parent)
        tk.Label(f, text="Base Color", font=FONT_BODY, fg=Colors.TEXT_MAIN, bg=Colors.CARD_BG).pack(side="left", padx=15)
        
        hex_col = '#{:02x}{:02x}{:02x}'.format(*self.rgb)
        color_preview = tk.Frame(f, bg=hex_col, width=30, height=30)
        color_preview.pack(side="right", padx=15)
        
        def pick():
            c = colorchooser.askcolor(initialcolor=hex_col)
            if c[1]:
                self.rgb = [int(x) for x in c[0]]
                color_preview.config(bg=c[1])
                
        pick_btn = tk.Button(f, text="PICK", font=FONT_SMALL,
                             bg=Colors.INPUT_BG, fg=Colors.TEXT_MAIN,
                             relief="flat", cursor="hand2", command=pick)
        pick_btn.pack(side="right", padx=5)

    def _check_updates(self):
        # Visual feedback immediately (keep button colored, don't grey it out)
        self.update_btn_text.set("⏳ Checking...")
        self.update_btn.configure(state="disabled", disabledforeground=Colors.TEXT_DIM)
        
        def worker():
            try:
                available, latest = is_update_available()
            except Exception:
                available, latest = False, None
            
            # All GUI updates MUST happen on the main thread via root.after()
            def update_gui():
                if available:
                    self.update_btn_text.set(f"⬆ Update to v{latest}")
                    self.update_btn.configure(state="normal", bg="#27ae60", fg="white", 
                                              command=lambda: threading.Thread(target=start_update_process, daemon=True).start())
                else:
                    self.update_btn_text.set("✅ Up to Date!")
                    self.update_btn.configure(state="normal", bg="#27ae60", fg="white")
                    self.root.after(4000, lambda: [self.update_btn_text.set("Check for Updates"), 
                                                  self.update_btn.configure(bg=Colors.CARD_BG, fg=Colors.TEXT_MAIN,
                                                                           command=self._check_updates)])
            
            try:
                self.root.after(0, update_gui)
            except Exception:
                pass
        
        threading.Thread(target=worker, daemon=True).start()

    def _save_all(self):
        try:
            # Gather all vars
            sensitive_keys = {"discord_client_id", "discord_client_secret", "discord_access_token"}
            for k, v in self.vars.items():
                val = v.get()
                log_val = "***" if k in sensitive_keys else val
                logger.info("Saving %s: %s", k, log_val)
                
                if k in ["scrollbar_padding", "text_padding_left", "local_port", "discord_local_port", "spotify_fetch_delay"]:
                    try: val = int(val)
                    except Exception: val = 0
                    self.prefs.preferences[k] = val
                elif k == "date_format":
                    self.prefs.preferences[k] = 24 if val else 12
                elif k == "hw_polling_interval":
                    try: self.prefs.preferences[k] = int(val)
                    except Exception: self.prefs.preferences[k] = 1000
                else:
                    self.prefs.preferences[k] = val
            
            self.prefs.preferences["rgb_color"] = self.rgb
            self.prefs.save_preferences()
            
            # Apply System Settings
            set_startup(self.vars["run_on_start"].get())
            
            logger.info("Settings Saved")
            
            # Show success message – include update instruction only on Spotify page
            if getattr(self, "current_page", None) == "Spotify":
                # Trigger callback BEFORE destroying (so reload_config deletes credentials.json)
                if self.on_save:
                    try: self.on_save()
                    except Exception: pass
                    
                messagebox.showinfo(
                    "Restart Required",
                    "Spotify settings changed. Please restart the application manually."
                )
                self.root.destroy()
                return
            else:
                messagebox.showinfo("Success", "Settings saved!")

            # Trigger callback (which calls DisplayManager.update_config which calls update_preferences)
            if self.on_save:
                try: self.on_save()
                except Exception: pass

            self.root.destroy()
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            messagebox.showerror("Error", f"Failed to save settings:\n{e}")


def open_settings(prefs, callback=None):
    SettingsGUI(prefs, callback).show()
