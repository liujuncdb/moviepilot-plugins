"""竖版 2:3 · 剧场（单图）。

深色礼堂 + 一块亮着的银幕。底色从画面色相压出深调（不是纯黑），
银幕内图完整显示；标题落在幕布下沿，像一张院线 one-sheet 的 billing 区。
"""
import colorsys

from PIL import ImageDraw

from .._type import (
    aspect_of, caps, draw_block, fit_block, fitted_box, hero_ref, meta_of, plate, rule,
    title_box, title_text,
)
from .._spec import margin as sys_margin, meta_px, photo, system_field, title_px


def get_schema():
    return [
        {"group": "版式", "items": [
            {"key": "screen_top", "label": "银幕顶部 %", "type": "range", "min": 4, "max": 14, "default": 8},
            {"key": "screen_height", "label": "银幕高度 %", "type": "range", "min": 46, "max": 72, "default": 56},
            {"key": "screen_pad", "label": "银幕内边 %", "type": "range", "min": 0, "max": 4, "default": 2},
            {"key": "glow", "label": "幕布光晕 0-100", "type": "range", "min": 0, "max": 100, "default": 45},
        ]},
        {"group": "文字", "items": [
            {"key": "kicker", "label": "顶部小字（幕上方）", "type": "text", "default": ""},
            {"key": "title", "label": "主标题", "type": "text", "default": ""},
            {"key": "subtitle", "label": "副标题", "type": "text", "default": ""},
            {"key": "meta_line", "label": "底部微信息", "type": "text", "default": ""},
            {"key": "title_size", "label": "主标题字号", "type": "range", "min": 28, "max": 44, "default": 40},
        ]},
    ]


def render(ctx, bg, config, assets, fonts):
    W, H = bg.size
    ref, img = hero_ref(assets, ctx)
    canvas, tone = system_field((W, H), dark=True)

    draw = ImageDraw.Draw(canvas)
    margin = sys_margin(W)
    has_title = bool(title_text(config, assets))

    top = int(H * 0.050)
    bottom = int(H * (0.780 if has_title else 0.920))
    box = (margin, top, W - margin, bottom)
    photo(ctx, canvas, ref, box, border=False, zoom=1.04)

    kicker = str(config.get("kicker") or "").strip()
    if kicker:
        caps(draw, kicker, (margin, int(H * 0.046)), max(13, int(W * 0.0145)),
             tone["dim"], 0.26)

    if has_title:
        accent_y = max(int(H * 0.812), box[3] + int(H * 0.036))
        rule(draw, (margin, accent_y), int(W * 0.070), tone["accent"] + (255,), max(2, int(H * 0.0026)))
        title_box(draw, config, assets, (margin, accent_y + int(H * 0.022)), W - margin * 2,
                  int(H * 0.092), title_px(W, config),
                  tone["ink"] + (255,), max_lines=2, leading=1.10)
        sub = str(config.get("subtitle") or "").strip()
        if sub:
            block = fit_block(sub, W - margin * 2, int(H * 0.048), int(H * 0.0245),
                              max_lines=1, serif=False, leading=1.2, tracking_ratio=0.05)
            draw_block(draw, block, (margin, int(H * 0.918)), tone["dim"] + (255,))
    meta = meta_of(assets, config)
    if meta:
        caps(draw, meta, (W - margin, H - int(H * 0.042)), meta_px(W),
             tone["dim"], 0.16, align="right")

    return canvas
