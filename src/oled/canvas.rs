/// 128x40 1-bit OLED framebuffer stored directly in SteelSeries GameSense MSB-first bitpacked format.
/// Each row is 16 bytes (128 pixels / 8), 40 rows total = 640 bytes.
pub const OLED_WIDTH: i32 = 128;
pub const OLED_HEIGHT: i32 = 40;
pub const OLED_BYTES: usize = 640;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Rect {
    pub x: i32,
    pub y: i32,
    pub w: i32,
    pub h: i32,
}

impl Rect {
    pub const fn new(x: i32, y: i32, w: i32, h: i32) -> Self {
        Self { x, y, w, h }
    }

    pub const fn full() -> Self {
        Self {
            x: 0,
            y: 0,
            w: OLED_WIDTH,
            h: OLED_HEIGHT,
        }
    }

    pub fn contains(&self, px: i32, py: i32) -> bool {
        px >= self.x && px < self.x + self.w && py >= self.y && py < self.y + self.h
    }
}

#[derive(Clone)]
pub struct Canvas128x40 {
    pub data: [u8; OLED_BYTES],
}

impl Default for Canvas128x40 {
    fn default() -> Self {
        Self::new()
    }
}

impl Canvas128x40 {
    pub fn new() -> Self {
        Self {
            data: [0u8; OLED_BYTES],
        }
    }

    pub fn clear(&mut self) {
        self.data.fill(0);
    }

    #[inline]
    pub fn set_pixel(&mut self, x: i32, y: i32, on: bool) {
        if x < 0 || x >= OLED_WIDTH || y < 0 || y >= OLED_HEIGHT {
            return;
        }
        let idx = (y as usize) * 16 + ((x as usize) >> 3);
        let mask = 1u8 << (7 - ((x as usize) & 7));
        if on {
            self.data[idx] |= mask;
        } else {
            self.data[idx] &= !mask;
        }
    }

    #[inline]
    pub fn set_pixel_clipped(&mut self, x: i32, y: i32, on: bool, clip: Rect) {
        if clip.contains(x, y) {
            self.set_pixel(x, y, on);
        }
    }

    #[inline]
    pub fn get_pixel(&self, x: i32, y: i32) -> bool {
        if x < 0 || x >= OLED_WIDTH || y < 0 || y >= OLED_HEIGHT {
            return false;
        }
        let idx = (y as usize) * 16 + ((x as usize) >> 3);
        let mask = 1u8 << (7 - ((x as usize) & 7));
        (self.data[idx] & mask) != 0
    }

    pub fn draw_hline(&mut self, x0: i32, x1: i32, y: i32, on: bool) {
        if y < 0 || y >= OLED_HEIGHT {
            return;
        }
        let (a, b) = if x0 <= x1 { (x0, x1) } else { (x1, x0) };
        let start = a.max(0);
        let end = b.min(OLED_WIDTH - 1);
        for x in start..=end {
            self.set_pixel(x, y, on);
        }
    }

    pub fn draw_vline(&mut self, x: i32, y0: i32, y1: i32, on: bool) {
        if x < 0 || x >= OLED_WIDTH {
            return;
        }
        let (a, b) = if y0 <= y1 { (y0, y1) } else { (y1, y0) };
        let start = a.max(0);
        let end = b.min(OLED_HEIGHT - 1);
        for y in start..=end {
            self.set_pixel(x, y, on);
        }
    }

    pub fn draw_line(&mut self, mut x0: i32, mut y0: i32, x1: i32, y1: i32, on: bool) {
        let dx = (x1 - x0).abs();
        let sx = if x0 < x1 { 1 } else { -1 };
        let dy = -(y1 - y0).abs();
        let sy = if y0 < y1 { 1 } else { -1 };
        let mut err = dx + dy;
        loop {
            self.set_pixel(x0, y0, on);
            if x0 == x1 && y0 == y1 {
                break;
            }
            let e2 = 2 * err;
            if e2 >= dy {
                err += dy;
                x0 += sx;
            }
            if e2 <= dx {
                err += dx;
                y0 += sy;
            }
        }
    }

    pub fn draw_rect(&mut self, x: i32, y: i32, w: i32, h: i32, on: bool) {
        if w <= 0 || h <= 0 {
            return;
        }
        self.draw_hline(x, x + w - 1, y, on);
        self.draw_hline(x, x + w - 1, y + h - 1, on);
        self.draw_vline(x, y, y + h - 1, on);
        self.draw_vline(x + w - 1, y, y + h - 1, on);
    }

    pub fn fill_rect(&mut self, x: i32, y: i32, w: i32, h: i32, on: bool) {
        if w <= 0 || h <= 0 {
            return;
        }
        for py in y..(y + h) {
            self.draw_hline(x, x + w - 1, py, on);
        }
    }

    /// Draws a 1px-chamfered / rounded-corner rectangle outline (ideal for small OLED screens).
    pub fn draw_rounded_rect(&mut self, x: i32, y: i32, w: i32, h: i32, on: bool) {
        if w < 3 || h < 3 {
            self.draw_rect(x, y, w, h, on);
            return;
        }
        self.draw_hline(x + 1, x + w - 2, y, on);
        self.draw_hline(x + 1, x + w - 2, y + h - 1, on);
        self.draw_vline(x, y + 1, y + h - 2, on);
        self.draw_vline(x + w - 1, y + 1, y + h - 2, on);
    }

    pub fn fill_rounded_rect(&mut self, x: i32, y: i32, w: i32, h: i32, on: bool) {
        if w < 3 || h < 3 {
            self.fill_rect(x, y, w, h, on);
            return;
        }
        self.draw_hline(x + 1, x + w - 2, y, on);
        for py in (y + 1)..(y + h - 1) {
            self.draw_hline(x, x + w - 1, py, on);
        }
        self.draw_hline(x + 1, x + w - 2, y + h - 1, on);
    }

    pub fn draw_circle(&mut self, cx: i32, cy: i32, r: i32, on: bool) {
        if r <= 0 {
            self.set_pixel(cx, cy, on);
            return;
        }
        let mut x = r;
        let mut y = 0;
        let mut err = 1 - x;
        while x >= y {
            self.set_pixel(cx + x, cy + y, on);
            self.set_pixel(cx + y, cy + x, on);
            self.set_pixel(cx - y, cy + x, on);
            self.set_pixel(cx - x, cy + y, on);
            self.set_pixel(cx - x, cy - y, on);
            self.set_pixel(cx - y, cy - x, on);
            self.set_pixel(cx + y, cy - x, on);
            self.set_pixel(cx + x, cy - y, on);
            y += 1;
            if err < 0 {
                err += 2 * y + 1;
            } else {
                x -= 1;
                err += 2 * (y - x) + 1;
            }
        }
    }

    pub fn fill_circle(&mut self, cx: i32, cy: i32, r: i32, on: bool) {
        if r <= 0 {
            self.set_pixel(cx, cy, on);
            return;
        }
        let r2 = r * r;
        for dy in -r..=r {
            for dx in -r..=r {
                if dx * dx + dy * dy <= r2 {
                    self.set_pixel(cx + dx, cy + dy, on);
                }
            }
        }
    }

    pub fn draw_bitmap(&mut self, x: i32, y: i32, rows: &[&str], on: bool) {
        self.draw_bitmap_clipped(x, y, rows, on, Rect::full());
    }

    pub fn draw_bitmap_clipped(&mut self, x: i32, y: i32, rows: &[&str], on: bool, clip: Rect) {
        for (ry, row) in rows.iter().enumerate() {
            for (rx, ch) in row.bytes().enumerate() {
                if ch == b'#' {
                    self.set_pixel_clipped(x + rx as i32, y + ry as i32, on, clip);
                }
            }
        }
    }

    /// Converts the 1-bit framebuffer to an RGBA8888 buffer (128x40x4) for the live UI preview.
    pub fn to_rgba_preview(&self, tint: [u8; 3]) -> Vec<u8> {
        let mut rgba = Vec::with_capacity((OLED_WIDTH * OLED_HEIGHT * 4) as usize);
        let bg = [8u8, 10u8, 14u8, 255u8];
        for y in 0..OLED_HEIGHT {
            for x in 0..OLED_WIDTH {
                if self.get_pixel(x, y) {
                    rgba.push(tint[0]);
                    rgba.push(tint[1]);
                    rgba.push(tint[2]);
                    rgba.push(255);
                } else {
                    rgba.extend_from_slice(&bg);
                }
            }
        }
        rgba
    }
}
