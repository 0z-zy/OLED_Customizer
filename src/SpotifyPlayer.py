from PIL import Image, ImageDraw, ImageFont
from src.image_utils import fetch_content_path, draw_spotify, draw_youtube, draw_generic_media
from src.ScrollableText import ScrollableText


class SpotifyPlayer:
    def __init__(self, config, preferences, fps=None):
        # ORİJİNAL FONTLAR
        self.ARTIST_FONT = ImageFont.truetype(
            font=fetch_content_path('fonts/MunroSmall.ttf'),
            size=10,
        )
        self.TITLE_FONT = ImageFont.truetype(
            font=fetch_content_path(
                'fonts/VerdanaBoldExtended.ttf'
                if preferences.get_preference('extended_font')
                else 'fonts/VerdanaBold.ttf'
            ),
            size=11,
        )

        self.DURATION_FONT = self.ARTIST_FONT

        self.config = config

        self.fps = fps
        self.step = 0

        self.scrollbar_region = (
            self.config.scrollbar_padding,
            24,
            self.config.width - self.config.scrollbar_padding + 1,
            30,
        )
        self.artist = ScrollableText(self.config, self.ARTIST_FONT, "", 3)
        self.title = ScrollableText(self.config, self.TITLE_FONT, "", 15)

        self.paused = True
        self.pause_started = 0
        self.changed = False
        self.song_position = 0
        self.song_duration = 0
        self.song_duration = 0
        self.previous_image = None
        self.source = "spotify"

    def set_paused(self, paused=True):
        self.paused = paused

    def update_song(self, title, artist, song_position=0, song_duration=0, paused=False, source="spotify"):
        self.title.set_text(title)
        self.artist.set_text(artist)

        self.paused = paused
        self.song_position = song_position
        self.song_duration = song_duration
        self.source = source
        self.changed = True
        self.step = 0
        self.title.set_step(0)
        self.artist.set_step(0)

    def is_playing(self):
        return self.song_position != self.song_duration

    def increase_timer(self):
        self.seek_song(self.song_position + 1000 / self.fps)

    def seek_song(self, song_position):
        is_same_second = int(self.song_position / 1000) == int(song_position / 1000)
        self.song_position = max(0, min(song_position, self.song_duration))

        if not is_same_second:
            self.changed = True

    def draw_progress_bar(self, draw, region):
        if self.song_duration == 0:
            percentage = 0
        else:
            percentage = self.song_position / self.song_duration

        draw.rectangle(region, outline=self.config.primary)
        draw.rectangle(
            (
                region[0],
                region[1],
                region[0] + int(percentage * (region[2] - region[0])),
                region[3],
            ),
            fill=self.config.primary,
        )

    def draw_duration(self, draw, duration, position, anchor):
        hours = duration // 3600
        minutes = (duration % 3600) // 60
        seconds = duration % 60

        if hours > 0:
            text = "{:02d}:{:02d}:{:02d}".format(hours, minutes, seconds)
        else:
            text = "{:02d}:{:02d}".format(minutes, seconds)

        draw.text(
            position,
            text,
            font=self.DURATION_FONT,
            fill=self.config.primary,
            anchor=anchor,
        )

    def will_it_change(self):
        if (
            not self.paused
            and int((self.song_position + 1000 / self.fps) / 1000)
            != int((self.song_position / 1000))
        ):
            return True

        return self.title.will_it_change() or self.artist.will_it_change()

    def set_style(self, style="Standard"):
        valid_styles = ["Standard", "Compact", "Centered", "Ticker", "Minimal"]
        if style not in valid_styles:
            style = "Standard"
        self.style = style
        self.changed = True
        self.step = 0

    def next_step(self, force_update=False):
        if (
            not self.changed
            and not force_update
            and not self.will_it_change()
            and self.previous_image is not None
        ):
            self.step += 1
            self.artist.increase_step()
            self.title.increase_step()

            if not self.paused:
                self.increase_timer()

            return self.previous_image

        if not self.paused:
            self.increase_timer()

        self.step += 1
        image = Image.new(
            mode="1",
            size=(self.config.width, self.config.height),
            color=self.config.secondary,
        )
        draw = ImageDraw.Draw(image)
        
        style = getattr(self, "style", "Standard")
        
        # Reset text positions and custom bounds to safe defaults
        # This prevents issues when switching styles
        try:
            self.title.pos_y = 15
            self.artist.pos_y = 3
            self.title.custom_x = None
            self.title.custom_width = None
            self.title.left_align = False
            self.artist.custom_x = None
            self.artist.custom_width = None
            self.artist.left_align = False
            self.title.steps_calculated = False
            self.artist.steps_calculated = False
        except:
            pass
        
        try:
            if style == "Compact":
                self._draw_compact(draw, image)
            elif style == "Centered":
                self._draw_centered(draw, image)
            elif style == "Ticker":
                self._draw_ticker(draw, image)
            elif style == "Minimal":
                self._draw_minimal(draw, image)
            else:
                self._draw_standard(draw, image)
        except Exception as e:
            # Fallback to standard on any drawing error
            try:
                self._draw_standard(draw, image)
            except:
                pass

        self.previous_image = image
        self.changed = False
        return image

    def _draw_icon(self, image, pos):
        """Helper to draw source icon."""
        if self.source == "youtube":
            draw_youtube(image, pos)
        elif self.source == "spotify":
            draw_spotify(image, pos)
        else:
            draw_generic_media(image, pos)

    # ========== STYLE: STANDARD ==========
    # Classic layout: Icon top-left, Title below icon, Artist below title, 
    # Progress bar at bottom with timestamps on sides.
    def _draw_standard(self, draw, image):
        # Reset text positions to defaults
        self.title.y = 15
        self.artist.y = 3
        
        self.artist.draw_next_step(draw)
        self.title.draw_next_step(draw)

        # Progress bar
        self.draw_progress_bar(
            draw,
            (
                self.config.scrollbar_padding,
                24,
                self.config.width - (self.config.scrollbar_padding + 1),
                30,
            ),
        )

        # Timestamps
        self.draw_duration(
            draw,
            int(round(self.song_position / 1000)),
            (self.config.scrollbar_padding, 34),
            "lm",
        )
        self.draw_duration(
            draw,
            int(round(self.song_duration / 1000)),
            (self.config.width - self.config.scrollbar_padding + 1, 34),
            "rm",
        )

        # Icon area (clear + draw)
        draw.rectangle(
            (0, 0, self.config.text_padding_left - 3, 22),
            fill=self.config.secondary,
        )
        self._draw_icon(image, (2, 3))

    # ========== STYLE: COMPACT ==========
    # Horizontal layout: ICON | TITLE (scrolling) | TIMESTAMP
    # Full-width progress bar at very bottom
    def _draw_compact(self, draw, image):
        # Title only (scrolling), positioned after icon, before timestamp
        self.title.pos_y = 12
        self.title.custom_x = 24
        self.title.custom_width = self.config.width - 75  # 128 - 24(icon) - 51(timestamp) = 53px for title
        self.title.steps_calculated = False
        self.title.draw_next_step(draw)
        
        # MASK: Clear icon area (left) to clip overflowing text
        draw.rectangle((0, 0, 23, 30), fill=self.config.secondary)
        
        # MASK: Clear timestamp area (right) to clip overflowing text
        draw.rectangle((self.config.width - 51, 0, self.config.width, 30), fill=self.config.secondary)
        
        # Draw icon on far left (on top of cleared area)
        self._draw_icon(image, (2, 11))
        
        # Timestamp on far right
        pos_sec = int(round(self.song_position / 1000))
        dur_sec = int(round(self.song_duration / 1000))
        time_str = f"{pos_sec // 60}:{pos_sec % 60:02d}/{dur_sec // 60}:{dur_sec % 60:02d}"
        draw.text((self.config.width - 2, 12), time_str, font=self.ARTIST_FONT, fill=self.config.primary, anchor="rm")
        
        # Full-width progress bar at bottom
        bar_y = 32
        bar_h = 6
        draw.rectangle((0, bar_y, self.config.width - 1, bar_y + bar_h), outline=self.config.primary)
        if self.song_duration > 0:
            pct = self.song_position / self.song_duration
            draw.rectangle((1, bar_y + 1, 1 + int(pct * (self.config.width - 3)), bar_y + bar_h - 1), fill=self.config.primary)

    # ========== STYLE: CENTERED ==========
    # Symmetrical design with decorative borders
    # Title/Artist scrolling (full width), timestamps on sides of progress bar
    def _draw_centered(self, draw, image):
        # Decorative top border line
        draw.line((10, 2, self.config.width - 11, 2), fill=self.config.primary)
        draw.line((4, 2, 8, 2), fill=self.config.primary)
        draw.line((self.config.width - 9, 2, self.config.width - 5, 2), fill=self.config.primary)
        
        # Title (scrolling, full width)
        self.title.pos_y = 6
        self.title.custom_x = 0
        self.title.custom_width = self.config.width
        self.title.steps_calculated = False
        self.title.draw_next_step(draw)
        
        # Artist (scrolling, full width)
        self.artist.pos_y = 18
        self.artist.custom_x = 0
        self.artist.custom_width = self.config.width
        self.artist.steps_calculated = False
        self.artist.draw_next_step(draw)
        
        # Progress bar with timestamps on sides
        bar_y = 32
        bar_h = 4
        
        # Left timestamp
        pos_sec = int(round(self.song_position / 1000))
        draw.text((2, 30), f"{pos_sec // 60}:{pos_sec % 60:02d}", font=self.DURATION_FONT, fill=self.config.primary)
        
        # Right timestamp
        dur_sec = int(round(self.song_duration / 1000))
        draw.text((self.config.width - 2, 30), f"{dur_sec // 60}:{dur_sec % 60:02d}", font=self.DURATION_FONT, fill=self.config.primary, anchor="rm")
        
        # Center progress bar (between timestamps)
        bar_start = 28
        bar_end = self.config.width - 29
        draw.rectangle((bar_start, bar_y, bar_end, bar_y + bar_h), outline=self.config.primary)
        if self.song_duration > 0:
            pct = self.song_position / self.song_duration
            fill_w = int(pct * (bar_end - bar_start - 2))
            draw.rectangle((bar_start + 1, bar_y + 1, bar_start + 1 + fill_w, bar_y + bar_h - 1), fill=self.config.primary)

    # ========== STYLE: TICKER ==========
    # Single line scrolling "Artist - Title" across the full width.
    # Large timestamp (current position) on the left.
    # Visual "VU meter" bars on right side.
    def _draw_ticker(self, draw, image):
        # Big timestamp on left
        pos_sec = int(round(self.song_position / 1000))
        mins = pos_sec // 60
        secs = pos_sec % 60
        time_str = f"{mins}:{secs:02d}"
        
        draw.text((4, 2), time_str, font=self.TITLE_FONT, fill=self.config.primary)
        
        # Combined "Artist - Title" as scrolling ticker at bottom
        ticker_text = f"{self.artist.content}  -  {self.title.content}" if self.artist.content else self.title.content
        
        # Calculate scroll offset based on step
        ticker_offset = (self.step * 2) % (len(ticker_text) * 8 + self.config.width)
        
        draw.text((self.config.width - ticker_offset, 22), ticker_text, font=self.ARTIST_FONT, fill=self.config.primary)
        
        # Fake VU meter bars on right (decorative, use song position as seed)
        meter_x = self.config.width - 28
        bar_heights = [
            8 + (self.step % 5),
            12 + ((self.step + 2) % 7),
            6 + ((self.step + 1) % 4),
            10 + (self.step % 6),
        ]
        for i, h in enumerate(bar_heights):
            x = meter_x + i * 6
            draw.rectangle((x, 18 - h, x + 4, 18), fill=self.config.primary)
        
        # Progress line at very bottom
        if self.song_duration > 0:
            pct = self.song_position / self.song_duration
            draw.line((0, 39, int(pct * self.config.width), 39), fill=self.config.primary, width=1)

    # ========== STYLE: MINIMAL ==========
    # Title + Artist scrolling, vertically centered
    # Decorative corner brackets, thin progress at bottom
    def _draw_minimal(self, draw, image):
        # Title (scrolling, inside brackets)
        self.title.pos_y = 8
        self.title.custom_x = 12
        self.title.custom_width = self.config.width - 24  # Inset from bracket edges
        self.title.steps_calculated = False
        self.title.draw_next_step(draw)
        
        # Artist (scrolling, inside brackets)
        self.artist.pos_y = 19
        self.artist.custom_x = 12
        self.artist.custom_width = self.config.width - 24
        self.artist.steps_calculated = False
        self.artist.draw_next_step(draw)
        
        # MASK: Clear left bracket area to clip overflowing text
        draw.rectangle((0, 0, 11, 30), fill=self.config.secondary)
        
        # MASK: Clear right bracket area to clip overflowing text
        draw.rectangle((self.config.width - 12, 0, self.config.width, 30), fill=self.config.secondary)
        
        # Decorative corner brackets (drawn on top of masked area)
        # Top-left
        draw.line((2, 2, 10, 2), fill=self.config.primary)
        draw.line((2, 2, 2, 10), fill=self.config.primary)
        # Top-right
        draw.line((self.config.width - 11, 2, self.config.width - 3, 2), fill=self.config.primary)
        draw.line((self.config.width - 3, 2, self.config.width - 3, 10), fill=self.config.primary)
        # Bottom-left
        draw.line((2, 28, 10, 28), fill=self.config.primary)
        draw.line((2, 20, 2, 28), fill=self.config.primary)
        # Bottom-right
        draw.line((self.config.width - 11, 28, self.config.width - 3, 28), fill=self.config.primary)
        draw.line((self.config.width - 3, 20, self.config.width - 3, 28), fill=self.config.primary)
        
        # Thin progress line at very bottom
        if self.song_duration > 0:
            pct = self.song_position / self.song_duration
            draw.line((0, 38, int(pct * self.config.width), 38), fill=self.config.primary, width=2)


