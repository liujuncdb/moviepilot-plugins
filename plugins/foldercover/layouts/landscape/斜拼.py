"""横版 16:9 · 斜拼（多图）。

上排宽窄混排，中排三张严格 3:2，下排大小混排；整块略收，四周留纸白。
"""
from PIL import ImageDraw

from .._type import caps, meta_of, title_box, title_text
from .._spec import margin as sys_margin, meta_px, system_field, title_px
from .._collage import collage_cells, rank_refs
from ._kit import collect_posters

# 1440×810：横向分割线通贯全宽，纵向分割线错开
CELLS = (
    (0, 0, 720, 200), (720, 0, 720, 200),
    (0, 200, 480, 320), (480, 200, 480, 320), (960, 200, 480, 320),
    (0, 520, 720, 290), (720, 520, 720, 290),
)


def get_schema():
    return [
        {"group": "版式", "items": [
            {"key": "angle", "label": "网格倾斜角（度）", "type": "range", "min": 0, "max": 30, "default": 12},
            {"key": "gap", "label": "白缝宽度 px", "type": "range", "min": 2, "max": 20, "default": 5},
        ]},
        {"group": "文字", "items": [
            {"key": "title", "label": "主标题", "type": "text", "default": ""},
            {"key": "meta_line", "label": "微信息", "type": "text", "default": ""},
            {"key": "title_size", "label": "主标题字号", "type": "range", "min": 28, "max": 48, "default": 40},
        ]},
    ]


def render(ctx, bg, config, assets, fonts):
    W, H = bg.size
    refs = rank_refs([r for r in collect_posters(assets) if r])
    if not refs and assets.get("bg_url"):
        refs = [assets["bg_url"]]
    canvas, tone = system_field((W, H), dark=False)
    draw = ImageDraw.Draw(canvas)

    margin = sys_margin(W, landscape=True)
    s = W / 1920.0
    cw = int(1440 * s)
    left = (W - cw) // 2
    cells = [(int(x * s), int(y * s), int(cw * s), int(ch * s))
             for x, y, cw, ch in CELLS]
    gap = max(2, int(float(config.get("gap", 5) or 5) * s))
    title = title_text(config, assets)
    if title:
        title_box(draw, config, assets, (margin, int(H * 0.052)), W - margin * 2, int(H * 0.060),
                  title_px(W, config, landscape=True), tone["ink"] + (255,), max_lines=1, leading=1.04)
    meta = meta_of(assets, config)
    if meta:
        caps(draw, meta, (margin, int(H * 0.128)), meta_px(W, landscape=True), tone["dim"], 0.16)

    top = int(H * 0.195)
    collage_cells(ctx, canvas, refs, (left, top, left + cw, top + int(810 * s)),
                  cells, angle=float(config.get("angle", 12) or 0), gap=gap)
    return canvas
