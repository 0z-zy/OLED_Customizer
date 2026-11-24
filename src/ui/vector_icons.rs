use eframe::egui::{self, pos2, vec2, Color32, CornerRadius, Rect, Stroke};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum IconKind {
    Styles,
    Clock,
    Cpu,
    Keyboard,
    Sparkles,
    Logs,
    BrandOled,
}

pub fn paint_vector_icon(ui: &egui::Ui, rect: Rect, kind: IconKind, color: Color32) {
    let p = ui.painter();
    let c = rect.center();
    let r = rect.width().min(rect.height()) * 0.42;
    let st = Stroke::new(1.6_f32, color);

    match kind {
        IconKind::BrandOled => {
            let box_r = Rect::from_center_size(c, vec2(rect.width() * 0.9, rect.height() * 0.56));
            p.rect_stroke(box_r, CornerRadius::same(4), Stroke::new(1.8_f32, color), egui::StrokeKind::Middle);
            p.line_segment(
                [pos2(box_r.left() + 4.0, c.y), pos2(box_r.left() + 9.0, c.y)],
                Stroke::new(1.8_f32, color),
            );
            p.circle_filled(pos2(box_r.right() - 5.0, c.y), 2.0, color);
        }
        IconKind::Styles => {
            let half = r * 0.85;
            let gap = 2.2;
            let sz = vec2(half - gap * 0.5, half - gap * 0.5);
            for (dx, dy) in [(-1.0, -1.0), (1.0, -1.0), (-1.0, 1.0), (1.0, 1.0)] {
                let cell = Rect::from_center_size(
                    pos2(c.x + dx * (sz.x * 0.5 + gap * 0.5), c.y + dy * (sz.y * 0.5 + gap * 0.5)),
                    sz,
                );
                p.rect_stroke(cell, CornerRadius::same(2), st, egui::StrokeKind::Middle);
            }
        }
        IconKind::Clock => {
            p.circle_stroke(c, r, st);
            p.line_segment([c, pos2(c.x, c.y - r * 0.55)], st);
            p.line_segment([c, pos2(c.x + r * 0.45, c.y + r * 0.15)], st);
        }
        IconKind::Cpu => {
            let die = Rect::from_center_size(c, vec2(r * 1.3, r * 1.3));
            p.rect_stroke(die, CornerRadius::same(2), st, egui::StrokeKind::Middle);
            p.rect_filled(Rect::from_center_size(c, vec2(r * 0.45, r * 0.45)), CornerRadius::same(1), color);
            for off in [-r * 0.32, r * 0.32] {
                p.line_segment([pos2(die.left(), c.y + off), pos2(die.left() - 3.0, c.y + off)], st);
                p.line_segment([pos2(die.right(), c.y + off), pos2(die.right() + 3.0, c.y + off)], st);
                p.line_segment([pos2(c.x + off, die.top()), pos2(c.x + off, die.top() - 3.0)], st);
                p.line_segment([pos2(c.x + off, die.bottom()), pos2(c.x + off, die.bottom() + 3.0)], st);
            }
        }
        IconKind::Keyboard => {
            let kb = Rect::from_center_size(c, vec2(r * 2.0, r * 1.3));
            p.rect_stroke(kb, CornerRadius::same(2), st, egui::StrokeKind::Middle);
            for x_f in [-0.45, 0.0, 0.45] {
                p.circle_filled(pos2(c.x + x_f * r, c.y - r * 0.2), 1.1, color);
            }
            p.line_segment(
                [pos2(c.x - r * 0.45, c.y + r * 0.28), pos2(c.x + r * 0.45, c.y + r * 0.28)],
                st,
            );
        }
        IconKind::Sparkles => {
            // 4-point star
            p.line_segment([pos2(c.x, c.y - r), pos2(c.x, c.y + r)], st);
            p.line_segment([pos2(c.x - r, c.y), pos2(c.x + r, c.y)], st);
            let d = r * 0.55;
            p.line_segment([pos2(c.x - d, c.y - d), pos2(c.x + d, c.y + d)], Stroke::new(1.2_f32, color));
            p.line_segment([pos2(c.x - d, c.y + d), pos2(c.x + d, c.y - d)], Stroke::new(1.2_f32, color));
        }
        IconKind::Logs => {
            let doc = Rect::from_center_size(c, vec2(r * 1.45, r * 1.75));
            p.rect_stroke(doc, CornerRadius::same(2), st, egui::StrokeKind::Middle);
            for dy in [-0.4, 0.0, 0.4] {
                p.line_segment(
                    [pos2(doc.left() + 3.0, c.y + dy * r), pos2(doc.right() - 3.0, c.y + dy * r)],
                    Stroke::new(1.3_f32, color),
                );
            }
        }
    }
}
