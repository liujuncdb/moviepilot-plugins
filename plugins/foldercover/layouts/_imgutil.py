"""图片工具：自动去掉截图自带的上下黑边，再按目标框裁切铺满。"""
from PIL import Image


def trim_bars(img: Image.Image, threshold: int = 20, max_frac: float = 0.24) -> Image.Image:
    """裁掉上下（或左右）接近纯黑的 letterbox 边。"""
    if img is None:
        return None
    rgb = img.convert("RGB")
    w, h = rgb.size
    limit_v = int(h * max_frac)
    limit_h = int(w * max_frac)

    def row_dark(y):
        return max(rgb.crop((0, y, w, y + 1)).getextrema()[0][1],
                   rgb.crop((0, y, w, y + 1)).getextrema()[1][1],
                   rgb.crop((0, y, w, y + 1)).getextrema()[2][1]) <= threshold

    top = 0
    while top < limit_v and row_dark(top):
        top += 1
    bottom = h
    while bottom > h - limit_v and row_dark(bottom - 1):
        bottom -= 1
    if bottom - top > h * 0.35 and (top > 0 or bottom < h):
        rgb = rgb.crop((0, top, w, bottom))
        w, h = rgb.size

    def col_dark(x):
        return max(rgb.crop((x, 0, x + 1, h)).getextrema()[0][1],
                   rgb.crop((x, 0, x + 1, h)).getextrema()[1][1],
                   rgb.crop((x, 0, x + 1, h)).getextrema()[2][1]) <= threshold

    left = 0
    while left < limit_h and col_dark(left):
        left += 1
    right = w
    while right > w - limit_h and col_dark(right - 1):
        right -= 1
    if right - left > w * 0.35 and (left > 0 or right < w):
        rgb = rgb.crop((left, 0, right, h))
    return rgb


def fill_cover(ctx, canvas, ref, box, trim: bool = True, zoom: float = 1.0):
    if not ref:
        return
    left, top, right, bottom = [int(v) for v in box]
    tw, th = max(1, right - left), max(1, bottom - top)
    img = ctx.load_img(ref)
    if img is None:
        return
    if trim:
        img = trim_bars(img)
    sw, sh = img.size
    scale = max(tw / sw, th / sh) * max(1.0, zoom)
    resized = img.resize((max(1, int(sw * scale)), max(1, int(sh * scale))), Image.LANCZOS)
    ox = max(0, (resized.size[0] - tw) // 2)
    oy = max(0, (resized.size[1] - th) // 2)
    canvas.paste(resized.crop((ox, oy, ox + tw, oy + th)).convert("RGBA"), (left, top))
