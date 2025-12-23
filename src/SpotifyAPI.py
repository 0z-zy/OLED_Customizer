from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode, urlparse, parse_qs
from requests import Session
from base64 import b64encode
from time import time
from json import loads, dumps

import ssl
import ctypes
import webbrowser
import logging
import sys
import os
import socket

from src.utils import fetch_app_data_path
from src.ssl import generate_cert

logger = logging.getLogger('SpotifyAPI')


class SpotifyAPI:
    SPOTIFY_API_URL = "https://accounts.spotify.com"

    def __init__(self, config):
        self.config = config
        self.client_id = str(self.config.get_preference('spotify_client_id')).strip()
        self.client_secret = str(self.config.get_preference('spotify_client_secret')).strip()
        self.redirect_uri = str(self.config.get_preference('spotify_redirect_uri')).strip()
        self.port = int(self.config.get_preference('local_port'))

        self.ready = self._check_configuration()

        self.refresh_token = ""
        self.token = ""
        self.expires = -1
        
        self.session = Session()
        self._auth_lock = __import__('threading').Lock()

    # ... (skipping unchanged code until fetch_token) ...

    def fetch_token(self, prompt_user=True):
        if not self.ready:
            return

        # Prevent concurrent auth attempts (spam prevention)
        if not self._auth_lock.acquire(blocking=False):
            logger.warning("Auth attempt skipped - already in progress")
            return

        try:
            if not self.load_token():
                if not prompt_user:
                    logger.info("No token found and prompt_user=False. Skipping browser auth.")
                    return

                url = self.SPOTIFY_API_URL + "/authorize?"
                url += urlencode({
                    "scope": "user-read-playback-state user-read-currently-playing",
                    "response_type": "code",
                    "client_id": self.client_id,
                    "redirect_uri": self.redirect_uri
                })

                server = self.start_server()
                
                if server.error: # Check for bind error immediately
                    logger.error(f"Cannot start auth server: {server.error}")
                    return

                webbrowser.open(url)

                while server.code is None and server.error is None:
                    server.handle_request()

                if server.code:
                    self.retrieve_token(server.code)
                elif server.error:
                    logger.error(f"Auth server error: {server.error}")
                    # raise Exception(server.error) # Don't crash, just log due to thread
        finally:
            self._auth_lock.release()

    # ... (skipping unchanged code until start_server) ...

    def start_server(self):
        """Create and return a raw socket server wrapper."""
        
        class RawSpotifyServer:
            def __init__(self, port, redirect_uri):
                self.port = port
                self.code = None
                self.error = None
                self.socket = None
                
                try:
                    self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    self.socket.bind(('127.0.0.1', port))
                    self.socket.listen(1)
                    self.socket.settimeout(1)
                except OSError as e:
                    self.error = f"Port {port} is busy or unavailable ({e})"
                    if self.socket:
                        self.socket.close()

            def handle_request(self):
                if self.error: return
                try:
                    conn, addr = self.socket.accept()
                    with conn:
                        conn.settimeout(5.0)
                        request_data = b""
                        try:
                            while True:
                                chunk = conn.recv(1024)
                                request_data += chunk
                                if len(chunk) < 1024 or b"\r\n\r\n" in request_data:
                                    break
                        except TimeoutError:
                            pass
                            
                        request_str = request_data.decode('utf-8', errors='ignore')
                        first_line = request_str.split('\r\n')[0]
                        
                        response_body = "<html><body><h1>Authentication Successful!</h1><p>You can close this window now. (v7 - RAW SOCKET)</p><script>window.close()</script></body></html>"
                        response = (
                            "HTTP/1.1 200 OK\r\n"
                            "Content-Type: text/html\r\n"
                            "Connection: close\r\n"
                            f"Content-Length: {len(response_body)}\r\n"
                            "\r\n"
                            f"{response_body}"
                        )
                        conn.sendall(response.encode('utf-8'))

                        if "GET" in first_line and "/callback" in first_line:
                            try:
                                path = first_line.split(" ")[1]
                                query = parse_qs(urlparse(path).query)
                                if 'code' in query:
                                    self.code = query['code'][0]
                                elif 'error' in query:
                                    self.error = query['error'][0]
                            except Exception as e:
                                logger.error(f"Failed to parse raw request: {e}")
                                self.error = "Parse error"
                            
                except TimeoutError:
                    pass
                except Exception as e:
                    pass
                    
        return RawSpotifyServer(self.port, self.redirect_uri)