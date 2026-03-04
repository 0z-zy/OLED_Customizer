"""
OLED Calculator - Win11-style calculator for the 128x40 OLED screen.

Activated via Ctrl+Insert (customizable). Input comes from numpad only.
Display: expression history on top, current number on bottom (right-aligned).
"""

from PIL import ImageFont, ImageDraw, Image
import logging

from src.image_utils import fetch_content_path

logger = logging.getLogger("OLED Customizer.Calculator")


class Calculator:
    """
    Win11-style calculator rendered on the 128x40 OLED display.

    Display layout:
      Top row:    expression history, right-aligned, small font
      Divider:    thin line
      Bottom row: current number / result, right-aligned, big font

    Behavior matches Win11 calculator:
      - Operator chaining: 5 + 3 + 2 = evaluates left-to-right
      - Repeated =: pressing = again repeats the last operation
      - After =, digit starts fresh; operator continues from result
    """

    def __init__(self, config):
        self.config = config

        # --- State ---
        self._current = "0"           # Number being displayed / entered
        self._history = ""            # Expression history on top line
        self._accumulator = None      # Running result
        self._pending_op = None       # Operator waiting to be applied
        self._just_evaluated = False  # True right after pressing =
        self._new_entry = True        # Next digit replaces current display
        self._error = None            # Error string ("DIV/0!", "ERROR")

        # For Win11-style repeated = (pressing = again repeats last op)
        self._last_op = None
        self._last_operand = None

        # --- Fonts (MunroSmall = pixel font with better symbol support) ---
        self._font_history = self._safe_font(fetch_content_path("fonts/MunroSmall.ttf"), 10)
        self._font_number = self._safe_font(fetch_content_path("fonts/MunroSmall.ttf"), 20)
        self._font_label = self._safe_font(fetch_content_path("fonts/MunroSmall.ttf"), 10)

    @staticmethod
    def _safe_font(path, size):
        try:
            return ImageFont.truetype(font=path, size=size)
        except Exception:
            try:
                return ImageFont.load_default()
            except Exception:
                return None

    # ==================================================================
    # PUBLIC INPUT
    # ==================================================================

    def key_input(self, key_str):
        """
        Feed a key press. Accepted values:
        '0'-'9', '+', '-', '*', '/', '.', 'enter', 'backspace', 'delete'
        """
        key = str(key_str).strip().lower()

        if key in "0123456789":
            self._append_digit(key)
        elif key in ("+", "-", "*", "/"):
            self._apply_operator(key)
        elif key in (".", ",", "decimal"):
            self._append_dot()
        elif key in ("enter", "return", "="):
            self._evaluate()
        elif key == "backspace":
            self._backspace()
        elif key in ("delete", "c", "escape"):
            self.clear()

    def clear(self):
        """Clear everything (C)."""
        self._current = "0"
        self._history = ""
        self._accumulator = None
        self._pending_op = None
        self._just_evaluated = False
        self._new_entry = True
        self._error = None
        self._last_op = None
        self._last_operand = None

    # ==================================================================
    # INTERNAL LOGIC (Win11 behavior)
    # ==================================================================

    def _append_digit(self, d):
        if self._error:
            self.clear()

        if self._just_evaluated:
            # After =, typing a digit starts a brand new calculation
            self.clear()

        if self._new_entry:
            self._current = d
            self._new_entry = False
        else:
            if self._current == "0":
                self._current = d          # Replace lone zero
            elif len(self._current) < 16:
                self._current += d

    def _append_dot(self):
        if self._error:
            self.clear()

        if self._just_evaluated:
            self.clear()

        if self._new_entry:
            self._current = "0"
            self._new_entry = False

        if "." not in self._current:
            self._current += "."

    def _apply_operator(self, op):
        if self._error:
            return

        if self._just_evaluated:
            # Continue from result (e.g., "= 8" then press "+")
            self._history = self._fmt(self._accumulator) + f" {op}"
            self._pending_op = op
            self._just_evaluated = False
            self._new_entry = True
            return

        if self._pending_op and not self._new_entry:
            # Chain: evaluate pending first (e.g., "5 + 3" then press "*")
            self._do_pending()
            if self._error:
                return
        elif self._pending_op and self._new_entry:
            # Replace operator: "5 +" press "-" → "5 -"
            self._history = self._fmt(self._accumulator) + f" {op}"
            self._pending_op = op
            return
        else:
            # First operator in expression
            self._accumulator = self._parse_current()

        self._history = self._fmt(self._accumulator) + f" {op}"
        self._pending_op = op
        self._new_entry = True

    def _evaluate(self):
        """Equals pressed."""
        if self._error:
            return

        # Repeated = : re-apply last operation (Win11 feature)
        if self._just_evaluated and self._last_op and self._last_operand is not None:
            self._history = (
                self._fmt(self._accumulator) +
                f" {self._last_op} {self._fmt(self._last_operand)} ="
            )
            result = self._compute(self._accumulator, self._last_op, self._last_operand)
            if self._error:
                return
            self._accumulator = result
            self._current = self._fmt(result)
            # _just_evaluated stays True, _new_entry stays True
            return

        if self._pending_op:
            current_val = self._parse_current()

            self._history = (
                self._fmt(self._accumulator) +
                f" {self._pending_op} {self._fmt(current_val)} ="
            )

            # Save for repeated =
            self._last_op = self._pending_op
            self._last_operand = current_val

            result = self._compute(self._accumulator, self._pending_op, current_val)
            if self._error:
                return
            self._accumulator = result
            self._current = self._fmt(result)
            self._pending_op = None
        else:
            # No pending op → just display "num ="
            current_val = self._parse_current()
            self._history = self._fmt(current_val) + " ="
            self._accumulator = current_val
            self._last_op = None
            self._last_operand = None

        self._just_evaluated = True
        self._new_entry = True

    def _do_pending(self):
        """Evaluate the pending operation (used when chaining operators)."""
        if self._accumulator is not None and self._pending_op:
            current_val = self._parse_current()
            result = self._compute(self._accumulator, self._pending_op, current_val)
            if not self._error:
                self._accumulator = result
                self._current = self._fmt(result)

    def _backspace(self):
        if self._just_evaluated or self._new_entry or self._error:
            return
        if len(self._current) > 1:
            self._current = self._current[:-1]
            # Don't leave a lone minus sign
            if self._current == "-":
                self._current = "0"
                self._new_entry = True
        else:
            self._current = "0"
            self._new_entry = True

    # ==================================================================
    # MATH
    # ==================================================================

    def _compute(self, left, op, right):
        """Perform one arithmetic operation. Sets self._error on failure."""
        try:
            if op == "+":
                result = left + right
            elif op == "-":
                result = left - right
            elif op == "*":
                result = left * right
            elif op == "/":
                if right == 0:
                    self._error = "DIV/0!"
                    return 0
                result = left / right
            else:
                return left

            # Guard against overflow / NaN
            if isinstance(result, float) and (
                result != result or abs(result) == float("inf")
            ):
                self._error = "OVERFLOW"
                return 0
            return result
        except Exception:
            self._error = "ERROR"
            return 0

    def _parse_current(self):
        """Parse the display string into a number."""
        try:
            if "." in self._current:
                return float(self._current)
            return int(self._current)
        except (ValueError, OverflowError):
            return 0

    @staticmethod
    def _fmt(val):
        """Format a number for display (no trailing .0, max 10 sig figs)."""
        if val is None:
            return "0"
        if isinstance(val, float):
            if val.is_integer() and abs(val) < 1e15:
                return str(int(val))
            return f"{val:.10g}"
        return str(val)

    # ==================================================================
    # RENDERING
    # ==================================================================

    def get_image(self):
        """Return a 128x40 PIL image of the calculator screen."""
        w = self.config.width    # 128
        h = self.config.height   # 40
        primary = self.config.primary
        secondary = self.config.secondary

        image = Image.new("1", (w, h), color=secondary)
        draw = ImageDraw.Draw(image)

        # --- Top: expression history (right-aligned, small) ---
        if self._history:
            disp_history = self._history.replace(".", ",")
            hist = self._truncate_left(draw, disp_history, self._font_history, w - 4)
            draw.text((w - 2, 1), hist, font=self._font_history, fill=primary, anchor="ra")

        # --- Divider line ---
        draw.line([(0, 15), (w, 15)], fill=primary, width=1)

        # --- Bottom: current number or error (right-aligned, big) ---
        if self._error:
            text = self._error
            font = self._font_history   # errors in smaller font
        else:
            text = self._current.replace(".", ",")
            font = self._font_number

        text = self._truncate_left(draw, text, font, w - 4)
        
        # Draw the text right-aligned at y=38 (baseline)
        draw.text((w - 2, 38), text, font=font, fill=primary, anchor="rd")

        # --- "CALC" label (bottom-left, tiny) ---
        draw.text((1, 38), "CALC", font=self._font_label, fill=primary, anchor="ld")

        return image

    @staticmethod
    def _truncate_left(draw, text, font, max_width):
        """Trim characters from the left until text fits within max_width."""
        if not font or not text:
            return text
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            text_w = bbox[2] - bbox[0]
            while text_w > max_width and len(text) > 1:
                text = text[1:]
                bbox = draw.textbbox((0, 0), text, font=font)
                text_w = bbox[2] - bbox[0]
        except Exception:
            pass
        return text
