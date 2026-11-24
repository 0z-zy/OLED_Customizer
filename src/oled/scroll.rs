use super::canvas::{Canvas128x40, Rect};
use super::fonts::{draw_font_clipped, measure_ttf, AlignH, TtfFontId};

/// Smooth marquee scroller with start/end pause and strict horizontal clipping.
#[derive(Clone, Debug)]
pub struct ScrollText {
    pub content: String,
    pub step: i32,
    pub pause_ticks: i32,
}

impl ScrollText {
    pub fn new(pause_ticks: i32) -> Self {
        Self {
            content: String::new(),
            step: 0,
            pause_ticks,
        }
    }

    pub fn set_text(&mut self, text: &str) {
        if self.content != text {
            self.content = text.to_string();
            self.step = 0;
        }
    }

    pub fn tick(&mut self) {
        self.step = self.step.wrapping_add(1);
    }

    pub fn draw(
        &self,
        canvas: &mut Canvas128x40,
        font: TtfFontId,
        x: i32,
        y: i32,
        avail_w: i32,
        clip_h: i32,
        centered_when_fit: bool,
    ) {
        if self.content.is_empty() || avail_w <= 0 {
            return;
        }
        let text_w = measure_ttf(font, &self.content);
        let clip = Rect::new(x, 0, avail_w, clip_h);

        let offset = if text_w <= avail_w {
            if centered_when_fit {
                (avail_w - text_w) / 2
            } else {
                0
            }
        } else {
            let overflow = text_w - avail_w + 2;
            let cycle = 2 * self.pause_ticks + overflow;
            let s = self.step.rem_euclid(cycle);
            if s <= self.pause_ticks {
                0
            } else if s >= self.pause_ticks + overflow {
                -overflow
            } else {
                -(s - self.pause_ticks)
            }
        };

        let draw_x = x + offset;
        draw_font_clipped(canvas, font, draw_x, y, &self.content, AlignH::Left, true, clip);
    }
}
