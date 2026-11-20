"""版式设计系统（typography & palette tokens）。

两族版式（竖版 2:3 / 横版 16:9）共用的一套"排版规矩"，目的是把之前散落在
各布局里的硬编码字号、手工 y 坐标收拢成可计算的排版块：

* 标题永远在给定盒子里**自动缩字 + 自动折行 + 必要时省略号**，
  长标题不会再顶出画面、也不会压到图片；
* 颜色不再是"取主色铺满"，而是从画面取色相，再落到一条**克制的明度/饱和梯**上，
  得到奶油白、雾灰蓝、灰玫瑰这类柔和但不脏的色场；
* 每个版式都按 8pt 网格（这里是画布比例的 1/125）对齐，间距只有 3 档，
  避免"哪里都差一点"的廉价感。
"""
from __future__ import annotations

import colorsys
from typing import Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

CJK_FONT = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
SERIF_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
SERIF_BOLD_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"

_FONT_CACHE: dict = {}
# 容器内是文泉驿，本地调试（macOS）没有该字体时按顺序回退
_FONT_FALLBACKS = (
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
)


def _resolve(path: str) -> str:
    import os
    if os.path.exists(path):
        return path
    for candidate in _FONT_FALLBACKS:
        if os.path.exists(candidate):
            return candidate
    return path


def load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    size = max(1, int(size))
    real = _resolve(path)
    key = (real, size)
    if key not in _FONT_CACHE:
        try:
            _FONT_CACHE[key] = ImageFont.truetype(real, size)
        except Exception:
            _FONT_CACHE[key] = ImageFont.load_default()
    return _FONT_CACHE[key]


def has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in str(text or ""))


def text_width(font: ImageFont.FreeTypeFont, text: str) -> float:
    try:
        return float(font.getlength(text))
    except Exception:
        bbox = font.getbbox(text)
        return float(bbox[2] - bbox[0])


def tracked_width(font: ImageFont.FreeTypeFont, text: str, tracking: float) -> float:
    if not text:
        return 0.0
    return text_width(font, text) + tracking * max(0, len(text) - 1)

# ------------------------------------------------------------------ 基础数值


def clamp(value: float, low: float, high: float) -> float:
    return low if value < low else (high if value > high else value)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def mix_rgb(a: Sequence[int], b: Sequence[int], t: float) -> Tuple[int, int, int]:
    t = clamp(t, 0.0, 1.0)
    return tuple(int(round(lerp(a[i], b[i], t))) for i in range(3))


def rgb_hsv(rgb: Sequence[int]) -> Tuple[float, float, float]:
    r, g, b = [clamp(v, 0, 255) / 255.0 for v in rgb[:3]]
    return colorsys.rgb_to_hsv(r, g, b)


def hsv_rgb(h: float, s: float, v: float) -> Tuple[int, int, int]:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, clamp(s, 0, 1), clamp(v, 0, 1))
    return (int(r * 255), int(g * 255), int(b * 255))


# ------------------------------------------------------------------ 取色 / 色场

# 七个"情绪锚点"，把任意画面色相拉回一个不会刺眼的区间
MOOD_ANCHORS: Tuple[Tuple[float, float], ...] = (
    (0.030, 0.26),   # 陶土 / 暖砂
    (0.075, 0.24),   # 蜜杏
    (0.130, 0.14),   # 橄榄 / 鼠尾草
    (0.430, 0.12),   # 雾青
    (0.560, 0.13),   # 灰蓝
    (0.760, 0.16),   # 藕荷
    (0.940, 0.18),   # 灰玫瑰
)


def _nearest_anchor(hue: float) -> Tuple[float, float]:
    best, score = MOOD_ANCHORS[0], 2.0
    for anchor in MOOD_ANCHORS:
        diff = min(abs(hue - anchor[0]), 1.0 - abs(hue - anchor[0]))
        if diff < score:
            best, score = anchor, diff
    return best


def dominant_rgb(img: Optional[Image.Image]) -> Tuple[int, int, int]:
    if img is None:
        return (36, 42, 54)
    try:
        small = img.convert("RGB").resize((40, 40), Image.LANCZOS)
        quant = small.quantize(colors=4, method=Image.MEDIANCUT)
        palette = quant.getpalette() or []
        entries = sorted(quant.getcolors() or [], key=lambda e: e[0], reverse=True)
        if not entries:
            return (36, 42, 54)
        index = entries[0][1]
        rgb = palette[index * 3:index * 3 + 3]
        return tuple(rgb) if len(rgb) == 3 else (36, 42, 54)
    except Exception:
        return (36, 42, 54)


def palette(img: Optional[Image.Image], dark: bool = False) -> Dict[str, Tuple[int, int, int]]:
    """从画面取色相，落到柔和的明度梯上；dark=True 得到深色版本。

    返回的键：``field`` / ``field2`` / ``paper`` / ``paper2`` / ``ink`` / ``dim`` /
    ``rule`` / ``accent`` / ``plate``。field 用于大底，paper 用于纸面版式。
    """
    hue, sat, _val = rgb_hsv(dominant_rgb(img))
    anchor_hue, anchor_sat = _nearest_anchor(hue)
    hue_final = lerp(hue, anchor_hue, 0.72) % 1.0
    sat_final = clamp(lerp(sat, anchor_sat, 0.65), 0.08, 0.34)

    if dark:
        field = hsv_rgb(hue_final, sat_final * 0.85, 0.115)
        field2 = hsv_rgb(hue_final, sat_final * 0.95, 0.185)
        paper = hsv_rgb(hue_final, sat_final * 0.30, 0.96)
        paper2 = hsv_rgb(hue_final, sat_final * 0.36, 0.915)
        ink = hsv_rgb(hue_final, 0.10, 0.95)
    else:
        paper = hsv_rgb(hue_final, sat_final * 0.26, 0.982)
        paper2 = hsv_rgb(hue_final, sat_final * 0.34, 0.925)
        field = paper
        field2 = paper2
        ink = hsv_rgb(hue_final, 0.22, 0.155)

    accent = hsv_rgb(hue_final, clamp(sat_final * 1.85, 0.24, 0.52), 0.56 if not dark else 0.66)
    plate = hsv_rgb(hue_final, sat_final * 0.22, 0.99) if not dark else hsv_rgb(hue_final, 0.16, 0.90)
    dim = mix_rgb(ink, paper, 0.46) if not dark else mix_rgb(ink, paper, 0.52)
    rule = mix_rgb(ink, paper, 0.72) if not dark else mix_rgb(ink, paper, 0.62)
    return {
        "field": field, "field2": field2, "paper": paper, "paper2": paper2,
        "ink": ink, "dim": dim, "rule": rule, "accent": accent, "plate": plate,
    }


def gradient(size: Tuple[int, int], top: Sequence[int], bottom: Sequence[int],
             wobble: float = 0.0) -> Image.Image:
    """竖向渐变底；wobble 给一点点横向明暗，避免大面积纯渐变显得像 PPT。"""
    width, height = max(1, size[0]), max(1, size[1])
    strip = Image.new("RGB", (1, height))
    for y in range(height):
        t = y / max(1, height - 1)
        strip.putpixel((0, y), mix_rgb(top, bottom, t))
    base = strip.resize((width, height), Image.BILINEAR)
    if wobble > 0:
        mask = Image.linear_gradient("L").rotate(90, expand=True).resize((width, height), Image.BILINEAR)
        tint = Image.new("RGB", (width, height), mix_rgb(top, (255, 255, 255), 0.10))
        base = Image.blend(base, Image.composite(tint, base, mask), wobble)
    return base


def glow(canvas: Image.Image, center: Tuple[float, float], radius: float,
         color: Sequence[int], alpha: int = 26) -> None:
    """一团极淡的柔光，给色场一点空气感（不改变文字对比度）。"""
    width, height = canvas.size
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    cx, cy = int(center[0]), int(center[1])
    r = int(max(8, radius))
    draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=tuple(color) + (alpha,))
    layer = layer.filter(ImageFilter.GaussianBlur(r * 0.45))
    canvas.alpha_composite(layer)


def soft_grain(canvas: Image.Image, amount: float = 0.03) -> Image.Image:
    if amount <= 0:
        return canvas
    base = canvas.convert("RGB")
    noise = Image.effect_noise(base.size, 20).convert("L")
    flat = Image.merge("RGB", (noise, noise, noise))
    out = Image.blend(base, flat, clamp(amount, 0, 0.12))
    if canvas.mode == "RGBA":
        out = out.convert("RGBA")
        out.putalpha(canvas.getchannel("A"))
    return out


def card_shadow(canvas: Image.Image, box: Tuple[int, int, int, int], blur: int = 26,
                offset: int = 12, opacity: int = 90) -> None:
    left, top, right, bottom = box
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(
        [(left + offset // 4, top + offset), (right + offset // 4, bottom + offset)],
        radius=max(2, int(min(right - left, bottom - top) * 0.03)), fill=(0, 0, 0, opacity),
    )
    layer = layer.filter(ImageFilter.GaussianBlur(max(2, blur)))
    canvas.alpha_composite(layer)


# ------------------------------------------------------------------ 文字排版


def title_font(text: str, size: int, serif: bool = True) -> ImageFont.FreeTypeFont:
    """中文一律正黑（容器内唯一 CJK 字体），纯拉丁标题可走衬线增加编辑感。"""
    if has_cjk(text) or not serif:
        return load_font(CJK_FONT, max(1, int(size)))
    return load_font(SERIF_BOLD_FONT, max(1, int(size)))


def body_font(text: str, size: int) -> ImageFont.FreeTypeFont:
    if has_cjk(text):
        return load_font(CJK_FONT, max(1, int(size)))
    return load_font(SERIF_FONT, max(1, int(size)))


def wrap(font: ImageFont.FreeTypeFont, text: str, max_width: float) -> List[str]:
    """逐字折行；拉丁词尽量不拆开（超长单词才硬断）。"""
    text = str(text or "").strip()
    if not text:
        return []
    lines: List[str] = []
    current = ""
    for ch in text:
        if ch == "\n":
            lines.append(current)
            current = ""
            continue
        candidate = current + ch
        if text_width(font, candidate) <= max_width:
            current = candidate
            continue
        if ch not in " ，。、,.;:!?）)" and " " in current and not has_cjk(current):
            head, _, tail = current.rpartition(" ")
            if head and text_width(font, head) <= max_width:
                lines.append(head)
                current = tail + ch
                continue
        lines.append(current)
        current = ch
    if current:
        lines.append(current)
    return [ln.strip() for ln in lines if ln.strip()]


def _ellipsis_for(font: ImageFont.FreeTypeFont, text: str, max_width: float) -> str:
    tail = "…"
    while text and text_width(font, text + tail) > max_width:
        text = text[:-1]
    return (text + tail) if text else ""


def fit_block(
    text: str,
    max_width: float,
    max_height: float,
    base_size: int,
    min_size: Optional[int] = None,
    max_lines: int = 2,
    serif: bool = True,
    leading: float = 1.14,
    tracking_ratio: float = 0.03,
) -> Dict[str, object]:
    """在"宽 × 高"双约束下求最优字号：先缩字号，再控行数，最后才省略号。"""
    text = str(text or "").strip()
    if not text:
        return {"lines": [], "font": None, "size": 0, "tracking": 0.0, "height": 0}
    if min_size is None:
        min_size = max(16, int(base_size * 0.42))
    size = int(base_size)
    chosen = None
    while size >= min_size:
        font = title_font(text, size, serif=serif)
        tracking = size * tracking_ratio
        lines = wrap(font, text, max_width)
        line_height = size * leading
        if len(lines) <= max_lines and len(lines) * line_height <= max_height + 1:
            chosen = (lines, font, size)
            break
        size = int(size * 0.93)
    if chosen is None:
        size = int(min_size)
        font = title_font(text, size, serif=serif)
        tracking = size * tracking_ratio
        # 先按行高算最多能放几行，再多行截断 + 省略号
        line_height = max(1.0, size * leading)
        allowed = max(1, min(max_lines, int(max_height // line_height) or 1))
        lines = wrap(font, text, max_width)
        lines = lines[:allowed]
        if lines and text_width(font, lines[-1]) > max_width - size * 0.6:
            lines[-1] = _ellipsis_for(font, lines[-1], max_width)
        elif len(wrap(font, text, max_width)) > allowed and lines:
            lines[-1] = _ellipsis_for(font, lines[-1] + "…", max_width)
        chosen = (lines, font, size)
    lines, font, size = chosen
    tracking = size * tracking_ratio
    return {
        "lines": lines, "font": font, "size": size, "tracking": tracking,
        "height": int(len(lines) * size * leading),
        "leading": leading,
    }


def draw_tracked_line(draw: ImageDraw.ImageDraw, text: str, xy: Tuple[float, float],
                      font: ImageFont.FreeTypeFont, fill, tracking: float = 0.0,
                      align: str = "left") -> float:
    if not text:
        return 0.0
    width = tracked_width(font, text, tracking)
    x, y = xy
    if align == "center":
        x -= width / 2
    elif align == "right":
        x -= width
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += text_width(font, ch) + tracking
    return width


def draw_block(draw: ImageDraw.ImageDraw, block: Dict[str, object], xy: Tuple[float, float],
               fill, align: str = "left") -> int:
    """按 fit_block 的结果绘制，返回块底部 y。"""
    lines = block.get("lines") or []
    if not lines:
        return int(xy[1])
    font = block["font"]
    size = int(block["size"])
    tracking = float(block["tracking"])
    leading = float(block.get("leading") or 1.14)
    x, y = xy
    step = int(round(size * leading))
    for line in lines:
        draw_tracked_line(draw, line, (x, y), font, fill, tracking, align)
        y += step
    return int(y)


def caps(draw: ImageDraw.ImageDraw, text: str, xy: Tuple[float, float], size: int,
         fill, tracking_ratio: float = 0.22, align: str = "left") -> float:
    """小号宽字距信息行（院线 billing / 目录序号那种语气）。"""
    text = str(text or "").strip()
    if not text:
        return 0.0
    font = load_font(SERIF_FONT if not has_cjk(text) else CJK_FONT, max(9, int(size)))
    return draw_tracked_line(draw, text.upper() if not has_cjk(text) else text, xy, font, fill,
                             max(0.4, size * tracking_ratio), align)


def rule(draw: ImageDraw.ImageDraw, start: Tuple[float, float], length: float, color,
         width: int = 2) -> None:
    draw.line([start, (start[0] + length, start[1])], fill=color, width=max(1, int(width)))


def title_text(config: dict, assets: dict) -> str:
    """取标题：页面显式关闭标题时不回退到文件夹名。"""
    if str(config.get("show_title")).lower() in ("false", "0", "off", "no"):
        return ""
    return str(config.get("title") or assets.get("title") or "").strip()


# ------------------------------------------------------------------ 版式件


def begin_field(size: Tuple[int, int], img: Optional[Image.Image], dark: bool = False,
                wobble: float = 0.05) -> Tuple[Image.Image, Dict[str, Tuple[int, int, int]]]:
    """开一张色场底：从素材取色，落到柔和明度梯上，再叠一点柔光。"""
    tone = palette(img, dark=dark)
    canvas = gradient(size, tone["field"], tone["field2"], wobble=wobble).convert("RGBA")
    return canvas, tone


def fitted_box(box: Tuple[float, float, float, float], aspect: float,
                fill: float = 0.96) -> Tuple[int, int, int, int]:
    """在给定盒子里按图片比例求一个"不裁切、居中、留一点边"的图版矩形。"""
    left, top, right, bottom = [int(v) for v in box]
    bw, bh = max(1, right - left), max(1, bottom - top)
    fw, fh = bw * fill, bh * fill
    if aspect <= 0:
        aspect = 1.0
    if fw / fh > aspect:
        w = fh * aspect
        h = fh
    else:
        w = fw
        h = fw / aspect
    w, h = int(min(w, bw)), int(min(h, bh))
    x = left + (bw - w) // 2
    y = top + (bh - h) // 2
    return (x, y, x + w, y + h)


def aspect_of(img: Optional[Image.Image], fallback: float = 1.78) -> float:
    if img is None or not img.size[0] or not img.size[1]:
        return fallback
    return img.size[0] / img.size[1]


def plate(canvas: Image.Image, ctx, ref: Optional[str], box: Tuple[int, int, int, int],
          plate_rgb: Sequence[int], pad: int = 0, shadow: int = 0,
          border: Optional[Sequence[int]] = None) -> None:
    """一块"图版"：先铺底，再把整张图（contain 不裁切）放进去。"""
    left, top, right, bottom = [int(v) for v in box]
    if right <= left or bottom <= top:
        return
    if shadow > 0:
        card_shadow(canvas, (left, top, right, bottom), blur=shadow, offset=int(shadow * 0.45),
                    opacity=78)
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([(left, top), (right - 1, bottom - 1)], fill=tuple(plate_rgb) + (255,))
    inner = (left + pad, top + pad, right - pad, bottom - pad)
    if ref:
        ctx.paste_full(canvas, ref, inner, matte=tuple(plate_rgb) + (255,))
    if border is not None:
        draw.rectangle([(left, top), (right - 1, bottom - 1)], outline=tuple(border), width=1)


def veil(canvas: Image.Image, box: Tuple[int, int, int, int], color: Sequence[int] = (0, 0, 0),
         top_alpha: int = 0, bottom_alpha: int = 210, power: float = 1.3) -> None:
    """竖向渐变遮罩（上淡下深），用来压住画面自带的片名与花纹。"""
    left, top, right, bottom = [int(v) for v in box]
    width, height = max(1, right - left), max(1, bottom - top)
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for y in range(height):
        t = (y / max(1, height - 1)) ** power
        draw.line([(0, y), (width, y)],
                  fill=(color[0], color[1], color[2], int(top_alpha + (bottom_alpha - top_alpha) * t)))
    canvas.paste(layer, (left, top), layer)


def hero_ref(assets: dict, ctx) -> Tuple[Optional[str], Optional[Image.Image]]:
    """取主图：优先海报/横幅，都没有就用目录里第一张。"""
    for key in ("posters", "backdrops", "bg_url"):
        for ref in assets.get(key) or []:
            if ref:
                img = ctx.load_img(ref)
                if img is not None:
                    return ref, img
    return None, None


def meta_of(assets: dict, config: dict) -> str:
    explicit = str(config.get("meta_line") or "").strip()
    if explicit:
        return explicit
    count = int(assets.get("count") or 0)
    return f"{count} 部作品" if count > 0 else ""


def title_box(draw, config, assets, xy, max_width, max_height, base_size, ink,
              max_lines: int = 2, align: str = "left", leading: float = 1.12) -> int:
    """统一的标题落位：自动缩字折行，高度用完就省略号。"""
    block = fit_block(title_text(config, assets), max_width, max_height, base_size,
                      max_lines=max_lines, leading=leading)
    if not block["lines"]:
        return int(xy[1])
    return draw_block(draw, block, xy, ink, align=align)
