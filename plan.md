# OLED Customizer - Plan Log

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
