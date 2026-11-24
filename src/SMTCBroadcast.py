"""
SMTC Broadcast — Exposes Windows media now-playing data as a JSON HTTP endpoint.

When enabled, starts a tiny HTTP server on a user-configured port (default 1231)
that serves GET /media with the current SMTC state. Designed for consumption by
SignalRGB custom effects or any other local tool that needs now-playing info.

The server reads from a shared state that the SMTC poll loop in DisplayManager
maintains — no extra Windows queries per request.
"""

import base64
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer as HTTPServer

logger = logging.getLogger("OLED Customizer.SMTCBroadcast")


class SMTCBroadcastState:
    """Thread-safe container for the data served by GET /media."""

    def __init__(self):
        self._lock = threading.Lock()
        self.changed_event = threading.Event()
        self.playing = False
        self.title = ""
        self.artist = ""
        self.album = ""
        self.cover = ""
        self._empty_streak = 0

    def update(self, smtc_data):
        """Called from the SMTC poll loop with the latest data dict."""
        if not smtc_data or not smtc_data.get("title"):
            with self._lock:
                self._empty_streak += 1
                if self._empty_streak < 10:
                    if self.playing:
                        self.playing = False
                        self.changed_event.set()
                    return
                was_active = self.playing or bool(self.title)
                self.playing = False
                self.title = ""
                self.artist = ""
                self.album = ""
                self.cover = ""
            if was_active:
                self.changed_event.set()
            return

        title = smtc_data.get("title") or ""
        artist = smtc_data.get("artist") or ""
        album = smtc_data.get("album") or ""
        paused = smtc_data.get("paused", True)
        new_playing = not paused
        cover = smtc_data.get("cover") or ""

        with self._lock:
            self._empty_streak = 0
            changed = (
                self.playing != new_playing
                or self.title != title
                or self.artist != artist
                or self.album != album
                or self.cover != cover
            )
            self.playing = new_playing
            self.title = title
            self.artist = artist
            self.album = album
            self.cover = cover

        if changed:
            self.changed_event.set()

    def to_json(self):
        """Return a JSON-serializable dict snapshot."""
        with self._lock:
            return {
                "playing": self.playing,
                "title": self.title,
                "artist": self.artist,
                "album": self.album,
                "cover": self.cover,
            }


# Global state instance — written by DisplayManager, read by HTTP handlers
broadcast_state = SMTCBroadcastState()


class _BroadcastHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler that serves GET /media as JSON."""

    def do_GET(self):
        if self.path == "/media" or self.path.startswith("/media?"):
            data = broadcast_state.to_json()
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)
        elif self.path in ("/cover", "/cover.jpg", "/cover.png") or self.path.startswith(("/cover.jpg?", "/cover.png?", "/cover?")):
            data = broadcast_state.to_json()
            cover_uri = data.get("cover") or ""
            if cover_uri and "," in cover_uri:
                header, b64 = cover_uri.split(",", 1)
                content_type = "image/png" if "png" in header else "image/jpeg"
                try:
                    img_bytes = base64.b64decode(b64)
                    self.send_response(200)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                    self.send_header("Content-Length", str(len(img_bytes)))
                    self.end_headers()
                    self.wfile.write(img_bytes)
                    return
                except Exception as e:
                    logger.debug("Failed decoding cover for HTTP client: %s", e)
            self.send_response(404)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
        else:
            self.send_response(404)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

    def do_OPTIONS(self):
        # Handle CORS preflight
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        # Suppress per-request console spam
        return


class SMTCBroadcastServer:
    """Start/stop wrapper around the broadcast HTTP server."""

    def __init__(self, port=1231, host="127.0.0.1"):
        self.port = port
        self.host = host
        self.server = None
        self.thread = None

    def start(self):
        """Start serving in a background daemon thread."""
        if self.thread and self.thread.is_alive():
            return

        def run_server():
            try:
                self.server = HTTPServer((self.host, self.port), _BroadcastHandler)
                logger.info(f"SMTC Broadcast listening on {self.host}:{self.port}")
                self.server.serve_forever()
            except OSError as e:
                logger.error(f"SMTC Broadcast failed to bind on port {self.port}: {e}")
            except Exception as e:
                logger.error(f"SMTC Broadcast server error: {e}")

        self.thread = threading.Thread(target=run_server, daemon=True, name="SMTC-Broadcast")
        self.thread.start()

    def stop(self):
        """Shut down the server safely."""
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception:
                pass
            self.server = None
            logger.info("SMTC Broadcast stopped")

    def is_running(self):
        return self.server is not None and self.thread is not None and self.thread.is_alive()
