use eframe::egui::{self, Color32, CornerRadius, Margin, RichText, Stroke, Vec2};

// Monochrome Obsidian & Pure White Palette
pub const BG_ROOT: Color32 = Color32::from_rgb(9, 9, 11);         // #09090B
pub const BG_SIDEBAR: Color32 = Color32::from_rgb(14, 14, 17);   // #0E0E11
pub const BG_CARD: Color32 = Color32::from_rgb(20, 20, 24);      // #141418
pub const BG_ELEVATED: Color32 = Color32::from_rgb(28, 28, 34);  // #1C1C22
pub const BORDER: Color32 = Color32::from_rgb(38, 38, 46);       // #26262E
pub const BORDER_STRONG: Color32 = Color32::from_rgb(63, 63, 74);// #3F3F4A
pub const ACCENT: Color32 = Color32::from_rgb(255, 255, 255);    // #FFFFFF Pure White
pub const ACCENT_SOFT: Color32 = Color32::from_rgb(228, 228, 231); // #E4E4E7
pub const TEXT_MAIN: Color32 = Color32::from_rgb(250, 250, 250); // #FAFAFA
pub const TEXT_DIM: Color32 = Color32::from_rgb(142, 142, 154);  // #8E8E9A
pub const STATUS_OK: Color32 = Color32::from_rgb(34, 197, 94);   // #22C55E (dot only)
pub const STATUS_WARN: Color32 = Color32::from_rgb(245, 158, 11);// #F59E0B (dot only)
pub const DANGER: Color32 = Color32::from_rgb(239, 68, 68);      // #EF4444

pub fn apply_modern_theme(ctx: &egui::Context) {
    let mut style = (*ctx.style()).clone();
    style.visuals = egui::Visuals::dark();
    style.visuals.panel_fill = BG_ROOT;
    style.visuals.window_fill = BG_CARD;
    style.visuals.faint_bg_color = BG_SIDEBAR;
    style.visuals.extreme_bg_color = Color32::from_rgb(6, 6, 8);
    style.visuals.widgets.noninteractive.bg_fill = BG_CARD;
    style.visuals.widgets.noninteractive.bg_stroke = Stroke::new(1.0_f32, BORDER);
    style.visuals.widgets.noninteractive.fg_stroke = Stroke::new(1.0_f32, TEXT_MAIN);
    style.visuals.widgets.inactive.bg_fill = BG_ELEVATED;
    style.visuals.widgets.inactive.bg_stroke = Stroke::new(1.0_f32, BORDER);
    style.visuals.widgets.inactive.fg_stroke = Stroke::new(1.0_f32, TEXT_MAIN);
    style.visuals.widgets.hovered.bg_fill = Color32::from_rgb(37, 37, 45);
    style.visuals.widgets.hovered.bg_stroke = Stroke::new(1.0_f32, BORDER_STRONG);
    style.visuals.widgets.active.bg_fill = Color32::from_rgb(48, 48, 58);
    style.visuals.widgets.active.bg_stroke = Stroke::new(1.0_f32, ACCENT);
    style.visuals.selection.bg_fill = Color32::from_rgba_unmultiplied(255, 255, 255, 36);
    style.visuals.selection.stroke = Stroke::new(1.0_f32, ACCENT);
    style.spacing.item_spacing = Vec2::new(8.0, 8.0);
    style.spacing.button_padding = Vec2::new(12.0, 6.0);
    ctx.set_style(style);
}

pub fn card(ui: &mut egui::Ui, add_contents: impl FnOnce(&mut egui::Ui)) {
    egui::Frame::new()
        .fill(BG_CARD)
        .stroke(Stroke::new(1.0_f32, BORDER))
        .corner_radius(CornerRadius::same(10))
        .inner_margin(Margin::same(14))
        .show(ui, add_contents);
}

pub fn section_title(ui: &mut egui::Ui, title: &str, subtitle: &str) {
    ui.label(RichText::new(title).size(15.0).strong().color(TEXT_MAIN));
    if !subtitle.is_empty() {
        ui.label(RichText::new(subtitle).size(11.5).color(TEXT_DIM));
    }
    ui.add_space(4.0);
}

pub fn toggle_switch(ui: &mut egui::Ui, on: &mut bool) -> egui::Response {
    let desired_size = Vec2::new(40.0, 22.0);
    let (rect, mut response) = ui.allocate_exact_size(desired_size, egui::Sense::click());
    if response.clicked() {
        *on = !*on;
        response.mark_changed();
    }
    if ui.is_rect_visible(rect) {
        let how_on = ui.ctx().animate_bool(response.id, *on);
        let radius = rect.height() * 0.5;
        let bg = if *on {
            ACCENT
        } else {
            Color32::from_rgb(39, 39, 47)
        };
        ui.painter().rect_filled(rect, CornerRadius::same(radius as u8), bg);
        if !*on {
            ui.painter().rect_stroke(
                rect,
                CornerRadius::same(radius as u8),
                Stroke::new(1.0_f32, BORDER_STRONG),
                egui::StrokeKind::Inside,
            );
        }
        let knob_x = egui::lerp((rect.left() + radius)..=(rect.right() - radius), how_on);
        let knob_color = if *on {
            Color32::from_rgb(9, 9, 11)
        } else {
            Color32::from_rgb(161, 161, 170)
        };
        ui.painter()
            .circle_filled(egui::pos2(knob_x, rect.center().y), radius - 3.0, knob_color);
    }
    response
}

pub fn toggle_row(ui: &mut egui::Ui, label: &str, desc: &str, value: &mut bool) -> bool {
    let mut changed = false;
    ui.horizontal(|ui| {
        ui.vertical(|ui| {
            ui.label(RichText::new(label).size(13.0).color(TEXT_MAIN));
            if !desc.is_empty() {
                ui.label(RichText::new(desc).size(11.0).color(TEXT_DIM));
            }
        });
        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
            if toggle_switch(ui, value).changed() {
                changed = true;
            }
        });
    });
    changed
}

pub fn style_chip(ui: &mut egui::Ui, label: &str, selected: bool) -> bool {
    let fill = if selected { ACCENT } else { BG_ELEVATED };
    let stroke = if selected {
        Stroke::new(1.0_f32, ACCENT)
    } else {
        Stroke::new(1.0_f32, BORDER)
    };
    let text_col = if selected { BG_ROOT } else { ACCENT_SOFT };
    let rt = if selected {
        RichText::new(label).size(12.0).strong().color(text_col)
    } else {
        RichText::new(label).size(12.0).color(text_col)
    };
    let btn = egui::Button::new(rt)
        .fill(fill)
        .stroke(stroke)
        .corner_radius(CornerRadius::same(8))
        .min_size(Vec2::new(0.0, 28.0));
    ui.add(btn).clicked()
}
