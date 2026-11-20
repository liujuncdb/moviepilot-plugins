"""横版 16:9 · 影院宽幅（单图）。

横幅素材：整幅画面是一块宽银幕（contain 不裁切），文字压在左下，billing 收在右下。
竖幅素材（海报）：自动改成"左灯箱 + 右文字"的图文对开，不把海报裁成一条。
"""
from PIL import ImageDraw

from .._type import (
    aspect_of, caps, draw_block, fit_block, fitted_box, hero_ref, meta_of, plate, rule,
    title_box, title_text,
)
from .._spec import margin as sys_margin, meta_px, photo, system_field, title_px


def get_schema():
    return [
        {"group": "版式", "items": [
            {"key": "screen_height", "label": "横幅时银幕高度 %", "type": "range", "min": 56, "max": 80, "default": 68},
            {"key": "screen_top", "label": "横幅时银幕顶部 %", "type": "range", "min": 3, "max": 12, "default": 5},
            {"key": "poster_width", "label": "竖幅时灯箱宽度 %", "type": "range", "min": 26, "max": 44, "default": 33},
            {"key": "glow", "label": "幕布光晕 0-100", "type": "range", "min": 0, "max": 100, "default": 50},
        ]},
        {"group": "文字", "items": [
            {"key": "kicker", "label": "顶部小字", "type": "text", "default": ""},
            {"key": "title", "label": "主标题", "type": "text", "default": ""},
            {"key": "subtitle", "label": "副标题", "type": "text", "default": ""},
            {"key": "meta_line", "label": "右下微信息", "type": "text", "default": ""},
            {"key": "title_size", "label": "主标题字号", "type": "range", "min": 28, "max": 48, "default": 44},
        ]},
    ]


def render(ctx, bg, config, assets, fonts):
    W, H = bg.size
    ref, img = hero_ref(assets, ctx)
    canvas, tone = system_field((W, H), dark=True)
    draw = ImageDraw.Draw(canvas)

    margin = sys_margin(W, landscape=True)
    has_title = bool(title_text(config, assets))
    aspect = (img.size[0] / max(1, img.size[1])) if img is not None else 1.78

    if aspect >= 1.05:
        top = int(H * 0.050)
        bottom = int(H * (0.740 if has_title else 0.920))
        box = (margin, top, W - margin, bottom)
        photo(ctx, canvas, ref, box, border=False, zoom=1.03)
        text_left = margin
        text_top = box[3] + int(H * 0.035)
        max_w = W * 0.56
        max_h = int(H * 0.115) if has_title else 0
    else:
        pw = int(W * float(config.get("poster_width", 33)) / 100.0)
        photo(ctx, canvas, ref, (margin, int(H * 0.075), margin + pw, int(H * 0.935)), border=True)
        text_left = margin + pw + int(W * 0.035)
        text_top = int(H * (0.315 if has_title else 0.50))
        max_w = W - text_left - margin
        max_h = int(H * 0.34)

    kicker = str(config.get("kicker") or "").strip()
    if kicker:
        caps(draw, kicker, (text_left, text_top - int(H * 0.058)), max(14, int(H * 0.0175)),
             tone["dim"], 0.26)

    if has_title:
        accent_y = text_top - int(H * 0.022)
        rule(draw, (text_left, accent_y), int(W * 0.040), tone["accent"] + (255,), max(2, int(H * 0.0022)))
        title_box(draw, config, assets, (text_left, text_top), max_w, max_h,
                  title_px(W, config, landscape=True), tone["ink"] + (255,),
                  max_lines=2, leading=1.08)
        sub = str(config.get("subtitle") or "").strip()
        if sub:
            block = fit_block(sub, max_w, int(H * 0.060), int(H * 0.0230), max_lines=1,
                              serif=False, leading=1.2, tracking_ratio=0.05)
            y = text_top + (int(H * 0.075) if aspect >= 1.05 else int(H * 0.360))
            draw_block(draw, block, (text_left, min(y, int(H * 0.865))), tone["dim"] + (255,))

    meta = meta_of(assets, config)
    if meta:
        caps(draw, meta, (W - margin, H - int(H * 0.042)), meta_px(W, landscape=True),
             tone["dim"], 0.16, align="right")

    return canvas
