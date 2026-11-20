"""画廊系统：Apple DESIGN.md 的摄影优先规则，落到封面尺寸。

- 照片 edge-to-edge，不旋转、不加相框、不加投影；
- 界面只剩一枚磨砂纸签和 3px 强调线；
- 字号只有 display / caption / micro 三级，间距全为 8 的倍数；
- 全系统一个强调色。
"""
from PIL import Image, ImageDraw

from ._type import body_font, text_width, title_font

PAPER = (244, 241, 234)
INK = (28, 27, 25)
MUTED = (120, 114, 105)
HAIR = (223, 217, 206)
ACCENT = (166, 90, 62)

S8, S12, S16, S24, S32, S48 = 8, 12, 16, 24, 32, 48


def display(text, size):
    return title_font(text, size, serif=False)


def caption(text, size):
    return body_font(text, size)


def chip(canvas, box, alpha=238):
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rectangle(box, fill=PAPER + (alpha,))
    canvas.alpha_composite(layer)


def accent_rule(draw, x, y, width=40, thickness=3):
    draw.rectangle([(x, y), (x + width, y + thickness)], fill=ACCENT + (255,))


def caption_line(draw, text, xy, size, color=MUTED, tracking=0.14):
    font = caption(text, size)
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=color + (255,))
        x += text_width(font, ch) + size * tracking
    return x


def fit_title(text, max_width, base, minimum, max_lines=2):
    """按宽度与行数双重约束缩字，返回 (行, 字号, 行高)。"""
    size = base
    while size >= minimum:
        font = display(text, size)
        lines, current = [], ""
        for ch in text:
            if text_width(font, current + ch) <= max_width or not current:
                current += ch
            else:
                lines.append(current)
                current = ch
        if current:
            lines.append(current)
        if len(lines) <= max_lines:
            return lines, size, int(size * 1.12)
        size -= 2
    return [text[:max_lines]], minimum, int(minimum * 1.12)


def draw_title(draw, text, box, base, minimum, color=INK, max_lines=2, leading=1.12):
    x, y, w, h = box
    lines, size, line_h = fit_title(text, w, base, minimum, max_lines)
    font = display(text, size)
    for i, line in enumerate(lines):
        if y + i * line_h + size > y + h:
            break
        draw.text((x, y + i * line_h), line, font=font, fill=color + (255,))
    return y + len(lines) * line_h
