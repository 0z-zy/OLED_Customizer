from PIL import ImageFont, ImageDraw, Image
from time import localtime, strftime
import math

from src.image_utils import fetch_content_path
from src.utils import normalize_text


class Timer:
    class Style:
        STANDARD = "Standard"
        BIG = "Big Timer"
        DATE_FOCUSED = "Date Focused"
        ANALOG = "Analog"

    def __init__(self, config, date_format, display_seconds, use_turkish_days=False, style="Standard"):
        self.config = config
        self.date_format = int(date_format)
        self.display_seconds = display_seconds
        self.use_turkish_days = use_turkish_days
        self.style = style
        
        # Instance-level fonts with Safety Fallbacks
        def safe_load_font(path, size):
            try:
                return ImageFont.truetype(font=path, size=size)
            except Exception:
                # Fallback to default if custom font fails
                try:
                    return ImageFont.load_default()
                except Exception:
                    # Absolute emergency fallback
                    return None

        digi_path = fetch_content_path('fonts/DS-DIGIB.ttf')
        self.FONT_DIGI_BIG = safe_load_font(digi_path, 24)
        self.FONT_DIGI_MED = safe_load_font(digi_path, 20)
        self.FONT_DIGI_SMALL = safe_load_font(digi_path, 14)
        self.FONT_HUGE = safe_load_font(digi_path, 38)
        # Deliberately NOT the DS-DIGI face: it is a 7-segment LCD font whose
        # digits break into disconnected bars at small sizes ('5' especially).
        # VerdanaBold at 9px stays solid and renders "100" at 18px — almost
        # exactly the battery icon's width, so it centres cleanly underneath.
        self.FONT_BATT = safe_load_font(fetch_content_path('fonts/VerdanaBold.ttf'), 9)

        # The clock changes at most once per second but get_image is called at
        # display FPS (10x/sec) — cache the rendered frame per displayed state.
        self._cache_key = None
        self._cached_image = None

        # Headset battery in the top-left corner. The HW monitor's three
        # columns have no free slot, but every clock style leaves this corner
        # empty. DisplayManager injects the getter.
        self.show_battery = False
        self.show_battery_percent = False   # icon only unless enabled
        self.battery_getter = None

    def set_style(self, style):
        self.style = style

    def _battery(self):
        if not self.show_battery or not self.battery_getter:
            return None
        try:
            val = self.battery_getter()
        except Exception:
            return None
        return val if isinstance(val, int) and 0 <= val <= 100 else None

    def _draw_battery(self, draw, pct):
        """Phone-style horizontal battery, top-right, level printed under it.

            ┌────────┐▌   <- body + terminal nub on the right
            │▓▓▓░░░░░│▌
            └────────┘▌
                   51     <- percentage
        """
        w = self.config.width
        on, off = self.config.primary, self.config.secondary

        x1 = w - 4                   # body right edge (nub sits outside it)
        x0 = x1 - 18                 # 19px wide
        top, bot = 1, 9              # 9px tall, 1px clear of the screen edge

        # Clear the corner first: the Big Timer face is wide enough to run
        # underneath the icon, and overlapping strokes make both unreadable.
        # Only reserve the taller area when the number is actually drawn.
        draw.rectangle((x0 - 2, 0, w - 1, 26 if self.show_battery_percent else 10),
                       fill=off)

        draw.rectangle((x0, top, x1, bot), outline=on)                  # body
        draw.rectangle((x1 + 1, top + 3, x1 + 2, bot - 3), fill=on)     # nub

        # 4 discrete segments (25% each) rather than one continuous fill —
        # a solid block reads as a single bar and you can't judge the level
        # at a glance. There is a 1px gap INSIDE the border as well as between
        # segments; without it the end segments merge with the outline and the
        # icon looks lopsided. 2px border + 2px padding + 4x3px + 3x1px = 19.
        SEGMENTS, SEG_W, GAP = 4, 3, 1
        lit = max(0, min(SEGMENTS, -(-max(0, min(100, pct)) // (100 // SEGMENTS))))
        for i in range(lit):
            left = x0 + 2 + i * (SEG_W + GAP)
            draw.rectangle((left, top + 2, left + SEG_W - 1, bot - 2), fill=on)

        # Level centred under the icon (icon spans x0..x1+2 including the nub)
        if self.show_battery_percent:
            draw.text(((x0 + x1 + 2) // 2, 11), str(pct), font=self.FONT_BATT,
                      fill=on, anchor="mt")

    def get_image(self):
        battery = self._battery()
        now = localtime()
        if self.style == self.Style.ANALOG:
            # use_turkish_days matters here too: analog draws the day name
            key = (self.style, now.tm_hour, now.tm_min,
                   now.tm_sec if self.display_seconds else -1,
                   self.use_turkish_days, battery, self.show_battery_percent)
        else:
            t_text, d_text = self.get_current_time()
            key = (self.style, t_text, d_text, battery, self.show_battery_percent)

        if key == self._cache_key and self._cached_image is not None:
            return self._cached_image

        image = Image.new(
            mode="1",
            size=(self.config.width, self.config.height),
            color=self.config.secondary
        )
        draw = ImageDraw.Draw(image)

        cx = self.config.width / 2
        cy = self.config.height / 2
        
        # === ANALOG STYLE ===
        if self.style == self.Style.ANALOG:
             current_time = localtime()
             # Draw Clock Face (Circle)
             radius = 18
             draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=self.config.primary)
             
             # Center dot
             draw.ellipse((cx - 1, cy - 1, cx + 1, cy + 1), fill=self.config.primary)

             # Calculate Angles
             # Hour hand: (Hours + Minutes/60) * 30 degrees per hour - 90 (to start at top)
             # Minute hand: Minutes * 6 degrees per minute - 90
             # Second hand: Seconds * 6 degrees per second - 90
             
             hour_angle = math.radians((current_time.tm_hour % 12 + current_time.tm_min / 60) * 30 - 90)
             minute_angle = math.radians(current_time.tm_min * 6 - 90)
             second_angle = math.radians(current_time.tm_sec * 6 - 90)

             # Draw Hands
             # Hour Hand (Shorter)
             hour_len = 10
             hx = cx + hour_len * math.cos(hour_angle)
             hy = cy + hour_len * math.sin(hour_angle)
             draw.line((cx, cy, hx, hy), fill=self.config.primary, width=2)

             # Minute Hand (Longer)
             min_len = 15
             mx = cx + min_len * math.cos(minute_angle)
             my = cy + min_len * math.sin(minute_angle)
             draw.line((cx, cy, mx, my), fill=self.config.primary, width=1)
             
             # Second Hand (Thin, if enabled)
             if self.display_seconds:
                 sec_len = 16
                 sx = cx + sec_len * math.cos(second_angle)
                 sy = cy + sec_len * math.sin(second_angle)
                 draw.line((cx, cy, sx, sy), fill=self.config.primary, width=1)
             
             # Draw Digital Time Side-by-Side? No, keep it clean analog only or maybe small digital corner?
             # Let's keep it purely analog + date on right side maybe?
             # For now, just clean analog centered.
             
             # Optional: Show Date on the right side if space permits?
             # 128 width. Clock is ~40px wide in center. 
             # Let's put date on the right side (Start at x=90)
             _, date_text = self.get_current_time()
             draw.text((100, cy), date_text.split(" ")[0], font=self.FONT_DIGI_SMALL, fill=self.config.primary, anchor="mm") # Day Name
             
        else:
            time_text, date_text = self.get_current_time()

            if self.style == self.Style.BIG:
                # === BIG STYLE: HUGE TIME, NO DATE ===
                draw.text(
                    (cx, cy),
                    time_text,
                    font=self.FONT_HUGE,
                    fill=self.config.primary,
                    anchor="mm"
                )

            elif self.style == self.Style.DATE_FOCUSED:
                # === DATE FOCUSED: BIG DATE, SMALL TIME ===
                draw.text(
                    (cx, cy - 8),
                    date_text,
                    font=self.FONT_DIGI_MED,
                    fill=self.config.primary,
                    anchor="mm"
                )
                draw.text(
                    (cx, cy + 12),
                    time_text,
                    font=self.FONT_DIGI_SMALL,
                    fill=self.config.primary,
                    anchor="mm"
                )

            else:
                # === STANDARD STYLE (Default) ===
                draw.text(
                    (cx, cy - 6),
                    time_text,
                    font=self.FONT_DIGI_BIG,
                    fill=self.config.primary,
                    anchor="mm"
                )
                draw.text(
                    (cx, cy + 10),
                    date_text,
                    font=self.FONT_DIGI_SMALL,
                    fill=self.config.primary,
                    anchor="mm"
                )

        if battery is not None:
            self._draw_battery(draw, battery)

        self._cache_key = key
        self._cached_image = image
        return image

    def get_current_time(self):
        current_time = localtime()
        seconds = ":%S" if self.display_seconds else ""

        hour_24 = current_time.tm_hour
        am_pm = "AM" if hour_24 < 12 else "PM"

        if self.date_format == 12:
            time_text = strftime("%I:%M" + seconds, current_time) + f" {am_pm}"
        else:
            time_text = strftime("%H:%M" + seconds, current_time)

        # Remove AM/PM for Big Style to fit huge text if desired, or keep it short
        if self.style == self.Style.BIG and self.display_seconds:
             pass

        day_str = strftime("%a", current_time)
        if self.use_turkish_days:
             mapping = {
                 "Mon": "Pzt", "Tue": "Sal", "Wed": "Çar", "Thu": "Per", "Fri": "Cum", "Sat": "Cmt", "Sun": "Paz",
                 "Monday": "Pzt", "Tuesday": "Sal", "Wednesday": "Çar", "Thursday": "Per", "Friday": "Cum", "Saturday": "Cmt", "Sunday": "Paz"
             }
             if day_str in mapping:
                 day_str = mapping[day_str]
        
        date_text = f"{day_str} {strftime('%d/%m/%Y', current_time)}"

        return time_text, normalize_text(date_text)

    def set_display_seconds(self, display_seconds):
        self.display_seconds = display_seconds

    def set_date_format(self, date_format):
        self.date_format = date_format if date_format == 12 else 24

    def set_use_turkish_days(self, use_turkish_days):
        self.use_turkish_days = use_turkish_days
