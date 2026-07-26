"""
OLED Customizer - Settings GUI
Frameless window, sidebar navigation, custom widgets, clean aesthetics.
"""

import tkinter as tk
from tkinter import ttk, colorchooser, messagebox
import os
import logging
import ctypes
import threading

logger = logging.getLogger("OLED Customizer.Settings")
from src.UserPreferences import UserPreferences
from src.utils import set_startup, is_startup_enabled, fetch_app_data_path as f_app_data
from src.updater import is_update_available

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
    # Dropdowns that show friendly labels but must save raw values.
    # _init_variables maps value -> label, _save_all maps label -> value.
    DROPDOWN_MAPS = {
        "spotify_fetch_delay": {"1s (Fast)": "1", "2s (Default)": "2", "3s": "3", "5s": "5", "10s": "10"},
        "hw_polling_interval": {"500ms": "500", "1s (Default)": "1000", "2s": "2000", "5s": "5000"},
    }

    def __init__(self, prefs, on_save=None):
        self.prefs = prefs
        self.on_save = on_save
        self.root = None
        self.hwnd = None
        self.vars = {}
        self.rgb = list(prefs.get_preference("rgb_color") or [0, 212, 170])
        self.current_page = None
        self.pages = {}
        self.nav_buttons = {}

    def show(self):
        self.root = tk.Tk()
        self.current_page = None
        self.root.overrideredirect(True)
        self.root.geometry("640x600")
        self.root.configure(bg=Colors.BG_ROOT)
        
        # Center
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - 640) // 2
        y = (self.root.winfo_screenheight() - 600) // 2
        self.root.geometry(f"+{x}+{y}")
        
        def set_appwindow(root):
            GWL_EXSTYLE = -20
            WS_EX_APPWINDOW = 0x00040000
            WS_EX_TOOLWINDOW = 0x00000080
            hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
            self.hwnd = hwnd or root.winfo_id()
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style = style & ~WS_EX_TOOLWINDOW
            style = style | WS_EX_APPWINDOW
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            root.wm_withdraw()
            root.after(10, lambda: root.wm_deiconify())

        self.root.after(10, lambda: set_appwindow(self.root))

        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TCombobox", fieldbackground=Colors.INPUT_BG, background=Colors.INPUT_BG, foreground=Colors.INPUT_FG, arrowcolor=Colors.TEXT_DIM, borderwidth=0)
        style.map("TCombobox", fieldbackground=[("readonly", Colors.INPUT_BG)], selectbackground=[("readonly", Colors.INPUT_BG)], selectforeground=[("readonly", Colors.INPUT_FG)])

        self._build_layout()
        try:
            self.root.mainloop()
        finally:
            self.root = None
            self.hwnd = None

    def _build_layout(self):
        CustomTitleBar(self.root, "OLED Customizer").pack(side="top", fill="x")
        container = tk.Frame(self.root, bg=Colors.BG_ROOT)
        container.pack(fill="both", expand=True)

        # === SIDEBAR ===
        sidebar = tk.Frame(container, bg=Colors.SIDEBAR, width=180)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        
        nav_items = [
            ("General", "⚙️"), ("Display", "📺"), ("Spotify", "🎵"), 
            ("Hotkeys", "⌨️"), ("Lighting", "🌈"), ("Advanced", "🔧"), 
            ("Backups", "💾"), ("Logs", "📄")
        ]
        
        for name, icon in nav_items:
            btn = SidebarButton(sidebar, name, icon, lambda n=name: self._switch_page(n), is_selected=(name=="General"))
            btn.pack(fill="x")
            self.nav_buttons[name] = btn
            
        spacer = tk.Frame(sidebar, bg=Colors.SIDEBAR)
        spacer.pack(fill="both", expand=True)
        
        save_btn = tk.Button(sidebar, text="SAVE", font=FONT_SUBHEADER,
                             bg=Colors.ACCENT_PRIMARY, fg="#000000",
                             activebackground=Colors.ACCENT_HOVER, activeforeground="#000000",
                             relief="flat", cursor="hand2", command=self._save_all)
        save_btn.pack(fill="x", padx=15, pady=20)

        # === CONTENT AREA ===
        self.content_container = tk.Frame(container, bg=Colors.CONTENT)
        self.content_container.pack(side="right", fill="both", expand=True)
        
        self.canvas = tk.Canvas(self.content_container, bg=Colors.CONTENT, highlightthickness=0)
        self.scrollbar = tk.Scrollbar(self.content_container, orient="vertical", command=self.canvas.yview, 
                                      bg=Colors.SIDEBAR, troughcolor=Colors.BG_ROOT, width=10)
        
        self.content_area = tk.Frame(self.canvas, bg=Colors.CONTENT)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.content_area, anchor="nw")
        
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        
        def update_scroll(e=None):
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            if self.canvas.bbox("all")[3] > self.canvas.winfo_height():
                self.scrollbar.pack(side="right", fill="y")
            else:
                self.scrollbar.pack_forget()

        self.content_area.bind("<Configure>", update_scroll)
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width))
        
        def _on_mousewheel(event):
            self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        self.root.bind("<MouseWheel>", _on_mousewheel)
        
        self._init_variables()
        self._create_pages()
        self.root.update()
        self._switch_page("General")

    def _display_for(self, key, value):
        """Map a stored raw value to its dropdown display label."""
        for disp, val in self.DROPDOWN_MAPS.get(key, {}).items():
            if val == str(value):
                return disp
        return str(value)

    def _init_variables(self):
        self.vars["clock_style"] = tk.StringVar(value=self.prefs.get_preference("clock_style") or "Standard")
        self.vars["display_seconds"] = tk.BooleanVar(value=bool(self.prefs.get_preference("display_seconds")))
        self.vars["use_turkish_days"] = tk.BooleanVar(value=bool(self.prefs.get_preference("use_turkish_days")))
        self.vars["run_on_start"] = tk.BooleanVar(value=is_startup_enabled())
        self.vars["date_format"] = tk.BooleanVar(value=(str(self.prefs.get_preference("date_format")) == "24"))
        self.vars["player_style"] = tk.StringVar(value=self.prefs.get_preference("player_style") or "Standard")
        self.vars["display_timer"] = tk.BooleanVar(value=bool(self.prefs.get_preference("display_timer")))
        self.vars["display_player"] = tk.BooleanVar(value=bool(self.prefs.get_preference("display_player")))
        self.vars["display_hw_monitor"] = tk.BooleanVar(value=bool(self.prefs.get_preference("display_hw_monitor")))
        self.vars["spotify_enabled"] = tk.BooleanVar(value=bool(self.prefs.get_preference("spotify_enabled")))
        self.vars["spotify_client_id"] = tk.StringVar(value=self.prefs.get_preference("spotify_client_id") or "")
        self.vars["spotify_client_secret"] = tk.StringVar(value=self.prefs.get_preference("spotify_client_secret") or "")
        self.vars["spotify_redirect_uri"] = tk.StringVar(value=self.prefs.get_preference("spotify_redirect_uri") or "")
        self.vars["local_port"] = tk.StringVar(value=str(self.prefs.get_preference("local_port") or "2408"))
        self.vars["discord_local_port"] = tk.StringVar(value=str(self.prefs.get_preference("discord_local_port") or "8888"))
        self.vars["hotkey_monitor"] = tk.StringVar(value=self.prefs.get_preference("hotkey_monitor") or "")
        self.vars["hotkey_mute"] = tk.StringVar(value=self.prefs.get_preference("hotkey_mute") or "")
        self.vars["hotkey_mute_2"] = tk.StringVar(value=self.prefs.get_preference("hotkey_mute_2") or "")
        self.vars["hotkey_calculator"] = tk.StringVar(value=self.prefs.get_preference("hotkey_calculator") or "")
        self.vars["rgb_enabled"] = tk.BooleanVar(value=bool(self.prefs.get_preference("rgb_enabled")))
        self.vars["scrollbar_padding"] = tk.StringVar(value=str(self.prefs.get_preference("scrollbar_padding") or "2"))
        self.vars["text_padding_left"] = tk.StringVar(value=str(self.prefs.get_preference("text_padding_left") or "30"))
        self.vars["auto_launch_gg"] = tk.BooleanVar(value=bool(self.prefs.get_preference("auto_launch_gg")))
        self.vars["hw_polling_interval"] = tk.StringVar(value=self._display_for("hw_polling_interval", self.prefs.get_preference("hw_polling_interval") or 1000))
        self.vars["show_game_fps"] = tk.BooleanVar(value=bool(self.prefs.get_preference("show_game_fps")))
        self.vars["selected_gpu"] = tk.StringVar(value=self.prefs.get_preference("selected_gpu") or "Auto")
        self.vars["spotify_fetch_delay"] = tk.StringVar(value=self._display_for("spotify_fetch_delay", self.prefs.get_preference("spotify_fetch_delay") or 2))
        self.vars["discord_client_id"] = tk.StringVar(value=self.prefs.get_preference("discord_client_id") or "")
        self.vars["discord_client_secret"] = tk.StringVar(value=self.prefs.get_preference("discord_client_secret") or "")
        self.vars["headset_hid_sync_enabled"] = tk.BooleanVar(value=bool(self.prefs.get_preference("headset_hid_sync_enabled")))
        self.vars["debug_enabled"] = tk.BooleanVar(value=bool(self.prefs.get_preference("debug_enabled")))

    def _create_pages(self):
        # General
        p_gen = tk.Frame(self.content_area, bg=Colors.CONTENT)
        self._header(p_gen, "⚙️ General Settings")
        self._dropdown_row(p_gen, "Clock Design", self.vars["clock_style"], ["Standard", "Big Timer", "Date Focused", "Analog"])
        self._toggle_row(p_gen, "Use 24-Hour Format", self.vars["date_format"])
        self._toggle_row(p_gen, "Show Seconds", self.vars["display_seconds"])
        self._toggle_row(p_gen, "Use Turkish Language", self.vars["use_turkish_days"])
        tk.Frame(p_gen, bg=Colors.CONTENT, height=10).pack()
        self._toggle_row(p_gen, "Run on Start", self.vars["run_on_start"])
        tk.Frame(p_gen, bg=Colors.CONTENT, height=20).pack()
        self._header(p_gen, "✨ Software Update")
        self.update_btn_text = tk.StringVar(value="Check for Updates")
        self.update_btn = tk.Button(p_gen, textvariable=self.update_btn_text, font=FONT_SUBHEADER, bg=Colors.CARD_BG, fg=Colors.TEXT_MAIN, relief="flat", cursor="hand2", padx=20, pady=5, command=self._check_updates)
        self.update_btn.pack(anchor="w", padx=5)
        self.pages["General"] = p_gen

        # Display
        p_disp = tk.Frame(self.content_area, bg=Colors.CONTENT)
        self._header(p_disp, "📺 Display Features")
        self._toggle_row(p_disp, "Enable Clock", self.vars["display_timer"], command=lambda: self._exclusive_toggle("display_timer", "display_hw_monitor"))
        self._toggle_row(p_disp, "Enable Music Info", self.vars["display_player"])
        self._dropdown_row(p_disp, "Player Style", self.vars["player_style"], ["Standard", "Compact", "Centered", "Ticker", "Minimal"])
        self._toggle_row(p_disp, "Always Show System Stats", self.vars["display_hw_monitor"], command=lambda: self._exclusive_toggle("display_hw_monitor", "display_timer"))
        tk.Frame(p_disp, bg=Colors.CONTENT, height=10).pack()
        self._toggle_row(p_disp, "Show Game FPS", self.vars["show_game_fps"])
        available_gpus = ["Auto"]
        try:
            from src.HardwareMonitor import _lhm_worker
            available_gpus += _lhm_worker.get_available_gpus()
        except: pass
        self._dropdown_row(p_disp, "Selected GPU", self.vars["selected_gpu"], available_gpus)
        self._dropdown_row(p_disp, "HW Polling Rate", self.vars["hw_polling_interval"], ["500ms", "1s (Default)", "2s", "5s"])
        self.pages["Display"] = p_disp

        # Spotify
        p_spotify = tk.Frame(self.content_area, bg=Colors.CONTENT)
        self._header(p_spotify, "🎵 Spotify Configuration")
        self._toggle_row(p_spotify, "Enable Spotify Integration", self.vars["spotify_enabled"])
        self._entry_row(p_spotify, "Spotify Client ID", self.vars["spotify_client_id"], width=25)
        self._entry_row(p_spotify, "Spotify Client Secret", self.vars["spotify_client_secret"], width=25, show="*")
        self._entry_row(p_spotify, "Redirect URI", self.vars["spotify_redirect_uri"], width=25)
        self._entry_row(p_spotify, "Connection Port", self.vars["local_port"])
        self._dropdown_row(p_spotify, "Polling Rate", self.vars["spotify_fetch_delay"], ["1s (Fast)", "2s (Default)", "3s", "5s", "10s"])
        self.pages["Spotify"] = p_spotify

        # Hotkeys
        p_hot = tk.Frame(self.content_area, bg=Colors.CONTENT)
        self._header(p_hot, "⌨️ Keyboard Shortcuts")
        self._hotkey_row(p_hot, "Show System Stats", self.vars["hotkey_monitor"])
        self._hotkey_row(p_hot, "Mute Mic (Primary)", self.vars["hotkey_mute"])
        self._hotkey_row(p_hot, "Mute Mic (Optional)", self.vars["hotkey_mute_2"])
        tk.Frame(p_hot, bg=Colors.CONTENT, height=10).pack()
        self._header(p_hot, "🖩 Calculator")
        self._hotkey_row(p_hot, "Toggle Calculator", self.vars["hotkey_calculator"])
        self.pages["Hotkeys"] = p_hot

        # Lighting
        p_rgb = tk.Frame(self.content_area, bg=Colors.CONTENT)
        self._header(p_rgb, "🌈 Ambiance Lighting")
        self._toggle_row(p_rgb, "Match Keyboard Color", self.vars["rgb_enabled"])
        self._color_picker_row(p_rgb)
        self.pages["Lighting"] = p_rgb

        # Advanced
        p_adv = tk.Frame(self.content_area, bg=Colors.CONTENT)
        self._header(p_adv, "🔧 Layout Adjustments")
        self._entry_row(p_adv, "Scrollbar Margin (px)", self.vars["scrollbar_padding"])
        self._entry_row(p_adv, "Text Indentation (px)", self.vars["text_padding_left"])
        self._toggle_row(p_adv, "Auto-Launch SteelSeries GG", self.vars["auto_launch_gg"])
        tk.Frame(p_adv, bg=Colors.CONTENT, height=10).pack()
        self._header(p_adv, "🎙️ Discord & Diagnostics")
        self._toggle_row(p_adv, "Enable Headset HID Sync", self.vars["headset_hid_sync_enabled"])
        self._toggle_row(p_adv, "Enable Diagnostic Debug Logging", self.vars["debug_enabled"], command=self._on_debug_toggle)
        self._entry_row(p_adv, "Discord App ID", self.vars["discord_client_id"], width=25)
        self._entry_row(p_adv, "Discord Client Secret", self.vars["discord_client_secret"], width=25, show="*")
        self._entry_row(p_adv, "Discord Port", self.vars["discord_local_port"], width=25)
        self.discord_btn = tk.Button(p_adv, text="🔗 Connect Discord", bg=Colors.CARD_BG, fg=Colors.TEXT_MAIN, relief="flat", cursor="hand2", command=self._authorize_discord_action)
        self.discord_btn.pack(pady=10)
        self.pages["Advanced"] = p_adv

        # Backups
        p_back = tk.Frame(self.content_area, bg=Colors.CONTENT)
        self._create_backups_page(p_back)
        self.pages["Backups"] = p_back

        # Logs
        p_logs = tk.Frame(self.content_area, bg=Colors.CONTENT)
        self._header(p_logs, "📄 Application Logs")
        tools = tk.Frame(p_logs, bg=Colors.CONTENT)
        tools.pack(fill="x", pady=10)
        tk.Button(tools, text="🔄 Refresh", command=self._refresh_logs, bg=Colors.CARD_BG, fg=Colors.TEXT_MAIN, relief="flat").pack(side="left", padx=5)
        tk.Button(tools, text="📂 Open Folder", command=self._open_log_folder, bg=Colors.CARD_BG, fg=Colors.TEXT_MAIN, relief="flat").pack(side="left")
        self.log_text = tk.Text(p_logs, bg=Colors.INPUT_BG, fg=Colors.TEXT_MAIN, font=("Consolas", 9), state="disabled", height=20)
        self.log_text.pack(fill="both", expand=True)
        self.pages["Logs"] = p_logs

    def _create_backups_page(self, parent):
        self._header(parent, "💾 SteelSeries Backups")
        tools = tk.Frame(parent, bg=Colors.CONTENT)
        tools.pack(fill="x", pady=10)
        tk.Button(tools, text="🔄 Refresh", command=self._refresh_backups_list, bg=Colors.CARD_BG, fg=Colors.TEXT_MAIN, relief="flat").pack(side="left", padx=5)
        tk.Button(tools, text="🛡️ Backup Now", command=self._do_manual_backup, bg=Colors.CARD_BG, fg=Colors.TEXT_MAIN, relief="flat").pack(side="left")
        self.backups_scrollable_frame = tk.Frame(parent, bg=Colors.INPUT_BG)
        self.backups_scrollable_frame.pack(fill="both", expand=True)
        self.root.after(100, self._refresh_backups_list)

    def _refresh_backups_list(self):
        from src import ProfileBackup
        for w in self.backups_scrollable_frame.winfo_children(): w.destroy()
        backups = ProfileBackup.list_backups()
        for name, p, count, mtime in (backups or []):
            row = tk.Frame(self.backups_scrollable_frame, bg=Colors.CARD_BG)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=name, bg=Colors.CARD_BG, fg=Colors.TEXT_MAIN).pack(side="left", padx=10)
            tk.Button(row, text="🗑️", command=lambda path=p: self._delete_backup_action(path), bg=Colors.CARD_BG, fg=Colors.DANGER, relief="flat").pack(side="right")

    def _do_manual_backup(self):
        from src import ProfileBackup
        if ProfileBackup.backup_profiles(): self._refresh_backups_list()

    def _delete_backup_action(self, path):
        from src import ProfileBackup
        if messagebox.askyesno("Delete", "Delete backup?", parent=self.root):
            if ProfileBackup.delete_backup(path): self._refresh_backups_list()

    def _authorize_discord_action(self):
        import webbrowser
        self.prefs.preferences["discord_client_id"] = self.vars["discord_client_id"].get()
        self.prefs.save_preferences()
        cid = self.vars["discord_client_id"].get()
        port = self.vars["discord_local_port"].get()
        url = f"https://discord.com/api/oauth2/authorize?client_id={cid}&redirect_uri=http://127.0.0.1:{port}&response_type=code&scope=rpc%20rpc.voice.read%20rpc.voice.write"
        webbrowser.open(url)

    def _switch_page(self, name):
        for p in self.pages.values(): p.pack_forget()
        self.pages[name].pack(fill="both", expand=True, padx=30, pady=20)
        for n, btn in self.nav_buttons.items(): btn.set_selected(n == name)
        self.current_page = name
        if name == "Logs": self._refresh_logs()

    def _refresh_logs(self):
        self.log_text.config(state="normal")
        self.log_text.delete(1.0, tk.END)
        log_file = f_app_data("debug.log")
        if os.path.exists(log_file):
            with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                self.log_text.insert(tk.END, "".join(f.readlines()[-200:]))
        self.log_text.config(state="disabled")

    def _open_log_folder(self):
        os.startfile(f_app_data())

    def _exclusive_toggle(self, k1, k2):
        if self.vars[k1].get(): self.vars[k2].set(False)

    def _header(self, p, t): tk.Label(p, text=t, font=FONT_HEADER, fg=Colors.TEXT_MAIN, bg=Colors.CONTENT).pack(anchor="w", pady=(0, 20))
    def _row_frame(self, p):
        f = tk.Frame(p, bg=Colors.CARD_BG, height=45); f.pack(fill="x", pady=5); f.pack_propagate(False); return f
    def _toggle_row(self, p, l, v, command=None):
        f = self._row_frame(p); tk.Label(f, text=l, font=FONT_BODY, fg=Colors.TEXT_MAIN, bg=Colors.CARD_BG).pack(side="left", padx=15)
        ToggleSwitch(f, v, command=command).pack(side="right", padx=15)
    def _dropdown_row(self, p, l, v, opts):
        f = self._row_frame(p); tk.Label(f, text=l, font=FONT_BODY, fg=Colors.TEXT_MAIN, bg=Colors.CARD_BG).pack(side="left", padx=15)
        cb = ttk.Combobox(f, textvariable=v, values=opts, state="readonly", width=15); cb.pack(side="right", padx=15)
    def _entry_row(self, p, l, v, width=10, show=None):
        f = self._row_frame(p); tk.Label(f, text=l, font=FONT_BODY, fg=Colors.TEXT_MAIN, bg=Colors.CARD_BG).pack(side="left", padx=15)
        tk.Entry(f, textvariable=v, bg=Colors.INPUT_BG, fg=Colors.INPUT_FG, relief="flat", width=width, show=show).pack(side="right", padx=15)
    def _hotkey_row(self, p, l, v):
        f = self._row_frame(p); tk.Label(f, text=l, font=FONT_BODY, fg=Colors.TEXT_MAIN, bg=Colors.CARD_BG).pack(side="left", padx=15)
        tk.Label(f, textvariable=v, fg=Colors.TEXT_DIM, bg=Colors.CARD_BG).pack(side="right", padx=15)

    def _color_picker_row(self, p):
        f = self._row_frame(p); tk.Label(f, text="Color", bg=Colors.CARD_BG, fg=Colors.TEXT_MAIN).pack(side="left", padx=15)
        tk.Button(f, text="PICK", command=lambda: self._on_color_pick(f)).pack(side="right", padx=15)

    def _on_color_pick(self, f):
        c = colorchooser.askcolor()
        if c[1]: self.rgb = [int(x) for x in c[0]]

    def _check_updates(self):
        def worker():
            available, latest = is_update_available()
            if available: self.update_btn_text.set(f"Update to v{latest}")
            else: self.update_btn_text.set("Up to Date")
        threading.Thread(target=worker, daemon=True).start()

    def _save_all(self):
        try:
            # Gather all vars with proper type conversion
            for k, v in self.vars.items():
                val = v.get()

                # Map dropdown display labels back to raw values ("1s (Fast)" -> "1")
                if k in self.DROPDOWN_MAPS:
                    val = self.DROPDOWN_MAPS[k].get(val, val)

                # Integer fields
                if k in ["scrollbar_padding", "text_padding_left", "local_port", "discord_local_port", "spotify_fetch_delay", "hw_polling_interval"]:
                    try: val = int(val)
                    except: val = UserPreferences.DEFAULT.get(k, 0)
                
                # Special mapping for date format checkbox
                if k == "date_format":
                    val = 24 if val else 12
                    
                self.prefs.preferences[k] = val
            
            self.prefs.preferences["rgb_color"] = self.rgb
            self.prefs.save_preferences()
            set_startup(self.vars["run_on_start"].get())
            
            if self.on_save:
                try: self.on_save()
                except: pass
            
            messagebox.showinfo("Success", "Settings saved!")
            self.root.destroy()
        except Exception as e:
            logger.error(f"Save failed: {e}")
            messagebox.showerror("Error", f"Failed to save: {e}")

    def _on_debug_toggle(self):
        from src.debug_utils import toggle_debug_logging
        toggle_debug_logging(self.vars["debug_enabled"].get())

# Only one settings window may exist: tkinter is not thread-safe, and each
# tray click spawns a fresh thread. If a window is already open we focus it
# via Win32 (safe from any thread) instead of touching Tk cross-thread.
_open_gui_lock = threading.Lock()
_open_gui = None


def open_settings(prefs, callback=None):
    global _open_gui
    with _open_gui_lock:
        if _open_gui is not None:
            hwnd = _open_gui.hwnd
            if hwnd:
                try:
                    ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
                except Exception:
                    pass
            return
        gui = SettingsGUI(prefs, callback)
        _open_gui = gui
    try:
        gui.show()
    except Exception:
        logger.exception("Settings window crashed")
    finally:
        with _open_gui_lock:
            if _open_gui is gui:
                _open_gui = None
