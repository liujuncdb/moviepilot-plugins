"""竖版 2:3 · 柔彩（单图）。

一张浅色色场上的图版：底色不是死白，而是从画面色相里调出的奶油色 / 雾色，
图中完整显示。标题居中、字距略宽，像展览海报的 caption 区。
"""
from PIL import ImageDraw

from .._type import (
    aspect_of, caps, draw_block, fit_block, fitted_box, hero_ref, meta_of, plate,
    title_box, title_text,
)
from .._spec import margin as sys_margin, meta_px, photo, system_field, title_px


def get_schema():
    return [
        {"group": "版式", "items": [
            {"key": "plate_width", "label": "图版宽度 %", "type": "range", "min": 60, "max": 92, "default": 78},
            {"key": "plate_top", "label": "图版顶部 %", "type": "range", "min": 8, "max": 18, "default": 12},
            {"key": "tint", "label": "色场浓度 0-100", "type": "range", "min": 0, "max": 100, "default": 42},
            {"key": "shadow", "label": "图版投影 0-100", "type": "range", "min": 0, "max": 100, "default": 50},
        ]},
        {"group": "文字", "items": [
            {"key": "kicker", "label": "顶部小字", "type": "text", "default": ""},
            {"key": "title", "label": "主标题", "type": "text", "default": ""},
            {"key": "subtitle", "label": "副标题", "type": "text", "default": ""},
            {"key": "meta_line", "label": "底部微信息", "type": "text", "default": ""},
            {"key": "title_size", "label": "主标题字号", "type": "range", "min": 28, "max": 44, "default": 40},
        ]},
    ]


def render(ctx, bg, config, assets, fonts):
    W, H = bg.size
    ref, img = hero_ref(assets, ctx)
    canvas, tone = system_field((W, H), dark=False)
    draw = ImageDraw.Draw(canvas)

    has_title = bool(title_text(config, assets))
    width = W - sys_margin(W) * 2
    left = sys_margin(W)
    top = int(H * 0.085)
    bottom = int(H * (0.800 if has_title else 0.900))
    box = (left, top, left + width, bottom)
    photo(ctx, canvas, ref, box, border=True, zoom=1.02)

    kicker = str(config.get("kicker") or "").strip()
    if kicker:
        caps(draw, kicker, (W // 2, int(H * 0.062)), max(12, int(W * 0.0135)), tone["dim"], 0.32,
             align="center")

    if has_title:
        mark_y = max(int(H * 0.838), box[3] + int(H * 0.032))
        draw.rectangle([(W // 2 - int(W * 0.012), mark_y), (W // 2 + int(W * 0.012), mark_y + int(H * 0.0028))],
                       fill=tone["accent"] + (255,))
        title_box(draw, config, assets, (W // 2, mark_y + int(H * 0.020)), int(W * 0.78),
                  int(H * 0.100), title_px(W, config),
                  tone["ink"] + (255,), max_lines=2, align="center", leading=1.12)
        sub = str(config.get("subtitle") or "").strip()
        if sub:
            block = fit_block(sub, int(W * 0.72), int(H * 0.048), int(H * 0.0255),
                              max_lines=1, serif=False, leading=1.2, tracking_ratio=0.06)
            draw_block(draw, block, (W // 2, int(H * 0.842)), tone["dim"] + (255,), align="center")

    meta = meta_of(assets, config)
    if meta:
        caps(draw, meta, (W // 2, H - int(H * 0.045)), meta_px(W),
             tone["dim"], 0.18, align="center")

    return canvas
