"""
OLED Customizer - Ultra Premium Settings GUI
Frameless window, sidebar navigation, custom widgets, high-end aesthetics.
"""

import tkinter as tk
from tkinter import ttk, colorchooser
import logging

logger = logging.getLogger("OLED Customizer.Settings")

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
        self.current_page = "General"
        self.pages = {}
        self.nav_buttons = {}

    def show(self):
        if self.root:
            try: self.root.lift(); return
            except: pass

        self.root = tk.Tk()
        self.root.overrideredirect(True) # Frameless
        self.root.geometry("640x480")
        self.root.configure(bg=Colors.BG_ROOT)
        
        # Center
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - 640) // 2
        y = (self.root.winfo_screenheight() - 480) // 2
        self.root.geometry(f"+{x}+{y}")
        
        # FIX: Force taskbar icon for frameless window
        import ctypes
        from ctypes import windll
        
        def set_appwindow(root):
            GWL_EXSTYLE = -20
            WS_EX_APPWINDOW = 0x00040000
            WS_EX_TOOLWINDOW = 0x00000080
            hwnd = windll.user32.GetParent(root.winfo_id())
            style = windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style = style & ~WS_EX_TOOLWINDOW
            style = style | WS_EX_APPWINDOW
            windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
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
            ("Advanced", "🔧")
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

        # === CONTENT AREA ===
        self.content_area = tk.Frame(container, bg=Colors.CONTENT)
        self.content_area.pack(side="right", fill="both", expand=True)
        
        # Initialize Pages
        self._init_variables()
        self._create_pages()
        self._switch_page("General")

    def _init_variables(self):
        # Create Tk variables for all prefs
        # General
        self.vars["clock_style"] = tk.StringVar(value=self.prefs.get_preference("clock_style") or "Standard")
        self.vars["display_seconds"] = tk.BooleanVar(value=bool(self.prefs.get_preference("display_seconds")))
        self.vars["use_turkish_days"] = tk.BooleanVar(value=bool(self.prefs.get_preference("use_turkish_days")))
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
        # Hotkeys
        self.vars["hotkey_monitor"] = tk.StringVar(value=self.prefs.get_preference("hotkey_monitor") or "")
        self.vars["hotkey_mute"] = tk.StringVar(value=self.prefs.get_preference("hotkey_mute") or "")
        # RGB
        self.vars["rgb_enabled"] = tk.BooleanVar(value=bool(self.prefs.get_preference("rgb_enabled")))
        # Advanced
        self.vars["scrollbar_padding"] = tk.StringVar(value=str(self.prefs.get_preference("scrollbar_padding") or "2"))
        self.vars["text_padding_left"] = tk.StringVar(value=str(self.prefs.get_preference("text_padding_left") or "30"))

    def _create_pages(self):
        # -- GENERAL PAGE --
        p_gen = tk.Frame(self.content_area, bg=Colors.CONTENT)
        self._header(p_gen, "⚙️ General Settings")
        self._dropdown_row(p_gen, "Clock Design", self.vars["clock_style"], ["Standard", "Big Timer", "Date Focused", "Analog"])
        self._toggle_row(p_gen, "Show Seconds", self.vars["display_seconds"])
        self._toggle_row(p_gen, "Use Turkish Language", self.vars["use_turkish_days"])
        self.pages["General"] = p_gen
        
        # -- DISPLAY PAGE --
        p_disp = tk.Frame(self.content_area, bg=Colors.CONTENT)
        self._header(p_disp, "📺 Display Features")
        self._toggle_row(p_disp, "Enable Clock", self.vars["display_timer"], 
                          command=lambda: self._exclusive_toggle("display_timer", "display_hw_monitor"))
        self._toggle_row(p_disp, "Enable Music Info", self.vars["display_player"])
        self._toggle_row(p_disp, "Always Show System Stats", self.vars["display_hw_monitor"],
                          command=lambda: self._exclusive_toggle("display_hw_monitor", "display_timer"))
        self.pages["Display"] = p_disp
        
        # -- SPOTIFY PAGE --
        p_spotify = tk.Frame(self.content_area, bg=Colors.CONTENT)
        self._header(p_spotify, "🎵 Spotify Configuration")
        self._toggle_row(p_spotify, "Enable Spotify Integration", self.vars["spotify_enabled"])
        self._entry_row(p_spotify, "Spotify Client ID", self.vars["spotify_client_id"], width=25)
        self._entry_row(p_spotify, "Spotify Client Secret", self.vars["spotify_client_secret"], width=25, show="*")
        self._entry_row(p_spotify, "Redirect URI", self.vars["spotify_redirect_uri"], width=25)
        self._entry_row(p_spotify, "Connection Port", self.vars["local_port"])
        
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
        self._hotkey_row(p_hot, "Mute Microphone Key", self.vars["hotkey_mute"])
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
        self.pages["Advanced"] = p_adv

    def _switch_page(self, page_name):
        # Hide all pages
        for p in self.pages.values():
            p.pack_forget()
        
        # Show selected
        if page_name in self.pages:
            self.pages[page_name].pack(fill="both", expand=True, padx=30, pady=20)
            
        # Update Nav
        for name, btn in self.nav_buttons.items():
            btn.set_selected(name == page_name)
        
        self.current_page = page_name

    def _exclusive_toggle(self, updated_key, other_key):
        """Ensures that if one is enabled, the other is disabled."""
        if self.vars[updated_key].get():
            self.vars[other_key].set(False)
        # Redraw switches since they are canvas based
        for widget in self.pages["Display"].winfo_children():
            for child in widget.winfo_children():
                if isinstance(child, ToggleSwitch):
                    child._draw()

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

    def _dropdown_row(self, parent, label, var, options):
        f = self._row_frame(parent)
        tk.Label(f, text=label, font=FONT_BODY, fg=Colors.TEXT_MAIN, bg=Colors.CARD_BG).pack(side="left", padx=15)
        cb = ttk.Combobox(f, textvariable=var, values=options, state="readonly", width=15)
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
                
            popup.bind("<Key>", on_key)
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

    def _save_all(self):
        try:
            # Gather all vars
            for k, v in self.vars.items():
                val = v.get()
                logger.info(f"Saving {k}: {val}")
                
                if k in ["scrollbar_padding", "text_padding_left", "local_port"]:
                    try: val = int(val)
                    except: val = 0
                    self.prefs.preferences[k] = val
                else:
                    self.prefs.preferences[k] = val
            
            self.prefs.preferences["rgb_color"] = self.rgb
            self.prefs.save_preferences()
            logger.info("Settings Saved via Ultra-Premium GUI")
            
            # Show success message – include update instruction only on Spotify page
            if getattr(self, "current_page", None) == "Spotify":
                # Trigger callback BEFORE destroying (so reload_config deletes credentials.json)
                if self.on_save:
                    try: self.on_save()
                    except: pass
                    
                tk.messagebox.showinfo(
                    "Restart Required",
                    "Spotify settings changed. Please restart the application manually."
                )
                self.root.destroy()
                return
            else:
                tk.messagebox.showinfo("Success", "Settings saved!")

            # Trigger callback (which calls DisplayManager.update_config which calls update_preferences)
            if self.on_save:
                try: self.on_save()
                except: pass

            self.root.destroy()
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            tk.messagebox.showerror("Error", f"Failed to save settings:\n{e}")


def open_settings(prefs, callback=None):
    SettingsGUI(prefs, callback).show()
