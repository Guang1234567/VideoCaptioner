import tempfile
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

from videocaptioner.config import ASSETS_PATH
from videocaptioner.core.dubbing import DubbingPipeline, build_dubbing_config, get_dubbing_preset
from videocaptioner.core.utils.logger import setup_logger
from videocaptioner.ui.common.config import cfg

logger = setup_logger("voice_preview_thread")

SAMPLE_TEXT = "你好，这是卡卡字幕助手的配音试听。"


class VoicePreviewThread(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, preset_name: str):
        super().__init__()
        self.preset_name = preset_name

    def run(self):
        try:
            bundled = self._bundled_preview()
            if bundled:
                self.finished.emit(str(bundled))
                return

            preset = get_dubbing_preset(self.preset_name)
            api_key = cfg.dubbing_api_key.value
            api_base = cfg.dubbing_api_base.value
            model = cfg.dubbing_model.value or preset.model
            if preset.provider == "edge":
                api_key = ""
                api_base = ""
            elif not api_key:
                raise ValueError(f"{preset.provider} 试听需要先在设置里填写配音 API Key")

            core_config = build_dubbing_config(
                provider=preset.provider,
                preset=self.preset_name,
                api_key=api_key,
                api_base=api_base,
                model=model,
                voice=preset.voice,
                timing="balanced",
                audio_mode="replace",
                tts_workers=1,
                use_cache=cfg.cache_enabled.value,
            )
            work = Path(tempfile.mkdtemp(prefix="videocaptioner-voice-"))
            srt = work / "preview.srt"
            srt.write_text(
                f"1\n00:00:00,000 --> 00:00:03,000\n{SAMPLE_TEXT}\n",
                encoding="utf-8",
            )
            output = work / f"{self.preset_name}.wav"
            result = DubbingPipeline(core_config).run(
                str(srt),
                str(output),
                work_dir=str(work / "parts"),
            )
            self.finished.emit(str(result.audio_path))
        except Exception as exc:
            logger.exception("音色试听失败: %s", exc)
            self.error.emit(str(exc))

    def _bundled_preview(self) -> Path | None:
        preview_dir = ASSETS_PATH / "voice-previews"
        for suffix in (".mp3", ".wav", ".flac"):
            path = preview_dir / f"{self.preset_name}{suffix}"
            if path.exists() and path.stat().st_size > 0:
                return path
        return None
