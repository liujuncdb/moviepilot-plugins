"""竖版 2:3 · 画框（单图）。

一张装裱好的艺术微喷：宽纸边、细线框，图版占视觉重量约七成，
标题落在纸面下沿左对齐，字号克制。图永远完整显示（contain 不裁切），
横屏截图与竖幅海报都不会被切边。
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
            {"key": "plate_pad", "label": "图版留边 %", "type": "range", "min": 1, "max": 6, "default": 3},
            {"key": "plate_top", "label": "图版顶部 %", "type": "range", "min": 6, "max": 14, "default": 9},
            {"key": "shadow", "label": "图版投影 0-100", "type": "range", "min": 0, "max": 100, "default": 45},
            {"key": "paper_color", "label": "纸面底色（留空取画面色）", "type": "color", "default": ""},
        ]},
        {"group": "文字", "items": [
            {"key": "kicker", "label": "顶部小字", "type": "text", "default": ""},
            {"key": "title", "label": "主标题", "type": "text", "default": ""},
            {"key": "subtitle", "label": "副标题", "type": "text", "default": ""},
            {"key": "meta_line", "label": "底部微信息", "type": "text", "default": ""},
            {"key": "title_size", "label": "主标题字号", "type": "range", "min": 28, "max": 44, "default": 40},
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
    paper = _hex(config.get("paper_color"))
    if paper:
        tone["field"] = paper
        tone["field2"] = tuple(int(v * 0.955 + 255 * 0.045) for v in paper)
    draw = ImageDraw.Draw(canvas)

    margin = sys_margin(W)
    kicker = str(config.get("kicker") or "").strip()
    if kicker:
        caps(draw, kicker, (margin, int(H * 0.056)), max(13, int(W * 0.0150)), tone["dim"], 0.24)

    has_title = bool(title_text(config, assets))
    box = (margin, int(H * 0.075), W - margin, int(H * (0.800 if has_title else 0.900)))
    photo(ctx, canvas, ref, box, border=True, zoom=1.0)

    if has_title:
        rule_y = max(int(H * 0.840), box[3] + int(H * 0.036))
        rule(draw, (margin, rule_y), int(W * 0.078), tone["accent"] + (255,), max(2, int(H * 0.0026)))
        ink = tone["ink"] + (255,)
        title_top = rule_y + int(H * 0.024)
        title_box(draw, config, assets, (margin, title_top), W - margin * 2,
                  int(H * 0.100), title_px(W, config), ink,
                  max_lines=2, leading=1.10)
        sub = str(config.get("subtitle") or "").strip()
        if sub:
            block = fit_block(sub, W - margin * 2, int(H * 0.046), int(H * 0.0250),
                              max_lines=1, serif=False, leading=1.2, tracking_ratio=0.03)
            draw_block(draw, block, (margin, int(H * 0.912)), tone["dim"] + (255,))

    meta = meta_of(assets, config)
    if meta:
        caps(draw, meta, (W - margin, H - int(H * 0.042)), meta_px(W),
             tone["dim"], 0.16, align="right")

    return canvas
