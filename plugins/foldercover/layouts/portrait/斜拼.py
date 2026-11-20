"""竖版 2:3 · 斜拼（多图）。

整块斜网格：上排宽窄混排，中排三张严格 3:2，下排大小混排。
标题在上方，整块四周留足纸白。
"""
import hashlib

from PIL import ImageDraw

from .._type import caps, meta_of, title_box, title_text
from .._spec import margin as sys_margin, meta_px, system_field, title_px
from .._collage import collage_cells, rank_refs
from ._kit import collect_posters

# 目标 840×1200（2:3 竖向）。左右两列分行线错开，大小图交替。
# 每组 6–7 张，按文件夹路径稳定选一组，不同文件夹会得到不同错落。
PATTERNS = [
    # 左列 500 宽，右列 340 宽；纵向分割线齐平，横向错落
    (
        (0, 0, 500, 480), (0, 480, 500, 340), (0, 820, 500, 380),
        (500, 0, 340, 600), (500, 600, 340, 600),
    ),
    # 左窄右宽，大小图对调
    (
        (0, 0, 360, 600), (0, 600, 360, 600),
        (360, 0, 480, 400), (360, 400, 480, 400), (360, 800, 480, 400),
    ),
]


def get_schema():
    return [
        {"group": "版式", "items": [
            {"key": "angle", "label": "网格倾斜角（度，竖版向左上）", "type": "range", "min": 0, "max": 30, "default": 12},
            {"key": "gap", "label": "白缝宽度 px", "type": "range", "min": 2, "max": 20, "default": 4},
        ]},
        {"group": "文字", "items": [
            {"key": "title", "label": "主标题", "type": "text", "default": ""},
            {"key": "meta_line", "label": "微信息", "type": "text", "default": ""},
            {"key": "title_size", "label": "主标题字号", "type": "range", "min": 24, "max": 44, "default": 36},
        ]},
    ]


def render(ctx, bg, config, assets, fonts):
    W, H = bg.size
    refs = rank_refs([r for r in collect_posters(assets) if r])
    if not refs and assets.get("bg_url"):
        refs = [assets["bg_url"]]
    canvas, tone = system_field((W, H), dark=False)
    draw = ImageDraw.Draw(canvas)

    s = W / 1000.0
    margin = int(W * 0.08)
    cw = int(840 * s)
    key = str(assets.get("path") or assets.get("title") or "")
    idx = int(hashlib.md5(key.encode("utf-8")).hexdigest()[:8], 16) % len(PATTERNS)
    cells = [(int(x * s), int(y * s), int(cw * s), int(ch * s))
             for x, y, cw, ch in PATTERNS[idx]]
    gap = max(2, int(float(config.get("gap", 4) or 4) * s))
    title = title_text(config, assets)
    if title:
        title_box(draw, config, assets, (margin, int(H * 0.066)), W - margin * 2, int(H * 0.048),
                  title_px(W, config), tone["ink"] + (255,), max_lines=1, leading=1.04)
    meta = meta_of(assets, config)
    if meta:
        caps(draw, meta, (margin, int(H * 0.112)), meta_px(W), tone["dim"], 0.16)

    top = int(H * 0.166)
    collage_cells(ctx, canvas, refs, (margin, top, margin + cw, top + int(1200 * s)),
                  cells, angle=-float(config.get("angle", 12) or 0), gap=gap)
    return canvas
