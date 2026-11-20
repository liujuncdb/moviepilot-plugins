"""横版 16:9 · 拼贴墙（多图）。

左侧严格网格：上半一张通栏大图，下半三张小图；三张小图的总宽 + 两条 8px 缝
恰好等于大图宽度。右侧文字收成一列，垂直居中，不再上下各留一块空。
"""
from PIL import ImageDraw

from .._type import caps, draw_block, fit_block, meta_of, rule, title_box, title_text
from .._spec import margin as sys_margin, meta_px, photo, system_field, title_px
from ._kit import collect_posters


def get_schema():
    return [
        {"group": "版式", "items": [
            {"key": "wall_width", "label": "图墙宽度 %", "type": "range", "min": 56, "max": 76, "default": 72},
        ]},
        {"group": "文字", "items": [
            {"key": "kicker", "label": "顶部小字", "type": "text", "default": ""},
            {"key": "title", "label": "主标题", "type": "text", "default": ""},
            {"key": "subtitle", "label": "副标题", "type": "text", "default": ""},
            {"key": "meta_line", "label": "底部微信息", "type": "text", "default": ""},
            {"key": "title_size", "label": "主标题字号", "type": "range", "min": 28, "max": 48, "default": 44},
        ]},
    ]


def render(ctx, bg, config, assets, fonts):
    W, H = bg.size
    refs = [r for r in collect_posters(assets) if r]
    if not refs and assets.get("bg_url"):
        refs = [assets["bg_url"]]
    canvas, tone = system_field((W, H), dark=False)
    draw = ImageDraw.Draw(canvas)

    margin = sys_margin(W, landscape=True)
    gap = 8
    has_title = bool(title_text(config, assets))
    wall_w = W - margin * 2 if not has_title else int(W * float(config.get("wall_width", 72)) / 100.0)
    wall = (margin, int(H * 0.070), margin + wall_w, int(H * 0.930))
    ww = wall[2] - wall[0]

    # 上半大图
    hero_h = int((wall[3] - wall[1]) * 0.62)
    photo(ctx, canvas, refs[0] if refs else None,
          (wall[0], wall[1], wall[2], wall[1] + hero_h), border=False, zoom=1.04)

    # 下半三张，总宽严格等于 ww
    small_w = (ww - gap * 2) // 3
    small_top = wall[1] + hero_h + gap
    for i in range(3):
        x = wall[0] + i * (small_w + gap)
        ref = refs[i + 1] if i + 1 < len(refs) else (refs[0] if refs else None)
        photo(ctx, canvas, ref, (x, small_top, x + small_w, wall[3]), border=False, zoom=1.04)

    if not has_title:
        return canvas

    # 右侧文字栏
    panel_x = wall[2] + int(W * 0.016)
    draw.rectangle([(panel_x, 0), (W, H)], fill=tone["paper"] + (255,))
    draw.line([(panel_x, int(H * 0.12)), (panel_x, int(H * 0.88))],
              fill=tone["rule"] + (220,), width=1)

    left = panel_x + int(W * 0.022)
    right = W - margin
    col_w = right - left

    # 垂直居中：先估一块高度，再落位
    kicker = str(config.get("kicker") or "").strip()
    sub = str(config.get("subtitle") or "").strip()
    meta = meta_of(assets, config)
    block_h = int(H * (0.34 if sub else 0.26))
    top = max(int(H * 0.16), (H - block_h) // 2)
    y = top

    if kicker:
        caps(draw, kicker, (left, y), meta_px(W, landscape=True), tone["dim"], 0.24)
        y += int(H * 0.055)

    rule(draw, (left, y), int(W * 0.026), tone["accent"] + (255,), max(2, int(H * 0.0022)))
    y += int(H * 0.026)
    bottom = title_box(draw, config, assets, (left, y), col_w, int(H * 0.180),
                       title_px(W, config, landscape=True), tone["ink"] + (255,),
                       max_lines=2, leading=1.12)
    y = bottom + int(H * 0.024)

    if sub:
        block = fit_block(sub, col_w, int(H * 0.130), int(H * 0.0185),
                          max_lines=3, serif=False, leading=1.32, tracking_ratio=0.03)
        draw_block(draw, block, (left, y), tone["dim"] + (255,))

    if meta:
        caps(draw, meta, (left, y),
             meta_px(W, landscape=True), tone["dim"], 0.16)

    return canvas
