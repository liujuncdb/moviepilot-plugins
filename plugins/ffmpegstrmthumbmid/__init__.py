import os
import subprocess
import threading
import time

try:
    import fcntl
except ImportError:  # 非 Linux 环境下降级为不做互斥
    fcntl = None
from datetime import datetime, timedelta
from pathlib import Path
from threading import Event as ThreadEvent
from typing import List, Tuple, Dict, Any, Optional

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.log import logger
from app.plugins import _PluginBase
from app.utils.system import SystemUtils
from app.schemas import Notification, NotificationType, MessageChannel

ffmpeg_lock = threading.Lock()

# 探测片长的超时时间（秒）
PROBE_TIMEOUT = 8
# 截帧（ffmpeg）的超时时间（秒）
FFMPEG_TIMEOUT = 18
# 取不到片长时使用的默认固定时间（秒，约 00:03:01）
DEFAULT_FIXED_SECONDS = 181.0
# 判定文件对 ffmpeg 彻底不可读的错误特征，命中后不再做首帧兜底重试
UNREADABLE_MARKS = ("moov atom not found", "Invalid data found when processing input")
# 扫描互斥锁：避免插件重载/自动续跑与仍在运行的旧扫描并发处理同一批文件
SCAN_LOCK_FILE = "/config/ffmpegstrmthumbmid.scan.lock"


class FFmpegStrmThumbMid(_PluginBase):
    # 插件名称
    plugin_name = "FFmpegStrm缩略图·中间帧魔改"
    # 插件描述
    plugin_desc = "魔改版：自动探测影片片长并截取正中间一帧作为缩略图，短视频不再因固定时间点超出时长而失败。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/imaliang/MoviePilot-Plugins/main/icons/ffmpegstrm.png"
    # 插件版本
    plugin_version = "2.1.0"
    # 插件作者
    plugin_author = "imaliang (魔改: local)"
    # 作者主页
    author_url = "https://github.com/imaliang"
    # 插件配置项ID前缀
    plugin_config_prefix = "ffmpegstrmthumbmid_"
    # 加载顺序
    plugin_order = 4
    # 可使用的用户级别
    user_level = 1

    # 私有属性
    _scheduler = None
    _enabled = False
    _onlyonce = False
    _cron = None
    _timeline = "00:03:01"
    _scan_paths = ""
    _exclude_paths = ""
    _overlay = False
    # 是否自动截取影片正中间一帧
    _auto_mid = True
    # 中间帧偏移量（秒），正数向后偏移，负数向前偏移
    _mid_offset = 0
    _gen_strategy = "100=60"
    _gen_strategy_count = 0
    _gen_strategy_max_count = 100
    _gen_strategy_delay = 60
    # 退出事件
    _event = ThreadEvent()
    # 启动/重启后是否自动继续补齐缺失缩略图
    _auto_resume = True
    # 当前是否有扫描正在执行（用于判断 stop_service 是否要打断它）
    _scanning = False
    # 扫描互斥锁的文件句柄（持有期间不允许第二个扫描并发）
    _lock_fh = None

    def init_plugin(self, config: dict = None):
        # 读取配置
        if config:
            self._enabled = config.get("enabled")
            self._onlyonce = config.get("onlyonce")
            self._cron = config.get("cron")
            self._timeline = config.get("timeline")
            self._scan_paths = config.get("scan_paths") or ""
            self._exclude_paths = config.get("exclude_paths") or ""
            self._overlay = config.get("overlay") or False
            self._auto_resume = config.get("auto_resume") if config.get("auto_resume") is not None else True
            self._auto_mid = config.get("auto_mid") if config.get("auto_mid") is not None else True
            self._mid_offset = self._to_seconds(config.get("mid_offset")) or 0
            self._gen_strategy = config.get("gen_strategy") or "100=60"
            # 生成策略容错解析：格式非法时回退默认值，避免整个插件加载失败
            try:
                _parts = [p.strip() for p in str(self._gen_strategy).split("=")]
                self._gen_strategy_max_count = int(_parts[0])
                self._gen_strategy_delay = (
                    int(_parts[1]) if len(_parts) > 1 and _parts[1] else 60
                )
                if self._gen_strategy_max_count <= 0:
                    self._gen_strategy_max_count = 100
                if self._gen_strategy_delay < 0:
                    self._gen_strategy_delay = 0
            except Exception:
                logger.warning(f"生成策略格式无法解析：{self._gen_strategy}，回退为 100=60")
                self._gen_strategy_max_count = 100
                self._gen_strategy_delay = 60

        # 停止现有任务
        self.stop_service()

        # 启动定时任务 & 立即运行一次
        if self._enabled or self._onlyonce:
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            if self._cron:
                logger.info(f"FFmpegStrm中间帧缩略图服务启动，周期：{self._cron}")
                try:

                    self._scheduler.add_job(func=self.__libraryscan,
                                            trigger=CronTrigger.from_crontab(
                                                self._cron),
                                            name="FFmpegStrm中间帧缩略图",
                                            args=[False])
                except Exception as e:
                    logger.error(f"FFmpegStrm中间帧缩略图服务启动失败，原因：{str(e)}")
                    self.systemmessage.put(
                        f"FFmpegStrm中间帧缩略图服务启动失败，原因：{str(e)}", title="FFmpegStrm中间帧缩略图")
            if self._onlyonce:
                logger.info(f"FFmpegStrm中间帧缩略图服务，立即运行一次")
                is_overlay = self._overlay
                self._scheduler.add_job(func=self.__libraryscan, trigger='date',
                                        run_date=datetime.now(tz=pytz.timezone(
                                            settings.TZ)) + timedelta(seconds=3),
                                        name="FFmpegStrm中间帧缩略图",
                                        args=[is_overlay])
                # 关闭一次性开关
                self._onlyonce = False
                self.update_config({
                    "onlyonce": False,
                    "enabled": self._enabled,
                    "cron": self._cron,
                    "timeline": self._timeline,
                    "scan_paths": self._scan_paths,
                    "exclude_paths": self._exclude_paths,
                    "overlay": self._overlay,
                    "auto_mid": self._auto_mid,
                    "mid_offset": self._mid_offset,
                    "gen_strategy": self._gen_strategy,
                    "auto_resume": self._auto_resume,
                })
            else:
                # 关键修复：服务重启（MoviePilot 自身重启/容器重启/插件重载）后自动续跑
                if self._auto_resume and self._enabled:
                    logger.info("已开启自动续跑：启动 15 秒后继续补齐缺失缩略图（已存在的会自动跳过）")
                    try:
                        self._scheduler.add_job(func=self.__libraryscan, trigger='date',
                                                run_date=datetime.now(tz=pytz.timezone(
                                                    settings.TZ)) + timedelta(seconds=15),
                                                name="FFmpegStrm中间帧缩略图-续跑",
                                                args=[False])
                    except Exception as e:
                        logger.error(f"自动续跑任务注册失败：{str(e)}")
            if self._scheduler.get_jobs():
                # 启动服务
                self._scheduler.print_jobs()
                self._scheduler.start()

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        pass

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'onlyonce',
                                            'label': '立即运行一次',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'overlay',
                                            'label': '覆盖生成',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'auto_resume',
                                            'label': '重启后自动续跑',
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'auto_mid',
                                            'label': '自动截取中间帧',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'mid_offset',
                                            'label': '中间帧偏移(秒)',
                                            'placeholder': '0'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'timeline',
                                            'label': '固定时间(兜底)',
                                            'placeholder': '00:03:01'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'gen_strategy',
                                            'label': '生成策略',
                                            'placeholder': '100=60'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 8
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'cron',
                                            'label': '定时扫描周期',
                                            'placeholder': '5位cron表达式，留空关闭'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12
                                },
                                'content': [
                                    {
                                        'component': 'VTextarea',
                                        'props': {
                                            'model': 'scan_paths',
                                            'label': '定时扫描路径',
                                            'rows': 5,
                                            'placeholder': '每一行一个目录'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12
                                },
                                'content': [
                                    {
                                        'component': 'VTextarea',
                                        'props': {
                                            'model': 'exclude_paths',
                                            'label': '定时扫描排除路径',
                                            'rows': 2,
                                            'placeholder': '每一行一个目录'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                },
                                'content': [
                                    {
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'variant': 'tonal',
                                            'text': '开启「自动截取中间帧」时，先用 ffprobe 探测片长，再取影片正中间（可叠加偏移秒数）一帧；'
                                                    '若探测不到片长，或关闭自动中间帧，则使用「固定时间」；当固定时间超过片长时，自动回退到中间帧，避免短视频报错。'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                },
                                'content': [
                                    {
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'variant': 'tonal',
                                            'text': '默认情况下，只会生成缺失的缩略图。如果打开覆盖生成，会对所有文件重新生成缩略图。请谨慎打开。覆盖生成只对立即运行一次生效。'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                },
                                'content': [
                                    {
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'variant': 'tonal',
                                            'text': '生成策略 100=60 表示每生成100个缩略图就暂停60s，以防被风控。'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                },
                                'content': [
                                    {
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'warning',
                                            'variant': 'tonal',
                                            'text': '注意：点击「立即运行一次」后，扫描会在后台持续较长时间（数以千计的文件可能需要数小时）。运行期间请勿再次保存本插件配置，否则会立即中断本次扫描。已生成的缩略图不会丢失，下次运行会自动跳过它们，因此可以分多次逐步补齐。'
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": False,
            "onlyonce": False,
            "cron": "",
            "timeline": "00:03:01",
            "scan_paths": "",
            "exclude_paths": "",
            "overlay": False,
            "auto_mid": True,
            "mid_offset": 0,
            "gen_strategy": "100=60",
            "auto_resume": True,
        }

    def get_page(self) -> List[dict]:
        pass

    def _acquire_scan_lock(self) -> bool:
        """
        获取扫描互斥锁（内核 flock，进程退出自动释放，不会留下陈旧锁）

        已有扫描在跑时返回 False，避免插件重载后新旧扫描并发处理同一批文件。
        """
        if fcntl is None:
            return True
        try:
            if getattr(self, "_lock_fh", None):
                return True
            fh = open(SCAN_LOCK_FILE, "a+")
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                fh.close()
                logger.warning("检测到已有扫描任务正在运行，本次跳过，避免并发重复处理")
                return False
            self._lock_fh = fh
            return True
        except Exception as err:
            logger.debug(f"扫描锁处理异常（忽略并继续）：{str(err)}")
            return True

    def _release_scan_lock(self):
        """
        释放扫描互斥锁
        """
        try:
            fh = getattr(self, "_lock_fh", None)
            if fh:
                try:
                    if fcntl is not None:
                        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                finally:
                    fh.close()
                self._lock_fh = None
        except Exception as err:
            logger.debug(f"扫描锁释放失败（忽略）：{str(err)}")

    def __libraryscan(self, is_overlay=False):
        """
        开始扫描媒体库
        """
        if not self._scan_paths:
            logger.warning("FFmpegStrm中间帧缩略图未配置扫描路径，跳过本次扫描")
            return

        # 清除上一次运行残留的停止标记，保证本次扫描能真正执行
        self._event.clear()

        # 互斥：若已有扫描在跑（例如插件重载留下仍在执行的旧扫描），本次直接跳过
        if not self._acquire_scan_lock():
            return
        # 标记扫描进行中：此时收到的停止请求只取消定时任务，不打断本次扫描
        self._scanning = True

        # 排除目录
        exclude_paths = [p for p in self._exclude_paths.split("\n") if p.strip()]
        # 已选择的目录
        paths = [p for p in self._scan_paths.split("\n") if p.strip()]

        run_start = time.time()
        total_ok = total_skip = total_fail = 0
        logger.info(
            f"开始扫描，模式：{'覆盖生成' if is_overlay else '仅补缺失'}，"
            f"扫描路径 {len(paths)} 个，生成策略 {self._gen_strategy_max_count}="
            f"{self._gen_strategy_delay}")

        for path in paths:
            scan_path = Path(path)
            if not scan_path.exists():
                logger.warning(f"FFmpegStrm中间帧缩略图扫描路径不存在：{path}")
                continue

            try:
                files = SystemUtils.list_files(scan_path, extensions=['.strm'])
            except Exception as err:
                logger.error(f"遍历目录 {path} 失败：{str(err)}")
                continue

            # 预先统计，用于提示本次工作量（仅补缺失模式下可跳过已生成的）
            if is_overlay:
                pending = len(files)
            else:
                pending = sum(
                    1 for f in files
                    if not f.with_name(f.stem + "-thumb.jpg").exists())
            logger.info(
                f"开始FFmpegStrm中间帧缩略图扫描：{path}，共 {len(files)} 个 strm，"
                f"本次需处理 {pending} 个 ...")

            ok = skip = fail = done = 0
            dir_start = time.time()
            # 遍历目录下的所有文件
            for file_path in files:
                if self._event.is_set():
                    logger.warning(
                        f"扫描被中断（插件配置被保存或服务被停止）：{path} 已处理 "
                        f"{done}/{len(files)}，成功 {ok}、跳过 {skip}、失败 {fail}。"
                        f"已生成的缩略图不会丢失，下次运行会自动跳过它们。")
                    self._scanning = False
                    self._release_scan_lock()
                    return
                # 排除目录
                exclude_flag = False
                for exclude_path in exclude_paths:
                    try:
                        if file_path.is_relative_to(Path(exclude_path)):
                            exclude_flag = True
                            break
                    except Exception as err:
                        print(str(err))
                if exclude_flag:
                    logger.debug(f"{file_path} 在排除目录中，跳过 ...")
                    continue

                # 开始处理文件
                result = self.gen_file_thumb(file_path, is_overlay)
                done += 1
                if result == 'ok':
                    ok += 1
                elif result == 'skip':
                    skip += 1
                else:
                    fail += 1

                # 每 50 个或全部结束时输出一次进度，便于确认任务仍在运行
                if done % 50 == 0 or done == len(files):
                    elapsed = time.time() - dir_start
                    speed = done / elapsed if elapsed > 0 else 0
                    remain = (len(files) - done) / speed if speed > 0 else 0
                    logger.info(
                        f"进度 {path}：{done}/{len(files)} "
                        f"({done * 100 / max(1, len(files)):.1f}%) 成功 {ok} 跳过 {skip} "
                        f"失败 {fail}，已用 {elapsed / 60:.1f} 分钟，"
                        f"预计还需 {remain / 60:.1f} 分钟")

            logger.info(
                f"目录 {path} 扫描完成：成功 {ok}，跳过 {skip}，失败 {fail}，"
                f"耗时 {(time.time() - dir_start) / 60:.1f} 分钟")
            total_ok += ok
            total_skip += skip
            total_fail += fail

        logger.info(
            f"全部扫描结束：成功 {total_ok}，跳过 {total_skip}，失败 {total_fail}，"
            f"总耗时 {(time.time() - run_start) / 60:.1f} 分钟")
        self._scanning = False
        self._release_scan_lock()

    def gen_file_thumb(self, file_path: Path, is_overlay) -> str:
        """
        处理一个文件

        :return: ok=生成成功，skip=跳过（已存在或内容为空），fail=失败
        """
        # 单线程处理
        with ffmpeg_lock:
            try:
                # 提前定义缩略图路径，覆盖生成时也可使用
                thumb_path = file_path.with_name(
                    file_path.stem + "-thumb.jpg")
                if not is_overlay and thumb_path.exists():
                    logger.debug(f"缩略图已存在：{thumb_path}")
                    return 'skip'
                with open(file_path, 'r', encoding='utf-8') as file:
                    strm_path = file.read().strip().strip('"').strip("'").strip()
                if not strm_path:
                    logger.warning(f"{file_path} strm 内容为空，跳过")
                    return 'skip'
                self._gen_strategy_count += 1
                if self._gen_strategy_count > self._gen_strategy_max_count:
                    logger.info(f"暂停{self._gen_strategy_delay}秒...")
                    # 分片等待，便于被中断时立刻响应，不必等满整个暂停时间
                    for _ in range(int(self._gen_strategy_delay)):
                        if self._event.is_set():
                            break
                        time.sleep(1)
                    self._gen_strategy_count = 0  # 重置计数器
                if self.get_thumb(strm_path=strm_path,
                                  image_path=str(thumb_path), frames=self._timeline):
                    logger.info(f"{file_path} 缩略图已生成：{thumb_path}")
                    return 'ok'
                return 'fail'
            except Exception as err:
                logger.error(f"FFmpegStrm中间帧处理文件 {file_path} 时发生错误：{str(err)}")
                return 'fail'

    @staticmethod
    def _to_seconds(value: Any) -> Optional[float]:
        """
        把 HH:MM:SS、MM:SS 或纯秒数解析为秒数；失败返回 None
        """
        if value is None:
            return None
        s = str(value).strip().strip('"').strip("'").strip()
        if not s:
            return None
        try:
            if ":" in s:
                parts = [float(p) for p in s.split(":")]
                seconds = 0.0
                for p in parts:
                    seconds = seconds * 60 + p
                return seconds
            return float(s)
        except (ValueError, TypeError):
            return None

    def _probe_duration(self, strm_path: str) -> Optional[float]:
        """
        使用 ffprobe 探测影片时长（秒），失败返回 None
        """
        base_cmd = ["ffprobe", "-v", "error", "-of",
                    "default=noprint_wrappers=1:nokey=1", strm_path]
        # 先取容器格式时长，再回退到视频流时长
        for entries in ("format=duration", "stream=duration"):
            cmd = base_cmd[:3] + ["-show_entries", entries] + base_cmd[3:]
            try:
                result = subprocess.run(cmd, check=False, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, text=True,
                                        timeout=PROBE_TIMEOUT)
                output = (result.stdout or "").strip()
                if output:
                    return float(output)
                # 链接本身不可读时，第二种探测也必然失败，直接放弃省时间
                if any(mark in (result.stderr or "") for mark in UNREADABLE_MARKS):
                    logger.debug(f"ffprobe 判定链接不可读，跳过片长探测：{strm_path}")
                    break
            except Exception as err:
                logger.debug(f"ffprobe 探测片长失败：{str(err)}")
        return None

    def _resolve_seconds(self, strm_path: str, frames: str) -> Tuple[float, str]:
        """
        计算实际截取时间点。

        :return: (秒数, 命中方式说明)
        """
        fixed = self._to_seconds(frames) or DEFAULT_FIXED_SECONDS
        duration = self._probe_duration(strm_path)

        if duration is not None and duration > 0:
            if self._auto_mid:
                target = duration / 2 + (self._mid_offset or 0)
                mode = "中间帧"
            else:
                target = fixed
                mode = "固定时间"
                # 短视频保护：固定时间超过片长时回退到中间帧
                if target >= duration:
                    target = duration / 2 + (self._mid_offset or 0)
                    mode = "固定时间超片长，回退中间帧"
            # 钳制在有效区间内，避免 -ss 越界
            lower = 0.3
            upper = max(0.1, duration - 0.1)
            target = max(lower, min(target, upper))
            logger.debug(f"片长 {duration:.2f}s，{mode}，截取点 {target:.2f}s")
            return target, mode

        # 探测不到片长：回退固定时间
        logger.debug(f"未探测到片长，使用固定时间 {fixed:.2f}s")
        return fixed, "未取到片长，固定时间兜底"

    def get_thumb(self, strm_path: str, image_path: str, frames: str = None) -> bool:
        """
        使用 ffmpeg 从视频文件中截取缩略图（自动按片长取中间帧）
        """
        if not frames:
            frames = "00:03:01"
        if not strm_path or not image_path:
            return False

        seconds, mode = self._resolve_seconds(strm_path, frames)
        seconds_str = f"{seconds:.3f}"

        # 列表参数执行，避免路径/URL 中的空格与 & 被 shell 误解
        cmd = ["ffmpeg", "-ss", seconds_str, "-i", strm_path,
               "-vframes", "1", "-f", "image2", "-y", image_path]
        if self._run(cmd):
            logger.info(f"缩略图截取成功（{mode}，{seconds_str}s）：{image_path}")
            return True

        # 兜底：中间帧/固定点 seek 失败时，尝试从头取第一帧
        if seconds > 0.3:
            last_err = getattr(self, "_last_ffmpeg_err", "") or ""
            # 链接本身对 ffmpeg 不可读（moov 缺失/数据无效）时，首帧重试必然也失败，直接跳过省时
            if any(mark in last_err for mark in UNREADABLE_MARKS):
                logger.warning(f"链接对 ffmpeg 不可读（moov/数据无效），跳过首帧重试：{strm_path}")
                return False
            logger.warning(f"{seconds_str}s 截取失败，回退首帧重试：{strm_path}")
            fallback_cmd = ["ffmpeg", "-ss", "0.3", "-i", strm_path,
                            "-vframes", "1", "-f", "image2", "-y", image_path]
            if self._run(fallback_cmd):
                logger.info(f"首帧兜底截取成功：{image_path}")
                return True
        return False

    def _run(self, cmd: List[str]) -> bool:
        """
        执行命令，成功返回 True；失败时把错误精简后记录到 _last_ffmpeg_err
        """
        self._last_ffmpeg_err = ""
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, text=True, timeout=FFMPEG_TIMEOUT)
            return True
        except subprocess.CalledProcessError as err:
            self._last_ffmpeg_err = err.stderr or ""
            # 只保留最后 3 行有效错误，避免 ffmpeg banner 把日志刷爆
            tail = [x for x in self._last_ffmpeg_err.splitlines() if x.strip()][-3:]
            logger.error(f"ffmpeg 执行失败：{' | '.join(tail)}")
            return False
        except subprocess.TimeoutExpired:
            logger.error(f"ffmpeg 执行超时（超过 {FFMPEG_TIMEOUT}s）")
            return False
        except Exception as err:
            self._last_ffmpeg_err = str(err)
            logger.error(f"ffmpeg 执行异常：{str(err)}")
            return False

    def execute(self, cmd: str) -> str:
        """
        兼容保留：执行命令，获得返回结果
        """
        try:
            result = subprocess.run(cmd, check=True, shell=True, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True)
            output = result.stdout.strip() if result.stdout else result.stderr.strip()
            return output
        except subprocess.CalledProcessError as err:
            logger.error(f"ffmpeg执行命令 '{cmd}' 失败-error: {err.stderr}")
            return ""

    def stop_service(self):
        """
        退出插件

        关键行为：当全量扫描正在执行时，只取消后续定时任务，不打断已经在跑的
        扫描线程。否则 MoviePilot 保存配置 / 插件重载 / 服务重启都会把补齐任务打断。
        """
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    if getattr(self, "_scanning", False):
                        logger.warning(
                            "检测到全量扫描正在进行：已取消后续定时任务，"
                            "但保留本次扫描继续执行（保存配置/重载不会再打断它）")
                        try:
                            # wait=False：不等待、也不终止正在执行的扫描任务
                            self._scheduler.shutdown(wait=False)
                        except Exception as err:
                            logger.debug(f"调度器关闭异常（可忽略）：{str(err)}")
                    else:
                        logger.info("收到停止请求，结束插件服务")
                        self._event.set()
                        self._scheduler.shutdown()
                        self._event.clear()
                self._scheduler = None
        except Exception as e:
            print(str(e))

    def post_message(self, channel: MessageChannel = None, mtype: NotificationType = None, title: str = None,
                     text: str = None, image: str = None, link: str = None, userid: str = None):
        """
        发送消息
        """
        self.chain.post_message(Notification(
            channel=channel, mtype=mtype, title=title, text=text,
            image=image, link=link, userid=userid
        ))
