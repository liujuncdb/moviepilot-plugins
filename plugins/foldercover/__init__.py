"""文件夹封面生成（FolderCover）。

为指定文件夹及其子文件夹生成 Emby 可识别的本地封面：

- ``folder.jpg``：竖版 2:3 文件夹主缩略图；
- ``backdrop.jpg``：横版 16:9 文件夹背景图。

制图机制参考胖虎封面中心（EmbyCoverCenter）：从目录收集已有图片素材
（poster / backdrop / fanart / thumb / extrafanart / 其它刮削图），缺图时从
strm/视频中间帧补截一张，再按所选布局用 Pillow 合成。当前提供竖版/横版
各 7 套确定性版式，详情页可实时预览并切换。与胖虎的区别：素材取自本地
文件系统，成品直接写回文件夹，不经过 Emby API。
"""
import hashlib
import os
import json
import subprocess
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from threading import Event as ThreadEvent
from typing import Any, Dict, List, Optional, Tuple

import pytz
from apscheduler.triggers.cron import CronTrigger
from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import settings
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import Notification, NotificationType, MessageChannel

from .engine import FolderCoverEngine, IMAGE_EXTS

# 探测 / 截帧超时（秒）
PROBE_TIMEOUT = 15
# 输出画布尺寸：folder 竖版 2:3，backdrop 横版 16:9
FOLDER_SIZE = (1000, 1500)
BACKDROP_SIZE = (1920, 1080)
# 不参与聚合素材的特殊子目录名
SPECIAL_DIRS = {
    "extrafanart", "behind the scenes", ".actors", ".clapperboards",
    "behindthescenes", "deleted", "featurettes", "interviews", "scenes",
    "samples", "trailers", ".git",
}
# 视为刮削背景图的文件名主干
BACKDROP_STEMS = {"backdrop", "fanart", "background", "art"}
# 本插件写出的成品文件名：绝不再作为新封面的素材（否则会图片套娃）。
# backdrop.jpg 与刮削背景同名，因此不能只看文件名，
# 还要结合目录内的生成清单 .foldercover.json 里记录的 sha1 判定。
OUTPUT_NAMES = {"folder.jpg", "folder.png", "backdrop.jpg"}
# 生成清单：记录本插件写出的文件及其内容摘要，用于下次扫描时排除自己的成品
MANIFEST_NAME = ".foldercover.json"
# 可作为主视觉的"剧照类"文件名主干（含海报、缩略图、背景、截图）
STILL_STEMS = {
    "poster", "cover", "thumb", "fanart", "backdrop", "background",
    "still", "stills", "screenshot", "scene", "art", "movie", "default",
}
# 文件名主干中出现这些词，说明是 logo / 光盘 / 横幅等美工图，不适合当主视觉
ARTWORK_STEMS = {
    "logo", "clearlogo", "clearart", "disc", "cdart", "banner",
    "landscape", "fanart_thumb",
}

ffmpeg_lock = threading.Lock()


class FolderCover(_PluginBase):
    # 插件名称
    plugin_name = "文件夹封面生成"
    # 插件描述
    plugin_desc = "为指定文件夹及子目录按所选风格生成 Emby 可用的 folder.jpg（竖版）与 backdrop.jpg（横版）封面。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/liujuncdb/moviepilot-plugins/main/icons/foldercover.png"
    # 插件版本
    plugin_version = "0.1"
    # 插件作者
    plugin_author = "liujuncdb"
    # 作者主页
    author_url = "https://github.com/liujuncdb"
    # 插件配置项ID前缀
    plugin_config_prefix = "foldercover_"
    # 加载顺序
    plugin_order = 6
    # 可使用的用户级别
    user_level = 1

    # 素材来源：避免把自己的成品当成新封面素材（图片套娃）
    ASSET_SOURCE_CHOICES = [
        {"title": "刮削静帧优先（无图再截帧）", "value": "mixed"},
        {"title": "只用视频截图", "value": "video_only"},
    ]

    # 竖版 2:3 布局：单图 3 套 + 多图 4 套（layouts/portrait/，与文件名一致）
    PORTRAIT_SINGLE_CHOICES = [
        {"title": "画框（单图 · 装裱留白）", "value": "画框"},
        {"title": "剧场（单图 · 深底银幕）", "value": "剧场"},
        {"title": "柔彩（单图 · 全彩渐变场）", "value": "柔彩"},
    ]
    PORTRAIT_MULTI_CHOICES = [
        {"title": "叠片（多图 · 相纸叠放）", "value": "叠片"},
        {"title": "网格（多图 · 接触印样）", "value": "网格"},
        {"title": "折页（多图 · 扇形铺开）", "value": "折页"},
        {"title": "斜拼（多图 · 斜网格拼贴）", "value": "斜拼"},
    ]
    PORTRAIT_CHOICES = PORTRAIT_SINGLE_CHOICES + PORTRAIT_MULTI_CHOICES

    # 横版 16:9 布局：单图 3 套 + 多图 4 套（layouts/landscape/，与文件名一致）
    LANDSCAPE_SINGLE_CHOICES = [
        {"title": "影院宽幅（单图 · 压暗底纹）", "value": "影院宽幅"},
        {"title": "杂志跨页（单图 · 图版+文字栏）", "value": "杂志跨页"},
        {"title": "留白横幅（单图 · 极简）", "value": "留白横幅"},
    ]
    LANDSCAPE_MULTI_CHOICES = [
        {"title": "层叠（多图 · 右侧叠卡）", "value": "层叠"},
        {"title": "胶片条（多图 · 一排画格）", "value": "胶片条"},
        {"title": "拼贴墙（多图 · 大图+三小图）", "value": "拼贴墙"},
        {"title": "斜拼（多图 · 斜网格拼贴）", "value": "斜拼"},
    ]
    LANDSCAPE_CHOICES = LANDSCAPE_SINGLE_CHOICES + LANDSCAPE_MULTI_CHOICES

    # 单图 / 多图判定：auto 时按目录层级与素材数量自动选
    COVER_MODE_CHOICES = [
        {"title": "自动（有子目录或多图 → 多图版式）", "value": "auto"},
        {"title": "全部用单图版式", "value": "single"},
        {"title": "全部用多图版式", "value": "multi"},
    ]

    # 旧版布局名 → 新版（升级后老配置不至于落到未知布局）
    LEGACY_LAYOUT_MAP = {
        "影院主视觉": "剧场",
        "杂志分割": "杂志跨页",
        "撕纸拼贴": "叠片",
        "单色海报": "柔彩",
        "双色调": "柔彩",
        "海报墙竖版": "网格",
        "极简留白": "画框",
        "经典平铺": "影院宽幅",
        "海报墙": "拼贴墙",
        "经典堆叠": "层叠",
        "扇形展开": "层叠",
        "极简": "留白横幅",
        "暗场右文": "影院宽幅",
    }

    _scheduler = None
    _enabled = False
    _onlyonce = False
    _cron = ""
    _scan_paths = ""
    _exclude_paths = ""
    _recursive = True
    _cover_mode = "auto"
    _portrait_layout = "画框"
    _portrait_multi_layout = "叠片"
    _landscape_layout = "影院宽幅"
    _landscape_multi_layout = "层叠"
    _exist_policy = "missing"
    _capture_missing = True
    # 素材来源：mixed=刮削静帧优先、缺图截帧；video_only=只用视频截图
    _asset_source = "mixed"
    _output_folder = True
    _output_backdrop = True
    _title_enabled = True
    _gen_strategy = "100=60"
    _gen_strategy_count = 0
    _gen_strategy_max_count = 100
    _gen_strategy_delay = 60
    _engine: Optional[FolderCoverEngine] = None
    _event = ThreadEvent()

    # ------------------------------------------------------------------ 生命周期

    def init_plugin(self, config: Optional[dict] = None) -> None:
        if config:
            self._enabled = config.get("enabled")
            self._onlyonce = config.get("onlyonce")
            self._cron = config.get("cron") or ""
            self._scan_paths = config.get("scan_paths") or ""
            self._exclude_paths = config.get("exclude_paths") or ""
            self._recursive = config.get("recursive") if config.get("recursive") is not None else True
            self._cover_mode = config.get("cover_mode") or "auto"
            self._portrait_layout = self._normalize_layout(config.get("portrait_layout"), "画框")
            self._portrait_multi_layout = self._normalize_layout(
                config.get("portrait_multi_layout"), "叠片")
            self._landscape_layout = self._normalize_layout(
                config.get("landscape_layout") or config.get("layout"), "影院宽幅")
            self._landscape_multi_layout = self._normalize_layout(
                config.get("landscape_multi_layout"), "层叠")
            self._exist_policy = config.get("exist_policy") or "missing"
            self._capture_missing = config.get("capture_missing") if config.get("capture_missing") is not None else True
            self._asset_source = config.get("asset_source") or "mixed"
            self._output_folder = config.get("output_folder") if config.get("output_folder") is not None else True
            self._output_backdrop = config.get("output_backdrop") if config.get("output_backdrop") is not None else True
            self._title_enabled = config.get("title_enabled") if config.get("title_enabled") is not None else True
            self._gen_strategy = config.get("gen_strategy") or "100=60"
            parts = self._gen_strategy.split("=")
            try:
                self._gen_strategy_max_count = int(parts[0])
                self._gen_strategy_delay = int(parts[1])
            except (ValueError, IndexError):
                self._gen_strategy_max_count, self._gen_strategy_delay = 100, 60

        self.stop_service()

        # 惰性构建引擎（布局目录随插件包分发）
        layouts_dir = Path(__file__).parent / "layouts"
        self._engine = FolderCoverEngine(self, layouts_dir)

        if self._enabled or self._onlyonce:
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            if self._cron:
                logger.info(f"文件夹封面服务启动，周期：{self._cron}")
                try:
                    self._scheduler.add_job(
                        func=self.__libraryscan,
                        trigger=CronTrigger.from_crontab(self._cron),
                        name="文件夹封面生成",
                        args=[False],
                    )
                except Exception as err:
                    logger.error(f"文件夹封面定时任务启动失败：{err}")
                    self.systemmessage.put(f"文件夹封面定时任务启动失败：{err}", title="文件夹封面生成")
            if self._onlyonce:
                logger.info("文件夹封面服务，立即运行一次")
                self._scheduler.add_job(
                    func=self.__libraryscan,
                    trigger="date",
                    run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                    name="文件夹封面生成",
                    args=[False],
                )
                self._onlyonce = False
                self.update_config({
                    "onlyonce": False,
                    "enabled": self._enabled,
                    "cron": self._cron,
                    "scan_paths": self._scan_paths,
                    "exclude_paths": self._exclude_paths,
                    "recursive": self._recursive,
                    "cover_mode": self._cover_mode,
                    "portrait_layout": self._portrait_layout,
                    "portrait_multi_layout": self._portrait_multi_layout,
                    "landscape_layout": self._landscape_layout,
                    "landscape_multi_layout": self._landscape_multi_layout,
                    "exist_policy": self._exist_policy,
                    "capture_missing": self._capture_missing,
                    "asset_source": self._asset_source,
                    "output_folder": self._output_folder,
                    "output_backdrop": self._output_backdrop,
                    "title_enabled": self._title_enabled,
                    "gen_strategy": self._gen_strategy,
                })
            if self._scheduler.get_jobs():
                self._scheduler.print_jobs()
                self._scheduler.start()

    def get_state(self) -> bool:
        return bool(self._enabled)

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        """暴露预览编辑页与其数据接口。"""
        from . import editor

        return editor.build_routes(self)

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {"component": "VCol", "props": {"cols": 12, "md": 4}, "content": [
                                {"component": "VSwitch", "props": {"model": "enabled", "label": "启用插件"}}
                            ]},
                            {"component": "VCol", "props": {"cols": 12, "md": 4}, "content": [
                                {"component": "VSwitch", "props": {"model": "onlyonce", "label": "立即运行一次"}}
                            ]},
                            {"component": "VCol", "props": {"cols": 12, "md": 4}, "content": [
                                {"component": "VSwitch", "props": {"model": "recursive", "label": "递归子目录"}}
                            ]},
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {"component": "VCol", "props": {"cols": 12, "md": 6}, "content": [
                                {
                                    "component": "VSelect",
                                    "props": {
                                        "model": "cover_mode",
                                        "label": "单图/多图判定",
                                        "items": self.COVER_MODE_CHOICES,
                                    },
                                }
                            ]},
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {"component": "VCol", "props": {"cols": 12, "md": 6}, "content": [
                                {
                                    "component": "VSelect",
                                    "props": {
                                        "model": "exist_policy",
                                        "label": "已有刮削封面/素材时",
                                        "items": [
                                            {"title": "仅补缺失（已有输出不重画）", "value": "missing"},
                                            {"title": "跳过（已有素材或封面则跳过该目录）", "value": "skip"},
                                            {"title": "覆盖（重新合成并覆盖已有封面）", "value": "overwrite"},
                                        ],
                                    },
                                }
                            ]},
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {"component": "VCol", "props": {"cols": 12, "md": 3}, "content": [
                                {"component": "VSwitch", "props": {"model": "output_folder", "label": "生成 folder.jpg（竖版）"}}
                            ]},
                            {"component": "VCol", "props": {"cols": 12, "md": 3}, "content": [
                                {"component": "VSwitch", "props": {"model": "output_backdrop", "label": "生成 backdrop.jpg（横版）"}}
                            ]},
                            {"component": "VCol", "props": {"cols": 12, "md": 3}, "content": [
                                {
                                    "component": "VSelect",
                                    "props": {
                                        "model": "asset_source",
                                        "label": "素材来源",
                                        "items": self.ASSET_SOURCE_CHOICES,
                                    },
                                }
                            ]},
                            {"component": "VCol", "props": {"cols": 12, "md": 3}, "content": [
                                {"component": "VSwitch", "props": {"model": "title_enabled", "label": "封面显示标题（关闭则只放图）"}}
                            ]},
                            {"component": "VCol", "props": {"cols": 12, "md": 3}, "content": [
                                {"component": "VSwitch", "props": {"model": "capture_missing", "label": "缺图时截视频帧"}}
                            ]},
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {"component": "VCol", "props": {"cols": 12, "md": 4}, "content": [
                                {"component": "VTextField", "props": {"model": "gen_strategy", "label": "生成策略", "placeholder": "100=60"}}
                            ]},
                            {"component": "VCol", "props": {"cols": 12, "md": 8}, "content": [
                                {"component": "VTextField", "props": {"model": "cron", "label": "定时扫描周期", "placeholder": "5位cron表达式，留空关闭"}}
                            ]},
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {"component": "VCol", "props": {"cols": 12}, "content": [
                                {"component": "VTextarea", "props": {"model": "scan_paths", "label": "扫描目录（每行一个）", "rows": 4, "placeholder": "/private/人物番号\n/media"}}
                            ]},
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {"component": "VCol", "props": {"cols": 12}, "content": [
                                {"component": "VTextarea", "props": {"model": "exclude_paths", "label": "排除目录（每行一个）", "rows": 2}}
                            ]},
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {"component": "VCol", "props": {"cols": 12}, "content": [
                                {"component": "VAlert", "props": {
                                    "type": "info", "variant": "tonal",
                                    "text": "这里只管扫描范围、生成策略和输出开关。具体用哪套风格、文字怎么写、哪些目录要重做，"
                                            "都到插件详情页的「文件夹封面工作室」里挑：左边是目录树可多选，右边会把当前画幅的所有风格同时渲染出来，点图即选。",
                                }},
                            ]},
                        ],
                    },
                ],
            }
        ], {
            "enabled": False,
            "onlyonce": False,
            "cron": "",
            "scan_paths": "",
            "exclude_paths": "",
            "recursive": True,
            "cover_mode": "auto",
            "portrait_layout": "画框",
            "portrait_multi_layout": "叠片",
            "landscape_layout": "影院宽幅",
            "landscape_multi_layout": "层叠",
            "exist_policy": "missing",
            "capture_missing": True,
            "asset_source": "mixed",
            "output_folder": True,
            "output_backdrop": True,
            "title_enabled": True,
            "gen_strategy": "100=60",
        }

    def get_page(self) -> List[dict]:
        """插件详情页：把预览编辑界面内嵌进来。

        宿主详情页支持 ``html`` 直出，所以这里用一个同源 iframe 承载编辑器，
        不额外开独立入口，也不需要前端构建。
        """
        url = f"/api/v1/plugin/{self.__class__.__name__}/editor"
        frame = (
            f'<iframe src="{url}" title="文件夹封面预览与编辑" '
            'style="width:100%;height:min(78vh,900px);border:0;border-radius:12px;'
            'background:#0e1116;display:block"></iframe>'
        )
        return [{
            "component": "div",
            "props": {"style": "width:100%"},
            "html": frame,
        }]

    # ------------------------------------------------------------------ 扫描

    def scan_once(self, overrides: Dict[str, Any] | None = None) -> None:
        """供详情页「一键全量」调用：同步跑一次扫描。

        overrides 可带 portrait/portrait_multi/landscape/landscape_multi 四个键，
        让全量任务分别沿用"竖单/竖多/横单/横多"挑好的风格。
        """
        self._scan_overrides = dict(overrides or {})
        try:
            self.__libraryscan(False)
        finally:
            self._scan_overrides = {}

    def __libraryscan(self, _is_overlay: bool = False) -> None:
        started = datetime.now()
        self._last_stats = {"running": True, "total": 0, "ok": 0, "skip": 0, "fail": 0,
                            "ts": getattr(self, "_last_stats", {}).get("ts", "")}
        try:
            self._scan_directories(started)
        finally:
            stats = getattr(self, "_last_stats", {}) or {}
            stats["running"] = False
            stats.setdefault("ts", "")
            self._last_stats = stats

    def _scan_directories(self, started) -> None:
        if not self._scan_paths:
            logger.warning("文件夹封面：未配置扫描目录，跳过")
            self._last_stats = {"running": False, "total": 0, "ok": 0, "skip": 0, "fail": 0,
                                "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            return
        exclude_paths = [p.strip() for p in self._exclude_paths.split("\n") if p.strip()]
        roots = [p.strip() for p in self._scan_paths.split("\n") if p.strip()]

        directories: List[Path] = []
        for root in roots:
            root_path = Path(root)
            if not root_path.exists():
                logger.warning(f"文件夹封面：扫描路径不存在：{root}")
                continue
            if self._recursive:
                for dirpath, dirnames, _filenames in root_path.walk():
                    # 剔除特殊目录，避免向下聚合花絮目录
                    dirnames[:] = [d for d in dirnames if d.lower() not in SPECIAL_DIRS and not d.startswith(".")]
                    directories.append(Path(dirpath))
            else:
                directories.append(root_path)

        logger.info(f"文件夹封面开始扫描：共 {len(directories)} 个目录")
        total = ok = skipped = failed = 0
        for directory in directories:
            if self._event.is_set():
                logger.info("文件夹封面扫描服务停止")
                return
            if self._is_excluded(directory, exclude_paths):
                continue
            total += 1
            try:
                state = self._process_dir(directory)
                if state == "ok":
                    ok += 1
                elif state == "skip":
                    skipped += 1
                else:
                    failed += 1
            except Exception as err:
                failed += 1
                logger.error(f"文件夹封面处理目录 {directory} 时发生错误：{err}")
        logger.info(f"文件夹封面扫描完成：处理 {total}，成功 {ok}，跳过 {skipped}，失败 {failed}")
        self._last_stats = {"running": False, "total": total, "ok": ok, "skip": skipped,
                            "fail": failed, "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

    def _is_excluded(self, directory: Path, exclude_paths: List[str]) -> bool:
        for exclude in exclude_paths:
            try:
                if directory.is_relative_to(Path(exclude)):
                    return True
            except Exception:
                continue
        return False

    @classmethod
    def _normalize_layout(cls, name, fallback: str) -> str:
        """把旧版布局名映射到新版，空值回落到默认。"""
        value = str(name or "").strip()
        if not value:
            return fallback
        return cls.LEGACY_LAYOUT_MAP.get(value, value)

    def _mode_for(self, assets: Dict[str, Any]) -> str:
        """单图 / 多图判定：显式配置优先，auto 时按目录层级与素材数量判断。"""
        if self._cover_mode in ("single", "multi"):
            return self._cover_mode
        child_dirs = int(assets.get("child_dirs") or 0)
        images = len(assets.get("posters") or []) + len(assets.get("backdrops") or [])
        return "multi" if (child_dirs >= 1 or images >= 4) else "single"

    def _pick_layout(self, orientation: str, assets: Dict[str, Any]) -> str:
        """按画幅与单图/多图模式取出要用的布局名。"""
        mode = self._mode_for(assets)
        overrides = getattr(self, "_scan_overrides", {}) or {}
        override = overrides.get(f"{orientation}_{mode}") or overrides.get(orientation)
        if override:
            return str(override)
        if orientation == "portrait":
            return self._portrait_multi_layout if mode == "multi" else self._portrait_layout
        return self._landscape_multi_layout if mode == "multi" else self._landscape_layout

    # ------------------------------------------------------------------ 单目录处理

    def _process_dir(self, directory: Path) -> str:
        folder_path = directory / "folder.jpg"
        backdrop_path = directory / "backdrop.jpg"

        want_folder = self._output_folder
        want_backdrop = self._output_backdrop
        if not want_folder and not want_backdrop:
            return "skip"

        has_scrape = self._has_image_assets(directory)
        folder_exists = folder_path.exists()
        backdrop_exists = backdrop_path.exists()

        # 已有素材 / 封面策略判定
        if self._exist_policy == "skip":
            if has_scrape or (want_folder and folder_exists) or (want_backdrop and backdrop_exists):
                logger.info(f"文件夹封面：已有素材/封面，跳过：{directory}")
                return "skip"
        elif self._exist_policy == "missing":
            folder_done = (not want_folder) or folder_exists
            backdrop_done = (not want_backdrop) or backdrop_exists
            if folder_done and backdrop_done:
                logger.info(f"文件夹封面：封面已存在，跳过：{directory}")
                return "skip"
        # overwrite：不做存在性跳过

        assets = self._collect_assets(directory)
        if not assets.get("posters") and not assets.get("backdrops"):
            logger.warning(f"文件夹封面：目录无可用素材，跳过：{directory}")
            return "skip"

        config = self._layout_config(directory)
        assets["mode"] = self._mode_for(assets)
        success = True

        if want_folder and (self._exist_policy != "missing" or not folder_exists):
            layout = self._pick_layout("portrait", assets)
            if self._render_and_save(self._engine, layout, "portrait", config, assets, FOLDER_SIZE, folder_path):
                logger.info(f"文件夹封面已生成（{layout}）：{folder_path}")
            else:
                success = False

        if want_backdrop and (self._exist_policy != "missing" or not backdrop_exists):
            layout = self._pick_layout("landscape", assets)
            if self._render_and_save(self._engine, layout, "landscape", config, assets, BACKDROP_SIZE, backdrop_path):
                logger.info(f"文件夹背景已生成：{backdrop_path}")
            else:
                success = False

        # 登记本次写出的成品：下次扫描时这些文件不会被当成新封面的素材
        written = [p.name for p in (folder_path, backdrop_path) if p.is_file()]
        if written:
            self._write_manifest(directory, written)
        return "ok" if success else "fail"

    @staticmethod
    def _read_style(directory: Path) -> Dict[str, Any]:
        """读取目录里保存的样式（由预览编辑页写入），批量重跑时沿用。"""
        path = directory / MANIFEST_NAME
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            style = data.get("style")
            return style if isinstance(style, dict) else {}
        except Exception:
            return {}

    def _layout_config(self, directory: Path) -> Dict[str, Any]:
        style = self._read_style(directory)
        config: Dict[str, Any] = {}
        config["title"] = directory.name if self._title_enabled else ""
        config["subtitle"] = ""
        # 目录里有编辑过的文字/参数时优先用，缺的键再退回全局默认
        for key in ("title", "subtitle", "kicker", "meta"):
            if style.get(key):
                config[key] = style[key]
        for key, value in (style.get("portrait_config") or {}).items():
            config.setdefault(key, value)
        for key, value in (style.get("landscape_config") or {}).items():
            config.setdefault(key, value)
        return config

    @staticmethod
    def _render_and_save(
        engine: FolderCoverEngine,
        layout_name: str,
        orientation: str,
        config: Dict[str, Any],
        assets: Dict[str, Any],
        size: Tuple[int, int],
        output_path: Path,
    ) -> bool:
        frame = engine.render(layout_name, config, assets, size, orientation)
        if frame is None:
            return False
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            frame.convert("RGB").save(output_path, format="JPEG", quality=90, subsampling=0, optimize=False)
            return True
        except Exception as err:
            logger.error(f"文件夹封面保存失败 {output_path}：{err}")
            return False

    # ------------------------------------------------------------------ 素材收集

    def _collect_assets(self, directory: Path) -> Dict[str, Any]:
        posters: List[str] = []
        backdrops: List[str] = []
        child_count = 0
        child_dirs = 0
        video_only = str(getattr(self, "_asset_source", "mixed")) == "video_only"

        if not video_only:
            for img in self._images_in(directory):
                stem = img.stem.lower()
                if stem in BACKDROP_STEMS or stem.startswith(("backdrop", "fanart", "background")):
                    backdrops.append(str(img))
                else:
                    posters.append(str(img))

            # extrafanart 子目录图作为补充海报
            ef_dir = directory / "extrafanart"
            if ef_dir.is_dir():
                for img in self._images_in(ef_dir):
                    posters.append(str(img))

            # 直接子目录代表图（聚合封面素材）：
            # 父目录自身通常没有图，封面素材要向下取一层，和"是否递归处理"无关
            for sub in sorted(directory.iterdir()):
                if not sub.is_dir() or sub.name.lower() in SPECIAL_DIRS or sub.name.startswith("."):
                    continue
                child_dirs += 1
                if child_count >= 8:
                    continue
                rep = self._representative_image(sub)
                if not rep:
                    # 子目录本身还是个"容器"（例如 /private 下面全是分类目录），
                    # 再向下探一层，否则父目录的封面只能拿到零星几张图
                    rep = self._image_below(sub, 2)
                if rep:
                    posters.append(rep)
                    child_count += 1

            # 素材还不够撑起多图版式时，继续向下补几张（有上限，避免大目录扫爆）
            if len(posters) < 6:
                posters.extend(self._images_below(directory, 6 - len(posters), depth=3))

        # 视频截图：视频专用模式下全量取自视频；混合模式只在无图时兜底
        need_frames = video_only or (not posters and not backdrops)
        if need_frames and (video_only or self._capture_missing):
            shots = self._capture_frames(directory, 3 if video_only else 1)
            if shots:
                posters.extend(shots)
                if video_only:
                    backdrops.append(shots[0])

        # 去重：先按路径，再按内容（不同子目录里常出现同一张海报）
        posters = self._dedupe_images(posters)[:8]
        backdrops = self._dedupe_images(backdrops)[:4]
        if not backdrops and posters:
            backdrops = [posters[0]]

        bg_url = backdrops[0] if backdrops else (posters[0] if posters else None)
        works = child_dirs
        try:
            exts = (".mp4", ".mkv", ".ts", ".avi", ".mov", ".wmv", ".flv", ".m2ts", ".strm")
            works += sum(1 for f in directory.iterdir() if f.is_file() and f.suffix.lower() in exts)
        except Exception:
            pass
        return {
            "posters": posters,
            "backdrops": backdrops,
            "bg_url": bg_url,
            "count": works,
            "child_dirs": child_dirs,
            "title": directory.name,
        }

    def _images_in(self, directory: Path) -> List[Path]:
        """目录内可用作素材的图片：排除隐藏文件与本插件自己写出的成品。"""
        result: List[Path] = []
        if not directory.is_dir():
            return result
        manifest = self._read_manifest(directory)
        for item in sorted(directory.iterdir()):
            if not item.is_file():
                continue
            if item.suffix.lower() not in IMAGE_EXTS:
                continue
            if item.name.startswith("."):
                continue
            # folder.jpg / folder.png 一定是"封面成品"（本插件或胖虎/其它工具写的），
            # 绝不拿来当新封面的素材，否则会出现图片套娃
            if item.stem.lower() == "folder":
                continue
            if self._is_own_output(item, manifest):
                continue
            if not self._is_still(item):
                continue
            result.append(item)
        return result

    @staticmethod
    def _dedupe_images(refs: List[str]) -> List[str]:
        """按"路径相同 / 内容相同"两种维度去重，避免封面里出现同一张图两次。"""
        seen_paths = set()
        seen_prints: List[tuple] = []
        result: List[str] = []
        for ref in refs:
            if not ref or ref in seen_paths:
                continue
            seen_paths.add(ref)
            print_hash = None
            if not str(ref).startswith(("http://", "https://")):
                print_hash = FolderCover._image_fingerprint(ref)
            if print_hash is not None:
                # 同一张海报常被复制成不同体积/不同裁切的文件，
                # 用「画面指纹 + 长宽比」双条件判重，避免误杀不同画面
                bits, aspect = print_hash
                if any(bin(bits ^ other_bits).count("1") <= 8 and abs(aspect - other_aspect) <= 0.04
                       for other_bits, other_aspect in seen_prints):
                    continue
                seen_prints.append((bits, aspect))
            result.append(ref)
        return result

    @staticmethod
    def _image_fingerprint(ref: str) -> Optional[int]:
        """64 位 dHash，用于识别"画面几乎一样"的重复素材。"""
        try:
            from PIL import Image
            with Image.open(ref) as img:
                try:
                    img.draft("L", (64, 64))
                except Exception:
                    pass
                small = img.convert("L").resize((9, 8), Image.LANCZOS)
                px = list(small.getdata())
            bits = 0
            for row in range(8):
                for col in range(8):
                    left = px[row * 9 + col]
                    right = px[row * 9 + col + 1]
                    bits = (bits << 1) | (1 if left > right else 0)
            return bits, round(img.width / float(img.height), 2)
        except Exception:
            return None

    def _image_below(self, directory: Path, depth: int) -> Optional[str]:
        """在子目录里向下找一张图（深度受限），用于容器型目录聚合素材。"""
        if depth <= 0 or not directory.is_dir():
            return None
        try:
            subs = [d for d in sorted(directory.iterdir())
                    if d.is_dir() and d.name.lower() not in SPECIAL_DIRS and not d.name.startswith(".")]
        except Exception:
            return None
        images = self._images_in(directory)
        if images:
            return str(images[0])
        for sub in subs:
            found = self._image_below(sub, depth - 1)
            if found:
                return found
        return None

    def _images_below(self, directory: Path, limit: int, depth: int) -> List[str]:
        """广度向下收集若干张图（补足多图素材），不重复、有深度与数量上限。"""
        found: List[str] = []
        if limit <= 0 or depth <= 0:
            return found
        try:
            subs = [d for d in sorted(directory.iterdir())
                    if d.is_dir() and d.name.lower() not in SPECIAL_DIRS and not d.name.startswith(".")]
        except Exception:
            return found
        for sub in subs:
            if len(found) >= limit:
                break
            for img in self._images_in(sub):
                found.append(str(img))
                if len(found) >= limit:
                    break
            if len(found) < limit:
                found.extend(self._images_below(sub, limit - len(found), depth - 1))
        return found[:limit]

    def _representative_image(self, directory: Path) -> Optional[str]:
        """取子目录内一张代表图：poster/cover 优先，其次 thumb，再次首图。"""
        images = self._images_in(directory)
        if not images:
            return None
        priority = {"poster": 0, "cover": 1, "default": 2, "movie": 3}
        images.sort(key=lambda img: priority.get(img.stem.lower(), 9))
        return str(images[0])

    def _has_image_assets(self, directory: Path) -> bool:
        return len(self._images_in(directory)) > 0 or any(
            self._images_in(sub)
            for sub in directory.iterdir()
            if sub.is_dir() and sub.name.lower() not in SPECIAL_DIRS
        )

    # ------------------------------------------------------------------ 生成清单

    @staticmethod
    def _sha1_file(path: Path) -> str:
        try:
            digest = hashlib.sha1()
            with open(path, "rb") as handle:
                for chunk in iter(lambda: handle.read(65536), b""):
                    digest.update(chunk)
            return digest.hexdigest()
        except Exception:
            return ""

    def _read_manifest(self, directory: Path) -> Dict[str, str]:
        """读取目录内的生成清单：{文件名: sha1}。"""
        path = directory / MANIFEST_NAME
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return {str(k): str((v or {}).get("sha1") or "") for k, v in (data.get("files") or {}).items()}
        except Exception:
            return {}

    def _write_manifest(self, directory: Path, names: List[str],
                        style: Optional[Dict[str, Any]] = None) -> None:
        path = directory / MANIFEST_NAME
        entries: Dict[str, Any] = {}
        for name in names:
            target = directory / name
            if target.is_file():
                entries[name] = {
                    "sha1": self._sha1_file(target),
                    "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
        payload: Dict[str, Any] = {"tool": "foldercover", "version": self.plugin_version, "files": entries}
        style_data = style if style is not None else self._read_style(directory)
        if style_data:
            payload["style"] = style_data
        try:
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as err:
            logger.debug(f"文件夹封面：写入生成清单失败：{err}")

    @staticmethod
    def _is_still(path: Path) -> bool:
        """是否是可用作主视觉的剧照类图片（排除 logo、光盘、横幅、演员头像等美工图）。"""
        stem = path.stem.lower()
        if stem in ARTWORK_STEMS:
            return False
        if stem in STILL_STEMS:
            return True
        return any(token in stem for token in ("poster", "thumb", "fanart", "backdrop", "background", "still", "screenshot"))

    def _is_own_output(self, path: Path, manifest: Dict[str, str]) -> bool:
        """判断是否为本插件自己写出的成品，防止成品被当成素材造成图片套娃。"""
        if path.name.lower() in OUTPUT_NAMES:
            return True
        recorded = manifest.get(path.name)
        if not recorded:
            return False
        cache = self.__dict__.setdefault("_sha1_cache", {})
        key = (str(path), path.stat().st_mtime_ns, path.stat().st_size)
        if key not in cache:
            cache[key] = self._sha1_file(path)
        return cache[key] == recorded

    # ------------------------------------------------------------------ 视频截帧

    @staticmethod
    def _source_of(directory: Path) -> Optional[str]:
        """目录对应的视频来源：优先 strm 内的地址，其次本地视频文件。"""
        strm_files = [p for p in directory.iterdir() if p.suffix.lower() == ".strm"]
        video_files = [
            p for p in directory.iterdir()
            if p.suffix.lower() in (".mp4", ".mkv", ".avi", ".ts", ".wmv", ".mov", ".flv")
        ]
        if strm_files:
            try:
                return strm_files[0].read_text(encoding="utf-8").strip().strip('"').strip("'").strip()
            except Exception:
                return None
        if video_files:
            return str(video_files[0])
        return None

    def _capture_frames(self, directory: Path, count: int = 1) -> List[str]:
        """从视频截取若干帧作为素材（count=1 取中点，多帧取 30%/55%/78%）。"""
        source = self._source_of(directory)
        if not source:
            return []


        """从目录内 strm/视频中间帧截一张临时图，返回临时文件路径；失败 None。"""
        self._gen_strategy_count += 1
        if self._gen_strategy_count > self._gen_strategy_max_count:
            logger.info(f"文件夹封面：暂停 {self._gen_strategy_delay}s 防风控")
            time.sleep(self._gen_strategy_delay)
            self._gen_strategy_count = 0

        tmp_dir = Path(self.get_data_path()) / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:12]
        duration = self._probe_duration(source)

        fractions = [0.30, 0.55, 0.78] if count > 1 else [0.50]
        frames: List[str] = []
        for index, fraction in enumerate(fractions[:max(1, count)]):
            if duration and duration > 0:
                seconds = max(0.3, min(duration * fraction, max(0.1, duration - 0.1)))
            else:
                seconds = 181.0
            out_path = tmp_dir / f"{directory.name}-{digest}-{index}.jpg"
            cmd = ["ffmpeg", "-ss", f"{seconds:.3f}", "-i", source, "-vframes", "1",
                   "-f", "image2", "-y", str(out_path)]
            if not self._run(cmd) or not out_path.exists() or out_path.stat().st_size <= 0:
                # 单帧兜底：取首帧，避免整组失败
                cmd = ["ffmpeg", "-ss", "0.3", "-i", source, "-vframes", "1",
                       "-f", "image2", "-y", str(out_path)]
                if not self._run(cmd) or not out_path.exists() or out_path.stat().st_size <= 0:
                    continue
            frames.append(str(out_path))
        return frames

    def _probe_duration(self, source: str) -> Optional[float]:
        base_cmd = ["ffprobe", "-v", "error", "-of", "default=noprint_wrappers=1:nokey=1", source]
        for entries in ("format=duration", "stream=duration"):
            cmd = base_cmd[:3] + ["-show_entries", entries] + base_cmd[3:]
            try:
                result = subprocess.run(cmd, check=False, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, text=True, timeout=PROBE_TIMEOUT)
                output = (result.stdout or "").strip()
                if output:
                    return float(output)
            except Exception as err:
                logger.debug(f"文件夹封面：ffprobe 探测失败：{err}")
        return None

    def _resolve_seconds(self, source: str) -> float:
        duration = self._probe_duration(source)
        if duration is not None and duration > 0:
            target = duration / 2
            return max(0.3, min(target, max(0.1, duration - 0.1)))
        return 181.0

    @staticmethod
    def _run(cmd: List[str]) -> bool:
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, text=True, timeout=PROBE_TIMEOUT * 2)
            return True
        except subprocess.CalledProcessError as err:
            logger.debug(f"文件夹封面：ffmpeg 失败：{(err.stderr or '')[-200:]}")
            return False
        except Exception as err:
            logger.debug(f"文件夹封面：ffmpeg 异常：{err}")
            return False

    # ------------------------------------------------------------------ 收尾

    def stop_service(self) -> None:
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._event.set()
                    self._scheduler.shutdown()
                    self._event.clear()
                self._scheduler = None
        except Exception as err:
            logger.debug(f"文件夹封面停止服务：{err}")

    def post_message(self, channel: MessageChannel = None, mtype: NotificationType = None,
                     title: str = None, text: str = None, image: str = None,
                     link: str = None, userid: str = None):
        self.chain.post_message(Notification(
            channel=channel, mtype=mtype, title=title, text=text,
            image=image, link=link, userid=userid,
        ))
