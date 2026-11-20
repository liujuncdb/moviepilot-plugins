"""已部署模板的统一规范层（源自 Apple DESIGN.md 的摄影优先规则）。

所有版式共用：暖纸底 / 近黑墨 / 赭石单一强调色；页边距 48（竖）· 76（横）；
标题只有 40/32 一档，允许向下缩，不允许超过；微信息 13/12；
不旋转、不投影、不加装饰渐变。版式原有的构图保留，只换掉违反规范的参数。
"""
from PIL import Image

PAPER = (244, 241, 234)
INK = (28, 27, 25)
MUTED = (120, 114, 105)
HAIR = (223, 217, 206)
PLATE = (250, 248, 243)
ACCENT = (166, 90, 62)

DARK = (28, 27, 25)
DARK_PLATE = (35, 34, 32)
DARK_HAIR = (58, 55, 51)
DARK_DIM = (160, 153, 142)
ACCENT_ON_DARK = (201, 122, 90)


def system_field(size, dark=False):
    """返回 (画布, tone)。不取画面色、不做渐变，只给一个系统底色。"""
    if dark:
        canvas = Image.new("RGBA", size, DARK + (255,))
        tone = {
            "field": DARK, "field2": DARK, "paper": PAPER, "paper2": PAPER,
            "ink": PAPER, "dim": DARK_DIM, "rule": DARK_HAIR,
            "accent": ACCENT_ON_DARK, "plate": DARK_PLATE,
        }
    else:
        canvas = Image.new("RGBA", size, PAPER + (255,))
        tone = {
            "field": PAPER, "field2": PAPER, "paper": PAPER, "paper2": PAPER,
            "ink": INK, "dim": MUTED, "rule": HAIR,
            "accent": ACCENT, "plate": PLATE,
        }
    return canvas, tone


def margin(width, landscape=False):
    return int(width * (0.040 if landscape else 0.048))


def title_px(width, config, landscape=False):
    """按画布宽度等比缩放，预览和成图字号一致；上限 44/48。"""
    full = 1920 if landscape else 1000
    cap = 48 if landscape else 44
    base = 44 if landscape else 40
    try:
        asked = int(config.get("title_size") or base)
    except (TypeError, ValueError):
        asked = base
    return max(10, min(cap, round(asked * width / full)))


def meta_px(width, landscape=False):
    full = 1920 if landscape else 1000
    return max(9, round((12 if landscape else 13) * width / full))


def photo(ctx, canvas, ref, box, border=False, zoom=1.0):
    """裁切铺满：照片是主体，不做 letterbox 留白。"""
    from ._imgutil import fill_cover
    fill_cover(ctx, canvas, ref, box, zoom=zoom)
    if border:
        from PIL import ImageDraw
        ImageDraw.Draw(canvas).rectangle(
            [(int(box[0]), int(box[1])), (int(box[2]) - 1, int(box[3]) - 1)],
            outline=HAIR + (255,), width=1)
