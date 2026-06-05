import os
import re
from pathlib import Path

import requests
import yt_dlp
from PyQt5.QtCore import QThread, pyqtSignal

from videocaptioner.config import APPDATA_PATH
from videocaptioner.core.utils.logger import setup_logger

logger = setup_logger("video_download_thread")


class VideoDownloadThread(QThread):
    """视频下载线程类"""

    finished = pyqtSignal(str, object)  # 发送下载完成的信号(视频路径, 字幕路径)
    progress = pyqtSignal(int, str)  # 发送下载进度的信号
    error = pyqtSignal(str)  # 发送错误信息的信号

    def __init__(self, url: str, work_dir: str):
        super().__init__()
        self.url = url
        self.work_dir = work_dir

    def run(self):
        try:
            video_file_path, subtitle_file_path, thumbnail_file_path, info_dict = (
                self.download()
            )
            self.finished.emit(video_file_path, subtitle_file_path)
        except Exception as e:
            logger.exception("下载视频失败: %s", str(e))
            self.error.emit(self._friendly_error(str(e)))

    def _friendly_error(self, message: str) -> str:
        if "Sign in to confirm" in message or "not a bot" in message:
            return self.tr(
                "YouTube 要求登录验证。请导出浏览器 cookies.txt 放到：{path}，然后重试。"
            ).format(path=str(APPDATA_PATH / "cookies.txt"))
        if "cookies" in message.lower() and "youtube" in message.lower():
            return self.tr(
                "YouTube 下载需要 cookies.txt。请把导出的 cookies.txt 放到：{path}"
            ).format(path=str(APPDATA_PATH / "cookies.txt"))
        if "BiliBili" in message and "HTTP Error 412" in message:
            return self.tr(
                "B 站拒绝了本次下载请求。请导出浏览器 cookies.txt 放到：{path}，或换一个公开可下载链接。"
            ).format(path=str(APPDATA_PATH / "cookies.txt"))
        if "ted.com" in self.url and "HTTP Error 403" in message:
            return self.tr(
                "TED 拒绝了本次下载请求。已尝试备用视频流仍失败，请稍后重试或换一个公开可下载链接。"
            )
        return message

    def progress_hook(self, d):
        """下载进度回调函数"""
        if d["status"] == "downloading":
            percent = d["_percent_str"]
            speed = d["_speed_str"]

            # 提取百分比和速度的纯文本
            clean_percent = (
                percent.replace("\x1b[0;94m", "")
                .replace("\x1b[0m", "")
                .strip()
                .replace("%", "")
            )
            clean_speed = speed.replace("\x1b[0;32m", "").replace("\x1b[0m", "").strip()

            self.progress.emit(
                int(float(clean_percent)),
                f"下载进度: {clean_percent}%  速度: {clean_speed}",
            )

    def sanitize_filename(self, name: str, replacement: str = "_") -> str:
        """清理文件名中不允许的字符"""
        # 定义不允许的字符
        forbidden_chars = r'<>:"/\\|?*'

        # 替换不允许的字符
        sanitized = re.sub(f"[{re.escape(forbidden_chars)}]", replacement, name)

        # 移除控制字符
        sanitized = re.sub(r"[\0-\31]", "", sanitized)

        # 去除文件名末尾的空格和点
        sanitized = sanitized.rstrip(" .")

        # 限制文件名长度
        max_length = 255
        if len(sanitized) > max_length:
            base, ext = os.path.splitext(sanitized)
            base_max_length = max_length - len(ext)
            sanitized = base[:base_max_length] + ext

        # 处理Windows保留名称
        windows_reserved_names = {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            "COM1",
            "COM2",
            "COM3",
            "COM4",
            "COM5",
            "COM6",
            "COM7",
            "COM8",
            "COM9",
            "LPT1",
            "LPT2",
            "LPT3",
            "LPT4",
            "LPT5",
            "LPT6",
            "LPT7",
            "LPT8",
            "LPT9",
        }
        name_without_ext = os.path.splitext(sanitized)[0].upper()
        if name_without_ext in windows_reserved_names:
            sanitized = f"{sanitized}_"

        # 如果文件名为空，返回默认名称
        if not sanitized:
            sanitized = "default_filename"

        return sanitized

    def download(self, need_subtitle: bool = True, need_thumbnail: bool = False):
        """下载视频"""
        try:
            return self._download_with_format(
                "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                need_subtitle=need_subtitle,
                need_thumbnail=need_thumbnail,
            )
        except Exception as exc:
            if "ted.com" not in self.url or "HTTP Error 403" not in str(exc):
                raise

            logger.warning("TED mp4 直链下载失败，改用 HLS 流重试: %s", exc)
            return self._download_with_format(
                "bestvideo[protocol^=m3u8]+bestaudio[protocol^=m3u8]/best[protocol^=m3u8]/best",
                need_subtitle=need_subtitle,
                need_thumbnail=need_thumbnail,
            )

    def _download_with_format(
        self, video_format: str, *, need_subtitle: bool, need_thumbnail: bool
    ):
        """使用指定格式下载视频。"""
        logger.info("开始下载视频: %s", self.url)

        # 初始化 ydl 选项
        initial_ydl_opts = {
            "outtmpl": {
                "default": "%(title).200s.%(ext)s",  # 限制文件名最长200个字符
                "subtitle": "【下载字幕】.%(ext)s",
                "thumbnail": "thumbnail",
            },
            "format": video_format,  # 优先下载mp4格式，必要时由上层切换备用流
            "progress_hooks": [self.progress_hook],  # 下载进度钩子
            "quiet": True,  # 禁用日志输出
            "no_warnings": True,  # 禁用警告信息
            "noprogress": True,
            "writesubtitles": need_subtitle,  # 下载人工字幕
            "writeautomaticsub": need_subtitle,  # 下载自动生成的字幕
            "writethumbnail": need_thumbnail,  # 下载缩略图
            "thumbnail_format": "jpg",  # 指定缩略图的格式
        }

        # 检查 cookies 文件
        cookiefile_path = APPDATA_PATH / "cookies.txt"
        if cookiefile_path.exists():
            logger.info(f"使用cookiefile: {cookiefile_path}")
            initial_ydl_opts["cookiefile"] = str(cookiefile_path)

        with yt_dlp.YoutubeDL(initial_ydl_opts) as ydl:
            # 提取视频信息（不下载）
            info_dict = ydl.extract_info(self.url, download=False)

            # 设置动态下载文件夹为视频标题
            video_title = self.sanitize_filename(info_dict.get("title", "MyVideo"))
            video_work_dir = Path(self.work_dir) / self.sanitize_filename(video_title)
            subtitle_language = info_dict.get("language", None)
            if subtitle_language:
                subtitle_language = subtitle_language.lower().split("-")[0]
                ydl.params["subtitleslangs"] = [subtitle_language]

            try:
                subtitle_download_link = None
                subtitle_sources = [
                    info_dict.get("subtitles"),
                    info_dict.get("automatic_captions"),
                ]
                for captions in subtitle_sources:
                    if not captions or not subtitle_language:
                        continue
                    for lang_code in captions:
                        if lang_code.startswith(subtitle_language):
                            subtitle_download_link = captions[lang_code][-1]["url"]
                            break
                    if subtitle_download_link:
                        break
            except Exception:
                subtitle_download_link = None

            # 设置 yt-dlp 下载选项
            ydl_opts = {
                "paths": {
                    "home": str(video_work_dir),
                    "subtitle": str(video_work_dir / "subtitle"),
                    "thumbnail": str(video_work_dir),
                },
            }
            # 更新 yt-dlp 的配置
            ydl.params.update(ydl_opts)

            # 使用 process_info 进行下载
            ydl.process_info(info_dict)

            # 获取视频文件路径
            video_file_path = Path(ydl.prepare_filename(info_dict))
            if video_file_path.exists():
                video_file_path = str(video_file_path)
            else:
                video_file_path = None

            # 获取字幕文件路径
            subtitle_file_path = None
            for file in video_work_dir.glob("**/【下载字幕】*"):
                file_path = str(file)
                if subtitle_language and subtitle_language not in file_path:
                    logger.info(
                        "字幕语言错误，重新下载字幕: %s", subtitle_download_link
                    )
                    os.remove(file_path)
                    if subtitle_download_link:
                        response = requests.get(subtitle_download_link)
                        file_path = (
                            video_work_dir
                            / "subtitle"
                            / f"【下载字幕】{subtitle_language}.vtt"
                        )
                        if res := response.text:
                            with open(file_path, "w", encoding="utf-8") as f:
                                f.write(res)
                            subtitle_file_path = file_path
                else:
                    subtitle_file_path = file_path
                break

            # 获取缩略图文件路径
            thumbnail_file_path = None
            for file in video_work_dir.glob("**/thumbnail*"):
                thumbnail_file_path = str(file)
                break

            logger.info(f"视频下载完成: {video_file_path}")
            logger.info(f"字幕文件路径: {subtitle_file_path}")
            return video_file_path, subtitle_file_path, thumbnail_file_path, info_dict
