use super::super::canvas::{Canvas128x40, Rect, OLED_WIDTH};
use super::super::fonts::{draw_font, draw_font_clipped, measure_ttf, AlignH, TtfFontId};

#[derive(Clone, Debug, PartialEq)]
pub struct CalculatorView {
    expr: String,
    current: String,
    history: String,
    just_evaluated: bool,
    new_entry: bool,
    error: Option<String>,
    last_expr: Option<String>,
    last_result: Option<f64>,
    open_parens: i32,
}

impl Default for CalculatorView {
    fn default() -> Self {
        Self::new()
    }
}

impl CalculatorView {
    pub fn new() -> Self {
        Self {
            expr: String::new(),
            current: "0".to_string(),
            history: String::new(),
            just_evaluated: false,
            new_entry: true,
            error: None,
            last_expr: None,
            last_result: None,
            open_parens: 0,
        }
    }

    pub fn clear(&mut self) {
        *self = Self::new();
    }

    pub fn set_demo_state(&mut self, history: &str, current: &str) {
        self.clear();
        self.history = history.to_string();
        self.current = current.to_string();
    }

    pub fn key_input(&mut self, key: &str) {
        let k = key.trim().to_ascii_lowercase();
        match k.as_str() {
            "0" | "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9" => self.append_digit(&k),
            "+" | "-" | "*" | "/" => self.apply_op(&k),
            "." | "," | "decimal" => self.append_dot(),
            "(" => self.append_paren('('),
            ")" => self.append_paren(')'),
            "enter" | "return" | "=" => self.evaluate(),
            "backspace" => self.backspace(),
            "delete" | "ce" => self.clear_entry(),
            "c" | "escape" => self.clear(),
            _ => {}
        }
    }

    fn clear_entry(&mut self) {
        if self.error.is_some() || self.just_evaluated {
            self.clear();
            return;
        }
        self.current = "0".to_string();
        self.new_entry = true;
    }

    fn append_digit(&mut self, d: &str) {
        if self.error.is_some() || self.just_evaluated {
            self.clear();
        }
        if self.new_entry {
            self.current = d.to_string();
            self.new_entry = false;
        } else if self.current == "0" {
            self.current = d.to_string();
        } else if self.current.len() < 16 {
            self.current.push_str(d);
        }
    }

    fn append_dot(&mut self) {
        if self.error.is_some() || self.just_evaluated {
            self.clear();
        }
        if self.new_entry {
            self.current = "0".to_string();
            self.new_entry = false;
        }
        if !self.current.contains('.') {
            self.current.push('.');
        }
    }

    fn apply_op(&mut self, op: &str) {
        if self.error.is_some() {
            return;
        }
        if self.just_evaluated {
            let fmt = Self::fmt(self.last_result.unwrap_or(0.0));
            self.expr = fmt.clone();
            self.current = fmt;
            self.history.clear();
            self.just_evaluated = false;
        }
        if !self.new_entry {
            self.expr.push_str(&self.current);
            self.new_entry = true;
        }
        if self.expr.ends_with(['+', '-', '*', '/']) {
            self.expr.pop();
        }
        self.expr.push_str(op);
    }

    fn append_paren(&mut self, ch: char) {
        if self.error.is_some() {
            return;
        }
        if ch == '(' {
            if self.just_evaluated {
                self.clear();
            }
            if !self.new_entry {
                self.expr.push_str(&self.current);
                self.expr.push('*');
                self.new_entry = true;
                self.current = "0".to_string();
            } else if self.expr.ends_with(|c: char| c.is_ascii_digit() || c == ')') {
                self.expr.push('*');
            }
            self.expr.push('(');
            self.open_parens += 1;
        } else if self.open_parens > 0 {
            if !self.new_entry {
                self.expr.push_str(&self.current);
                self.new_entry = true;
                self.current = "0".to_string();
            }
            self.expr.push(')');
            self.open_parens -= 1;
        }
    }

    fn evaluate(&mut self) {
        if self.error.is_some() {
            return;
        }
        if self.just_evaluated {
            if let Some(ref le) = self.last_expr.clone() {
                match safe_eval(le) {
                    Ok(v) => {
                        self.last_result = Some(v);
                        self.current = Self::fmt(v);
                        self.history = format!("{} =", le);
                    }
                    Err(e) => self.error = Some(e.to_string()),
                }
            }
            return;
        }

        if !self.new_entry {
            self.expr.push_str(&self.current);
            self.new_entry = true;
        }
        for _ in 0..self.open_parens {
            self.expr.push(')');
        }
        self.open_parens = 0;

        if self.expr.is_empty() {
            self.history = "0 =".to_string();
            self.just_evaluated = true;
            return;
        }

        match safe_eval(&self.expr) {
            Ok(v) => {
                self.history = format!("{} =", self.expr);
                self.last_expr = Some(self.expr.clone());
                self.last_result = Some(v);
                self.current = Self::fmt(v);
                self.just_evaluated = true;
            }
            Err(e) => self.error = Some(e.to_string()),
        }
    }

    fn backspace(&mut self) {
        if self.error.is_some() {
            self.clear();
            return;
        }
        if self.just_evaluated {
            return;
        }
        if !self.new_entry {
            if self.current.len() > 1 {
                self.current.pop();
                if self.current == "-" {
                    self.current = "0".to_string();
                    self.new_entry = true;
                }
            } else {
                self.current = "0".to_string();
                self.new_entry = true;
            }
        } else if let Some(last) = self.expr.pop() {
            if last == '(' {
                self.open_parens = (self.open_parens - 1).max(0);
            } else if last == ')' {
                self.open_parens += 1;
            }
            if self.expr.ends_with(|c: char| c.is_ascii_digit() || c == '.') {
                let idx = self
                    .expr
                    .rfind(|c: char| !(c.is_ascii_digit() || c == '.'))
                    .map(|i| i + 1)
                    .unwrap_or(0);
                self.current = self.expr[idx..].to_string();
                self.expr.truncate(idx);
                self.new_entry = false;
            } else if last.is_ascii_digit() || last == '.' {
                self.current = "0".to_string();
                self.new_entry = true;
            }
        }
    }

    fn fmt(v: f64) -> String {
        if v.fract() == 0.0 && v.abs() < 1e14 {
            format!("{}", v as i64)
        } else {
            let s = format!("{:.8}", v);
            s.trim_end_matches('0').trim_end_matches('.').to_string()
        }
    }

    pub fn render(&self, canvas: &mut Canvas128x40) {
        canvas.clear();
        let clip = Rect::full();

        // Top-left inverted CALC badge
        canvas.fill_rounded_rect(1, 2, 22, 9, true);
        draw_font(canvas, TtfFontId::Munro10, 12, 4, "CALC", AlignH::Center, false);

        // Top-right expression / history
        let top_str = if !self.history.is_empty() {
            self.history.as_str()
        } else {
            self.expr.as_str()
        };
        if !top_str.is_empty() {
            let mut disp = top_str.replace('.', ",");
            while measure_ttf(TtfFontId::Munro10, &disp) > (OLED_WIDTH - 28) && disp.len() > 1 {
                disp.remove(0);
            }
            draw_font_clipped(
                canvas,
                TtfFontId::Munro10,
                OLED_WIDTH - 2,
                4,
                &disp,
                AlignH::Right,
                true,
                Rect::new(25, 0, OLED_WIDTH - 25, 14),
            );
        }

        // Divider
        canvas.draw_hline(0, OLED_WIDTH - 1, 13, true);

        // Bottom: MunroSmall 20px current number or Verdana9 error
        if let Some(ref err) = self.error {
            draw_font_clipped(
                canvas,
                TtfFontId::Verdana9,
                OLED_WIDTH - 3,
                23,
                err,
                AlignH::Right,
                true,
                clip,
            );
        } else {
            let mut num_disp = self.current.replace('.', ",");
            while measure_ttf(TtfFontId::Munro20, &num_disp) > (OLED_WIDTH - 6)
                && num_disp.len() > 1
            {
                num_disp.remove(0);
            }
            draw_font(
                canvas,
                TtfFontId::Munro20,
                OLED_WIDTH - 3,
                22,
                &num_disp,
                AlignH::Right,
                true,
            );
        }
    }
}

fn safe_eval(expr: &str) -> Result<f64, &'static str> {
    let tokens = tokenize(expr)?;
    let mut pos = 0usize;
    let res = parse_expr(&tokens, &mut pos)?;
    if pos < tokens.len() {
        return Err("SYNTAX");
    }
    if !res.is_finite() {
        return Err("OVERFLOW");
    }
    Ok(res)
}

#[derive(Clone, Debug, PartialEq)]
enum Tok {
    Num(f64),
    Op(char),
    LParen,
    RParen,
}

fn tokenize(expr: &str) -> Result<Vec<Tok>, &'static str> {
    let mut out = Vec::new();
    let chars: Vec<char> = expr.chars().collect();
    let mut i = 0;
    while i < chars.len() {
        let c = chars[i];
        if c.is_whitespace() {
            i += 1;
            continue;
        }
        match c {
            '+' | '-' | '*' | '/' => {
                out.push(Tok::Op(c));
                i += 1;
            }
            '(' => {
                out.push(Tok::LParen);
                i += 1;
            }
            ')' => {
                out.push(Tok::RParen);
                i += 1;
            }
            c if c.is_ascii_digit() || c == '.' => {
                let start = i;
                let mut has_dot = false;
                while i < chars.len()
                    && (chars[i].is_ascii_digit() || (chars[i] == '.' && !has_dot))
                {
                    if chars[i] == '.' {
                        has_dot = true;
                    }
                    i += 1;
                }
                let s: String = chars[start..i].iter().collect();
                let n: f64 = s.parse().map_err(|_| "ERROR")?;
                out.push(Tok::Num(n));
            }
            _ => return Err("ERROR"),
        }
    }
    Ok(out)
}

fn parse_expr(toks: &[Tok], pos: &mut usize) -> Result<f64, &'static str> {
    let mut left = parse_term(toks, pos)?;
    while let Some(Tok::Op(op @ ('+' | '-'))) = toks.get(*pos) {
        *pos += 1;
        let right = parse_term(toks, pos)?;
        left = if *op == '+' { left + right } else { left - right };
    }
    Ok(left)
}

fn parse_term(toks: &[Tok], pos: &mut usize) -> Result<f64, &'static str> {
    let mut left = parse_factor(toks, pos)?;
    while let Some(Tok::Op(op @ ('*' | '/'))) = toks.get(*pos) {
        *pos += 1;
        let right = parse_factor(toks, pos)?;
        if *op == '/' {
            if right == 0.0 {
                return Err("DIV/0!");
            }
            left /= right;
        } else {
            left *= right;
        }
    }
    Ok(left)
}

fn parse_factor(toks: &[Tok], pos: &mut usize) -> Result<f64, &'static str> {
    match toks.get(*pos) {
        Some(Tok::Op('-')) => {
            *pos += 1;
            Ok(-parse_factor(toks, pos)?)
        }
        Some(Tok::Op('+')) => {
            *pos += 1;
            parse_factor(toks, pos)
        }
        Some(Tok::LParen) => {
            *pos += 1;
            let v = parse_expr(toks, pos)?;
            if toks.get(*pos) != Some(&Tok::RParen) {
                return Err("PAREN");
            }
            *pos += 1;
            Ok(v)
        }
        Some(Tok::Num(n)) => {
            *pos += 1;
            Ok(*n)
        }
        _ => Err("ERROR"),
    }
}
