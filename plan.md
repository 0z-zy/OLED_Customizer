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
