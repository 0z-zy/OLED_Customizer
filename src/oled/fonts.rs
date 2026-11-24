use std::ffi::c_void;
use std::ptr;
use std::sync::{Mutex, OnceLock};

use windows::Win32::Foundation::{COLORREF, HANDLE, SIZE};
use windows::Win32::Graphics::Gdi::{
    AddFontMemResourceEx, CreateCompatibleDC, CreateDIBSection, CreateFontIndirectW, GdiFlush,
    GetTextExtentPoint32W, SelectObject, SetBkMode, SetTextColor, TextOutW, BITMAPINFO,
    BITMAPINFOHEADER, BI_RGB, DIB_RGB_COLORS, HDC, HFONT, HGDIOBJ, LOGFONTW,
    NONANTIALIASED_QUALITY, TRANSPARENT,
};

use super::canvas::{Canvas128x40, Rect, OLED_HEIGHT, OLED_WIDTH};

static FONT_DIGI_BYTES: &[u8] = include_bytes!("../../assets/fonts/DS-DIGIB.ttf");
static FONT_VERDANA_BYTES: &[u8] = include_bytes!("../../assets/fonts/VerdanaBold.ttf");
static FONT_MUNRO_BYTES: &[u8] = include_bytes!("../../assets/fonts/MunroSmall.ttf");

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum TtfFontId {
    DigiHuge,  // DS-Digital -38 (24px ink)
    DigiBig,   // DS-Digital -24 (15px ink)
    DigiMed,   // DS-Digital -20 (13px ink)
    DigiSmall, // DS-Digital -14 (9px ink)
    Verdana11, // Verdana Bold -11 (8px caps / 11px descenders)
    Verdana10, // Verdana Bold -10 (7px ink)
    Verdana9,  // Verdana Bold -9 (7px ink)
    Munro20,   // Munro Small -20 (10px ink)
    Munro10,   // Munro Small -10 (5px ink)
}

impl TtfFontId {
    const ALL: [TtfFontId; 9] = [
        TtfFontId::DigiHuge,
        TtfFontId::DigiBig,
        TtfFontId::DigiMed,
        TtfFontId::DigiSmall,
        TtfFontId::Verdana11,
        TtfFontId::Verdana10,
        TtfFontId::Verdana9,
        TtfFontId::Munro20,
        TtfFontId::Munro10,
    ];

    fn idx(self) -> usize {
        match self {
            TtfFontId::DigiHuge => 0,
            TtfFontId::DigiBig => 1,
            TtfFontId::DigiMed => 2,
            TtfFontId::DigiSmall => 3,
            TtfFontId::Verdana11 => 4,
            TtfFontId::Verdana10 => 5,
            TtfFontId::Verdana9 => 6,
            TtfFontId::Munro20 => 7,
            TtfFontId::Munro10 => 8,
        }
    }

    fn spec(self) -> (&'static str, i32, i32) {
        match self {
            TtfFontId::DigiHuge => ("DS-Digital", 38, 700),
            TtfFontId::DigiBig => ("DS-Digital", 24, 700),
            TtfFontId::DigiMed => ("DS-Digital", 20, 700),
            TtfFontId::DigiSmall => ("DS-Digital", 14, 700),
            TtfFontId::Verdana11 => ("Verdana", 11, 700),
            TtfFontId::Verdana10 => ("Verdana", 10, 700),
            TtfFontId::Verdana9 => ("Verdana", 9, 700),
            TtfFontId::Munro20 => ("Munro Small", 20, 400),
            TtfFontId::Munro10 => ("Munro Small", 10, 400),
        }
    }

    fn ink_top_offset(self) -> i32 {
        match self {
            TtfFontId::DigiHuge => 7,
            TtfFontId::DigiBig => 5,
            TtfFontId::DigiMed => 3,
            TtfFontId::DigiSmall => 2,
            TtfFontId::Verdana11 => 2,
            TtfFontId::Verdana10 => 3,
            TtfFontId::Verdana9 => 3,
            TtfFontId::Munro20 => 8,
            TtfFontId::Munro10 => 4,
        }
    }

    fn needs_ascii_norm(self) -> bool {
        matches!(
            self,
            TtfFontId::DigiHuge
                | TtfFontId::DigiBig
                | TtfFontId::DigiMed
                | TtfFontId::DigiSmall
                | TtfFontId::Munro20
                | TtfFontId::Munro10
        )
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum AlignH {
    Left,
    Center,
    Right,
}

struct GdiFontBank {
    hdc: HDC,
    bits: *mut u32,
    fonts: [HFONT; 9],
    _mem_handles: [HANDLE; 3],
}

unsafe impl Send for GdiFontBank {}

impl GdiFontBank {
    fn new() -> Self {
        unsafe {
            let mut mem_handles = [HANDLE::default(); 3];
            for (i, bytes) in [FONT_DIGI_BYTES, FONT_VERDANA_BYTES, FONT_MUNRO_BYTES]
                .iter()
                .enumerate()
            {
                let mut count = 0u32;
                mem_handles[i] = AddFontMemResourceEx(
                    bytes.as_ptr() as *const c_void,
                    bytes.len() as u32,
                    None,
                    &mut count,
                );
            }

            let hdc = CreateCompatibleDC(HDC::default());
            let mut bmi = BITMAPINFO::default();
            bmi.bmiHeader = BITMAPINFOHEADER {
                biSize: std::mem::size_of::<BITMAPINFOHEADER>() as u32,
                biWidth: OLED_WIDTH,
                biHeight: -OLED_HEIGHT,
                biPlanes: 1,
                biBitCount: 32,
                biCompression: BI_RGB.0,
                ..Default::default()
            };

            let mut bits_ptr: *mut c_void = ptr::null_mut();
            if let Ok(hbmp) =
                CreateDIBSection(hdc, &bmi, DIB_RGB_COLORS, &mut bits_ptr, None, 0)
            {
                let _ = SelectObject(hdc, HGDIOBJ(hbmp.0));
            }
            let _ = SetBkMode(hdc, TRANSPARENT);
            let _ = SetTextColor(hdc, COLORREF(0x00FFFFFF));

            let mut fonts = [HFONT::default(); 9];
            for id in TtfFontId::ALL {
                let (face, size, weight) = id.spec();
                let mut lf = LOGFONTW {
                    lfHeight: -size,
                    lfWeight: weight,
                    lfQuality: NONANTIALIASED_QUALITY,
                    ..Default::default()
                };
                for (dst, src) in lf.lfFaceName.iter_mut().zip(face.encode_utf16()) {
                    *dst = src;
                }
                fonts[id.idx()] = CreateFontIndirectW(&lf);
            }

            Self {
                hdc,
                bits: bits_ptr as *mut u32,
                fonts,
                _mem_handles: mem_handles,
            }
        }
    }

    fn prepare_text(id: TtfFontId, text: &str) -> Vec<u16> {
        if id.needs_ascii_norm() {
            normalize_text(text).encode_utf16().collect()
        } else {
            text.replace(['—', '–'], "-").encode_utf16().collect()
        }
    }

    fn measure(&mut self, id: TtfFontId, text: &str) -> i32 {
        if text.is_empty() {
            return 0;
        }
        let wide = Self::prepare_text(id, text);
        unsafe {
            let _ = SelectObject(self.hdc, HGDIOBJ(self.fonts[id.idx()].0));
            let mut sz = SIZE::default();
            let _ = GetTextExtentPoint32W(self.hdc, &wide, &mut sz);
            sz.cx
        }
    }

    fn draw(
        &mut self,
        canvas: &mut Canvas128x40,
        id: TtfFontId,
        x: i32,
        top_y: i32,
        text: &str,
        on: bool,
        clip: Rect,
    ) {
        if text.is_empty() || self.bits.is_null() {
            return;
        }
        let wide = Self::prepare_text(id, text);
        let len = (OLED_WIDTH * OLED_HEIGHT) as usize;
        unsafe {
            let buf = std::slice::from_raw_parts_mut(self.bits, len);
            buf.fill(0);
            let _ = SelectObject(self.hdc, HGDIOBJ(self.fonts[id.idx()].0));
            let _ = TextOutW(self.hdc, x, top_y, &wide);
            let _ = GdiFlush();

            let y0 = clip.y.max(0);
            let y1 = (clip.y + clip.h).min(OLED_HEIGHT);
            let x0 = clip.x.max(0);
            let x1 = (clip.x + clip.w).min(OLED_WIDTH);
            for py in y0..y1 {
                let row = (py * OLED_WIDTH) as usize;
                for px in x0..x1 {
                    if (buf[row + px as usize] & 0x00FFFFFF) != 0 {
                        canvas.set_pixel(px, py, on);
                    }
                }
            }
        }
    }
}

fn bank() -> &'static Mutex<GdiFontBank> {
    static BANK: OnceLock<Mutex<GdiFontBank>> = OnceLock::new();
    BANK.get_or_init(|| Mutex::new(GdiFontBank::new()))
}

pub fn normalize_text(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    for ch in text.chars() {
        match ch {
            'ş' => out.push('s'),
            'Ş' => out.push('S'),
            'ç' => out.push('c'),
            'Ç' => out.push('C'),
            'ü' => out.push('u'),
            'Ü' => out.push('U'),
            'ö' => out.push('o'),
            'Ö' => out.push('O'),
            'ğ' => out.push('g'),
            'Ğ' => out.push('G'),
            'ı' => out.push('i'),
            'İ' => out.push('I'),
            '—' | '–' => out.push('-'),
            _ => out.push(ch),
        }
    }
    out
}

pub fn measure_ttf(id: TtfFontId, text: &str) -> i32 {
    bank().lock().unwrap().measure(id, text)
}

pub fn draw_font_clipped(
    canvas: &mut Canvas128x40,
    id: TtfFontId,
    x: i32,
    ink_top_y: i32,
    text: &str,
    align: AlignH,
    on: bool,
    clip: Rect,
) {
    let mut b = bank().lock().unwrap();
    let w = b.measure(id, text);
    let draw_x = match align {
        AlignH::Left => x,
        AlignH::Center => x - w / 2,
        AlignH::Right => x - w,
    };
    let top_y = ink_top_y - id.ink_top_offset();
    b.draw(canvas, id, draw_x, top_y, text, on, clip);
}

pub fn draw_font(
    canvas: &mut Canvas128x40,
    id: TtfFontId,
    x: i32,
    ink_top_y: i32,
    text: &str,
    align: AlignH,
    on: bool,
) {
    draw_font_clipped(canvas, id, x, ink_top_y, text, align, on, Rect::full());
}
