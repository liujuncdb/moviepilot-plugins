"""横版 16:9 · 留白横幅（单图）。

接近白纸的底，图完整居中（contain 不裁切），标题用克制字号与宽字距压在下方。
在 Emby 列表里像一张安静的卡片，不跟内容抢注意力。
"""
import re

from PIL import ImageDraw

from .._type import (
    aspect_of, caps, draw_block, fit_block, fitted_box, hero_ref, meta_of, plate, rule,
    title_box, title_text,
)
from .._spec import margin as sys_margin, meta_px, photo, system_field, title_px


def get_schema():
    return [
        {"group": "版式", "items": [
            {"key": "image_width", "label": "画面宽度 %", "type": "range", "min": 26, "max": 52, "default": 40},
            {"key": "image_height", "label": "画面高度 %", "type": "range", "min": 42, "max": 66, "default": 56},
            {"key": "image_top", "label": "画面顶部 %", "type": "range", "min": 6, "max": 16, "default": 10},
            {"key": "paper_color", "label": "纸面底色（留空取画面色）", "type": "color", "default": ""},
        ]},
        {"group": "文字", "items": [
            {"key": "kicker", "label": "顶部小字", "type": "text", "default": ""},
            {"key": "title", "label": "主标题", "type": "text", "default": ""},
            {"key": "subtitle", "label": "副标题", "type": "text", "default": ""},
            {"key": "meta_line", "label": "底部微信息", "type": "text", "default": ""},
            {"key": "title_size", "label": "主标题字号", "type": "range", "min": 28, "max": 48, "default": 44},
        ]},
    ]


def _hex(value):
    text = str(value or "").strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6:
        return None
    try:
        return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def render(ctx, bg, config, assets, fonts):
    W, H = bg.size
    ref, img = hero_ref(assets, ctx)
    canvas, tone = system_field((W, H), dark=False)
    draw = ImageDraw.Draw(canvas)

    has_title = bool(title_text(config, assets))
    iw = int(W * 0.520)
    ih = int(H * 0.640)
    if not has_title:
        ih = max(ih, int(H * 0.62))
    top = int(H * float(config.get("image_top", 10)) / 100.0)
    left = (W - iw) // 2
    box = (left, top, left + iw, top + ih)
    photo(ctx, canvas, ref, box, border=True, zoom=1.02)

    kicker = str(config.get("kicker") or "").strip()
    if kicker:
        caps(draw, kicker, (W // 2, int(H * 0.052)), max(12, int(H * 0.0155)), tone["dim"], 0.30,
             align="center")

    if has_title:
        title_top = top + ih + int(H * 0.040)
        title_box(draw, config, assets, (W // 2, title_top), int(W * 0.62),
                  int(H * 0.090), title_px(W, config, landscape=True),
                  tone["ink"] + (255,), max_lines=1, align="center", leading=1.08)
        rule_y = title_top + int(H * 0.058)
        draw.line([(W // 2 - int(W * 0.028), rule_y), (W // 2 + int(W * 0.028), rule_y)],
                  fill=tone["accent"] + (255,), width=max(2, int(H * 0.0022)))
        sub = str(config.get("subtitle") or "").strip()
        if sub:
            block = fit_block(sub, int(W * 0.58), int(H * 0.052), int(H * 0.0215),
                              max_lines=1, serif=False, leading=1.2, tracking_ratio=0.10)
            draw_block(draw, block, (W // 2, rule_y + int(H * 0.026)), tone["dim"] + (255,), align="center")

    meta = meta_of(assets, config)
    if meta:
        caps(draw, meta, (W // 2, H - int(H * 0.045)), meta_px(W, landscape=True),
             tone["dim"], 0.18, align="center")

    return canvas
