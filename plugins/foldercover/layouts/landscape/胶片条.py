"""横版 16:9 · 胶片条（多图）。

一排等高的画格，每格一张完整图片（contain 不裁切），像一段未剪的胶片；
齿孔只保留极细的一排点，不做成"假胶片"的廉价装饰。
"""
from PIL import Image, ImageDraw

from .._type import (
    caps, draw_block, fit_block, meta_of, rule, title_box, title_text,
)
from .._spec import margin as sys_margin, meta_px, system_field, title_px
from ._kit import collect_posters, contain


def get_schema():
    return [
        {"group": "版式", "items": [
            {"key": "frame_count", "label": "画格数量", "type": "range", "min": 2, "max": 4, "default": 3},
            {"key": "frame_height", "label": "画格高度 %", "type": "range", "min": 28, "max": 48, "default": 40},
            {"key": "strip_y", "label": "胶片中心位置 %", "type": "range", "min": 44, "max": 68, "default": 55},
            {"key": "strip_width", "label": "胶片宽度 %", "type": "range", "min": 72, "max": 94, "default": 88},
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
    refs = [r for r in collect_posters(assets) if r]
    if not refs and assets.get("bg_url"):
        refs = [assets["bg_url"]]
    first = ctx.load_img(refs[0]) if refs else None
    canvas, tone = system_field((W, H), dark=True)
    draw = ImageDraw.Draw(canvas)

    has_title = bool(title_text(config, assets))
    count = max(2, min(int(config.get("frame_count", 3)), 4))
    frame_h = int(H * 0.420)
    if not has_title:
        frame_h = int(frame_h * 1.18)
    gap = int(W * 0.006)
    pad = int(W * 0.004)
    strip_w = int(W * float(config.get("strip_width", 88)) / 100.0)
    frame_w = (strip_w - gap * (count - 1)) // count
    strip_x = (W - strip_w) // 2
    cy = int(H * float(config.get("strip_y", 55)) / 100.0)
    film_h = frame_h + pad * 4
    strip_y = cy - film_h // 2

    # 一条深色片基，只在画格四周露出一点
    draw.rectangle([(strip_x - pad * 2, strip_y), (strip_x + strip_w + pad * 2, strip_y + film_h)],
                   fill=(12, 12, 13, 255))
    # 齿孔：上下各一排细点
    hole_w = max(3, int(pad * 1.4))
    hole_h = max(3, int(pad * 1.0))
    for i in range(count * 4 + 1):
        hx = strip_x + int(i * strip_w / (count * 4)) - hole_w // 2
        if hx < strip_x or hx > strip_x + strip_w:
            continue
        for hy in (strip_y + pad // 2, strip_y + film_h - pad // 2 - hole_h):
            draw.rectangle([(hx, hy), (hx + hole_w, hy + hole_h)], fill=(38, 38, 40, 255))

    frame_top = strip_y + pad * 2
    for index in range(count):
        x = strip_x + index * (frame_w + gap)
        draw.rectangle([(x, frame_top), (x + frame_w, frame_top + frame_h)], fill=(24, 24, 26, 255))
        if index < len(refs):
            img = ctx.load_img(refs[index])
            if img is None:
                continue
            fitted = contain(img, frame_w - pad * 2, frame_h - pad * 2)
            canvas.paste(fitted, (x + (frame_w - fitted.size[0]) // 2,
                                  frame_top + (frame_h - fitted.size[1]) // 2))

    margin = sys_margin(W, landscape=True)
    kicker = str(config.get("kicker") or "").strip()
    title_top = strip_y - int(H * 0.115)
    if kicker:
        caps(draw, kicker, (margin, title_top - int(H * 0.052)), max(13, int(H * 0.0165)),
             tone["dim"], 0.26)

    if has_title:
        rule(draw, (margin, title_top - int(H * 0.014)), int(W * 0.028), tone["accent"] + (255,),
             max(2, int(H * 0.0022)))
        title_box(draw, config, assets, (margin, title_top), W * 0.60, int(H * 0.095),
                  title_px(W, config, landscape=True), tone["ink"] + (255,),
                  max_lines=1, leading=1.06)
        sub = str(config.get("subtitle") or "").strip()
        if sub:
            block = fit_block(sub, W * 0.56, int(H * 0.052), int(H * 0.0215), max_lines=1,
                              serif=False, leading=1.2, tracking_ratio=0.05)
            draw_block(draw, block, (margin, strip_y + film_h + int(H * 0.040)),
                       tone["dim"] + (255,))

    meta = meta_of(assets, config)
    if meta:
        caps(draw, meta, (W - margin, H - int(H * 0.048)), meta_px(W, landscape=True),
             tone["dim"], 0.16, align="right")

    return canvas
