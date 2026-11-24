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
enum PixelAccent {
    Acute,
    Grave,
    Circumflex,
    Umlaut,
    Tilde,
    Breve,
    DotAbove,
    Slash,
    Cedilla,
}

fn precomposed_accent(ch: char) -> Option<PixelAccent> {
    match ch {
        'á' | 'Á' | 'é' | 'É' | 'í' | 'Í' | 'ó' | 'Ó' | 'ú' | 'Ú' | 'ý' | 'Ý' | 'ć' | 'Ć'
        | 'ń' | 'Ń' | 'ŕ' | 'Ŕ' | 'ś' | 'Ś' | 'ź' | 'Ź' | 'ĺ' | 'Ĺ' => {
            Some(PixelAccent::Acute)
        }
        'à' | 'À' | 'è' | 'È' | 'ì' | 'Ì' | 'ò' | 'Ò' | 'ù' | 'Ù' => Some(PixelAccent::Grave),
        'â' | 'Â' | 'ê' | 'Ê' | 'î' | 'Î' | 'ô' | 'Ô' | 'û' | 'Û' | 'ĉ' | 'Ĉ' | 'ĝ' | 'Ĝ'
        | 'ĥ' | 'Ĥ' | 'ĵ' | 'Ĵ' | 'ŝ' | 'Ŝ' | 'ŵ' | 'Ŵ' | 'ŷ' | 'Ŷ' => {
            Some(PixelAccent::Circumflex)
        }
        'ä' | 'Ä' | 'ë' | 'Ë' | 'ï' | 'Ï' | 'ö' | 'Ö' | 'ü' | 'Ü' | 'ÿ' | 'Ÿ' => {
            Some(PixelAccent::Umlaut)
        }
        'ã' | 'Ã' | 'ñ' | 'Ñ' | 'õ' | 'Õ' | 'ĩ' | 'Ĩ' | 'ũ' | 'Ũ' => Some(PixelAccent::Tilde),
        'ğ' | 'Ğ' | 'ă' | 'Ă' | 'ĕ' | 'Ĕ' | 'ĭ' | 'Ĭ' | 'ŏ' | 'Ŏ' | 'ŭ' | 'Ŭ' | 'č' | 'Č'
        | 'ď' | 'Ď' | 'ě' | 'Ě' | 'ň' | 'Ň' | 'ř' | 'Ř' | 'š' | 'Š' | 'ť' | 'Ť' | 'ž' | 'Ž' => {
            Some(PixelAccent::Breve)
        }
        'İ' | 'å' | 'Å' | 'ċ' | 'Ċ' | 'ġ' | 'Ġ' | 'ż' | 'Ż' => Some(PixelAccent::DotAbove),
        'ø' | 'Ø' | 'ł' | 'Ł' | 'đ' | 'Đ' => Some(PixelAccent::Slash),
        'ş' | 'Ş' | 'ç' | 'Ç' => Some(PixelAccent::Cedilla),
        _ => None,
    }
}

fn combining_accent(ch: char) -> Option<PixelAccent> {
    match ch {
        '\u{0301}' => Some(PixelAccent::Acute),
        '\u{0300}' => Some(PixelAccent::Grave),
        '\u{0302}' => Some(PixelAccent::Circumflex),
        '\u{0308}' => Some(PixelAccent::Umlaut),
        '\u{0303}' => Some(PixelAccent::Tilde),
        '\u{0306}' | '\u{030C}' => Some(PixelAccent::Breve),
        '\u{0307}' | '\u{030A}' => Some(PixelAccent::DotAbove),
        '\u{0327}' => Some(PixelAccent::Cedilla),
        _ => None,
    }
}

fn extract_munro_accents(text: &str) -> Vec<(usize, PixelAccent)> {
    let mut out = Vec::new();
    let mut norm_idx = 0usize;
    let mut last_idx: Option<usize> = None;

    for ch in text.chars() {
        if let Some(acc) = combining_accent(ch) {
            if let Some(idx) = last_idx {
                out.push((idx, acc));
            }
            continue;
        }
        if matches!(ch, '\u{0300}'..='\u{036F}' | '\u{200B}'..='\u{200F}' | '\u{FEFF}') {
            continue;
        }
        let prev_len = norm_idx;
        let single = [ch];
        let s: String = single.iter().collect();
        let mapped = normalize_text(&s);
        let added = mapped.encode_utf16().count();
        if added > 0 {
            if let Some(acc) = precomposed_accent(ch) {
                out.push((prev_len, acc));
            }
            last_idx = Some(prev_len);
            norm_idx += added;
        } else {
            last_idx = None;
        }
    }
    out
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

            if id == TtfFontId::Munro10 {
                let accents = extract_munro_accents(text);
                if !accents.is_empty() {
                    let ink_y = top_y + id.ink_top_offset();
                    for (utf16_idx, acc) in accents {
                        if utf16_idx >= wide.len() {
                            continue;
                        }
                        let prefix_w = if utf16_idx == 0 {
                            0
                        } else {
                            let mut sz = SIZE::default();
                            let _ = GetTextExtentPoint32W(self.hdc, &wide[..utf16_idx], &mut sz);
                            sz.cx
                        };
                        let mut csz = SIZE::default();
                        let _ = GetTextExtentPoint32W(
                            self.hdc,
                            &wide[utf16_idx..utf16_idx + 1],
                            &mut csz,
                        );
                        let cx = x + prefix_w;
                        let gw = (csz.cx - 1).max(3);
                        let mid = cx + gw / 2;

                        match acc {
                            PixelAccent::Acute => {
                                canvas.set_pixel_clipped(mid + 1, ink_y - 2, on, clip);
                                canvas.set_pixel_clipped(mid, ink_y - 1, on, clip);
                            }
                            PixelAccent::Grave => {
                                canvas.set_pixel_clipped(mid - 1, ink_y - 2, on, clip);
                                canvas.set_pixel_clipped(mid, ink_y - 1, on, clip);
                            }
                            PixelAccent::Circumflex => {
                                canvas.set_pixel_clipped(mid, ink_y - 2, on, clip);
                                canvas.set_pixel_clipped(mid - 1, ink_y - 1, on, clip);
                                canvas.set_pixel_clipped(mid + 1, ink_y - 1, on, clip);
                            }
                            PixelAccent::Umlaut => {
                                canvas.set_pixel_clipped(mid - 1, ink_y - 2, on, clip);
                                canvas.set_pixel_clipped(mid + 1, ink_y - 2, on, clip);
                            }
                            PixelAccent::Tilde => {
                                canvas.set_pixel_clipped(mid - 1, ink_y - 2, on, clip);
                                canvas.set_pixel_clipped(mid, ink_y - 2, on, clip);
                                canvas.set_pixel_clipped(mid + 1, ink_y - 1, on, clip);
                            }
                            PixelAccent::Breve => {
                                canvas.set_pixel_clipped(mid - 1, ink_y - 2, on, clip);
                                canvas.set_pixel_clipped(mid, ink_y - 1, on, clip);
                                canvas.set_pixel_clipped(mid + 1, ink_y - 2, on, clip);
                            }
                            PixelAccent::DotAbove => {
                                canvas.set_pixel_clipped(mid, ink_y - 2, on, clip);
                            }
                            PixelAccent::Slash => {
                                let top_x = cx + (gw - 1).min(4);
                                for i in 0..5 {
                                    canvas.set_pixel_clipped(top_x - i, ink_y + i, on, clip);
                                }
                            }
                            PixelAccent::Cedilla => {
                                canvas.set_pixel_clipped(mid, ink_y + 5, on, clip);
                                canvas.set_pixel_clipped(mid - 1, ink_y + 6, on, clip);
                            }
                        }
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
            // Combining diacritics & zero-width formatting chars: drop cleanly
            '\u{0300}'..='\u{036F}' | '\u{200B}'..='\u{200F}' | '\u{FEFF}' => {}

            // Turkish & common Latin-1 / Extended-A accented letters
            'á' | 'à' | 'â' | 'ä' | 'ã' | 'å' | 'ā' | 'ă' | 'ą' => out.push('a'),
            'Á' | 'À' | 'Â' | 'Ä' | 'Ã' | 'Å' | 'Ā' | 'Ă' | 'Ą' => out.push('A'),
            'ç' | 'ć' | 'č' | 'ĉ' | 'ċ' => out.push('c'),
            'Ç' | 'Ć' | 'Č' | 'Ĉ' | 'Ċ' => out.push('C'),
            'ď' | 'đ' | 'ð' => out.push('d'),
            'Ď' | 'Đ' | 'Ð' => out.push('D'),
            'é' | 'è' | 'ê' | 'ë' | 'ē' | 'ĕ' | 'ė' | 'ę' | 'ě' => out.push('e'),
            'É' | 'È' | 'Ê' | 'Ë' | 'Ē' | 'Ĕ' | 'Ė' | 'Ę' | 'Ě' => out.push('E'),
            'ğ' | 'ĝ' | 'ġ' | 'ģ' => out.push('g'),
            'Ğ' | 'Ĝ' | 'Ġ' | 'Ģ' => out.push('G'),
            'ĥ' | 'ħ' => out.push('h'),
            'Ĥ' | 'Ħ' => out.push('H'),
            'í' | 'ì' | 'î' | 'ï' | 'ı' | 'ĩ' | 'ī' | 'ĭ' | 'į' => out.push('i'),
            'Í' | 'Ì' | 'Î' | 'Ï' | 'İ' | 'Ĩ' | 'Ī' | 'Ĭ' | 'Į' => out.push('I'),
            'ĵ' => out.push('j'),
            'Ĵ' => out.push('J'),
            'ķ' => out.push('k'),
            'Ķ' => out.push('K'),
            'ĺ' | 'ļ' | 'ľ' | 'ł' => out.push('l'),
            'Ĺ' | 'Ļ' | 'Ľ' | 'Ł' => out.push('L'),
            'ñ' | 'ń' | 'ņ' | 'ň' => out.push('n'),
            'Ñ' | 'Ń' | 'Ņ' | 'Ň' => out.push('N'),
            'ó' | 'ò' | 'ô' | 'ö' | 'õ' | 'ø' | 'ō' | 'ŏ' | 'ő' => out.push('o'),
            'Ó' | 'Ò' | 'Ô' | 'Ö' | 'Õ' | 'Ø' | 'Ō' | 'Ŏ' | 'Ő' => out.push('O'),
            'ŕ' | 'ŗ' | 'ř' => out.push('r'),
            'Ŕ' | 'Ŗ' | 'Ř' => out.push('R'),
            'ş' | 'ś' | 'ŝ' | 'š' => out.push('s'),
            'Ş' | 'Ś' | 'Ŝ' | 'Š' => out.push('S'),
            'ţ' | 'ť' | 'ŧ' => out.push('t'),
            'Ţ' | 'Ť' | 'Ŧ' => out.push('T'),
            'ú' | 'ù' | 'û' | 'ü' | 'ũ' | 'ū' | 'ŭ' | 'ů' | 'ű' | 'ų' => out.push('u'),
            'Ú' | 'Ù' | 'Û' | 'Ü' | 'Ũ' | 'Ū' | 'Ŭ' | 'Ů' | 'Ű' | 'Ų' => out.push('U'),
            'ŵ' => out.push('w'),
            'Ŵ' => out.push('W'),
            'ý' | 'ÿ' | 'ŷ' => out.push('y'),
            'Ý' | 'Ÿ' | 'Ŷ' => out.push('Y'),
            'ź' | 'ż' | 'ž' => out.push('z'),
            'Ź' | 'Ż' | 'Ž' => out.push('Z'),
            'æ' => out.push_str("ae"),
            'Æ' => out.push_str("AE"),
            'œ' => out.push_str("oe"),
            'Œ' => out.push_str("OE"),
            'ß' => out.push_str("ss"),

            // Punctuation & symbols missing from MunroSmall.ttf
            '—' | '–' | '−' | '·' | '•' => out.push('-'),
            '`' | '‘' | '’' | '‚' | '´' => out.push('\''),
            '“' | '”' | '„' => out.push('"'),
            '…' => out.push_str("..."),
            '×' => out.push('x'),
            '°' | ' ' => out.push(ch),
            '\u{00A0}' => out.push(' '),
            '!'..='~' => out.push(ch),
            _ => {}
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

#[cfg(test)]
mod tests {
    use super::{extract_munro_accents, normalize_text, PixelAccent};

    #[test]
    fn normalizes_accented_and_unsupported_chars() {
        assert_eq!(normalize_text("LÉON"), "LEON");
        assert_eq!(normalize_text("LE\u{0301}ON"), "LEON");
        assert_eq!(normalize_text("LØN — Café"), "LON - Cafe");
        assert_eq!(normalize_text("56° 🔥"), "56° ");
        assert_eq!(
            extract_munro_accents("LÉON"),
            vec![(1, PixelAccent::Acute)]
        );
        assert_eq!(
            extract_munro_accents("LE\u{0301}ON"),
            vec![(1, PixelAccent::Acute)]
        );
        assert_eq!(
            extract_munro_accents("MØ - Şebnem"),
            vec![(1, PixelAccent::Slash), (5, PixelAccent::Cedilla)]
        );
    }
}
