"""
SignalRGB Pusher — Pushes now-playing state and album art colors to SignalRGB.

SignalRGB's effect webview cannot make network requests; the canvas event API
is the only inbound channel to a custom effect. When enabled, this module
pushes play/pause state, 5 dominant colors from the album cover, and optional
track title to SignalRGB's local canvas endpoint (POST http://127.0.0.1:{port}/canvas/event).
"""

import base64
import io
import logging
import os
import threading
import time
from urllib.parse import quote, urlencode

import colorsys
from PIL import Image
import urllib3

from src.SMTCBroadcast import broadcast_state

logger = logging.getLogger("OLED Customizer.SignalRGBPusher")

# Constants
HOST = "127.0.0.1"
DEFAULT_PORT = 16034
DEFAULT_SENDER = "OLED Customizer"
POLL_INTERVAL = 0.15
HEARTBEAT_INTERVAL = 6.0
MIN_COLOR_DISTANCE = 100
NEAR_BLACK_THRESHOLD = 35
QUANTIZE_COLORS = 16
FALLBACK_PALETTE = ["#141926", "#1c2541", "#2d3a54", "#415a77", "#778da9"]


def extract_colors(img, count=5):
    """
    Extract up to `count` pure, vibrant hex colors engineered specifically for physical RGB LEDs:
    - Bins pixels by Hue into 36 bins (10 deg each).
    - Ignores murky grays (s < 0.20) and dark shadow pixels (v < 0.14) where sensor/compression noise
      causes false chromatic distortion (e.g. shadow pixels being misread as red).
    - Detects truly monochrome / black-and-white artwork (< 6% colored pixels) and extracts an authentic,
      elegant grayscale/silver gradient directly from the image instead of amplifying noise into fake colors.
    - Selects distinct hues (>= 28 deg separation) across multi-color artwork.
    - Eliminates physical LED 'white bleed' by boosting diode purity (S >= 0.92-0.95).
    - For monochromatic single-hue albums (e.g. Billie Eilish / BLUE), builds 5 rich,
      harmonious variations of the dominant hue so sweeps and animations show distinct glowing tones.
    """
    try:
        small = img.convert("RGB").resize((96, 96))
        pixels = list(small.getdata())

        NUM_BINS = 36
        bins = [[] for _ in range(NUM_BINS)]
        grays = []

        for r, g, b in pixels:
            # Skip dark shadow/background pixels where compression/sensor noise creates false hue
            v_raw = max(r, g, b) / 255.0
            if v_raw < 0.14:
                continue
            h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
            if s < 0.20:
                grays.append((r, g, b, h, s, v))
            else:
                b_idx = int(h * NUM_BINS) % NUM_BINS
                bins[b_idx].append((r, g, b, h, s, v))

        total_colored = sum(len(b) for b in bins)
        total_visible = len(grays) + total_colored

        # If the image is overwhelmingly black-and-white / monochrome (< 6% colored pixels)
        # OR total colored pixels are fewer than 80 in the entire 96x96 image, treat as monochrome
        is_monochrome = (total_colored < 80) or (total_visible > 0 and (total_colored / total_visible) < 0.06)

        candidates = []
        if not is_monochrome:
            min_bin_size = max(20, int(total_visible * 0.015))
            for b_idx, px_list in enumerate(bins):
                if len(px_list) < min_bin_size:
                    continue
                avg_h = sum(p[3] for p in px_list) / len(px_list)
                avg_s = sum(p[4] for p in px_list) / len(px_list)
                avg_v = sum(p[5] for p in px_list) / len(px_list)
                score = (len(px_list) ** 0.5) * (avg_s ** 1.2) * (avg_v ** 0.8)
                candidates.append((score, avg_h, avg_s, avg_v, len(px_list)))

            candidates.sort(key=lambda x: x[0], reverse=True)

        def hue_dist(h1, h2):
            d = abs(h1 - h2)
            if d > 0.5:
                d = 1.0 - d
            return d * 360.0

        picked = []
        for score, h, s, v, _ in candidates:
            if all(hue_dist(h, p[0]) >= 28.0 for p in picked):
                picked.append((h, s, v))
            if len(picked) >= count:
                break

        # If truly grayscale / black & white artwork: extract real brightness tiers from photo
        if not picked:
            if not grays:
                return ["#f0f0f0", "#b0b0b0", "#707070", "#404040", "#202020"]
            grays.sort(key=lambda x: x[5], reverse=True)
            percentiles = [0.05, 0.25, 0.50, 0.75, 0.95]
            palette = []
            for p in percentiles:
                idx = int(p * (len(grays) - 1))
                r, g, b = grays[idx][:3]
                palette.append(f"#{r:02x}{g:02x}{b:02x}")
            return palette[:count]

        palette = []
        if len(picked) == 1:
            # Monochromatic album: create 5 rich harmonic variations of the dominant hue
            # with maximum LED saturation (S = 0.95) to prevent washed-out white diode dilution.
            base_h, base_s, base_v = picked[0]
            hue_shifts = [0.0, 10.0 / 360.0, -10.0 / 360.0, 22.0 / 360.0, -18.0 / 360.0]
            v_steps = [0.92, 0.90, 0.85, 0.95, 0.80]
            for i in range(count):
                h = (base_h + hue_shifts[i % len(hue_shifts)]) % 1.0
                s = 0.95
                v = v_steps[i % len(v_steps)]
                r, g, b = [round(c * 255) for c in colorsys.hsv_to_rgb(h, s, v)]
                palette.append(f"#{r:02x}{g:02x}{b:02x}")
        else:
            # Multi-hue album: boost each distinct hue to LED purity
            for h, s, v in picked:
                led_s = max(0.92, min(1.0, s * 1.5))
                led_v = max(0.85, min(1.0, v * 1.25))
                r, g, b = [round(c * 255) for c in colorsys.hsv_to_rgb(h, led_s, led_v)]
                palette.append(f"#{r:02x}{g:02x}{b:02x}")

            # Fill remaining slots with harmonic steps of the primary dominant hue
            base_h, base_s, base_v = picked[0]
            step_idx = 1
            while len(palette) < count:
                shift = (step_idx * 14.0) / 360.0
                h = (base_h + shift) % 1.0
                r, g, b = [round(c * 255) for c in colorsys.hsv_to_rgb(h, 0.95, 0.90)]
                palette.append(f"#{r:02x}{g:02x}{b:02x}")
                step_idx += 1

        return palette[:count]
    except Exception as e:
        logger.debug("extract_colors failed: %s", e)
        return list(FALLBACK_PALETTE)


def colors_from_data_uri(data_uri):
    """
    Decode base64 data URI to image and extract palette.
    Returns list of 5 hex color strings.
    """
    if not data_uri or not isinstance(data_uri, str):
        return list(FALLBACK_PALETTE)
    try:
        if "," in data_uri:
            _, b64 = data_uri.split(",", 1)
        else:
            b64 = data_uri
        img_bytes = base64.b64decode(b64)
        image = Image.open(io.BytesIO(img_bytes))
        return extract_colors(image)
    except Exception as e:
        logger.debug("colors_from_data_uri failed: %s", e)
        return list(FALLBACK_PALETTE)


def safe_text(text, max_length=32):
    """
    Sanitize text for SignalRGB event payload:
    Keep ASCII [A-Za-z0-9._-], replace other characters with '_',
    truncate to max_length, return '?' if empty.
    """
    if not text:
        return "?"
    cleaned = "".join(
        ch if (ch.isalnum() and ch.isascii()) or ch in ".-_" else "_"
        for ch in str(text).strip()
    )
    cleaned = cleaned[:max_length].strip("_")
    return cleaned or "?"


def save_cover_images(data_uri, slot=1):
    """
    Save the current album cover art to disk for the SignalRGB custom effect
    (supporting optional Screen Ambience album art mode).
    """
    if not data_uri or not isinstance(data_uri, str) or "," not in data_uri:
        return
    try:
        _, b64 = data_uri.split(",", 1)
        raw_bytes = base64.b64decode(b64)
        target_dirs = []
        vortx = os.path.expandvars(r"%LOCALAPPDATA%\VortxEngine")
        if os.path.isdir(vortx):
            for entry in os.listdir(vortx):
                dyn = os.path.join(vortx, entry, "Signal-x64", "Effects", "Dynamic")
                if os.path.isdir(dyn):
                    target_dirs.append(dyn)

        for d in target_dirs:
            try:
                with open(os.path.join(d, "current_cover.jpg"), "wb") as f:
                    f.write(raw_bytes)
                if slot:
                    with open(os.path.join(d, f"cover_{slot}.jpg"), "wb") as f:
                        f.write(raw_bytes)
            except Exception:
                pass
    except Exception as e:
        logger.debug("save_cover_images error: %s", e)


def build_event(playing, colors, title="", include_title=False, image_slot=None):
    """
    Wire format: p.<0|1>|c.<30 lowercase hex chars rrggbb>|t.<title>|i.<image_slot>
    When title is disabled or empty, emits t.?
    """
    hex_colors = []
    if colors:
        for c in colors[:5]:
            h = str(c).lstrip("#").lower()
            if len(h) == 6:
                hex_colors.append(h)

    # Ensure exactly 5 colors (30 hex chars total)
    fallback_hex = [c.lstrip("#").lower() for c in FALLBACK_PALETTE]
    while len(hex_colors) < 5:
        if hex_colors:
            hex_colors.append(hex_colors[-1])
        else:
            hex_colors.append(fallback_hex[len(hex_colors)])
    hexes = "".join(hex_colors[:5])

    p_val = "1" if playing else "0"
    t_val = safe_text(title) if include_title else "?"
    parts = [f"p.{p_val}", f"c.{hexes}", f"t.{t_val}"]
    if image_slot:
        parts.append(f"i.{image_slot}")
    return "|".join(parts)


class SignalRGBPusher:
    """
    Background worker that monitors SMTC broadcast state and pushes
    canvas events to SignalRGB at 127.0.0.1:{port}.
    """

    def __init__(self, port=DEFAULT_PORT, sender=DEFAULT_SENDER, include_title=False, state=None):
        self.port = port
        self.sender = sender
        self.include_title = include_title
        self._state = state or broadcast_state
        self._running = False
        self._thread = None
        self._last_track = None
        self._had_cover_for_track = None
        self._img_slot = 1
        self._last_colors = list(FALLBACK_PALETTE)
        self._palette_cache = {}
        self._last_delivered = None
        self._last_push = 0.0
        # Dedicated urllib3 PoolManager with persistent keep-alive connection
        self._http = urllib3.PoolManager(
            num_pools=1,
            headers={"Connection": "keep-alive"},
            timeout=urllib3.Timeout(connect=0.5, read=1.0),
            retries=False,
        )

    def start(self):
        """Start the background pusher daemon thread."""
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="SignalRGB-Pusher")
        self._thread.start()

    def stop(self):
        """Stop the background pusher daemon thread."""
        self._running = False
        ev = getattr(self._state, "changed_event", None)
        if ev is not None:
            ev.set()
        try:
            if self._http:
                self._http.clear()
        except Exception:
            pass
        logger.info("SignalRGB Pusher stopped")

    def is_running(self):
        """Check if pusher thread is actively running."""
        return self._running and self._thread is not None and self._thread.is_alive()

    def _run(self):
        logger.info(f"SignalRGB Pusher started (target {HOST}:{self.port}, sender='{self.sender}')")
        while self._running:
            try:
                self._tick()
            except Exception as e:
                logger.debug("SignalRGB Pusher tick error: %s", e)
            ev = getattr(self._state, "changed_event", None)
            if ev is not None:
                ev.wait(timeout=POLL_INTERVAL)
                ev.clear()
            else:
                time.sleep(POLL_INTERVAL)

    def _tick(self):
        snapshot = self._state.to_json()
        playing = bool(snapshot.get("playing"))
        title = snapshot.get("title") or ""
        artist = snapshot.get("artist") or ""
        album = snapshot.get("album") or ""
        cover = snapshot.get("cover") or ""

        # Extract palette with memory cache (0.00ms recall for known tracks)
        track_key = (title, artist, album)
        if track_key != self._last_track:
            self._last_track = track_key
            self._img_slot = 2 if self._img_slot == 1 else 1
            if cover:
                if track_key in self._palette_cache:
                    self._last_colors = self._palette_cache[track_key]
                else:
                    self._last_colors = colors_from_data_uri(cover)
                    if len(self._palette_cache) > 80:
                        self._palette_cache.pop(next(iter(self._palette_cache)))
                    self._palette_cache[track_key] = self._last_colors
                self._had_cover_for_track = track_key
                save_cover_images(cover, self._img_slot)
            else:
                self._last_colors = list(FALLBACK_PALETTE)
                self._had_cover_for_track = None
        elif cover and self._had_cover_for_track != track_key:
            if track_key in self._palette_cache:
                self._last_colors = self._palette_cache[track_key]
            else:
                self._last_colors = colors_from_data_uri(cover)
                self._palette_cache[track_key] = self._last_colors
            self._had_cover_for_track = track_key
            save_cover_images(cover, self._img_slot)

        event = build_event(
            playing=playing,
            colors=self._last_colors,
            title=title,
            include_title=self.include_title,
            image_slot=self._img_slot if cover else None,
        )

        now = time.monotonic()
        forced = (now - self._last_push) >= HEARTBEAT_INTERVAL
        if event != self._last_delivered or forced:
            self._last_push = now
            if self._post_event(event):
                self._last_delivered = event

    def _post_event(self, event):
        # quote_via=quote is required so spaces in sender become %20 instead of +
        query = urlencode({"sender": self.sender, "event": event}, quote_via=quote)
        url = f"http://{HOST}:{self.port}/canvas/event?{query}"
        try:
            response = self._http.request("POST", url, body=b"")
            resp_data = response.data  # Read response data to release connection
            if response.status == 200:
                return True
            else:
                logger.debug("SignalRGB push non-200 (%s): %s", response.status, resp_data)
                return False
        except Exception as e:
            logger.debug("SignalRGB push failed: %s", e)
            return False
