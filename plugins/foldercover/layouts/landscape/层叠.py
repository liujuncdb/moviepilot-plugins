"""横版 16:9 · 层叠（多图）。

左侧一条窄文字栏，右侧把三张图斜着叠成一摞（最上面一张完整，其余允许被压角）。
底色是从画面取色的深色场，不用模糊图，避免整幅糊成一片。
"""
from PIL import Image, ImageDraw

from .._type import (
    caps, draw_block, fit_block, meta_of, rule, title_box, title_text,
)
from .._spec import margin as sys_margin, meta_px, system_field, title_px
from ._kit import collect_posters, contain, paste_card, rotated


def get_schema():
    return [
        {"group": "版式", "items": [
            {"key": "card_count", "label": "叠放张数", "type": "range", "min": 2, "max": 4, "default": 3},
            {"key": "card_height", "label": "卡片高度 %", "type": "range", "min": 44, "max": 78, "default": 66},
            {"key": "card_angle", "label": "旋转角（规范锁定 0）", "type": "range", "min": 0, "max": 2, "default": 0},
            {"key": "text_width", "label": "文字栏宽度 %", "type": "range", "min": 28, "max": 46, "default": 38},
        ]},
        {"group": "文字", "items": [
            {"key": "kicker", "label": "顶部小字", "type": "text", "default": ""},
            {"key": "title", "label": "主标题", "type": "text", "default": ""},
            {"key": "subtitle", "label": "副标题", "type": "text", "default": ""},
            {"key": "meta_line", "label": "右下微信息", "type": "text", "default": ""},
            {"key": "title_size", "label": "主标题字号", "type": "range", "min": 28, "max": 48, "default": 44},
        ]},
    ]


def _card(ctx, ref, height, max_width, plate_rgb, pad):
    img = ctx.load_img(ref)
    if img is None:
        return None
    aspect = img.size[0] / max(1, img.size[1])
    h = int(height)
    w = int(h * aspect)
    if w > max_width:
        w = int(max_width)
        h = int(w / max(1.0, aspect))
    card = Image.new("RGBA", (max(2, w), max(2, h)), tuple(plate_rgb) + (255,))
    fitted = contain(img, max(1, w - pad * 2), max(1, h - pad * 2))
    card.paste(fitted, ((w - fitted.size[0]) // 2, (h - fitted.size[1]) // 2))
    return card


def render(ctx, bg, config, assets, fonts):
    W, H = bg.size
    refs = [r for r in collect_posters(assets) if r]
    if not refs and assets.get("bg_url"):
        refs = [assets["bg_url"]]
    first = ctx.load_img(refs[0]) if refs else None
    canvas, tone = system_field((W, H), dark=True)

    has_title = bool(title_text(config, assets))
    text_w = int(W * float(config.get("text_width", 38)) / 100.0) if has_title else 0
    margin = sys_margin(W, landscape=True)
    count = max(2, min(int(config.get("card_count", 3)), len(refs) or 1, 4))
    card_h = int(H * 0.700)
    angle = 0.0
    pad = int(W * 0.008)

    zone_l = margin + text_w
    zone_r = W - margin
    zone_w = zone_r - zone_l
    deck_cx = zone_l + zone_w // 2 + int(zone_w * 0.02)
    deck_cy = int(H * 0.50)
    max_w = int(zone_w * 0.92)

    slots = [(-0.14, -0.13, -angle), (0.10, -0.02, angle * 0.6), (0.0, 0.11, 0.0), (0.05, 0.02, angle * 0.3)]
    for index in range(count - 1, -1, -1):
        card = _card(ctx, refs[index % len(refs)], card_h, max_w, tone["plate"], pad)
        if card is None:
            continue
        dx, dy, deg = slots[min(index, len(slots) - 1)]
        turned = rotated(card, deg) if abs(deg) > 0.3 else card
        cx = deck_cx + int(zone_w * dx)
        cy = deck_cy + int(H * dy)
        cx = max(zone_l + turned.size[0] // 2 + 6, min(zone_r - turned.size[0] // 2 - 6, cx))
        cy = max(turned.size[1] // 2 + 10, min(H - turned.size[1] // 2 - 10, cy))
        paste_card(canvas, turned, (cx - turned.size[0] // 2, cy - turned.size[1] // 2),
                   shadow=0, shadow_opacity=0)

    draw = ImageDraw.Draw(canvas)
    text_top = int(H * (0.335 if has_title else 0.500))
    kicker = str(config.get("kicker") or "").strip()
    if kicker:
        caps(draw, kicker, (margin, text_top - int(H * 0.060)), max(13, int(H * 0.0165)),
             tone["dim"], 0.26)

    if has_title:
        accent_y = text_top - int(H * 0.024)
        rule(draw, (margin, accent_y), int(W * 0.030), tone["accent"] + (255,), max(2, int(H * 0.0022)))
        title_box(draw, config, assets, (margin, text_top), text_w - int(W * 0.012),
                  int(H * 0.200), title_px(W, config, landscape=True),
                  tone["ink"] + (255,), max_lines=2, leading=1.12)
        sub = str(config.get("subtitle") or "").strip()
        if sub:
            block = fit_block(sub, text_w - int(W * 0.012), int(H * 0.110), int(H * 0.0215),
                              max_lines=3, serif=False, leading=1.3, tracking_ratio=0.04)
            draw_block(draw, block, (margin, int(H * 0.640)), tone["dim"] + (255,))

    meta = meta_of(assets, config)
    if meta:
        caps(draw, meta, (margin, H - int(H * 0.062)), meta_px(W, landscape=True),
             tone["dim"], 0.16)

    return canvas
