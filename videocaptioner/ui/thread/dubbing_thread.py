import datetime
import shutil
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

from videocaptioner.core.dubbing import DubbingPipeline, SpeakerProfile, build_dubbing_config
from videocaptioner.core.entities import DubbingTask
from videocaptioner.core.utils.logger import setup_logger

logger = setup_logger("dubbing_thread")


class DubbingThread(QThread):
    finished = pyqtSignal(DubbingTask)
    progress = pyqtSignal(int, str)
    error = pyqtSignal(str)

    def __init__(self, task: DubbingTask):
        super().__init__()
        self.task = task
        logger.debug(f"初始化 DubbingThread，任务: {self.task}")

    def run(self):
        try:
            self.task.started_at = datetime.datetime.now()
            config = self.task.dubbing_config
            if config is None:
                raise ValueError(self.tr("配音配置为空"))
            if not self.task.subtitle_path:
                raise ValueError(self.tr("字幕路径为空"))
            if not self.task.output_audio_path:
                raise ValueError(self.tr("输出音频路径为空"))

            logger.info(f"\n{config.print_config()}")
            self.progress.emit(2, self.tr("准备配音"))

            speaker_profiles = {
                name: SpeakerProfile(name=name, voice=voice)
                for name, voice in config.speaker_voices.items()
                if voice
            }
            if config.clone_audio_path:
                speaker_profiles["default"] = SpeakerProfile(
                    name="default",
                    clone_audio_path=config.clone_audio_path,
                    clone_audio_text=config.clone_audio_text,
                )

            core_config = build_dubbing_config(
                provider=config.provider,
                preset=config.preset,
                api_key=config.api_key,
                api_base=config.api_base,
                model=config.model,
                voice=config.voice,
                timing=config.timing,
                audio_mode=config.audio_mode,
                tts_workers=config.tts_workers,
                use_cache=config.use_cache,
                speaker_profiles=speaker_profiles,
            )

            output_audio = Path(self.task.output_audio_path)
            artifact_dir = output_audio.parent / ".videocaptioner" / output_audio.stem
            artifact_dir.mkdir(parents=True, exist_ok=True)

            result = DubbingPipeline(core_config).run(
                self.task.subtitle_path,
                self.task.output_audio_path,
                video_path=self.task.video_path or None,
                output_video_path=self.task.output_video_path or None,
                text_track=config.text_track,
                work_dir=str(artifact_dir / "parts"),
                callback=self._on_progress,
            )
            report_path = Path(result.audio_path).with_suffix(".dubbing.json")
            if report_path.exists():
                shutil.move(str(report_path), str(artifact_dir / report_path.name))

            self.task.output_audio_path = str(result.audio_path)
            self.task.output_video_path = str(result.video_path) if result.video_path else None
            self.task.completed_at = datetime.datetime.now()
            self.progress.emit(100, self.tr("配音完成"))
            self.finished.emit(self.task)
        except Exception as exc:
            logger.exception(f"配音失败: {exc}")
            self.error.emit(str(exc))
            self.progress.emit(100, self.tr("配音失败"))

    def _on_progress(self, value: int, message: str):
        self.progress.emit(value, self.tr(message))
