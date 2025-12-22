from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import threading
import logging
import time

logger = logging.getLogger("OLED Customizer.ExtensionReceiver")

class ExtensionData:
    def __init__(self):
        self.data = None
        self.last_update = 0

    def update(self, new_data):
        self.data = new_data
        self.last_update = time.time()

    def get_data(self):
        # Data is valid for 5 seconds
        if self.data and (time.time() - self.last_update < 5):
            return self.data
        return None

# Global storage instance
extension_storage = ExtensionData()

class ExtensionHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/extension_data':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            try:
                data = json.loads(post_data.decode('utf-8'))
                extension_storage.update(data)
                self.send_response(200)
            except Exception as e:
                logger.error(f"Failed to parse extension data: {e}")
                self.send_response(400)
            
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        # Handle CORS preflight
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, format, *args):
        # Suppress server logs
        return

class ExtensionReceiver:
    def __init__(self, port=2408):
        self.port = port
        self.server = None
        self.thread = None

    def start(self):
        def run_server():
            self.server = HTTPServer(('127.0.0.1', self.port), ExtensionHandler)
            logger.info(f"Extension Receiver listening on port {self.port}")
            self.server.serve_forever()

        self.thread = threading.Thread(target=run_server, daemon=True)
        self.thread.start()

    def get_latest_data(self):
        return extension_storage.get_data()
