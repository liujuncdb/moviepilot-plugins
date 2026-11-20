"""竖版 2:3 · 叠片（多图）。

规范后改为：暖纸底、2×2 等比例图版，行间错开 12px 制造"叠放"的层次，
但没有旋转、没有投影。标题只在页脚出现一次。
"""
from PIL import ImageDraw

from .._type import caps, meta_of, title_box, title_text
from .._spec import margin as sys_margin, meta_px, photo, system_field, title_px
from ._kit import collect_posters


def get_schema():
    return [
        {"group": "版式", "items": [
            {"key": "cell_gap", "label": "图版间距", "type": "range", "min": 4, "max": 16, "default": 8},
            {"key": "stagger", "label": "第二行错位 px", "type": "range", "min": 0, "max": 32, "default": 0},
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
    refs = [r for r in collect_posters(assets) if r]
    if not refs and assets.get("bg_url"):
        refs = [assets["bg_url"]]
    canvas, tone = system_field((W, H), dark=False)
    draw = ImageDraw.Draw(canvas)

    margin = sys_margin(W)
    gap = int(config.get("cell_gap", 8) or 8)
    stagger = int(config.get("stagger", 0) or 0)
    cell_w = (W - margin * 2 - gap) // 2
    cell_h = int(H * 0.320)
    top = int(H * 0.064)

    for index in range(4):
        col, row = index % 2, index // 2
        x = margin + col * (cell_w + gap)
        y = top + row * (cell_h + gap)
        if row == 1 and col == 1:
            x += stagger
        ref = refs[index] if index < len(refs) else (refs[0] if refs else None)
        photo(ctx, canvas, ref, (x, y, x + cell_w, y + cell_h), border=False, zoom=1.04)

    kicker = str(config.get("kicker") or "").strip()
    if kicker:
        caps(draw, kicker, (margin, top - int(H * 0.024)), meta_px(W), tone["dim"], 0.24)

    title = title_text(config, assets)
    if title:
        title_box(draw, config, assets, (margin, H - int(H * 0.200)), W - margin * 2, int(H * 0.064),
                  title_px(W, config), tone["ink"] + (255,), max_lines=1, leading=1.06)
    meta = meta_of(assets, config)
    if meta:
        caps(draw, meta, (margin, H - int(H * 0.064)), meta_px(W), tone["dim"], 0.18)

    return canvas
