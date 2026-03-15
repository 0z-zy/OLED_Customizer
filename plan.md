# OLED Customizer - Plan Log

---

## Plan: Fix Garbage Collection Crash in SteelSeries API

**Date:** 2026-03-08

### Goal

Fix a hard crash (SIGSEGV/Heap Corruption) that occurs during Garbage Collection, specifically when the app is under high load (10 FPS updates + Hardware Monitor + Spotify).

### Problem

- Stack trace (`fault.log`) shows the crash during `Garbage-collecting` while inside `requests.post` -> `email\feedparser.py`.
- `requests` is a high-level library that creates many intermediate objects (Session, Request, Response, CaseInsensitiveDict) for every call.
- At 10 FPS, this creates massive object churn, which can lead to GC corruption or race conditions in underlying C libraries.
- `debug.log` also shows occasional Spotify API timeouts, which add to the pressure.

### Solution

- **SteelSeriesAPI.py**: Replace `requests` with the lean `urllib3` library.
- Use a persistent `urllib3.PoolManager` to reuse connections without the overhead of `requests.Session`.
- Manually encode JSON to avoid `requests`' internal overhead.
- Explicitly close response objects and put a `gc.collect(1)` every 100 frames to keep the heap clean.
- (Drafting) Apply similar optimizations to `SpotifyAPI.py` if stability issues persist.

### Files Changed

- `src/SteelSeriesAPI.py`

---

## Plan: Add Parentheses to Calculator Mode

**Date:** 2026-03-06

### Goal

Add `(` and `)` support to the OLED calculator so users can type grouped expressions like `(2+3)*4`.

### Problem

- Calculator used a simple accumulator + pending-operator system — no expression tree, no parentheses possible.
- Keyboard layout varied: on TR QWERTY, `(` is Shift+8 and `)` is Shift+9. On EN, they're Shift+9 and Shift+0. Hardcoding VK codes would break other layouts.

### Solution

#### Calculator.py

- Replaced accumulator/pending-op with a **full expression string** (e.g. `"(5+3)*2"`).
- Added a **safe recursive-descent math evaluator** (no `eval()`, no `ast`) that handles `+`, `-`, `*`, `/`, `(`, `)` and floats.
- New `_append_paren("(")` / `_append_paren(")")` method with guard logic (no unmatched closing paren, auto-closes on `=`, auto-inserts `*` between digit and `(`).
- `_backspace()` now pops the last token from the expression string.
- Display now shows the expression being built on the top line while typing.

#### DisplayManager.py

- Added `_shift_held` to track VK_LSHIFT / VK_RSHIFT in the keyboard hook.
- Set up Windows `ToUnicode` API in the hook.
- After Escape/Enter/Backspace/Delete checks, calls `_vk_to_char(vk, scan)` which uses `ToUnicode` with injected Shift state to translate the VK code → actual character.
- If the character is `(` or `)`, enqueues `calc_input:(` / `calc_input:)` and **suppresses** the key (game won't see it).
- Layout-agnostic: works on TR, EN, DE, FR, any keyboard layout automatically.

### Files Changed

- `src/Calculator.py`
- `src/DisplayManager.py`

---

## Proposed Optimizations (2026-03-15)

Full project review. Items below are proposals — pick the ones you want done.

### 🔴 High Priority

- [ ] **DisplayManager.py — Add graceful shutdown**
  No `shutdown()` method exists. Six daemon threads are spawned (Hotkey-Actions, Keyboard-Hook, SMTC-poller, Spotify-Worker, plus two dynamic auth threads) with no `_running` flag or cleanup. Queues (`_hotkey_action_queue`, `_spotify_queue`) are never drained on exit. Add a `_running` flag, a `shutdown()` method that sets it to `False`, drains queues, and lets threads exit their loops cleanly.

- [ ] **SpotifyAPI.py — Add timeout to auth loop (line 114)**
  `while server.code is None and server.error is None: server.handle_request()` loops forever if the user never completes browser auth. Add a time-based or iteration-based limit (e.g. 120 seconds) so the app doesn't hang permanently.

- [ ] **UltimateManager.py — Remove dead code**
  This 178-line file is not imported or referenced anywhere in the project. It's an orphaned standalone script with hardcoded paths and Turkish comments. Safe to delete.

### 🟠 Medium Priority

- [ ] **SpotifyAPI.py — Cache base64 auth header (lines 167, 203)**
  The same `b64encode(f"{client_id}:{client_secret}".encode())` is computed identically in both `retrieve_token()` and `refresh_access_token()`. Compute once in `__init__` and reuse.

- [ ] **ExtensionReceiver.py — Fix Content-Length crash (line 30)**
  `int(self.headers['Content-Length'])` raises `KeyError` if the header is missing. Use `self.headers.get('Content-Length', '0')` and add a max-size check to prevent huge payloads.

- [ ] **ExtensionReceiver.py — Add server shutdown method**
  `serve_forever()` runs with no way to stop it. Expose a `stop()` that calls `server.shutdown()` so it can be cleaned up with DisplayManager.

- [ ] **volume.py — Extract shared mic-init helper (lines 37-55, 250-259)**
  Microphone initialisation code (pycaw `GetMicrophone` → `Activate` → `IAudioEndpointVolume`) is duplicated between `__init__` and the re-init path in `update()`. Extract to a `_init_microphone()` method.

- [ ] **fps_monitor.py — Log errors in worker loop (lines 107-108)**
  `except Exception: pass` silently swallows all DLL call errors. Replace with `except Exception as e: logger.debug("FPS worker error: %s", e)` so problems are diagnosable.

- [ ] **Systray.py — Close icon image resource (line 497)**
  `Image.open(icon_path)` is never closed. Since pystray keeps a reference to the image, the simplest fix is to keep it open but note it, or copy the image data and close the file handle.

- [ ] **WindowsMedia.py — Add logging to silent except blocks (lines 85-100)**
  Multiple `except Exception: pass` blocks hide failures in SMTC media info retrieval. Add `logger.debug()` calls so problems can be traced.

### 🟡 Low Priority

- [ ] **Timer.py — Deduplicate font path resolution (lines 35-38)**
  `fetch_content_path('fonts/DS-DIGIB.ttf')` is called four times for the same file. Resolve path once, then pass it to `safe_load_font()` four times with different sizes.

- [ ] **UserPreferences.py — Use deep copy for DEFAULT (line 50)**
  `self.DEFAULT.copy()` is a shallow copy. Currently safe because DEFAULT has no nested dicts, but `copy.deepcopy()` or `json.loads(json.dumps(...))` would be future-proof.

- [ ] **SpotifyAPI.py — Close socket in error paths (line 299)**
  The `socket.socket()` in the OAuth callback server isn't always closed in error branches. Wrap in a context manager.

- [ ] **text_rendering.py — Check for dead code**
  `truncate_text()` appears unused. Verify whether it's called anywhere; if not, remove it.

- [ ] **updater.py — Harden version parsing (line 36)**
  `.split('"')[1]` assumes exact format. Use regex: `re.search(r'__version__\s*=\s*"([^"]+)"', content).group(1)` for robustness.

### ✅ Already Done

- [x] **Systray.py — Auto-create config file in `open_config()`**
  Previously just logged a warning if `config.json` didn't exist. Now calls `save_preferences()` to create it with defaults before opening.

- [x] **UserPreferences.py — Fix mutable DEFAULT reference**
  Changed `self.preferences = self.DEFAULT` to `.copy()` to prevent mutations from leaking into the class-level dict.

- [x] **SteelSeriesAPI.py — Replace requests with urllib3**
  Eliminated GC crash from high object churn by switching to lean `urllib3.PoolManager`.

### Notes

- **SteelSeriesAPI.py**, **HardwareMonitor.py**, and **Calculator.py** are already well-optimised and need no changes.
- No test infrastructure exists in the project; adding tests would be a separate effort.
