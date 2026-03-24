r"""
Discord IPC Client — Reads mic mute/deaf state with full OAuth support.
"""
import json
import struct
import uuid
import logging
import time
import msvcrt
import win32pipe
import win32file
import pywintypes
import requests

logger = logging.getLogger("OLED Customizer.DiscordRPC")

# Default Application ID
DEFAULT_CLIENT_ID = "1485778090104721550"

class DiscordIPC:
    """IPC connection to Discord with OAuth AUTHORIZE/AUTHENTICATE support."""

    OP_HANDSHAKE = 0
    OP_FRAME = 1
    OP_CLOSE = 2

    def __init__(self, client_id=None, preferences=None, extension_receiver=None):
        self.client_id = str(client_id or DEFAULT_CLIENT_ID).strip()
        self.prefs = preferences
        self.extension_receiver = extension_receiver
        self._pipe = None
        self._connected = False
        self._authenticated = False
        self._last_voice_state = {"mute": False, "deaf": False}

    @property
    def is_connected(self):
        return self._connected and self._pipe is not None

    def set_client_id(self, client_id):
        new_id = str(client_id or DEFAULT_CLIENT_ID).strip()
        if new_id != self.client_id:
            logger.info(f"Discord Client ID changed to {new_id} — reconnecting")
            self.client_id = new_id
            self.close()

    def connect(self):
        if self.is_connected:
            return True

        for i in range(10):
            pipe_path = rf"\\.\pipe\discord-ipc-{i}"
            try:
                # Use binary mode, no buffering
                self._pipe = open(pipe_path, "w+b", buffering=0)
                logger.info(f"Connected to {pipe_path}")

                if self._handshake():
                    self._connected = True
                    # Try to authenticate immediately if we have a token
                    self._try_authenticate()
                    return True
                else:
                    self.close()
            except (FileNotFoundError, OSError):
                continue
            except Exception as e:
                logger.debug(f"Error connecting to {pipe_path}: {e}")
                self.close()
                continue
        return False

    def _handshake(self):
        try:
            self._send(self.OP_HANDSHAKE, {"v": 1, "client_id": self.client_id})
            resp = self._recv(timeout=2.0)
            if resp and resp.get("evt") == "READY":
                logger.info(f"Discord Handshake OK - user: {resp['data']['user']['username']}")
                return True
            return False
        except Exception as e:
            logger.debug(f"Handshake failed: {e}")
            return False

    def _try_authenticate(self):
        """Perform AUTHORIZE/AUTHENTICATE flow to get voice access."""
        if not self.prefs:
            return

        token = self.prefs.get_preference("discord_access_token")
        
        # 1) If we have a token, try to AUTHENTICATE
        if token:
            if self._authenticate(token):
                self._authenticated = True
                self._subscribe()
                return True
            else:
                logger.warning("Discord token invalid/expired, clearing...")
                self.prefs.preferences["discord_access_token"] = ""
                self.prefs.save_preferences()
                token = None

        # 2) If no token, check if ExtensionReceiver captured a 'code'
        if not token and self.extension_receiver:
            code = self.extension_receiver.get_discord_code()
            if code:
                logger.info("Found captured Discord Auth Code, exchanging for token...")
                new_token = self._exchange_code(code)
                if new_token:
                    self.prefs.preferences["discord_access_token"] = new_token
                    self.prefs.save_preferences()
                    if self._authenticate(new_token):
                        self._authenticated = True
                        self._subscribe()
                        return True
        return False

    def _exchange_code(self, code):
        """Exchange OAuth code for access_token via Discord API."""
        secret = self.prefs.get_preference("discord_client_secret")
        if not secret:
            logger.error("Discord Client Secret missing — cannot exchange code")
            return None

        port = self.prefs.get_preference("discord_local_port") or 8888
        redirect_uri = f"http://127.0.0.1:{port}"

        try:
            resp = requests.post("https://discord.com/api/oauth2/token", data={
                "client_id": self.client_id,
                "client_secret": secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri
            }, timeout=10)
            
            data = resp.json()
            if "access_token" in data:
                return data["access_token"]
            else:
                logger.error(f"Discord Token Exchange failed: {data}")
                return None
        except Exception as e:
            logger.error(f"Discord Token Exchange error: {e}")
            return None

    def _authenticate(self, token):
        """Send AUTHENTICATE command with the token."""
        try:
            self._send(self.OP_FRAME, {
                "cmd": "AUTHENTICATE",
                "args": {"access_token": token},
                "nonce": str(uuid.uuid4())
            })
            resp = self._recv(timeout=3.0)
            if resp and resp.get("cmd") == "AUTHENTICATE" and not resp.get("evt") == "ERROR":
                logger.info("Discord Authentication SUCCESS")
                return True
            logger.warning(f"Discord Authentication FAILED: {resp}")
            return False
        except Exception:
            return False

    def _subscribe(self):
        """Subscribe to voice settings updates."""
        try:
            self._send(self.OP_FRAME, {
                "cmd": "SUBSCRIBE",
                "evt": "VOICE_SETTINGS_UPDATE",
                "nonce": str(uuid.uuid4())
            })
            # Response is usually just confirmation, we don't need to wait for it here
        except Exception:
            pass

    def _send(self, opcode, payload):
        data = json.dumps(payload).encode("utf-8")
        header = struct.pack("<II", opcode, len(data))
        self._pipe.write(header + data)
        self._pipe.flush()

    def _recv(self, timeout=0.1):
        """Non-blocking read from the IPC pipe."""
        if not self._pipe:
            return None
        
        handle = msvcrt.get_osfhandle(self._pipe.fileno())
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                _, avail, _ = win32pipe.PeekNamedPipe(handle, 0)
                if avail >= 8:
                    header = self._pipe.read(8)
                    op, length = struct.unpack("<II", header)
                    if length > 0:
                        # Wait for full payload if header was found
                        body = b""
                        while len(body) < length:
                            body += self._pipe.read(length - len(body))
                        return json.loads(body.decode("utf-8"))
                    return {}
            except Exception:
                break
            time.sleep(0.01)
        return None

    def get_voice_settings(self):
        """Check for events or poll if authenticated."""
        if not self.is_connected:
            return None

        # 1) If not authenticated yet, try to do it (handles captured codes)
        if not self._authenticated:
            self._try_authenticate()

        # 2) Drain any pending events/responses
        while True:
            resp = self._recv(timeout=0.01)
            if not resp:
                break
            
            if resp.get("evt") == "VOICE_SETTINGS_UPDATE":
                data = resp.get("data", {})
                self._last_voice_state = {
                    "mute": bool(data.get("mute", False)),
                    "deaf": bool(data.get("deaf", False))
                }
            elif resp.get("cmd") == "GET_VOICE_SETTINGS":
                data = resp.get("data", {})
                self._last_voice_state = {
                    "mute": bool(data.get("mute", False)),
                    "deaf": bool(data.get("deaf", False))
                }

        # 3) If authenticated, explicitly poll once in a while to be sure
        # (Though VOICE_SETTINGS_UPDATE handles it mostly)
        if self._authenticated:
            try:
                self._send(self.OP_FRAME, {
                    "cmd": "GET_VOICE_SETTINGS",
                    "args": {},
                    "nonce": str(uuid.uuid4())
                })
            except Exception:
                self.close()
                return None

        return self._last_voice_state

    def close(self):
        self._connected = False
        self._authenticated = False
        if self._pipe:
            try: self._pipe.close()
            except: pass
            self._pipe = None
            logger.info("Discord IPC connection closed")
