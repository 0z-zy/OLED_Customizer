"""
OLED Calculator - Win11-style calculator for the 128x40 OLED screen.

Activated via Ctrl+Insert (customizable). Input comes from numpad only.
Display: expression history on top, current number on bottom (right-aligned).

Supports: 0-9, +, -, *, /, ., (, ), Enter, Backspace, Delete/Escape
"""

from PIL import ImageFont, ImageDraw, Image
import logging

from src.image_utils import fetch_content_path

logger = logging.getLogger("OLED Customizer.Calculator")


# ==============================================================
# Safe math evaluator — no eval(), supports +, -, *, /, (, )
# ==============================================================

class _ParseError(Exception):
    pass


def _safe_eval(expr: str):
    """
    Safely evaluate a math expression string.
    Supports: integers, floats, +, -, *, /, (, )
    Raises _ParseError or ZeroDivisionError on bad input.
    Raises OverflowError on huge results.
    """
    tokens = _tokenize(expr)
    pos = [0]  # mutable so inner funcs can advance it

    def peek():
        if pos[0] < len(tokens):
            return tokens[pos[0]]
        return None

    def consume(expected=None):
        tok = peek()
        if expected is not None and tok != expected:
            raise _ParseError(f"Expected {expected!r}, got {tok!r}")
        pos[0] += 1
        return tok

    def parse_expr():
        """Addition / subtraction — lowest precedence."""
        left = parse_term()
        while peek() in ('+', '-'):
            op = consume()
            right = parse_term()
            if op == '+':
                left = left + right
            else:
                left = left - right
        return left

    def parse_term():
        """Multiplication / division."""
        left = parse_factor()
        while peek() in ('*', '/'):
            op = consume()
            right = parse_factor()
            if op == '*':
                left = left * right
            else:
                if right == 0:
                    raise ZeroDivisionError
                left = left / right
        return left

    def parse_factor():
        """Unary minus, parenthesised group, or number."""
        tok = peek()
        if tok is None:
            raise _ParseError("Unexpected end of expression")

        # Unary minus
        if tok == '-':
            consume()
            val = parse_factor()
            return -val

        # Unary plus (just eat it)
        if tok == '+':
            consume()
            return parse_factor()

        # Parenthesised sub-expression
        if tok == '(':
            consume('(')
            val = parse_expr()
            consume(')')
            return val

        # Number literal
        try:
            consume()
            if '.' in tok:
                return float(tok)
            return int(tok)
        except (ValueError, TypeError):
            raise _ParseError(f"Not a number: {tok!r}")

    result = parse_expr()
    if peek() is not None:
        raise _ParseError("Unexpected token after expression")

    # Guard against NaN / infinity
    if isinstance(result, float):
        if result != result or abs(result) == float('inf'):
            raise OverflowError
    return result


def _tokenize(expr: str):
    """
    Splits a math expression string into a list of tokens.
    Numbers (possibly with '.'), operators (+, -, *, /), and parens.
    """
    tokens = []
    i = 0
    while i < len(expr):
        ch = expr[i]
        if ch in ' \t':
            i += 1
            continue
        if ch in '+-*/()':
            tokens.append(ch)
            i += 1
        elif ch.isdigit() or ch == '.':
            j = i
            has_dot = False
            while j < len(expr) and (expr[j].isdigit() or (expr[j] == '.' and not has_dot)):
                if expr[j] == '.':
                    has_dot = True
                j += 1
            tokens.append(expr[i:j])
            i = j
        else:
            raise _ParseError(f"Unknown character: {ch!r}")
    return tokens


# ==============================================================
# Calculator class
# ==============================================================

class Calculator:
    """
    Win11-style calculator rendered on the 128x40 OLED display.

    Display layout:
      Top row:    expression history, right-aligned, small font
      Divider:    thin line
      Bottom row: current number / result, right-aligned, big font

    Now supports full parenthesised expressions: (2+3)*4 = 20
    """

    def __init__(self, config):
        self.config = config

        # --- Expression state ---
        self._expr = ""          # Full expression string being built, e.g. "(5+3)*2"
        self._current = "0"      # Number currently being entered (shown on bottom row)
        self._history = ""       # Top-row label (expression + "=" or error)
        self._just_evaluated = False   # True right after pressing =
        self._new_entry = True         # Next digit starts fresh (replaces _current)
        self._error = None             # Error string ("DIV/0!", "ERROR", etc.)

        # For Win11-style repeated = (re-apply last full expression)
        self._last_expr = None         # Last expression string used for =
        self._last_result = None       # Last numeric result

        # Open-paren count (so we can validate ) key)
        self._open_parens = 0

        # --- Fonts ---
        self._font_history = self._safe_font(fetch_content_path("fonts/MunroSmall.ttf"), 10)
        self._font_number  = self._safe_font(fetch_content_path("fonts/MunroSmall.ttf"), 20)
        self._font_label   = self._safe_font(fetch_content_path("fonts/MunroSmall.ttf"), 10)

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
        '0'-'9', '+', '-', '*', '/', '.', '(', ')',
        'enter', 'backspace', 'delete'
        """
        key = str(key_str).strip().lower()

        if key in "0123456789":
            self._append_digit(key)
        elif key in ("+", "-", "*", "/"):
            self._apply_operator(key)
        elif key in (".", ",", "decimal"):
            self._append_dot()
        elif key == "(":
            self._append_paren("(")
        elif key == ")":
            self._append_paren(")")
        elif key in ("enter", "return", "="):
            self._evaluate()
        elif key == "backspace":
            self._backspace()
        elif key in ("delete", "ce"):
            self._clear_entry()   # CE: clears current number only, keeps expression
        elif key in ("c", "escape"):
            self.clear()          # C:  clears everything

    def clear(self):
        """Clear everything (C)."""
        self._expr = ""
        self._current = "0"
        self._history = ""
        self._just_evaluated = False
        self._new_entry = True
        self._error = None
        self._last_expr = None
        self._last_result = None
        self._open_parens = 0

    def _clear_entry(self):
        """CE — clear current entry (just the number on the bottom row).
        Keeps the expression prefix on the top row intact.
        Win11 equivalent: the CE button."""
        if self._error:
            self.clear()
            return
        if self._just_evaluated:
            # After a result, CE is a full clear (nothing partial to undo)
            self.clear()
            return
        # Just reset the number being typed; the expression prefix stays
        self._current = "0"
        self._new_entry = True

    # ==================================================================
    # INTERNAL LOGIC
    # ==================================================================

    def _append_digit(self, d):
        if self._error:
            self.clear()

        if self._just_evaluated:
            # After =, typing a digit starts a brand-new calculation
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
            # Continue from the last result (e.g. after "= 45" press "+")
            self._expr = self._fmt(self._last_result)
            self._current = self._fmt(self._last_result)  # keep result visible on bottom
            self._history = ""                             # clear so new expr shows on top
            self._just_evaluated = False

        if not self._new_entry:
            # Commit the current number into the expression
            self._expr += self._current
            self._new_entry = True

        # Replace a trailing operator if user changes their mind
        # (strip any trailing operator, then re-add new one)
        stripped = self._expr.rstrip()
        if stripped and stripped[-1] in "+-*/":
            self._expr = stripped[:-1]

        self._expr += op
        # Don't reset _current to "0" here — keep showing the last number
        # as a hint. _new_entry=True means next digit will replace it cleanly.

    def _append_paren(self, ch):
        """Handle ( and ) keypresses."""
        if self._error:
            return

        if ch == "(":
            if self._just_evaluated:
                # After = we allow starting a fresh expression with (
                self.clear()

            if not self._new_entry:
                # If we're mid-number, treat as implicit multiply: 5( → 5*(
                self._expr += self._current + "*"
                self._new_entry = True
                self._current = "0"
            elif self._expr and self._expr[-1] in "0123456789)":
                # Same: result) followed by ( → implicit *
                self._expr += "*"

            self._expr += "("
            self._open_parens += 1

        elif ch == ")":
            # Only valid if there's an unclosed (
            if self._open_parens <= 0:
                return

            if not self._new_entry:
                # Commit current number first
                self._expr += self._current
                self._new_entry = True
                self._current = "0"

            self._expr += ")"
            self._open_parens -= 1

    def _evaluate(self):
        """Equals pressed."""
        if self._error:
            return

        # Repeated = : re-apply last expression
        if self._just_evaluated and self._last_expr is not None:
            try:
                result = _safe_eval(self._last_expr)
                self._last_result = result
                self._current = self._fmt(result)
                self._history = self._last_expr + " ="
            except ZeroDivisionError:
                self._error = "DIV/0!"
            except OverflowError:
                self._error = "OVERFLOW"
            except Exception:
                self._error = "ERROR"
            return

        # Commit any pending number
        if not self._new_entry:
            self._expr += self._current
            self._new_entry = True

        # Auto-close unclosed parentheses
        self._expr += ")" * self._open_parens
        self._open_parens = 0

        if not self._expr:
            # Nothing entered — just show "0 ="
            self._history = "0 ="
            self._just_evaluated = True
            return

        try:
            result = _safe_eval(self._expr)

            # Guard overflow / NaN
            if isinstance(result, float):
                if result != result or abs(result) == float("inf"):
                    self._error = "OVERFLOW"
                    return

            self._history = self._expr + " ="
            self._last_expr = self._expr
            self._last_result = result
            self._current = self._fmt(result)
            self._just_evaluated = True

        except ZeroDivisionError:
            self._error = "DIV/0!"
        except OverflowError:
            self._error = "OVERFLOW"
        except Exception:
            self._error = "ERROR"

    def _backspace(self):
        if self._error:
            self.clear()
            return
        if self._just_evaluated:
            return  # Can't backspace after =

        if not self._new_entry:
            # We're typing a number — backspace within it
            if len(self._current) > 1:
                self._current = self._current[:-1]
                if self._current == "-":
                    self._current = "0"
                    self._new_entry = True
            else:
                self._current = "0"
                self._new_entry = True
        else:
            # Backspace into the expression string
            if not self._expr:
                return
            last = self._expr[-1]
            self._expr = self._expr[:-1]
            if last == "(":
                self._open_parens = max(0, self._open_parens - 1)
            elif last == ")":
                self._open_parens += 1
            # After removing a digit/number-end from expr, switch back to editing
            if self._expr and self._expr[-1] in "0123456789.":
                # Find the trailing number token and pop it into _current
                i = len(self._expr) - 1
                while i >= 0 and (self._expr[i].isdigit() or self._expr[i] == '.'):
                    i -= 1
                self._current = self._expr[i + 1:]
                self._expr = self._expr[:i + 1]
                self._new_entry = False
            elif last in "0123456789.":
                # Removed a digit, but _expr is now empty or ends in operator
                self._current = "0"
                self._new_entry = True

    # ==================================================================
    # FORMATTING
    # ==================================================================

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

        # --- Top: expression / history (right-aligned, small) ---
        if self._history:
            disp_history = self._history.replace(".", ",")
            hist = self._truncate_left(draw, disp_history, self._font_history, w - 4)
            draw.text((w - 2, 1), hist, font=self._font_history, fill=primary, anchor="ra")
        elif self._expr:
            # While building expression, show it on the top line
            disp_expr = self._expr.replace(".", ",")
            expr_disp = self._truncate_left(draw, disp_expr, self._font_history, w - 4)
            draw.text((w - 2, 1), expr_disp, font=self._font_history, fill=primary, anchor="ra")

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

        # Draw right-aligned at y=38 (baseline)
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
