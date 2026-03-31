from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer as HTTPServer
import json
import threading
import logging
import time

logger = logging.getLogger("OLED Customizer.ExtensionReceiver")

class ExtensionData:
    def __init__(self):
        self.tabs = {}  # {tabId: {"data": data, "last_update": time}}
        self.discord_code = None
        self.last_winner_id = None
        self._lock = threading.Lock()

    def update(self, new_data):
        tab_id = new_data.get("tabId", "default")
        with self._lock:
            self.tabs[tab_id] = {
                "data": new_data,
                "last_update": time.time()
            }

    def get_data(self):
        now = time.time()
        with self._lock:
            # 1. Cleanup stale tabs
            stale_keys = []
            for k, v in self.tabs.items():
                is_playing = v["data"].get("playing") is True
                limit = 120 if is_playing else 10
                if now - v["last_update"] > limit:
                    stale_keys.append(k)
            for k in stale_keys:
                if k == self.last_winner_id: self.last_winner_id = None
                del self.tabs[k]
            
            if not self.tabs:
                return None
            
            # 2. PRIORITY SELECTION
            # Prio 0: Visible + Playing
            # Prio 1: Playing (Background)
            # Prio 2: Visible (Paused)
            # Prio 3: Other
            
            tab_ids = list(self.tabs.keys())
            def get_prio(k):
                v = self.tabs[k]
                data = v["data"]
                is_playing = data.get("playing") is True
                is_visible = data.get("isFocused") is True # isFocused is document.visibilityState
                
                if is_playing and is_visible: return 0
                if is_playing: return 1
                if is_visible: return 2
                return 3

            tab_ids.sort(key=lambda k: (get_prio(k), -self.tabs[k]["last_update"]))
            best_id = tab_ids[0]
            
            # Stickiness: Stay with current winner if they are still playing and best is not 'visible'
            if self.last_winner_id in self.tabs:
                winner_v = self.tabs[self.last_winner_id]
                if winner_v["data"].get("playing") is True and get_prio(best_id) >= 1:
                    best_id = self.last_winner_id

            self.last_winner_id = best_id
            return self.tabs[best_id]["data"]

    def set_discord_code(self, code):
        with self._lock:
            self.discord_code = code
            logger.info("Captured Discord Auth Code from localhost callback")

    def consume_discord_code(self):
        with self._lock:
            code = self.discord_code
            self.discord_code = None
            return code

# Global storage instance
extension_storage = ExtensionData()

class ExtensionHandler(BaseHTTPRequestHandler):
    MAX_BODY_SIZE = 1_048_576  # 1 MB limit

    def do_POST(self):
        logger.info(f"DEBUG: Received POST request on {self.path}")
        if self.path == '/extension_data':
            raw = self.headers.get('Content-Length', '0')
            try:
                content_length = int(raw)
            except (ValueError, TypeError):
                self.send_response(400)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                return

            if content_length > self.MAX_BODY_SIZE:
                self.send_response(413)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                return

            post_data = self.rfile.read(content_length)
            
            try:
                data = json.loads(post_data.decode('utf-8'))
                logger.info(f"DEBUG: Ext payload -> Title: {data.get('title')} | Playing: {data.get('playing')} | Focused: {data.get('isFocused')}")
                extension_storage.update(data)
                self.send_response(200)
            except Exception as e:
                logger.error(f"Failed to parse extension data: {e}")
                self.send_response(400)
            
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Private-Network', 'true')
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        # Handle Discord OAuth Redirect: http://localhost:PORT/?code=XYZ
        from urllib.parse import urlparse, parse_qs
        query = urlparse(self.path).query
        params = parse_qs(query)
        
        if 'code' in params:
            code = params['code'][0]
            extension_storage.set_discord_code(code)
            
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(b"<html><body style='background:#1f1f1f;color:white;font-family:sans-serif;text-align:center;padding-top:50px;'>")
            self.wfile.write(b"<h1>Discord Connected!</h1><p>You can close this window and go back to App.</p></body></html>")
            self.wfile.flush()
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        logger.info(f"DEBUG: Received OPTIONS (preflight) request on {self.path}")
        # Handle CORS preflight
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Allow-Private-Network', 'true')
        self.end_headers()

    def log_message(self, format, *args):
        # Suppress server logs
        return

class ExtensionReceiver:
    def __init__(self, port=2408, host='127.0.0.1'):
        self.port = port
        self.host = host
        self.server = None
        self.thread = None

    def start(self):
        def run_server():
            self.server = HTTPServer((self.host, self.port), ExtensionHandler)
            logger.info(f"Extension Receiver listening on {self.host}:{self.port}")
            self.server.serve_forever()

        self.thread = threading.Thread(target=run_server, daemon=True)
        self.thread.start()

    def stop(self):
        if self.server:
            logger.info("Extension Receiver: Stopping...")
            # We don't call shutdown() directly here because it can deadlock 
            # if the server is in the middle of a request or haven't fully started.
            # main.py's os._exit(0) is our ultimate safety net for Lite.
            self.server = None

    def get_latest_data(self):
        return extension_storage.get_data()

    def get_discord_code(self):
        return extension_storage.consume_discord_code()
