"""已部署模板的统一规范层（源自 Apple DESIGN.md 的摄影优先规则）。

所有版式共用：暖纸底 / 近黑墨 / 赭石单一强调色；页边距 48（竖）· 76（横）；
标题只有 40/32 一档，允许向下缩，不允许超过；微信息 13/12；
不旋转、不投影、不加装饰渐变。版式原有的构图保留，只换掉违反规范的参数。
"""
from contextlib import contextmanager
from contextvars import ContextVar
import colorsys
import random
import secrets

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

# 随机配色：同一色相派生纸面与深场两套 tone。
# 色相取自低饱和的自然色系，饱和度和明度都限制在窄区间，避免花哨。
_PALETTE = ContextVar("foldercover_palette", default=None)
_PALETTE_ANCHORS = [
    ("沙砾", 36, 0.125),
    ("鼠尾草", 106, 0.115),
    ("雾蓝", 204, 0.135),
    ("灰紫", 292, 0.115),
    ("陶土", 18, 0.165),
    ("橄榄", 72, 0.120),
    ("烟粉", 346, 0.115),
    ("青灰", 186, 0.120),
    ("燕麦", 44, 0.075),
]


def _hsl(hue: float, sat: float, light: float) -> tuple:
    r, g, b = colorsys.hls_to_rgb((hue % 360) / 360.0, light, sat)
    return (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))


def random_palette(seed=None) -> dict:
    """返回一组低饱和、同色系的 light/dark tone；seed 相同则结果稳定。"""
    seed = str(seed) if seed else secrets.token_hex(8)
    rng = random.Random(seed)
    _name, base_hue, base_sat = rng.choice(_PALETTE_ANCHORS)
    hue = (base_hue + rng.uniform(-5.5, 5.5)) % 360
    sat = max(0.095, min(0.245, base_sat + 0.055 + rng.uniform(-0.016, 0.016)))
    lift = rng.uniform(-0.008, 0.008)
    light = {
        "field": _hsl(hue, sat, 0.908 + lift),
        "field2": _hsl(hue, sat * 0.95, 0.925 + lift),
        "paper": _hsl(hue, sat * 0.75, 0.954),
        "paper2": _hsl(hue, sat * 0.62, 0.966),
        "ink": _hsl(hue, 0.045, 0.105),
        "dim": _hsl(hue, max(0.05, sat * 0.52), 0.505),
        "rule": _hsl(hue, sat * 0.62, 0.845),
        "accent": _hsl(hue, min(0.32, sat * 1.8), 0.455),
        "plate": _hsl(hue, sat * 0.42, 0.972),
    }
    dark = {
        "field": _hsl(hue, sat * 1.02, 0.108 + lift * 0.5),
        "field2": _hsl(hue, sat * 1.12, 0.086 + lift * 0.5),
        "paper": _hsl(hue, sat * 0.52, 0.912),
        "paper2": _hsl(hue, sat * 0.45, 0.932),
        "ink": _hsl(hue, 0.038, 0.935),
        "dim": _hsl(hue, max(0.05, sat * 0.50), 0.620),
        "rule": _hsl(hue, sat * 0.70, 0.222),
        "accent": _hsl(hue, min(0.32, sat * 1.8), 0.625),
        "plate": _hsl(hue, sat * 0.80, 0.146),
    }
    return {"id": seed, "name": _name, "light": light, "dark": dark}


@contextmanager
def palette_context(palette=None):
    token = _PALETTE.set(palette if isinstance(palette, dict) else None)
    try:
        yield
    finally:
        _PALETTE.reset(token)


def system_field(size, dark=False):
    """返回 (画布, tone)。不取画面色、不做渐变，只给一个系统底色。"""
    palette = _PALETTE.get()
    if isinstance(palette, dict):
        base = palette.get("dark" if dark else "light") or {}
        try:
            colors = {k: tuple(int(c) for c in v[:3]) for k, v in base.items()}
            if "field" in colors and "ink" in colors:
                canvas = Image.new("RGBA", size, colors["field"] + (255,))
                return canvas, colors
        except Exception:
            pass
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
