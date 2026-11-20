"""竖版 2:3 · 网格（多图）。

像一张胶片接触印样：严格的 2 列网格，每格一张完整图片（contain 不裁切），
页眉放标题、页脚放数量。格子用统一底色 letterbox，横屏截图与竖幅海报都能共存。
"""
from PIL import ImageDraw

from .._type import (
    aspect_of, caps, draw_block, fit_block, meta_of, plate, rule, title_box, title_text,
)
from .._spec import margin as sys_margin, meta_px, system_field, title_px
from ._kit import collect_posters


def get_schema():
    return [
        {"group": "版式", "items": [
            {"key": "rows", "label": "行数", "type": "range", "min": 2, "max": 4, "default": 3},
            {"key": "cell_gap", "label": "格间距 %", "type": "range", "min": 1, "max": 5, "default": 2},
            {"key": "cell_pad", "label": "格内留边 %", "type": "range", "min": 0, "max": 4, "default": 2},
            {"key": "show_frame", "label": "是否画细边框 0/1", "type": "range", "min": 0, "max": 1, "default": 1},
        ]},
        {"group": "文字", "items": [
            {"key": "kicker", "label": "顶部小字", "type": "text", "default": ""},
            {"key": "title", "label": "主标题", "type": "text", "default": ""},
            {"key": "subtitle", "label": "页脚说明", "type": "text", "default": ""},
            {"key": "meta_line", "label": "底部微信息", "type": "text", "default": ""},
            {"key": "title_size", "label": "主标题字号", "type": "range", "min": 28, "max": 44, "default": 40},
        ]},
    ]


def render(ctx, bg, config, assets, fonts):
    W, H = bg.size
    refs = [r for r in collect_posters(assets) if r]
    if not refs and assets.get("bg_url"):
        refs = [assets["bg_url"]]
    first = ctx.load_img(refs[0]) if refs else None
    canvas, tone = system_field((W, H), dark=False)
    draw = ImageDraw.Draw(canvas)

    margin = sys_margin(W)
    has_title = bool(title_text(config, assets))
    kicker = str(config.get("kicker") or "").strip()
    if kicker:
        caps(draw, kicker, (margin, int(H * 0.046)), max(12, int(W * 0.0135)), tone["dim"], 0.28)

    head_bottom = int(H * 0.135 if has_title else H * 0.075)
    if has_title:
        title_box(draw, config, assets, (margin, int(H * 0.068)), W - margin * 2,
                  int(H * 0.072), title_px(W, config),
                  tone["ink"] + (255,), max_lines=1, leading=1.06)
        rule(draw, (margin, int(H * 0.140)), W - margin * 2, tone["rule"] + (255,), max(1, int(H * 0.0012)))

    rows = max(2, min(int(config.get("rows", 3)), 4))
    gap = 8
    pad = 8
    grid_top = int(H * (0.190 if has_title else 0.095))
    grid_bottom = int(H * 0.880)
    cell_w = (W - margin * 2 - gap) // 2
    aspect = aspect_of(first, 1.78)
    avail = grid_bottom - grid_top - gap * (rows - 1)
    cell_h = int(min(cell_w / max(0.5, aspect) * 1.22, avail / rows))
    block_h = cell_h * rows + gap * (rows - 1)
    start_y = grid_top + max(0, (avail - block_h) // 2)
    show_frame = int(config.get("show_frame", 1))

    for index in range(rows * 2):
        col, row = index % 2, index // 2
        x = margin + col * (cell_w + gap)
        y = start_y + row * (cell_h + gap)
        box = (x, y, x + cell_w, y + cell_h)
        ref = refs[index] if index < len(refs) else None
        plate(canvas, ctx, ref, box, tone["plate"], pad=pad, shadow=0,
              border=(tone["rule"] + (255,)) if show_frame else None)

    sub = str(config.get("subtitle") or "").strip()
    if sub:
        block = fit_block(sub, W - margin * 2, int(H * 0.040), int(H * 0.0235),
                          max_lines=1, serif=False, leading=1.2, tracking_ratio=0.03)
        draw_block(draw, block, (margin, int(H * 0.905)), tone["dim"] + (255,))

    meta = meta_of(assets, config)
    if meta:
        caps(draw, meta, (W - margin, H - int(H * 0.040)), meta_px(W),
             tone["dim"], 0.16, align="right")

    return canvas
