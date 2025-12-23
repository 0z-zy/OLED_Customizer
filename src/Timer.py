from PIL import ImageFont, ImageDraw, Image
from time import localtime, strftime
import math

from src.image_utils import fetch_content_path
from src.utils import normalize_text


class Timer:
    # Fonts
    FONT_DIGI_BIG = ImageFont.truetype(font=fetch_content_path('fonts/DS-DIGIB.ttf'), size=24)
    FONT_DIGI_MED = ImageFont.truetype(font=fetch_content_path('fonts/DS-DIGIB.ttf'), size=20)
    FONT_DIGI_SMALL = ImageFont.truetype(font=fetch_content_path('fonts/DS-DIGIB.ttf'), size=14)
    
    FONT_HUGE = ImageFont.truetype(font=fetch_content_path('fonts/DS-DIGIB.ttf'), size=38)

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

    def set_style(self, style):
        self.style = style

    def get_image(self):
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
