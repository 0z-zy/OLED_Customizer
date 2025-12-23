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

    def _check_configuration(self):
        if not all([self.client_id, self.client_secret, self.redirect_uri, self.port]):
            logger.error(f"Configuration not completed for Spotify API, check configuration file : {self.config.config_path}")
            return False
        return True

    def reload_config(self):
        """Called when settings are saved to reload credentials without restart."""
        old_id = self.client_id
        old_secret = self.client_secret
        old_redirect = self.redirect_uri
        old_port = self.port

        self.client_id = str(self.config.get_preference('spotify_client_id')).strip()
        self.client_secret = str(self.config.get_preference('spotify_client_secret')).strip()
        self.redirect_uri = str(self.config.get_preference('spotify_redirect_uri')).strip()
        self.port = int(self.config.get_preference('local_port'))
        
        self.ready = self._check_configuration()
        
        changed = (old_id != self.client_id) or \
                  (old_secret != self.client_secret) or \
                  (old_redirect != self.redirect_uri) or \
                  (old_port != self.port)

        if changed:
            logger.info("Spotify credentials reloaded from config (CHANGED).")
            # Invalidate old token file because it likely belongs to the old credentials
            try:
                os.remove(fetch_app_data_path("credentials.json"))
                logger.info("Old credentials.json deleted to force re-auth.")
            except OSError:
                pass
            return True
        else:
            logger.info("Spotify credentials reloaded (NO CHANGE).")
            return False

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

    def load_token(self):
        """Load token from credentials.json. Returns True if valid token exists."""
        try:
            with open(fetch_app_data_path("credentials.json"), "r") as f:
                data = loads(f.read())
                self.token = data.get("token", "")
                self.refresh_token = data.get("refresh_token", "")
                self.expires = data.get("expires", -1)
                
                if not self.token or not self.refresh_token:
                    return False
                
                # Check if expired and refresh if needed
                if time() >= self.expires:
                    logger.info("Token expired, refreshing...")
                    return self.refresh_access_token()
                
                return True
        except FileNotFoundError:
            logger.info("No credentials.json found - will need to authenticate.")
            return False
        except Exception as e:
            logger.error(f"Failed to load token: {e}")
            return False

    def save_token(self):
        """Save current token to credentials.json."""
        try:
            with open(fetch_app_data_path("credentials.json"), "w") as f:
                f.write(dumps({
                    "token": self.token,
                    "refresh_token": self.refresh_token,
                    "expires": self.expires
                }))
            logger.info("Token saved to credentials.json")
        except Exception as e:
            logger.error(f"Failed to save token: {e}")

    def retrieve_token(self, code):
        """Exchange authorization code for access token."""
        try:
            auth_header = b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
            response = self.session.post(
                self.SPOTIFY_API_URL + "/api/token",
                headers={
                    "Authorization": f"Basic {auth_header}",
                    "Content-Type": "application/x-www-form-urlencoded"
                },
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.redirect_uri
                }
            )
            
            if response.status_code != 200:
                logger.error(f"Token exchange failed: {response.status_code} - {response.text}")
                return False
            
            data = response.json()
            self.token = data.get("access_token", "")
            self.refresh_token = data.get("refresh_token", "")
            self.expires = time() + data.get("expires_in", 3600) - 60  # Refresh 1 min early
            
            self.save_token()
            logger.info("Successfully retrieved and saved token!")
            return True
        except Exception as e:
            logger.error(f"Failed to retrieve token: {e}")
            return False

    def refresh_access_token(self):
        """Refresh the access token using the refresh token."""
        try:
            auth_header = b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
            response = self.session.post(
                self.SPOTIFY_API_URL + "/api/token",
                headers={
                    "Authorization": f"Basic {auth_header}",
                    "Content-Type": "application/x-www-form-urlencoded"
                },
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token
                }
            )
            
            if response.status_code != 200:
                logger.error(f"Token refresh failed: {response.status_code} - {response.text}")
                return False
            
            data = response.json()
            self.token = data.get("access_token", "")
            # Refresh token may or may not change
            if "refresh_token" in data:
                self.refresh_token = data["refresh_token"]
            self.expires = time() + data.get("expires_in", 3600) - 60
            
            self.save_token()
            logger.info("Successfully refreshed token!")
            return True
        except Exception as e:
            logger.error(f"Failed to refresh token: {e}")
            return False

    def fetch_song(self):
        """Fetch currently playing song from Spotify."""
        if not self.ready or not self.token:
            return None
        
        # Check if token needs refresh
        if time() >= self.expires:
            if not self.refresh_access_token():
                return None
        
        try:
            response = self.session.get(
                "https://api.spotify.com/v1/me/player/currently-playing",
                headers={"Authorization": f"Bearer {self.token}"}
            )
            
            if response.status_code == 204:
                # No content - nothing playing
                return None
            
            if response.status_code == 401:
                # Token expired, try refresh
                if self.refresh_access_token():
                    return self.fetch_song()
                return None
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            
            if not data or not data.get("item"):
                return None
            
            item = data["item"]
            artists = ", ".join([a["name"] for a in item.get("artists", [])])
            
            return {
                "title": item.get("name", "Unknown"),
                "artist": artists,
                "duration": item.get("duration_ms", 0),
                "progress": data.get("progress_ms", 0),
                "paused": not data.get("is_playing", False)
            }
        except Exception as e:
            logger.error(f"Failed to fetch song: {e}")
            return None


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