use super::canvas::{Canvas128x40, OLED_WIDTH};
use super::fonts::{draw_font, measure_ttf, AlignH, TtfFontId};

/// Clean Modern Tech 12x12 CPU icon: symmetrical microchip die with 3 pins per side.
pub const ICON_CPU: &[&str] = &[
    "...#.##.#...",
    "...#.##.#...",
    "..########..",
    "##........##",
    "..#.####.#..",
    "##..####..##",
    "##..####..##",
    "..#.####.#..",
    "##........##",
    "..########..",
    "...#.##.#...",
    "...#.##.#...",
];

/// Clean Modern Tech 12x12 GPU icon: sleek graphics card shroud with fan + heatsink + PCIe tab.
pub const ICON_GPU: &[&str] = &[
    "............",
    ".##########.",
    "#..........#",
    "#.##..###..#",
    "#.##.#...#.#",
    "#.##.#.#.#.#",
    "#.##.#...#.#",
    "#.##..###..#",
    "#..........#",
    ".##########.",
    "..###..##...",
    "............",
];

/// Clean Modern Tech 12x12 RAM icon: crisp DIMM stick with 3 IC chips and bottom edge pins.
pub const ICON_RAM: &[&str] = &[
    "............",
    "............",
    ".##########.",
    "#..........#",
    "#.##.##.##.#",
    "#.##.##.##.#",
    "#.##.##.##.#",
    "#..........#",
    ".##########.",
    "..##.##.##..",
    "............",
    "............",
];

/// Speaker muted (12x12) with clean geometric X.
pub const ICON_SPEAKER_MUTE: &[&str] = &[
    "............",
    "....#.......",
    "...##.......",
    ".####.......",
    "#####..#...#",
    "#####...#.#.",
    "#####....#..",
    "#####...#.#.",
    ".####..#...#",
    "...##.......",
    "....#.......",
    "............",
];

/// Speaker low (12x12) with 1 clean wave.
pub const ICON_SPEAKER_LOW: &[&str] = &[
    "............",
    "....#.......",
    "...##.......",
    ".####.......",
    "#####..#....",
    "#####...#...",
    "#####...#...",
    "#####...#...",
    ".####..#....",
    "...##.......",
    "....#.......",
    "............",
];

/// Speaker mid (12x12) with 2 clean waves.
pub const ICON_SPEAKER_MID: &[&str] = &[
    "............",
    "....#.......",
    "...##.......",
    ".####....#..",
    "#####..#..#.",
    "#####...#.#.",
    "#####...#.#.",
    "#####...#.#.",
    ".####..#..#.",
    "...##....#..",
    "....#.......",
    "............",
];

/// Speaker high (12x12) with 3 clean waves.
pub const ICON_SPEAKER_HIGH: &[&str] = &[
    "............",
    "....#.......",
    "...##.....#.",
    ".####...#..#",
    "#####.#..#.#",
    "#####..#.#.#",
    "#####..#.#.#",
    "#####..#.#.#",
    ".####.#..#.#",
    "...##...#..#",
    "....#.....#.",
    "............",
];

/// Studio microphone ON (12x12): pill capsule + U-cradle + base.
pub const ICON_MIC_ON: &[&str] = &[
    "....####....",
    "...######...",
    "...######...",
    "...######...",
    ".#.######.#.",
    ".#..####..#.",
    ".#........#.",
    "..########..",
    ".....##.....",
    ".....##.....",
    "...######...",
    "............",
];

/// Studio microphone OFF (12x12): crisp diagonal slash with 1px black knockout margin.
pub const ICON_MIC_OFF: &[&str] = &[
    ".#..####....",
    "..#.#####...",
    "...#.#####..",
    "...##.####..",
    ".#..##.###.#",
    ".#...##.##.#",
    ".#....##..#.",
    "..#####.##..",
    ".....##..#..",
    ".....##...#.",
    "...######...",
    "............",
];

/// Spotify 18x18: clean circle with 3 smooth sound arcs.
pub const ICON_SPOTIFY_18: &[&str] = &[
    "......######......",
    "....##########....",
    "...############...",
    "..##############..",
    ".################.",
    ".####........####.",
    "###..########..###",
    "##################",
    "####..........####",
    "#####.######.#####",
    "##################",
    ".####........####.",
    ".#####.#####.####.",
    "..##############..",
    "..##############..",
    "...############...",
    "....##########....",
    "......######......",
];

/// YouTube 18x18: sleek rounded screen with centered crisp play triangle.
pub const ICON_YOUTUBE_18: &[&str] = &[
    "..................",
    "..................",
    "..##############..",
    ".#..............#.",
    "#................#",
    "#.....#..........#",
    "#.....###........#",
    "#.....#####......#",
    "#.....#######....#",
    "#.....#######....#",
    "#.....#####......#",
    "#.....###........#",
    "#.....#..........#",
    "#................#",
    ".#..............#.",
    "..##############..",
    "..................",
    "..................",
];

/// Generic Media 18x18: crisp standalone double-eighth music note (no outer box).
pub const ICON_MEDIA_18: &[&str] = &[
    "..................",
    ".........########.",
    "......###########.",
    "......###########.",
    "......##.......##.",
    "......##.......##.",
    "......##.......##.",
    "......##.......##.",
    "......##.......##.",
    "......##.......##.",
    "....####.....####.",
    "..######...######.",
    ".#######..#######.",
    ".#######..#######.",
    "..#####....#####..",
    "..................",
    "..................",
    "..................",
];

/// Compact 16x16 Spotify icon for CompactBar/SpectrumTicker.
pub const ICON_SPOTIFY_16: &[&str] = &[
    ".....######.....",
    "...##########...",
    "..############..",
    ".##############.",
    ".###........###.",
    "##..########..##",
    "################",
    "###..........###",
    "####.######.####",
    "################",
    ".###........###.",
    ".####.####.####.",
    "..############..",
    "...##########...",
    ".....######.....",
    "................",
];

/// Compact 16x16 YouTube icon.
pub const ICON_YOUTUBE_16: &[&str] = &[
    "................",
    "..############..",
    ".#............#.",
    "#..............#",
    "#....#.........#",
    "#....###.......#",
    "#....#####.....#",
    "#....#######...#",
    "#....#####.....#",
    "#....###.......#",
    "#....#.........#",
    "#..............#",
    ".#............#.",
    "..############..",
    "................",
    "................",
];

/// Compact 16x16 Generic Media icon: standalone double-eighth music note.
pub const ICON_MEDIA_16: &[&str] = &[
    "................",
    "........#######.",
    ".....##########.",
    ".....##########.",
    ".....##......##.",
    ".....##......##.",
    ".....##......##.",
    ".....##......##.",
    ".....##......##.",
    "...####....####.",
    ".######..######.",
    ".######..######.",
    "..####....####..",
    "................",
    "................",
    "................",
];

pub fn draw_battery_icon(canvas: &mut Canvas128x40, x: i32, y: i32, pct: u8) {
    let w = 18;
    let h = 9;
    // Clear the 20x9 area before drawing
    canvas.fill_rect(x, y, w + 2, h, false);

    // Outer rounded shell (columns x..x+17, rows y..y+8) + centered 2x3 positive terminal
    canvas.draw_rounded_rect(x, y, w, h, true);
    canvas.fill_rect(x + w, y + 3, 2, 3, true);

    // Smooth proportional fill with an exact 1px black breathing margin on all 4 sides
    let clamped = pct.min(100) as i32;
    let max_fill = w - 4; // 14px (columns x+2..x+15)
    let fill_w = if clamped == 0 {
        0
    } else {
        ((clamped * max_fill + 50) / 100).clamp(1, max_fill)
    };
    if fill_w > 0 {
        canvas.fill_rect(x + 2, y + 2, fill_w, h - 4, true);
    }
}

pub fn draw_battery(
    canvas: &mut Canvas128x40,
    x: i32,
    y: i32,
    pct: u8,
    show_percent: bool,
) {
    canvas.fill_rect(x - 4, y - 1, 28, if show_percent { 20 } else { 11 }, false);
    draw_battery_icon(canvas, x, y, pct);

    if show_percent {
        let label = format!("{}%", pct.min(100));
        let half = measure_ttf(TtfFontId::Verdana9, &label) / 2;
        let cx = (x + 10).min(OLED_WIDTH - 1 - half);
        draw_font(canvas, TtfFontId::Verdana9, cx, y + 11, &label, AlignH::Center, true);
    }
}

pub fn draw_battery_inline(
    canvas: &mut Canvas128x40,
    x: i32,
    y: i32,
    pct: u8,
    show_percent: bool,
) -> i32 {
    draw_battery_icon(canvas, x, y, pct);
    if show_percent {
        let label = format!("{}%", pct.min(100));
        draw_font(canvas, TtfFontId::Verdana9, x + 23, y + 1, &label, AlignH::Left, true);
        23 + measure_ttf(TtfFontId::Verdana9, &label)
    } else {
        20
    }
}
