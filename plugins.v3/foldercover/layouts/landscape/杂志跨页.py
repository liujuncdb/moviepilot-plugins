"""横版 16:9 · 杂志跨页（单图）。

左半一张装裱完整的图版，右半一条纸色文字栏，中间用一根发丝线分开。
更像作品集的内页，而不是海报：留白多、字号小、行距松。
"""
import re

from PIL import ImageDraw

from .._type import (
    aspect_of, caps, draw_block, fit_block, fitted_box, hero_ref, meta_of, plate,
    title_box, title_text,
)
from .._spec import margin as sys_margin, meta_px, photo, system_field, title_px


def get_schema():
    return [
        {"group": "版式", "items": [
            {"key": "plate_width", "label": "图版宽度 %", "type": "range", "min": 34, "max": 52, "default": 44},
            {"key": "plate_pad", "label": "图版内边 %", "type": "range", "min": 0, "max": 3, "default": 1},
            {"key": "shadow", "label": "图版投影 0-100", "type": "range", "min": 0, "max": 100, "default": 40},
            {"key": "paper_color", "label": "纸面底色（留空取画面色）", "type": "color", "default": ""},
        ]},
        {"group": "文字", "items": [
            {"key": "kicker", "label": "顶部小字", "type": "text", "default": ""},
            {"key": "title", "label": "主标题", "type": "text", "default": ""},
            {"key": "subtitle", "label": "副标题", "type": "text", "default": ""},
            {"key": "meta_line", "label": "右下微信息", "type": "text", "default": ""},
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

    margin = sys_margin(W, landscape=True)
    has_title = bool(title_text(config, assets))
    plate_w = int(W * float(config.get("plate_width", 48 if has_title else 64)) / 100.0)
    pad = int(W * float(config.get("plate_pad", 1)) / 100.0)
    box = (margin, int(H * 0.095), margin + plate_w, int(H * 0.905))
    photo(ctx, canvas, ref, box, border=True, zoom=1.02)

    col_x = margin + plate_w + int(W * 0.045)
    if has_title:
        draw.line([(col_x - int(W * 0.018), int(H * 0.12)),
               (col_x - int(W * 0.018), H - int(H * 0.12))], fill=tone["rule"] + (230,), width=1)
    col_w = W - col_x - margin

    kicker = str(config.get("kicker") or "").strip()
    if kicker:
        caps(draw, kicker, (col_x, int(H * 0.175)), max(13, int(H * 0.0165)), tone["dim"], 0.26)

    if has_title:
        title_box(draw, config, assets, (col_x, int(H * 0.215)), col_w, int(H * 0.235),
                  title_px(W, config, landscape=True), tone["ink"] + (255,),
                  max_lines=2, leading=1.16)
        block_sub = str(config.get("subtitle") or "").strip()
        if block_sub:
            sub = fit_block(block_sub, col_w, int(H * 0.175), int(H * 0.0225), max_lines=4,
                            serif=False, leading=1.35, tracking_ratio=0.03)
            draw_block(draw, sub, (col_x, int(H * 0.520)), tone["dim"] + (255,))

    meta = meta_of(assets, config)
    if meta:
        caps(draw, meta, (W - margin, H - int(H * 0.055)), meta_px(W, landscape=True),
             tone["dim"], 0.16, align="right")

    return canvas
