"""文件夹封面渲染引擎（本地素材版）。

机制参考胖虎封面中心（EmbyCoverCenter）的 PosterEngine，但素材来源由 Emby
URL 改为**本地文件路径**；布局脚本与胖虎保持同一契约：

- 布局模块提供 ``get_schema()`` 与 ``render(ctx, bg, config, assets, fonts)``；
- 引擎上下文提供 ``download_img`` / ``load_img``、``paste_cover``、
  ``draw_text_wrapper``、``create_smart_mask``、``load_font``、
  ``build_background_for_layout``，与胖虎布局调用名一致，布局脚本无需改动。
"""
from __future__ import annotations

import hashlib
import importlib.util
import inspect
import sys
import threading
import types
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image, ImageColor, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from app.sdk.logging import logger

from .layouts._spec import palette_context, random_palette

# 容器内置中文字体（文泉驿正黑），避免标题中文渲染成方块。
DEFAULT_CJK_FONT = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")


class FolderCoverEngine:
    """把一批本地素材图片按所选布局合成为一张封面。"""

    def __init__(self, plugin, layouts_dir: Path) -> None:
        self.plugin = plugin
        self.layouts_dir = Path(layouts_dir)
        self._layouts: Dict[str, Dict[str, Any]] = {}
        self._img_cache: Dict[str, Image.Image] = {}
        self._lock = threading.RLock()
        # 布局导入必须串行：页面会并发请求 6 套风格，多线程同时 import 同一模块
        # 会拿到"还没执行完"的半成品（没有 render），进而回退到别的布局
        self._import_lock = threading.RLock()

    # ------------------------------------------------------------------ 布局

    @staticmethod
    def orientation_of(size: tuple) -> str:
        """按画布尺寸判定画幅：高 >= 宽为竖版 portrait，否则横版 landscape。"""
        w, h = size
        return "portrait" if h >= w else "landscape"

    def _layout_files(self, orientation: str) -> Dict[str, Path]:
        files: Dict[str, Path] = {}
        sub_dir = self.layouts_dir / orientation
        scan_dir = sub_dir if sub_dir.exists() else self.layouts_dir
        if scan_dir.exists():
            for item in sorted(scan_dir.glob("*.py")):
                # 下划线开头的是共享设计基元（如 _kit.py），不参与布局注册
                if item.name == "__init__.py" or item.stem.startswith("_"):
                    continue
                files[item.stem] = item
        return files

    def _package_for(self, orientation: str) -> str:
        """注册嵌套包，使布局可用 ``from ._kit`` 与 ``from .._shared`` 两种相对导入。"""
        base = "foldercover_layouts"
        base_mod = sys.modules.get(base)
        if base_mod is None:
            base_mod = types.ModuleType(base)
            base_mod.__path__ = [str(self.layouts_dir)]
            sys.modules[base] = base_mod
        else:
            base_mod.__path__ = [str(self.layouts_dir)]

        # 关键：动态包名会让布局里的 ``from .._spec import ...`` 再加载一份 _spec，
        # 与引擎导入的 _spec 不是同一个模块，ContextVar 调色板上下文会失效。
        # 这里把共享模块在动态包名下做单例别名，确保 system_field 读到同一个 _PALETTE。
        for shared in ("_spec", "_type", "_imgutil", "_collage", "_gallery"):
            real_name = f"{__package__}.layouts.{shared}"
            alias_name = f"{base}.{shared}"
            try:
                real_mod = importlib.import_module(real_name)
                sys.modules[alias_name] = real_mod
            except Exception:
                pass

        package = f"{base}.{orientation}"
        existing = sys.modules.get(package)
        if existing is None:
            module = types.ModuleType(package)
            module.__path__ = [str(self.layouts_dir / orientation)]
            sys.modules[package] = module
        else:
            existing.__path__ = [str(self.layouts_dir / orientation)]
        return package

    def layout_modules(self, orientation: str) -> Dict[str, Any]:
        """按需加载指定画幅的布局模块（线程安全，整族一次性装好）。"""
        if orientation in self._layouts:
            return self._layouts[orientation]
        with self._import_lock:
            if orientation in self._layouts:
                return self._layouts[orientation]
            modules: Dict[str, Any] = {}
            package = self._package_for(orientation)
            for name, path in self._layout_files(orientation).items():
                module_name = f"{package}.{name}"
                cached = sys.modules.get(module_name)
                if cached is not None and hasattr(cached, "render"):
                    modules[name] = cached
                    continue
                try:
                    spec = importlib.util.spec_from_file_location(module_name, path)
                    if spec is None or spec.loader is None:
                        logger.warning(f"[FolderCover] 布局 {name} 无法加载")
                        continue
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    try:
                        spec.loader.exec_module(module)
                    except Exception:
                        sys.modules.pop(module_name, None)
                        raise
                    if hasattr(module, "render"):
                        modules[name] = module
                    else:
                        sys.modules.pop(module_name, None)
                        logger.warning(f"[FolderCover] 跳过布局 {name}：缺少 render()")
                except Exception as error:
                    logger.error(f"[FolderCover] 加载布局失败 {name}: {error}")
            if modules:
                self._layouts[orientation] = modules
        return self._layouts.get(orientation, {})

    def layout_names(self, orientation: str) -> List[str]:
        return sorted(self.layout_modules(orientation).keys())

    # ------------------------------------------------------------------ 素材

    @staticmethod
    def _is_http(ref: str) -> bool:
        return str(ref).lower().startswith(("http://", "https://", "data:image"))

    def load_img(self, ref: Optional[str]) -> Optional[Image.Image]:
        """读取素材图片：本地路径直接打开；HTTP/URL 走宿主网络工具。失败返回 None。"""
        if not ref:
            return None
        ref = str(ref).strip()
        if not ref:
            return None

        with self._lock:
            cached = self._img_cache.get(ref)
        if cached is not None:
            return cached.copy()

        img: Optional[Image.Image] = None
        try:
            if self._is_http(ref):
                img = self._load_http(ref)
            else:
                path = Path(ref)
                if path.is_file():
                    with Image.open(path) as handle:
                        img = handle.convert("RGBA")
        except Exception as error:
            logger.debug(f"[FolderCover] 读取素材失败 {ref[:120]}: {error}")
            return None

        if img is None:
            return None
        with self._lock:
            if len(self._img_cache) >= 128:
                self._img_cache.pop(next(iter(self._img_cache)), None)
            self._img_cache[ref] = img.copy()
        return img

    def _load_http(self, url: str) -> Optional[Image.Image]:
        try:
            from app.sdk.network import RequestUtils

            res = RequestUtils(timeout=12).get_res(url=url)
            if res is None or res.status_code != 200:
                return None
            return Image.open(BytesIO(res.content)).convert("RGBA")
        except Exception as error:
            logger.debug(f"[FolderCover] 下载素材失败 {url[:120]}: {error}")
            return None

    # 胖虎布局里调用的是 download_img，这里保留同名别名。
    download_img = load_img

    # ------------------------------------------------------------------ 字体

    def load_font(self, _filename: Optional[str], size: int) -> ImageFont.FreeTypeFont:
        """加载字体：插件不随包分发字体，直接回退容器内置中文字体。"""
        size = max(1, int(size or 1))
        try:
            return ImageFont.truetype(DEFAULT_CJK_FONT, size)
        except Exception:
            return ImageFont.load_default()

    # ------------------------------------------------------------------ 背景

    def _first_image(self, assets: Dict[str, Any], keys: List[str]) -> Optional[Image.Image]:
        for key in keys:
            for ref in assets.get(key) or []:
                img = self.load_img(ref)
                if img is not None:
                    return img
        return None

    def build_background(
        self,
        assets: Dict[str, Any],
        size: tuple,
        blur_radius: int = 0,
        brightness: float = 1.0,
    ) -> Image.Image:
        """构建铺满画布的背景：优先背景图，其次首张海报；都没有则深色纯色底。"""
        canvas_w, canvas_h = size
        bg = self._first_image(assets, ["bg_url", "backdrops", "posters"])
        if bg is None:
            bg = Image.new("RGBA", (canvas_w, canvas_h), (20, 30, 50, 255))
        else:
            if bg.size != (canvas_w, canvas_h):
                bg = ImageOps.fit(bg, (canvas_w, canvas_h), method=Image.LANCZOS)
        if bg.mode != "RGBA":
            bg = bg.convert("RGBA")
        if blur_radius > 0:
            bg = bg.filter(ImageFilter.GaussianBlur(blur_radius))
        try:
            if brightness and abs(float(brightness) - 1.0) > 0.01:
                bg = ImageEnhance.Brightness(bg).enhance(float(brightness))
        except Exception:
            pass
        return bg

    def build_background_for_layout(self, config: Dict[str, Any], assets: Dict[str, Any], size: tuple) -> Image.Image:
        """供布局按需重建背景，与主渲染背景口径一致。"""
        return self.build_background(
            assets,
            size,
            blur_radius=int(config.get("blur_radius") or 0),
            brightness=float(config.get("brightness") or 1.0),
        )

    # ------------------------------------------------------------------ 贴入

    @staticmethod
    def _rounded_mask(size: tuple, radius: int) -> Image.Image:
        mask = Image.new("L", size, 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [(0, 0), (size[0] - 1, size[1] - 1)], radius=max(0, int(radius)), fill=255
        )
        return mask

    @staticmethod
    def _rel_lum(rgb) -> float:
        def lin(v):
            v = float(v) / 255.0
            return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
        r, g, b = (lin(x) for x in rgb[:3])
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    def text_color(self, canvas: Image.Image, box: tuple, preferred=None, alpha: int = 255,
                   min_ratio: float = 3.6) -> tuple:
        """按文字区域实际亮度选可读色，避免黑底黑字/白底白字。"""
        from PIL import ImageStat

        w, h = canvas.size
        left, top, right, bottom = (max(0, int(box[0])), max(0, int(box[1])),
                                    min(w, max(1, int(box[2]))), min(h, max(1, int(box[3]))))
        if right <= left or bottom <= top:
            left, top, right, bottom = 0, 0, w, h
        patch = canvas.crop((left, top, right, bottom)).convert("L")
        mean = ImageStat.Stat(patch).mean[0]
        bg_lum = self._rel_lum((mean, mean, mean))

        def parse(value, fallback):
            if isinstance(value, (tuple, list)) and len(value) >= 3:
                return tuple(int(v) for v in value[:3])
            if isinstance(value, str) and value.startswith("#") and len(value) in (7, 9):
                try:
                    return (int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16))
                except ValueError:
                    return fallback
            return fallback

        light, dark = (250, 248, 244), (17, 16, 14)
        if preferred:
            rgb = parse(preferred, light)
            lum = self._rel_lum(rgb)
            if (max(lum, bg_lum) + 0.05) / (min(lum, bg_lum) + 0.05) >= min_ratio:
                return rgb + (alpha,)
        chosen = light if bg_lum < 0.45 else dark
        return chosen + (alpha,)

    def paste_cover(self, canvas: Image.Image, ref: Optional[str], box: tuple, radius: int = 0,
                    trim_bottom: float = 0.0) -> None:
        """按 cover 模式填满 box（保持比例、居中裁剪）后贴到画布。

        trim_bottom: 先裁掉原图底部这一比例（海报自带的片名/logo 区），避免与标题叠字。
        """
        img = self.load_img(ref)
        if img is None:
            return
        if trim_bottom > 0:
            src_w, src_h = img.size
            img = img.crop((0, 0, src_w, max(1, int(src_h * (1.0 - trim_bottom))))
                           ).resize((src_w, max(1, int(src_h * (1.0 - trim_bottom)))), Image.LANCZOS)
        left, top, right, bottom = box
        target_w, target_h = max(1, right - left), max(1, bottom - top)
        src_w, src_h = img.size
        if src_w <= 0 or src_h <= 0:
            return
        scale = max(target_w / src_w, target_h / src_h)
        resized = img.resize(
            (max(1, int(src_w * scale)), max(1, int(src_h * scale))), Image.LANCZOS
        )
        offset_x = max(0, (resized.size[0] - target_w) // 2)
        offset_y = max(0, (resized.size[1] - target_h) // 2)
        cropped = resized.crop((offset_x, offset_y, offset_x + target_w, offset_y + target_h))
        if radius > 0:
            canvas.paste(cropped, (left, top), self._rounded_mask(cropped.size, radius))
        else:
            canvas.paste(cropped, (left, top))

    # -------------------------------------------------------------- 整图不裁切

    @staticmethod
    def _contain(img: Image.Image, box_w: int, box_h: int) -> Image.Image:
        """等比缩放到能完整放进 box 内（短边贴合），不裁掉任何画面。"""
        src_w, src_h = img.size
        if src_w <= 0 or src_h <= 0:
            return img
        scale = min(box_w / src_w, box_h / src_h)
        return img.resize((max(1, int(src_w * scale)), max(1, int(src_h * scale))), Image.LANCZOS)

    def fit_full(self, ref: Optional[str], box_w: int, box_h: int) -> Optional[Image.Image]:
        """读取素材并整图缩放（不裁切）。"""
        img = self.load_img(ref)
        if img is None:
            return None
        return self._contain(img, box_w, box_h)

    def paste_full(
        self,
        canvas: Image.Image,
        ref: Optional[str],
        box: tuple,
        matte=None,
        radius: int = 0,
        shadow: int = 0,
        border=None,
    ) -> tuple:
        """把整张图完整放进 box（letterbox 不裁切），返回实际贴图矩形。"""
        img = self.load_img(ref)
        if img is None:
            return box
        left, top, right, bottom = [int(v) for v in box]
        box_w, box_h = max(1, right - left), max(1, bottom - top)
        fitted = self._contain(img, box_w, box_h)
        px = left + (box_w - fitted.size[0]) // 2
        py = top + (box_h - fitted.size[1]) // 2
        if matte is not None:
            canvas.paste(Image.new("RGBA", (box_w, box_h), tuple(matte)), (left, top))
        if shadow:
            shadow_layer = Image.new("RGBA", (fitted.size[0] + shadow * 4, fitted.size[1] + shadow * 4), (0, 0, 0, 0))
            ImageDraw.Draw(shadow_layer).rectangle(
                [(shadow * 2, shadow * 2), (shadow * 2 + fitted.size[0], shadow * 2 + fitted.size[1])],
                fill=(0, 0, 0, 110),
            )
            shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(shadow))
            canvas.paste(shadow_layer, (px - shadow * 2, py - shadow * 2 + shadow // 2), mask=shadow_layer)
        if radius > 0:
            canvas.paste(fitted, (px, py), self._rounded_mask(fitted.size, radius))
        else:
            canvas.paste(fitted, (px, py))
        if border is not None:
            ImageDraw.Draw(canvas).rectangle(
                [(px, py), (px + fitted.size[0] - 1, py + fitted.size[1] - 1)], outline=tuple(border), width=1
            )
        return (px, py, px + fitted.size[0], py + fitted.size[1])

    def fill_cover(
        self,
        canvas: Image.Image,
        ref: Optional[str],
        box: tuple,
        blur: int = 0,
        dim: float = 0.0,
        brightness: float = 1.0,
    ) -> None:
        """把图铺满 box（会裁切），用于背景底纹；可模糊、压暗。"""
        img = self.load_img(ref)
        if img is None:
            return
        left, top, right, bottom = [int(v) for v in box]
        target_w, target_h = max(1, right - left), max(1, bottom - top)
        src_w, src_h = img.size
        scale = max(target_w / src_w, target_h / src_h)
        resized = img.resize((max(1, int(src_w * scale)), max(1, int(src_h * scale))), Image.LANCZOS)
        ox = max(0, (resized.size[0] - target_w) // 2)
        oy = max(0, (resized.size[1] - target_h) // 2)
        layer = resized.crop((ox, oy, ox + target_w, oy + target_h)).convert("RGBA")
        if brightness != 1.0:
            layer = ImageEnhance.Brightness(layer).enhance(brightness)
        if blur > 0:
            layer = layer.filter(ImageFilter.GaussianBlur(blur))
        if dim > 0:
            layer = Image.blend(layer, Image.new("RGBA", layer.size, (0, 0, 0, 255)), dim)
        canvas.paste(layer, (left, top))

    # ------------------------------------------------------------------ 文字

    def draw_text_wrapper(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        x: int,
        y: int,
        font: ImageFont.FreeTypeFont,
        max_width: int,
        fill: Any,
        line_spacing: int = 10,
        align: str = "left",
    ) -> int:
        """按最大宽度换行绘制文本，返回下一行的 y。"""
        if not text:
            return y
        lines: List[str] = []
        current = ""
        for char in str(text):
            candidate = current + char
            try:
                width = font.getlength(candidate)
            except Exception:
                width = font.getbbox(candidate)[2]
            if width <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = char
        if current:
            lines.append(current)

        try:
            metrics = font.getmetrics()
            line_height = metrics[0] + metrics[1] + line_spacing
        except Exception:
            bbox = font.getbbox("Hg")
            line_height = (bbox[3] - bbox[1]) + line_spacing

        draw_y = y
        for line in lines:
            try:
                line_width = font.getlength(line)
            except Exception:
                line_width = font.getbbox(line)[2]
            draw_x = x
            if align == "center":
                draw_x = x - line_width / 2
            elif align == "right":
                draw_x = x - line_width
            draw.text((draw_x, draw_y), line, font=font, fill=fill)
            draw_y += line_height
        return draw_y

    # ------------------------------------------------------------------ 遮罩

    def create_smart_mask(
        self,
        width: int,
        height: int,
        opacity: int,
        coverage_percent: int,
        direction: str = "horizontal",
    ) -> Image.Image:
        """渐变遮罩，供布局叠加压暗层（与胖虎同口径）。"""
        mask = Image.new("L", (width, height), 0)
        draw = ImageDraw.Draw(mask)
        key = str(direction or "horizontal").strip().lower()
        coverage = max(0.0, min(100.0, float(coverage_percent or 0))) / 100.0

        def _curve(value: float) -> float:
            value = max(0.0, min(1.0, value))
            return value * value * (3.0 - 2.0 * value)

        if key in ("vertical", "vertical_reverse", "top", "bottom"):
            span = int(height * coverage)
            if span <= 0:
                return mask
            from_top = key in ("vertical_reverse", "top")
            for y in range(height):
                if from_top:
                    ratio = (height - y) / span if y >= height - span else 1.0
                else:
                    ratio = (y - (height - span)) / span if y >= height - span else 0.0
                alpha = int(opacity * _curve(ratio))
                draw.line([(0, y), (width, y)], fill=alpha)
        else:
            span = int(width * coverage)
            if span <= 0:
                return mask
            reverse = key in ("horizontal_reverse", "right", "right_to_left")
            for x in range(width):
                offset = (width - 1 - x) if reverse else x
                ratio = offset / span if offset <= span else 1.0
                draw.line([(x, 0), (x, height)], fill=int(opacity * (1.0 - _curve(ratio))))
        return mask

    # ------------------------------------------------------------------ 渲染

    def render(
        self,
        layout_name: str,
        config: Dict[str, Any],
        assets: Dict[str, Any],
        size: tuple,
        orientation: Optional[str] = None,
    ) -> Optional[Image.Image]:
        """按指定布局渲染一张封面；布局缺失时回退该族第一套，失败返回 None。"""
        orientation = orientation or self.orientation_of(size)
        modules = self.layout_modules(orientation)
        layout = modules.get(layout_name)
        if layout is None:
            logger.warning(f"[FolderCover] 布局未注册：{layout_name}，已注册：{sorted(modules.keys())}")
            layout = next(iter(modules.values()), None)
        if layout is None:
            logger.warning(f"[FolderCover] {orientation} 没有可用布局")
            return None

        canvas_w, canvas_h = size
        bg = self.build_background(
            assets,
            size,
            blur_radius=int(config.get("blur_radius") or 0),
            brightness=float(config.get("brightness") or 1.0),
        )

        title_size = int(config.get("title_size") or 160)
        subtitle_size = int(config.get("subtitle_size") or 80)
        fonts: Dict[str, Any] = {
            "main": self.load_font(config.get("font_title"), title_size),
            "sub": self.load_font(config.get("font_subtitle"), subtitle_size),
        }

        try:
            params = len(inspect.signature(layout.render).parameters)
        except (TypeError, ValueError):
            params = 5
        palette = config.get("_palette")
        if not isinstance(palette, dict) and str(config.get("color_mode") or "default") == "random":
            palette = random_palette(config.get("color_seed"))
        try:
            with palette_context(palette):
                if params >= 6:
                    frame = layout.render(self, bg, config, assets, fonts, None)
                else:
                    frame = layout.render(self, bg, config, assets, fonts)
        except Exception as error:
            logger.error(f"[FolderCover] 布局 {layout_name} 渲染失败: {error}")
            return None

        if frame is None:
            return None
        return frame.convert("RGBA")
