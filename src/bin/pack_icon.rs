use std::fs;
use std::io::BufWriter;
use std::path::Path;

use image::{
    codecs::ico::{IcoEncoder, IcoFrame},
    imageops::FilterType,
    ExtendedColorType, Rgba,
};

fn sdf_rounded_rect(x: f32, y: f32, cx: f32, cy: f32, hw: f32, hh: f32, r: f32) -> f32 {
    let dx = (x - cx).abs() - hw + r;
    let dy = (y - cy).abs() - hh + r;
    let outside = (dx.max(0.0).powi(2) + dy.max(0.0).powi(2)).sqrt();
    let inside = dx.max(dy).min(0.0);
    outside + inside - r
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let src_path = args.get(1).expect("Usage: pack_icon <input_image_path>");
    let src = image::open(src_path).expect("open generated icon").to_rgba8();

    let size = 1024u32;
    let mut img = image::imageops::resize(&src, size, size, FilterType::Lanczos3);

    // Apply crisp antialiased rounded-squircle alpha mask (radius = 22%)
    let s = size as f32;
    let half = s * 0.48;
    let rad = s * 0.21;
    for y in 0..size {
        for x in 0..size {
            let d = sdf_rounded_rect(x as f32 + 0.5, y as f32 + 0.5, s * 0.5, s * 0.5, half, half, rad);
            if d > 0.0 {
                let cov = (1.0 - d).clamp(0.0, 1.0);
                let p = img.get_pixel_mut(x, y);
                let new_a = ((p[3] as f32) * cov).round() as u8;
                *p = Rgba([p[0], p[1], p[2], new_a]);
            }
        }
    }

    let assets_dir = Path::new("assets");
    fs::create_dir_all(assets_dir).expect("assets dir");
    img.save(assets_dir.join("app_icon.png"))
        .expect("save app_icon.png");

    let ico_sizes = [16u32, 24, 32, 48, 64, 128, 256];
    let mut frames = Vec::new();
    for sz in ico_sizes {
        let resized = image::imageops::resize(&img, sz, sz, FilterType::Lanczos3);
        let raw = resized.into_raw();
        frames.push(IcoFrame::as_png(&raw, sz, sz, ExtendedColorType::Rgba8).expect("ico frame"));
    }
    let ico_file = fs::File::create(assets_dir.join("app_icon.ico")).expect("create app_icon.ico");
    let encoder = IcoEncoder::new(BufWriter::new(ico_file));
    encoder.encode_images(&frames).expect("encode ico");

    println!("Packed assets/app_icon.png and assets/app_icon.ico from {}", src_path);
}
