"""竖版 2:3 设计基元（design kit）。

院线 one-sheet 的几条硬规则，本文件把它们固化成可复用函数：

* 标题落在下三分之一，视觉锚点只有一个；
* 字号级差要大（主标题与微信息 ≥ 6:1），不做"什么都一样大"的平面排版；
* 标题四周必须留负空间，宁可少塞信息；
* 缩略图（约 200px 高）仍要读得清，主标题不依赖细笔画与低对比；
* 中文用文泉驿正黑，拉丁文标题可用 DejaVu Serif 做编辑感对比。

布局模块只依赖本文件的函数与 ctx（引擎上下文），不引入额外三方库。
"""
from __future__ import annotations

import hashlib
import math
import random
from typing import Iterable, List, Optional, Sequence, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

CJK_FONT = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
SERIF_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
SERIF_BOLD_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"

_FONT_CACHE: dict = {}


# --------------------------------------------------------------------- 字体 / 文字


def load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    size = max(1, int(size))
    key = (path, size)
    if key not in _FONT_CACHE:
        try:
            _FONT_CACHE[key] = ImageFont.truetype(path, size)
        except Exception:
            _FONT_CACHE[key] = ImageFont.load_default()
    return _FONT_CACHE[key]


def has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in str(text or ""))


def hex_rgba(value, alpha: int = 255) -> Tuple[int, int, int, int]:
    """把 #RRGGBB / #RGB 转成带透明度的 RGBA 元组，供 draw 直接使用。"""
    text = str(value or "").strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6:
        return (255, 255, 255, alpha)
    try:
        r, g, b = (int(text[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return (255, 255, 255, alpha)
    return (r, g, b, alpha)


def title_font(text: str, size: int, serif: bool = True) -> ImageFont.FreeTypeFont:
    """标题字体：中文走正黑（容器内唯一 CJK 字体），拉丁文可走衬线。"""
    if has_cjk(text) or not serif:
        return load_font(CJK_FONT, size)
    return load_font(SERIF_BOLD_FONT if serif else CJK_FONT, size)


def micro_font(size: int, serif: bool = False) -> ImageFont.FreeTypeFont:
    return load_font(SERIF_FONT if serif else CJK_FONT, size)


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


def draw_tracked(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: Tuple[float, float],
    font: ImageFont.FreeTypeFont,
    fill,
    tracking: float = 0.0,
    align: str = "left",
) -> float:
    """逐字绘制以实现字距（tracking），返回整行宽度。

    xy 的语义随 align 变化：left=左起点，center=中线，right=右终点。
    """
    text = str(text or "")
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


def wrap_lines(font: ImageFont.FreeTypeFont, text: str, max_width: float) -> List[str]:
    """按最大宽度折行：中文逐字断行，拉丁优先在空格处断行。"""
    text = str(text or "").strip()
    if not text:
        return []
    lines: List[str] = []
    current = ""
    for ch in text:
        if ch == "\n":
            if current:
                lines.append(current)
            current = ""
            continue
        candidate = current + ch
        if text_width(font, candidate) <= max_width:
            current = candidate
            continue
        # 拉丁文回退到最近空格处断行
        if ch != " " and " " in current.strip() and not has_cjk(current):
            head, _, tail = current.rpartition(" ")
            if head:
                lines.append(head)
                current = tail + ch
                continue
        if current:
            lines.append(current)
        current = ch
    if current:
        lines.append(current)
    return lines


def fit_title(
    text: str,
    max_width: float,
    size: int,
    max_lines: int = 2,
    serif: bool = True,
    min_size: int = 40,
) -> Tuple[List[str], ImageFont.FreeTypeFont, int]:
    """逐级缩小字号，直到折行数不超过 max_lines 且不超宽。"""
    size = int(size)
    while size > min_size:
        font = title_font(text, size, serif=serif)
        lines = wrap_lines(font, text, max_width)
        if len(lines) <= max_lines and all(text_width(font, ln) <= max_width for ln in lines):
            return lines, font, size
        size = int(size * 0.94)
    font = title_font(text, min_size, serif=serif)
    return wrap_lines(font, text, max_width)[:max_lines], font, min_size


def line_height(font: ImageFont.FreeTypeFont, ratio: float = 1.18) -> int:
    try:
        ascent, descent = font.getmetrics()
        return int((ascent + descent) * ratio)
    except Exception:
        bbox = font.getbbox("汉Ag")
        return int((bbox[3] - bbox[1]) * ratio)


def draw_block(
    draw: ImageDraw.ImageDraw,
    lines: Sequence[str],
    xy: Tuple[float, float],
    font: ImageFont.FreeTypeFont,
    fill,
    tracking: float = 0.0,
    leading: float = 1.12,
    align: str = "left",
) -> int:
    """绘制多行标题，返回块底部 y。行高按字号比例控制，标题更紧凑。"""
    x, y = xy
    step = int(font.size * leading)
    for line in lines:
        draw_tracked(draw, line, (x, y), font, fill, tracking, align)
        y += step
    return int(y)


# --------------------------------------------------------------------- 颜色 / 材质


def tune_color(rgb: Sequence[int], saturate: float = 0.55, lightness: float = 0.40) -> Tuple[int, int, int]:
    """把任意颜色调整到目标饱和度与明度，用于把画面色变成可大面积铺的色场。"""
    r, g, b = [int(v) for v in rgb[:3]]
    lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
    gray = lum * 255
    r = int(gray + (r - gray) * saturate)
    g = int(gray + (g - gray) * saturate)
    b = int(gray + (b - gray) * saturate)
    target = lightness * 255
    if lum > 0:
        factor = min(1.8, max(0.40, target / max(1.0, lum * 255)))
        r, g, b = int(r * factor), int(g * factor), int(b * factor)
    return (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))


def dominant_color(img: Image.Image, saturate: float = 0.55, lightness: float = 0.42) -> Tuple[int, int, int]:
    """取图片主色并压低饱和/明度，用作大面积色场。"""
    small = img.convert("RGB").resize((48, 48), Image.LANCZOS)
    quant = small.quantize(colors=5, method=Image.MEDIANCUT)
    palette = quant.getpalette() or []
    entries = sorted(quant.getcolors() or [], reverse=True)
    if not entries:
        return (26, 32, 44)
    index = entries[0][1]
    rgb = palette[index * 3: index * 3 + 3]
    if len(rgb) < 3:
        return (26, 32, 44)
    return tune_color(rgb, saturate, lightness)


def duotone(img: Image.Image, dark: Tuple[int, int, int], light: Tuple[int, int, int]) -> Image.Image:
    gray = ImageOps.grayscale(img)
    gray = ImageEnhance.Contrast(gray).enhance(1.08)
    return ImageOps.colorize(gray, dark, light).convert("RGBA")


def grain(img: Image.Image, amount: float = 0.06, sigma: float = 22.0) -> Image.Image:
    """叠一层极淡的胶片颗粒，避免大色块显得像 PPT。"""
    if amount <= 0:
        return img
    base = img.convert("RGB")
    noise = Image.effect_noise(base.size, sigma).convert("L")
    flat = Image.merge("RGB", (noise, noise, noise))
    out = Image.blend(base, flat, max(0.0, min(0.35, amount)))
    if img.mode == "RGBA":
        out = out.convert("RGBA")
        out.putalpha(img.getchannel("A"))
    return out


def vignette(img: Image.Image, strength: float = 0.32, radius: float = 0.72) -> Image.Image:
    """四角压暗，把视线收回中心。"""
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    inset_x, inset_y = int(w * (1 - radius) / 2), int(h * (1 - radius) / 2)
    draw.ellipse([inset_x, inset_y, w - inset_x, h - inset_y], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(max(2, int(min(w, h) * 0.06))))
    dark = Image.new("RGBA", (w, h), (0, 0, 0, int(255 * max(0.0, min(0.9, strength)))))
    dark.putalpha(ImageChops.invert(mask).point(lambda v: int(v * strength)))
    return Image.alpha_composite(img.convert("RGBA"), dark)


def gradient_band(size: Tuple[int, int], from_y: int, color=(0, 0, 0), top_alpha: int = 0,
                  bottom_alpha: int = 235) -> Image.Image:
    """纵向渐变层：用于标题带压暗，顶部透明、底部接近实色。"""
    w, h = size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    span = max(1, h - from_y)
    for y in range(from_y, h):
        ratio = (y - from_y) / span
        alpha = int(top_alpha + (bottom_alpha - top_alpha) * (ratio ** 1.35))
        draw.line([(0, y), (w, y)], fill=(color[0], color[1], color[2], alpha))
    return layer


# --------------------------------------------------------------------- 撕纸边


def torn_mask(size: Tuple[int, int], tear_y: int, seed: int = 0, depth: int = 26) -> Image.Image:
    """生成上实下透的撕纸遮罩。

    用"随机游走 + 低频正弦"代替逐列独立随机：相邻列的偏移是相关的，
    撕口才会是一条连续的纤维边，而不是一排竖立的草叶。
    """
    w, h = size
    rnd = random.Random(seed)
    step = max(2, w // 300)

    offsets: List[float] = []
    current = 0.0
    for _ in range(w // step + 3):
        current = current * 0.82 + rnd.uniform(-1.0, 1.0) * depth * 0.38
        current = max(-depth, min(depth, current))
        offsets.append(current)

    phase_a = rnd.uniform(0.0, math.tau)
    phase_b = rnd.uniform(0.0, math.tau)
    line: List[Tuple[int, int]] = []
    for x in range(0, w + 1, max(1, step // 3)):
        idx = min(len(offsets) - 1, x // step)
        wobble = (
            offsets[idx]
            + depth * 0.62 * math.sin(x / max(1, w) * math.tau * 1.3 + phase_a)
            + depth * 0.30 * math.sin(x / max(1, w) * math.tau * 3.1 + phase_b)
            + rnd.uniform(-depth * 0.10, depth * 0.10)
        )
        y = int(max(tear_y - depth * 1.5, min(h - 2, tear_y + wobble)))
        line.append((x, y))

    polygon = [(0, 0), (w, 0), (w, line[-1][1])] + list(reversed(line)) + [(0, line[0][1])]
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).polygon(polygon, fill=255)
    return mask.filter(ImageFilter.GaussianBlur(0.5))


def soft_plate(size: Tuple[int, int], top_y: int, color=(0, 0, 0), alpha: int = 225,
               feather: int = 80) -> Image.Image:
    """标题压板：上沿羽化的半透明色块，用来压住海报自带的片名与花纹。"""
    w, h = size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    start = max(0, top_y - feather)
    for y in range(start, h):
        if y < top_y:
            ratio = (y - start) / max(1, feather)
            value = int(alpha * (ratio ** 1.6))
        else:
            value = alpha
        draw.line([(0, y), (w, y)], fill=(color[0], color[1], color[2], value))
    return layer


def paste_masked(canvas: Image.Image, img: Image.Image, box: Tuple[int, int, int, int],
                 mask: Image.Image) -> None:
    """按 cover 比例把图片填入 box 后，用遮罩贴入。"""
    left, top, right, bottom = box
    tw, th = max(1, right - left), max(1, bottom - top)
    sw, sh = img.size
    if sw <= 0 or sh <= 0:
        return
    scale = max(tw / sw, th / sh)
    resized = img.resize((max(1, int(sw * scale)), max(1, int(sh * scale))), Image.LANCZOS)
    ox = max(0, (resized.size[0] - tw) // 2)
    oy = max(0, (resized.size[1] - th) // 2)
    cropped = resized.crop((ox, oy, ox + tw, oy + th)).convert("RGBA")
    canvas.paste(cropped, (left, top), mask.crop((0, 0, tw, th)))


def drop_shadow(canvas: Image.Image, box: Tuple[int, int, int, int], blur: int = 26,
                offset: int = 14, opacity: int = 110) -> None:
    """在 box 下方投一层柔和阴影（先画后贴图，避免遮住主体）。"""
    left, top, right, bottom = box
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.rounded_rectangle(
        [(left + offset // 3, top + offset), (right + offset // 3, bottom + offset)],
        radius=6, fill=(0, 0, 0, opacity),
    )
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    canvas.alpha_composite(layer)


# --------------------------------------------------------------------- 版式件


def hairline(draw: ImageDraw.ImageDraw, start: Tuple[float, float], end: Tuple[float, float],
             color=(255, 255, 255, 90), width: int = 2) -> None:
    draw.line([start, end], fill=color, width=width)


def micro_line(draw: ImageDraw.ImageDraw, text: str, xy: Tuple[float, float], size: int,
               color, tracking: float = 2.4, align: str = "left", serif: bool = False) -> float:
    """小号宽字距信息行（院线海报里的 billing / meta 语气）。"""
    if not str(text or "").strip():
        return 0.0
    font = micro_font(size, serif=serif)
    return draw_tracked(draw, text, xy, font, color, tracking, align)


def clamp_text(text: str, limit: int) -> str:
    text = str(text or "").strip()
    return text if len(text) <= limit else text[: max(1, limit - 1)] + "…"


def seed_of(text: str) -> int:
    return int(hashlib.sha1(str(text).encode("utf-8")).hexdigest()[:8], 16)


def cover_fit(img: Image.Image, size: Tuple[int, int], trim_bottom: float = 0.0) -> Image.Image:
    """按 cover 填满 size，可选先裁掉底部片名区（海报自带标题常在下三分之一）。"""
    box_w, box_h = max(1, size[0]), max(1, size[1])
    if trim_bottom > 0:
        src_w, src_h = img.size
        img = img.crop((0, 0, src_w, max(1, int(src_h * (1.0 - trim_bottom))))
                       ).resize((src_w, max(1, int(src_h * (1.0 - trim_bottom)))), Image.LANCZOS)
    src_w, src_h = img.size
    scale = max(box_w / src_w, box_h / src_h)
    resized = img.resize((max(1, int(src_w * scale)), max(1, int(src_h * scale))), Image.LANCZOS)
    ox = max(0, (resized.size[0] - box_w) // 2)
    oy = max(0, (resized.size[1] - box_h) // 2)
    return resized.crop((ox, oy, ox + box_w, oy + box_h))


# --------------------------------------------------------------------- 文字对比度

def _linear(channel: float) -> float:
    """sRGB 单通道转线性值。"""
    value = channel / 255.0
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb: Tuple[int, int, int]) -> float:
    """按 WCAG 公式计算相对亮度（0=纯黑，1=纯白）。"""
    r, g, b = (_linear(float(v)) for v in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(color: Tuple[int, int, int], bg_lum: float) -> float:
    """前景色与给定背景亮度的对比度。"""
    lum = relative_luminance(color)
    lighter, darker = max(lum, bg_lum), min(lum, bg_lum)
    return (lighter + 0.05) / (darker + 0.05)


def region_luminance(img: Image.Image, box: Tuple[int, int, int, int]) -> float:
    """取区域内平均亮度，用于判断文字该用深色还是浅色。"""
    w, h = img.size
    left, top, right, bottom = box
    left, right = max(0, int(left)), min(w, max(1, int(right)))
    top, bottom = max(0, int(top)), min(h, max(1, int(bottom)))
    if right <= left or bottom <= top:
        return relative_luminance(dominant_color(img))
    patch = img.crop((left, top, right, bottom)).convert("L").resize((32, 32), Image.BILINEAR)
    return relative_luminance((int(patch.getpixel((16, 16))) * 3, ) * 3)


def _parse_color(value, fallback: tuple) -> Tuple[int, int, int]:
    if isinstance(value, (tuple, list)) and len(value) >= 3:
        return (int(value[0]), int(value[1]), int(value[2]))
    if isinstance(value, str) and value.startswith("#") and len(value) in (7, 9):
        try:
            return (int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16))
        except ValueError:
            return fallback
    return fallback


def text_color_for(bg: Image.Image, box, preferred=None, alpha: int = 255,
                   light: Tuple[int, int, int] = (250, 248, 244),
                   dark: Tuple[int, int, int] = (17, 16, 14),
                   min_ratio: float = 3.6) -> Tuple[int, int, int, int]:
    """按文字所在区域的亮度挑选可读颜色，必要时推翻配置/默认色。

    - 未指定 preferred：深背景给浅字，浅背景给深字；
    - 指定了 preferred：对比度不足 min_ratio 时自动换成相反色，避免黑底黑字。
    """
    bg_lum = region_luminance(bg, box)
    if preferred:
        rgb = _parse_color(preferred, light)
        if contrast_ratio(rgb, bg_lum) >= min_ratio:
            return rgb + (alpha,)
    chosen = light if bg_lum < 0.45 else dark
    return chosen + (alpha,)


def text_color_on_color(bg_rgb, preferred=None, alpha: int = 255,
                        light: Tuple[int, int, int] = (250, 248, 244),
                        dark: Tuple[int, int, int] = (17, 16, 14),
                        min_ratio: float = 3.6) -> Tuple[int, int, int, int]:
    """已知纯色底（如纸面色块）时的同名判定。"""
    bg_lum = relative_luminance(_parse_color(bg_rgb, (255, 255, 255)))
    if preferred:
        rgb = _parse_color(preferred, dark)
        if contrast_ratio(rgb, bg_lum) >= min_ratio:
            return rgb + (alpha,)
    chosen = light if bg_lum < 0.45 else dark
    return chosen + (alpha,)


def pick_ref(assets: dict, *keys: str) -> Optional[str]:
    for key in keys:
        for ref in assets.get(key) or []:
            if ref:
                return ref
    return None


def collect_posters(assets: dict) -> List[str]:
    refs = [r for r in (assets.get("posters") or []) if r]
    refs += [r for r in (assets.get("backdrops") or []) if r]
    return refs


def meta_text(assets: dict, config: dict) -> str:
    explicit = str(config.get("meta_line") or "").strip()
    if explicit:
        return explicit
    count = int(assets.get("count") or 0)
    if count > 0:
        return f"{count} 部作品"
    return ""


def palette_accent(img: Image.Image) -> Tuple[int, int, int]:
    """从主图取一个高饱和点缀色。"""
    small = img.convert("RGB").resize((48, 48), Image.LANCZOS)
    quant = small.quantize(colors=6, method=Image.MEDIANCUT)
    palette = quant.getpalette() or []
    best = None
    best_score = -1.0
    import colorsys
    for _count, index in (quant.getcolors() or []):
        rgb = palette[index * 3: index * 3 + 3]
        if len(rgb) < 3:
            continue
        r, g, b = [v / 255.0 for v in rgb]
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        score = s * 1.6 + max(0.0, 0.75 - abs(v - 0.55)) * 1.2
        if score > best_score:
            best_score = score
            best = rgb
    return tuple(best) if best else (228, 87, 46)


# ----------------------------------------------------------- 整图不裁切 / 卡片 / 旋转


def contain(img: Image.Image, box_w: int, box_h: int) -> Image.Image:
    """等比缩放到完整放进 box（短边贴合），绝不裁切画面。"""
    src_w, src_h = img.size
    if src_w <= 0 or src_h <= 0:
        return img
    scale = min(max(1, int(box_w)) / src_w, max(1, int(box_h)) / src_h)
    return img.resize((max(1, int(src_w * scale)), max(1, int(src_h * scale))), Image.LANCZOS)


def photo_card(img: Image.Image, card_w: int, card_h: int, border_ratio: float = 0.05,
               bg: Tuple[int, int, int, int] = (252, 250, 246, 255), radius: int = 2) -> Image.Image:
    """把整图放进一张带白边的相纸卡片里（卡片内 letterbox，图完整可见）。"""
    card_w, card_h = max(2, int(card_w)), max(2, int(card_h))
    inner_w = max(1, int(card_w * (1 - 2 * border_ratio)))
    inner_h = max(1, int(card_h * (1 - 2 * border_ratio)))
    fitted = contain(img.convert("RGB"), inner_w, inner_h)
    card = Image.new("RGBA", (card_w, card_h), tuple(bg))
    card.paste(fitted, ((card_w - fitted.size[0]) // 2, (card_h - fitted.size[1]) // 2))
    if radius > 0:
        mask = Image.new("L", (card_w, card_h), 0)
        ImageDraw.Draw(mask).rounded_rectangle([(0, 0), (card_w - 1, card_h - 1)], radius=radius, fill=255)
        card.putalpha(mask)
    return card


def rotated(card: Image.Image, angle: float) -> Image.Image:
    """绕中心旋转卡片，扩展画布并保留透明边缘。"""
    return card.rotate(angle, expand=True, resample=Image.BICUBIC)


def paste_card(canvas: Image.Image, card: Image.Image, xy: Tuple[int, int],
               shadow: int = 26, shadow_opacity: int = 96) -> None:
    """贴一张卡片并加投影；xy 是卡片左上角。"""
    if shadow > 0:
        alpha = card.split()[-1]
        layer = Image.new("RGBA", card.size, (0, 0, 0, shadow_opacity))
        layer.putalpha(alpha.point(lambda v: int(v * shadow_opacity / 255)))
        layer = layer.filter(ImageFilter.GaussianBlur(shadow))
        canvas.paste(layer, (xy[0] + shadow // 2, xy[1] + shadow), layer)
    canvas.paste(card, xy, card)


def paper_tone(img: Image.Image) -> Tuple[int, int, int]:
    """从画面取色并与暖白混合，得到"纸"的感觉而不是脏灰。"""
    tone = dominant_color(img, saturate=0.12, lightness=0.93)
    base = (250, 247, 240)
    return tuple(int(tone[i] * 0.20 + base[i] * 0.80) for i in range(3))


def deep_tone(img: Image.Image) -> Tuple[int, int, int]:
    """从画面取色并与近黑混合，得到带一点画面气息的深底。"""
    tone = dominant_color(img, saturate=0.40, lightness=0.11)
    base = (13, 13, 15)
    return tuple(int(tone[i] * 0.32 + base[i] * 0.68) for i in range(3))


def scrim(canvas: Image.Image, box: Tuple[int, int, int, int], color=(0, 0, 0),
          top_alpha: int = 0, bottom_alpha: int = 210) -> None:
    """在 box 区域叠一层竖向渐变（上淡下深），用于压住文字。"""
    left, top, right, bottom = box
    width, height = max(1, right - left), max(1, bottom - top)
    if width <= 0 or height <= 0:
        return
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for y in range(height):
        ratio = y / max(1, height - 1)
        alpha = int(top_alpha + (bottom_alpha - top_alpha) * ratio)
        draw.line([(0, y), (width, y)], fill=tuple(color) + (alpha,))
    canvas.paste(layer, (left, top), layer)


def card_size(img: Image.Image, max_w: int, max_h: int) -> Tuple[int, int]:
    """按图片自身比例给出卡片尺寸：先占满宽度，超高了再按高度回收，避免白边。"""
    aspect = img.size[1] / max(1, img.size[0])
    w = int(max(2, max_w))
    h = int(w * aspect)
    if h > max_h:
        h = int(max(2, max_h))
        w = int(h / max(1.0, aspect))
    return max(2, w), max(2, h)


# --------------------------------------------------------------- 彩色 / 柔调（v1.4.1）


def soft_grade(img: Image.Image, accent: Optional[Sequence[int]] = None,
               strength: float = 0.08, sat: float = 1.14, lift: float = 1.04) -> Image.Image:
    """彩色直出 + 轻微调色：只提亮、加一点色相，绝不转单色。"""
    rgb = img.convert("RGB")
    rgb = ImageEnhance.Color(rgb).enhance(sat)
    rgb = ImageEnhance.Brightness(rgb).enhance(lift)
    rgb = ImageEnhance.Contrast(rgb).enhance(1.04)
    if accent is not None and strength > 0:
        tint = Image.new("RGB", rgb.size, tune_color(accent, 0.26, 0.62))
        rgb = Image.blend(rgb, tint, max(0.0, min(0.18, strength)))
    return rgb


def soft_paper(img: Optional[Image.Image]) -> Tuple[int, int, int]:
    """带一丝画面色相的暖白纸面，永远不会发灰。"""
    if img is None:
        return (250, 246, 238)
    tone = dominant_color(img, saturate=0.30, lightness=0.92)
    base = (255, 250, 240)
    cream = (250, 242, 227)
    tinted = [tone[i] * 0.12 + base[i] * 0.88 for i in range(3)]
    # 再往奶油白拉一点，保证"纸"永远是暖的，不会在深色画面旁显灰
    return tuple(int(tinted[i] * 0.80 + cream[i] * 0.20) for i in range(3))


def warm_bottom(paper: Sequence[int]) -> Tuple[int, int, int]:
    """纸面下缘的暖调，做出"纸张受光"的层次，不需要压暗。"""
    warm = (244, 233, 214)
    return tuple(int(paper[i] * 0.80 + warm[i] * 0.20) for i in range(3))


def tinted_deep(img: Optional[Image.Image], sat: float = 0.50,
                light: float = 0.16) -> Tuple[int, int, int]:
    """带画面色相的深底，比纯黑更有色彩层次。"""
    if img is None:
        return (18, 18, 22)
    accent = palette_accent(img)
    return tune_color(accent, saturate=sat, lightness=light)


def paper_gradient(size: Tuple[int, int], top_rgb: Sequence[int],
                   bottom_rgb: Sequence[int]) -> Image.Image:
    """竖向双色渐变底，用来替掉一整块死板的纯色。"""
    width, height = size
    strip = Image.new("RGB", (1, max(1, height)))
    for y in range(max(1, height)):
        t = y / max(1, height - 1)
        strip.putpixel((0, y), tuple(int(top_rgb[i] + (bottom_rgb[i] - top_rgb[i]) * t) for i in range(3)))
    return strip.resize((width, height), Image.BILINEAR)
