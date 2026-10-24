"""
SMTC Broadcast — Exposes Windows media now-playing data as a JSON HTTP endpoint.

When enabled, starts a tiny HTTP server on a user-configured port (default 1231)
that serves GET /media with the current SMTC state. Designed for consumption by
SignalRGB custom effects or any other local tool that needs now-playing info.

The server reads from a shared state that the SMTC poll loop in DisplayManager
maintains — no extra Windows queries per request.
"""

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer as HTTPServer

logger = logging.getLogger("OLED Customizer.SMTCBroadcast")


class SMTCBroadcastState:
    """Thread-safe container for the data served by GET /media."""

    def __init__(self):
        self._lock = threading.Lock()
        self.playing = False
        self.title = ""
        self.artist = ""
        self.album = ""
        self.cover = ""

    def update(self, smtc_data):
        """Called from the SMTC poll loop with the latest data dict."""
        if not smtc_data:
            with self._lock:
                self.playing = False
                self.title = ""
                self.artist = ""
                self.album = ""
                self.cover = ""
            return

        title = smtc_data.get("title") or ""
        artist = smtc_data.get("artist") or ""
        album = smtc_data.get("album") or ""
        paused = smtc_data.get("paused", True)
        cover = smtc_data.get("cover") or ""

        with self._lock:
            self.playing = not paused
            self.title = title
            self.artist = artist
            self.album = album
            self.cover = cover

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
