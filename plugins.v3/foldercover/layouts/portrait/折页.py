"""竖版 2:3 · 折页（多图）。

规范后改为：页首标题，下方一张主图 + 三张方形小图，像一册摊开的折页。
全部裁切铺满、同间距、无旋转、无投影。
"""
from PIL import ImageDraw

from .._type import caps, meta_of, title_box, title_text
from .._spec import margin as sys_margin, meta_px, photo, system_field, title_px
from ._kit import collect_posters


def get_schema():
    return [
        {"group": "版式", "items": [
            {"key": "cell_gap", "label": "图版间距", "type": "range", "min": 4, "max": 16, "default": 8},
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
    canvas, tone = system_field((W, H), dark=True)
    draw = ImageDraw.Draw(canvas)

    margin = sys_margin(W)
    k = H / 1500.0
    gap = int(config.get("cell_gap", 8) or 8)
    title = title_text(config, assets)
    title_box(draw, config, assets, (margin, int(48 * k)), W - margin * 2, int(64 * k),
              title_px(W, config), tone["ink"] + (255,), max_lines=1, leading=1.06)
    meta = meta_of(assets, config) or f"{assets.get('count', 0)} 部"
    caps(draw, meta, (margin, int(116 * k)), meta_px(W), tone["dim"], 0.18)

    hero = refs[0] if refs else None
    photo(ctx, canvas, hero, (margin, int(168 * k), W - margin, int(788 * k)), border=False, zoom=1.06)

    side = (W - margin * 2 - gap) // 2
    top = int(804 * k)
    for i in range(2):
        x = margin + i * (side + gap)
        ref = refs[i + 1] if i + 1 < len(refs) else (refs[0] if refs else None)
        photo(ctx, canvas, ref, (x, top, x + side, top + side), border=False, zoom=1.04)

    return canvas
