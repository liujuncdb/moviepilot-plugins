"""斜网格拼贴：整块网格统一旋转，白色缝平行，外框裁成直边。

rows: [(行高 px, [列宽 px, ...]), ...]。网格只多铺一圈，够旋转裁切用，
所以不会把同一张图重复铺满整块。
"""
import math

from PIL import Image

from ._spec import PAPER, photo


def _fill(ctx, canvas, ref, box):
    photo(ctx, canvas, ref, box, border=False, zoom=1.04)


def collage(ctx, canvas, refs, box, rows, angle=12, gap=None):
    x0, y0, x1, y1 = [int(v) for v in box]
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return
    gap = gap or max(4, int(min(w, h) * 0.008))
    h0 = sum(r[0] for r in rows)

    bleed = int(max(w, h0) * 0.15)
    gw, gh = w + bleed * 2, h + bleed * 2
    diag = int(math.ceil(math.hypot(gw, gh))) + gap * 4
    big = Image.new("RGBA", (diag, diag), PAPER + (255,))
    gx, gy = (diag - gw) // 2, (diag - gh) // 2
    ox, oy = (diag - w) // 2, (diag - h) // 2

    cx, cy = gx + gw / 2.0, gy + gh / 2.0
    vis = 0
    bleed_i = 0
    y = cy - h0 / 2.0 - h0
    while y < gy + gh:
        for row_h, cols in rows:
            x = cx - w / 2.0 - w
            left = 0
            while x < gx + gw:
                cw = cols[left % len(cols)]
                if (x + cw > gx - gap and x < gx + gw + gap
                        and y < gy + gh and y + row_h > gy):
                    cell = (int(x) + gap // 2, int(y) + gap // 2,
                            int(x + cw) - gap // 2, int(y + row_h) - gap // 2)
                    if cell[2] > cell[0] and cell[3] > cell[1]:
                        ccx, ccy = (cell[0] + cell[2]) / 2, (cell[1] + cell[3]) / 2
                        inside = ox <= ccx <= ox + w and oy <= ccy <= oy + h
                        if refs:
                            if inside:
                                ref = refs[vis % len(refs)]
                                vis += 1
                            else:
                                ref = refs[(bleed_i + 2) % len(refs)]
                                bleed_i += 1
                        else:
                            ref = None
                        _fill(ctx, big, ref, cell)
                x += cw
                left += 1
            y += row_h

    if angle:
        big = big.rotate(-float(angle), resample=Image.BICUBIC, expand=False)

    crop = big.crop((ox, oy, ox + w, oy + h))
    canvas.alpha_composite(crop, (x0, y0))


def collage_cells(ctx, canvas, refs, box, cells, angle=0, gap=None, patches=0):
    """旋转拼贴：主图撑满画框，边缘格位向外延伸补满四角。

    cells 是主图格位，正好铺满 box。最外缘格位向画框外多画一圈，
    旋转后四角仍然有图，只会露出边缘的一部分，不会留白。
    """
    x0, y0, x1, y1 = [int(v) for v in box]
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return
    gap = gap or max(4, int(min(w, h) * 0.008))
    bleed = int(max(w, h) * 0.38)
    big = Image.new("RGBA", (w + bleed * 2, h + bleed * 2), PAPER + (255,))
    # 大格优先拿色彩更丰富的图，纯色/白墙留给小格
    order = sorted(range(len(cells)), key=lambda i: -(cells[i][2] * cells[i][3]))
    ref_of = {}
    for pos, ci in enumerate(order):
        ref_of[ci] = refs[pos % len(refs)] if refs else None
    for i, (cx, cy, cw, ch) in enumerate(cells):
        bx0, by0, bx1, by1 = cx, cy, cx + cw, cy + ch
        if bx0 <= 0:
            bx0 -= bleed
        if by0 <= 0:
            by0 -= bleed
        if bx1 >= w:
            bx1 += bleed
        if by1 >= h:
            by1 += bleed
        rect = (bx0 + bleed + (gap // 2 if cx > 0 else 0),
                by0 + bleed + (gap // 2 if cy > 0 else 0),
                bx1 + bleed - (gap // 2 if cx + cw < w else 0),
                by1 + bleed - (gap // 2 if cy + ch < h else 0))
        _fill(ctx, big, ref_of.get(i), rect)
    if angle:
        big = big.rotate(-float(angle), resample=Image.BICUBIC, expand=False)
    canvas.alpha_composite(big.crop((bleed, bleed, bleed + w, bleed + h)), (x0, y0))


def rank_refs(refs):
    """按画面色彩丰富度排序，避免大片白墙/纯色占据主格。"""
    ranked = []
    for i, ref in enumerate(refs):
        flat = False
        try:
            im = Image.open(ref).convert("RGB")
            im.thumbnail((72, 72))
            hsv = im.convert("HSV")
            sat = sum(hsv.getdata(band=1)) / 255.0 / max(1, im.width * im.height)
            val = sum(hsv.getdata(band=2)) / 255.0 / max(1, im.width * im.height)
            score = sat * 0.75 + (1.0 - abs(val - 0.52) * 2) * 0.25
            flat = sat < 0.08 or (val > 0.80 and sat < 0.14)
        except Exception:
            score = 0.5
        ranked.append((score, i, ref, flat))
    ranked.sort(key=lambda t: (-t[0], t[1]))
    solid = [r for r in ranked if not r[3]]
    use = solid if len(solid) >= 4 else ranked
    return [r[2] for r in use]
