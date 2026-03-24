# OLED Customizer - Plan Log

---

## Plan: Fix Rapid Mute Toggle Not Registering on Discord

**Date:** 2026-03-25 02:39

### Problem

Three debounce/lockout timers combine to block rapid headphone mute button presses from reaching Discord:

1. **600ms Flutter Debounce** (`HIDListener.py:512`) — Ignores hardware reports within 600ms
2. **1200ms Echo Debounce** (`HIDListener.py:517`) — Ignores hardware reports after a host write
3. **1500ms Sync Lockout** (`DisplayManager.py:1299`) — Blocks hardware events after a Discord push

**Result:** Quick mute→unmute (or back-to-back presses) within 1.5s are silently dropped.

### Solution

Reduce all timers to responsive values while still preventing echo/firmware loops:

| Timer | File | Old | New |
|-------|------|-----|-----|
| Flutter debounce | HIDListener.py | 600ms | 150ms |
| Echo debounce | HIDListener.py | 1200ms | 400ms |
| HW→Discord lockout | DisplayManager.py | 1500ms | 600ms |
| Discord→HW lockout | DisplayManager.py | 1200ms | 600ms |
| Initial align lockout | DisplayManager.py | 1200ms | 600ms |

### Files Changed

- `src/HIDListener.py` — Reduced flutter and echo debounce timers
- `src/DisplayManager.py` — Reduced sync lockout timers

---

## Plan: Brainstorm Discord -> Headset Not Applying

**Date:** 2026-03-24 22:35

### Current Observations (From Logs)

1. HID discovery now works and consistently selects `Col05` with read+write open checks passing.
2. Discord state changes are detected (`Discord State Event: ...`).
3. Discord -> headset writes are attempted and reported as success (`HID Sync: Success (3/3 writes)`).
4. Headset button -> app -> Discord path works reliably.
5. Discord -> headset still appears ineffective on physical headset state/LED.

### Most Likely Causes (Ranked)

1. **Wrong output collection endpoint**
   - `Col05` is valid for input reports (button events), but firmware might require output on `Col03`/`Col04` for host mute commands.
   - Write success from `WriteFile` only confirms transport success, not firmware action.

2. **Payload is accepted by HID stack but ignored by firmware**
   - One or more bytes in report `0d 02 03 00 03 xx` may be version-specific.
   - The known byte-5 meaning may differ between firmware revisions.

3. **Wrong report type/API for this device revision**
   - Device may require `HidD_SetFeature` or `HidD_SetOutputReport` instead of plain `WriteFile`.
   - Some HID devices silently ignore unsupported report channels.

4. **Write-handle strategy mismatch**
   - Opening a short-lived write handle while a separate read handle is active might not be accepted by firmware state machine.
   - Device may require a persistent shared handle or strict serialization.

5. **Discord effective state mapping edge cases**
   - `mute/deaf` transitions can produce rapid true/false flips; headset command may be overwritten by next poll cycle.
   - App may need per-source debounce and command deduping.

6. **Timing/protocol pacing issue**
   - Triple pulse at 20 ms may be too fast or too short for this firmware.
   - Some devices require 50-150 ms spacing or a single clean write.

### Diagnostic Experiments

1. **Endpoint sweep**
   - Send the exact same mute/unmute payload to all discovered `Col01..Col06`.
   - Record which endpoint actually changes headset LED/state.

2. **Report variation sweep**
   - Keep `0d 02 03 00 03` fixed and test candidate values around byte-5 and adjacent control bytes.
   - Correlate with physical headset response.

3. **API sweep**
   - Test `WriteFile` vs `HidD_SetFeature` vs `HidD_SetOutputReport` on the same endpoint/payload.
   - Keep all other variables fixed.

4. **Handle model test**
   - Compare short-lived write handle vs persistent write handle vs single bidirectional handle.
   - Check if one model yields consistent Discord -> headset action.

5. **Ack-based validation**
   - After each write, wait up to 500 ms for a matching incoming HID report.
   - If no confirm report arrives, treat command as unconfirmed and retry with alternate path.

6. **Discord event trace hardening**
   - Log raw `mute`, raw `deaf`, computed effective state, command sent, and post-send observed headset state.
   - Verify no immediate loop cycle reverses the intended command.

### Proposed Next Debug Build Scope

1. Add a temporary "HID Diagnostics" mode that can manually trigger mute/unmute and endpoint selection.
2. Add endpoint and API fallback chain for Discord-originated writes.
3. Mark write result as `transport_ok` vs `state_confirmed` (separate metrics in logs).
4. Keep current working path (headset -> Discord) unchanged while experimenting.

### Exit Criteria

1. Discord mute/unmute consistently changes headset state within 1 second.
2. Headset button still syncs to Discord with no regressions.
3. No mute oscillation/override loops in logs for a 5-minute stress test.

---

## Plan: Fix Bi-Directional Mute Sync (Discord & Headset)

**Date:** 2026-03-24 06:10

### Problem

1. **Discord -> Headset**: When muting in Discord, the Keyboard OLED updates correctly, but the physical Headset LED does not mute.
2. **Headset -> Discord**: Pressing the physical mute button on the headset mutes system microphones but fails to update Discord. Additionally, the Keyboard OLED shows the wrong status (Unmuted) because it prioritizes Discord's state.

### Solution

1. **DiscordRPC.py — Write Support**: Add `set_mute(muted)` to send `SET_VOICE_SETTINGS` commands to Discord's IPC.
2. **DisplayManager.py — Bi-directional Sync Loop**: 
   - Check if the hardware state (from `HIDListener`) has changed compared to Discord.
   - If changed, push the new state to Discord using `DiscordIPC.set_mute`.
   - Ensure the headset LED is always in sync with the current source of truth.
3. **volume.py — State Consistency**: Ensure `_last_mic_mute` reflects the actual system state even when Discord is connected.

### Files Changed

- `src/DiscordRPC.py` — Added `set_mute()` method.
- `src/DisplayManager.py` — Updated `_discord_rpc_loop` to handle hardware-to-discord sync.
- `src/volume.py` — Refined state priority for better consistency.

---



---

## Plan: Discord Mic Mute Detection (Replace System Mic Muting)

**Date:** 2026-03-24 02:09

### Problem
Pressing the mute hotkey muted ALL system microphones ("nuclear option"). This is not ideal — it mutes your mic in every app, not just Discord.

### Solution
Instead of muting system mics, **read Discord's actual mute/deaf state** via its local IPC pipe (`\\.\pipe\discord-ipc-0`). The OLED passively shows whether Discord says you're muted. No bot, no OAuth needed — just a Discord Application ID.

### How It Works
1. New `src/DiscordRPC.py` connects to Discord's named pipe IPC
2. Sends `GET_VOICE_SETTINGS` every ~2 seconds
3. Reads `mute` and `deaf` booleans from the response
4. `volume.py` shows Discord mute state on OLED (priority over system mic state)
5. Falls back to system mic detection when Discord isn't running

### Files Changed
- `src/DiscordRPC.py` (NEW) — Discord IPC pipe client
- `src/volume.py` — Discord mute state priority, `set_discord_mute()`, hotkey skips system toggle when Discord connected
- `src/DisplayManager.py` — Discord RPC thread, cleanup on shutdown

---

## Plan: Fix OLED Display Disappearing (Auto-Recovery)

**Date:** 2026-03-16 06:08

### Problem
The OLED screen goes blank after a while — no crash, no error in debug.log. Root cause: SteelSeries GG deregisters the game after 60s without events. When API errors pile up (GG restart, port change, sleep/wake), the app backs off but never re-registers. All frame errors were silently swallowed (`except: pass`).

### Solution
1. **SteelSeriesAPI.py — Auto-recovery**: After 10 consecutive errors, automatically call `reset()` to re-read the port and re-register the game.
2. **SteelSeriesAPI.py — Escalating backoff**: 2s → 5s → 10s instead of flat 2s.
3. **SteelSeriesAPI.py — Log transport errors**: Transport errors logged at DEBUG level (were fully silent before).
4. **DisplayManager.py — Frame failure logging & recovery**: Frame send errors now logged. If frames fail for 30s+, forces a full `steelseries_api.reset()`.

### Files Changed
- `src/SteelSeriesAPI.py`
- `src/DisplayManager.py`

---

## Plan: Fix "Access Violation" Crash & Harden Stability

**Date:** 2026-03-15 23:30

### Problem
The application crashed with a `Windows fatal exception: access violation` after running for about 50 minutes. This is a "hard crash" usually caused by memory corruption. Analysis of the logs and code points to three potential culprits:
1. **Thread-safety:** `SpotifyPlayer` and other state objects are accessed from both the main thread and the new Spotify worker thread without a lock.
2. **COM Leaks:** `VolumeOverlay` might be leaking COM interfaces when re-initializing the microphone.
3. **Memory Pressure:** High-frequency HTTP calls to SteelSeries GG combined with COM/WinRT/pythonnet can lead to heap fragmentation or GC issues.

### Solution
1. **Thread-safety:** Add a threading lock to `DisplayManager` to protect shared state (`self.player`, etc.).
2. **Fix COM Leaks:** Ensure COM interfaces are explicitly released when `VolumeOverlay` re-initializes or fails.
3. **Harden SteelSeriesAPI:** Optimize header creation and error handling to reduce object churn.
4. **Maintenance:** Add a manual `gc.collect()` every 30 seconds to keep the memory clean and stable.

---

## Plan: Fix Missing WinRT Collections & Storage (Root Cause Found)

**Date:** 2026-03-15 20:45

### Problem
The `ModuleNotFoundError` for `winrt.windows.foundation.collections` was happening even in the development environment because those specific sub-packages (Collections and Storage) were never installed. They are "lazy-loaded" by Windows Media components, which is why we didn't catch them until now.

### Solution
1. **Installed Missing Packages:** I ran `pip install winrt-Windows.Foundation.Collections winrt-Windows.Storage`.
2. **Verified Dev:** A diagnostic script now successfully retrieves media sessions without errors.
3. **Spec Update:** Update `OLED-Customizer.spec` to explicitly `collect_all` on these new namespaces.

---


---

## Plan: Fix Missing WinRT Modules & Deadlock on Exit

**Date:** 2026-03-15 20:25

### Problem 1: WinRT Module Still Missing
PyInstaller's `hiddenimports` failed to bundle the underlying compiled C extensions for `winrt` (e.g. `_winrt_windows_foundation.cp313-win_amd64.pyd`).
### Solution 1
Modify `OLED-Customizer.spec` to explicitly add `_winrt_windows_foundation` and `_winrt_windows_media_control` as hidden imports.

### Problem 2: Deadlock on Exit
The previous `WM_QUIT` fix causes a deadlock because a Windows thread created without a window often ignores message queue posts. This prevents `GetMessageW` from ever returning, causing `Systray.py`'s `icon.manager.shutdown()` to block indefinitely.
### Solution 2
- **`DisplayManager.py`**: Save the hook handles (`self._k_hook`, `self._m_hook`). In `shutdown()`, explicitly call `UnhookWindowsHookEx` on both from the main thread before setting `_running = False`.
- **`Systray.py`**: Revert to calling `os._exit(0)` immediately *after* `icon.manager.shutdown()` cleans up the hooks.

---


---

## Plan: Fix Windows Input Freeze on App Exit

**Date:** 2026-03-15 20:20

### Problem
When the user clicks "Exit", their entire computer mouse/keyboard input freezes for 2-3 seconds. This happens because the new "Check for Bugs and Optimize" Copilot branch introduced a low-level Global Windows Hook (`WH_KEYBOARD_LL` and `WH_MOUSE_LL`) to fix the Hotkey issues in games.
However, `Systray.py` calls `os._exit(0)` to instantly terminate the app. This sudden death prevents Windows from cleanly unregistering the hooks. Windows freezes input momentarily while waiting for those dead hooks to respond before forcefully dropping them.

### Solution
- **`Systray.py`**: Call `icon.manager.shutdown()` before exiting.
- **`DisplayManager.py`**: Save the Thread ID of the hook loop, and during `shutdown()`, send a `WM_QUIT` signal via `PostThreadMessageW` so the `GetMessageW` loop breaks safely and executes `UnhookWindowsHookEx`.
- Rebuild the executable.

---


## Plan: Fix Missing WinRT Collection Module in EXE

**Date:** 2026-03-15 20:16

### Problem

After building the optimized executable with the new Logs tab, the `WindowsMedia.py` module started throwing `Session validation failed: No module named 'winrt.windows.foundation.collections'`. PyInstaller failed to package this specific WinRT submodule because it is likely imported dynamically by another WinRT component.

### Solution

- Edit `OLED-Customizer.spec`.
- Add `'winrt.windows.foundation.collections'` to the explicit `hiddenimports` list.
- Rebuild the executable.

---
## Plan: Add Logs Window to Settings

**Date:** 2026-03-15 20:10

### Goal

Add a new "Logs" tab to the Settings window to allow users to view `debug.log` directly from the app interface.

### Steps

1.  **UI Updates**: Modify `SettingsWindow.py` to add "Logs" to the sidebar.
2.  **Display Widget**: Add a `tk.Text` widget with a scrollbar on the new Logs page.
3.  **Data Loading**: Implement a function to read the last 200 lines of `%APPDATA%/OLED Customizer/debug.log`.
4.  **Utilities**: Add "Refresh" and "Open Folder" buttons.

### Verification

- Ensure the Logs tab renders correctly.
- Test that logs actually load and scrolling works.
- Confirm "Open Folder" correctly opens the AppData directory.

---

### Old Plans

---

### [ARCHIVE] Plan: Review and Merge Copilot "Check for Bugs and Optimize"

**Date:** 2026-03-15 19:35

#### Goal Case 3

Review the work done by Copilot in the `copilot/check-for-bugs-and-optimize` branch and merge it into `main` if it looks good.

#### Changes Summary Case 3

- **Optimizations**: `DisplayManager`, `SpotifyAPI`, and `ExtensionReceiver` have been refactored for better performance and resource handling.
- **Bug Fixes**: Handled potential crashes in `ExtensionReceiver` and refined microphone detection in `volume.py`.
- **Cleanup**: Deleted `src/UltimateManager.py` (Copilot claims it is dead code).
- **Hardening**: Improved version parsing and configuration handling.

#### Steps Case 3

1. **Explain**: Provide a simple "Vibe Coder" guide to Branches and PRs.
2. **Review**: Show how to use VS Code's "Source Control" tab to compare branches.
3. **Merge**: Guide the user through the merge process if they approve.

---

### [ARCHIVE] Plan: Fix Garbage Collection Crash in SteelSeries API

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

- [x] **DisplayManager.py — Add graceful shutdown**
  Added `_running` flag (checked by all thread loops: `run()`, `_hotkey_action_worker`, `_spotify_worker_loop`, `_poll_smtc_loop`). Added `shutdown()` method that sets `_running = False`, drains queues, and stops the ExtensionReceiver server.

- [x] **SpotifyAPI.py — Add timeout to auth loop (line 114)**
  Added a 120-second `deadline` to the `while server.code is None` loop. Breaks with `"Auth timeout"` error if user never completes browser auth.

- [x] **UltimateManager.py — Remove dead code**
  Deleted. 178-line orphaned standalone script with hardcoded paths, not imported anywhere.

### 🟠 Medium Priority

- [x] **SpotifyAPI.py — Cache base64 auth header (lines 167, 203)**
  Computed once in `__init__` as `self._basic_auth`. Both `retrieve_token()` and `refresh_access_token()` now use the cached value. Also refreshed in `reload_config()` when credentials change.

- [x] **ExtensionReceiver.py — Fix Content-Length crash (line 30)**
  Changed to `self.headers.get('Content-Length', '0')` with `ValueError` handling and a 1 MB `MAX_BODY_SIZE` limit. Returns 413 for oversized payloads, 400 for invalid headers.

- [x] **ExtensionReceiver.py — Add server shutdown method**
  Added `stop()` method that calls `self.server.shutdown()`. Called from `DisplayManager.shutdown()`.

- [x] **volume.py — Extract shared mic-init helper (lines 37-55, 250-259)**
  Extracted `_init_microphone()` method. Called from `__init__` and from the re-init path in `update()` (replacing the duplicated code block).

- [x] **fps_monitor.py — Log errors in worker loop (lines 107-108)**
  Replaced `except Exception: pass` with `except Exception as e: logger.debug("FPS worker error: %s", e)`.

- [x] **Systray.py — Close icon image resource (line 497)**
  Changed to `with Image.open(...) as img: icon_image = img.copy()` so the file handle is properly released.

- [x] **WindowsMedia.py — Add logging to silent except blocks (lines 85-100)**
  Added `logger.debug()` calls to the timeline check, staleness check, and session validation `except` blocks.

### 🟡 Low Priority

- [x] **Timer.py — Deduplicate font path resolution (lines 35-38)**
  Resolved `fetch_content_path('fonts/DS-DIGIB.ttf')` once into `digi_path`, then passed it to `safe_load_font()` four times.

- [x] **UserPreferences.py — Use deep copy for DEFAULT (line 50)**
  Changed from `self.DEFAULT.copy()` to `copy.deepcopy(self.DEFAULT)` for future-proof safety.

- [x] **SpotifyAPI.py — Close socket in error paths (line 299)**
  Added `close()` method to `RawSpotifyServer`. Called from `fetch_token()` after the auth loop completes (success or timeout).

- [x] **text_rendering.py — Check for dead code**
  Confirmed `truncate_text()` is not called anywhere in the project. Removed.

- [x] **updater.py — Harden version parsing (line 36)**
  Replaced `.split('"')[1]` with `re.search(r'__version__\s*=\s*"([^"]+)"', line)` for robust parsing.

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
