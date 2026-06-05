import tempfile
from pathlib import Path

from PyQt5.QtCore import QThread, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QGridLayout
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    InfoBar,
    MessageBoxBase,
    PrimaryPushButton,
    PushButton,
)

from videocaptioner.core.dubbing import DubbingPipeline, build_dubbing_config
from videocaptioner.core.dubbing.presets import get_dubbing_preset
from videocaptioner.core.utils.logger import setup_logger
from videocaptioner.ui.common.config import cfg

logger = setup_logger("dubbing_voice_dialog")


VOICE_CHOICES = [
    ("edge-cn-female", "中文女声", "免费 Edge 音色，适合中文解说"),
    ("edge-cn-male", "中文男声", "免费 Edge 音色，适合旁白"),
    ("edge-en-female", "英文女声", "免费 Edge 音色，适合英文内容"),
    ("edge-en-male", "英文男声", "免费 Edge 音色，适合英文旁白"),
    ("gemini-en-friendly", "Gemini 友好英文", "需要 Gemini Key，不支持克隆"),
    ("gemini-en-neutral", "Gemini 自然英文", "需要 Gemini Key，不支持克隆"),
    ("siliconflow-cn-female", "硅基中文女声", "需要 SiliconFlow Key，支持克隆"),
    ("siliconflow-cn-male", "硅基中文男声", "需要 SiliconFlow Key，支持克隆"),
]

SAMPLE_TEXT = "你好，这是卡卡字幕助手的配音试听。"


class VoicePreviewThread(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, preset_name: str):
        super().__init__()
        self.preset_name = preset_name

    def run(self):
        try:
            preset = get_dubbing_preset(self.preset_name)
            api_key = cfg.dubbing_api_key.value
            api_base = cfg.dubbing_api_base.value
            model = cfg.dubbing_model.value
            if preset.provider == "edge":
                api_key = ""
                api_base = ""
                model = ""
            elif not api_key:
                raise ValueError(f"{preset.provider} 试听需要先在设置里填写配音 API Key")

            core_config = build_dubbing_config(
                provider=preset.provider,
                preset=self.preset_name,
                api_key=api_key,
                api_base=api_base,
                model=model,
                voice=preset.voice,
                timing="natural",
                audio_mode="replace",
                tts_workers=1,
                use_cache=True,
            )
            work = Path(tempfile.mkdtemp(prefix="videocaptioner-voice-"))
            srt = work / "preview.srt"
            srt.write_text(
                f"1\n00:00:00,000 --> 00:00:03,000\n{SAMPLE_TEXT}\n",
                encoding="utf-8",
            )
            output = work / f"{self.preset_name}.wav"
            result = DubbingPipeline(core_config).run(str(srt), str(output), work_dir=str(work / "parts"))
            self.finished.emit(str(result.audio_path))
        except Exception as exc:
            logger.exception(f"音色试听失败: {exc}")
            self.error.emit(str(exc))


class DubbingVoiceDialog(MessageBoxBase):
    presetSelected = pyqtSignal(str)

    def __init__(self, current_preset: str, parent=None):
        super().__init__(parent)
        self.current_preset = current_preset
        self.preview_thread: VoicePreviewThread | None = None
        self.setWindowTitle(self.tr("选择配音音色"))
        self._init_ui()

    def _init_ui(self):
        title = BodyLabel(self.tr("选择配音音色"), self)
        subtitle = BodyLabel(self.tr("先试听，再选择。Edge 音色免 API Key，Gemini 和 SiliconFlow 需要在设置里填写 Key。"), self)
        self.viewLayout.addWidget(title)
        self.viewLayout.addWidget(subtitle)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)
        for index, (preset, name, desc) in enumerate(VOICE_CHOICES):
            grid.addWidget(self._voice_card(preset, name, desc), index // 2, index % 2)
        self.viewLayout.addLayout(grid)
        self.viewLayout.setSpacing(12)

        self.widget.setMinimumWidth(760)
        self.yesButton.hide()
        self.cancelButton.setText(self.tr("关闭"))

    def _voice_card(self, preset: str, name: str, desc: str) -> CardWidget:
        card = CardWidget(self)
        card.setMinimumHeight(118)
        layout = QGridLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(8)

        title = BodyLabel(name, card)
        detail = BodyLabel(desc, card)
        preview = PushButton(self.tr("试听"), card)
        use_text = self.tr("当前") if preset == self.current_preset else self.tr("使用")
        use = PrimaryPushButton(use_text, card) if preset == self.current_preset else PushButton(use_text, card)

        preview.clicked.connect(lambda: self._preview(preset))
        use.clicked.connect(lambda: self._select(preset))

        layout.addWidget(title, 0, 0, 1, 2)
        layout.addWidget(detail, 1, 0, 1, 2)
        layout.addWidget(preview, 2, 0)
        layout.addWidget(use, 2, 1)
        return card

    def _preview(self, preset: str):
        if self.preview_thread and self.preview_thread.isRunning():
            return
        self.preview_thread = VoicePreviewThread(preset)
        self.preview_thread.finished.connect(self._on_preview_finished)
        self.preview_thread.error.connect(self._on_preview_error)
        self.preview_thread.start()

    def _on_preview_finished(self, path: str):
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _on_preview_error(self, message: str):
        InfoBar.error(self.tr("试听失败"), message, parent=self)

    def _select(self, preset: str):
        self.presetSelected.emit(preset)
        self.accept()
