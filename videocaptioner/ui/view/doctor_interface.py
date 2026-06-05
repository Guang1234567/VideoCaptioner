from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    InfoBar,
    PrimaryPushButton,
    PushButton,
    ScrollArea,
)
from qfluentwidgets import FluentIcon as FIF

from videocaptioner.cli.commands.doctor import Check, run_diagnostics
from videocaptioner.core.constant import INFOBAR_DURATION_ERROR, INFOBAR_DURATION_SUCCESS
from videocaptioner.ui.common.config import cfg


class DoctorThread(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, check_api: bool = False):
        super().__init__()
        self.check_api = check_api

    def run(self):
        try:
            self.finished.emit(run_diagnostics(_build_doctor_config(), check_api=self.check_api))
        except Exception as exc:
            self.error.emit(str(exc))


class DoctorInterface(ScrollArea):
    """桌面端诊断页。"""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setWindowTitle(self.tr("诊断"))
        self.thread: DoctorThread | None = None
        self.scrollWidget = QWidget()
        self.pageLayout = QVBoxLayout(self.scrollWidget)
        self.titleLabel = QLabel(self.tr("诊断"), self)
        self.summaryLabel = BodyLabel(self.tr("检查依赖、下载、转录、LLM、翻译和配音配置"), self.scrollWidget)
        self.introCard = CardWidget(self.scrollWidget)
        self.resultContainer = QWidget(self.scrollWidget)
        self.resultLayout = QVBoxLayout(self.resultContainer)
        self.resultLayout.setContentsMargins(0, 0, 0, 0)
        self.resultLayout.setSpacing(10)
        self._init_ui()

    def _init_ui(self):
        self.resize(1000, 800)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # type: ignore
        self.setViewportMargins(0, 80, 0, 20)
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)
        self.setObjectName("doctorInterface")
        self.scrollWidget.setObjectName("scrollWidget")
        self.titleLabel.setObjectName("settingLabel")
        self.titleLabel.move(36, 30)
        self.setStyleSheet(
            """
            DoctorInterface, #scrollWidget { background-color: transparent; }
            QScrollArea { border: none; background-color: transparent; }
            QLabel#settingLabel { font: 33px 'Microsoft YaHei'; background-color: transparent; color: white; }
            """
        )

        toolbar = QWidget(self.scrollWidget)
        toolbarLayout = QHBoxLayout(toolbar)
        toolbarLayout.setContentsMargins(0, 0, 0, 0)
        toolbarLayout.addWidget(self.summaryLabel, 1)
        self.runButton = PrimaryPushButton(self.tr("运行诊断"), toolbar, FIF.SEARCH)
        self.deepRunButton = PushButton(self.tr("深度诊断"), toolbar, FIF.SYNC)
        self.deepRunButton.setToolTip(self.tr("包含少量真实 API 请求，可能产生费用"))
        toolbarLayout.addWidget(self.runButton)
        toolbarLayout.addWidget(self.deepRunButton)

        introLayout = QVBoxLayout(self.introCard)
        introLayout.setContentsMargins(16, 14, 16, 14)
        introLayout.setSpacing(8)
        introLayout.addWidget(BodyLabel(self.tr("开始前可以先做一次诊断"), self.introCard))
        introLayout.addWidget(
            CaptionLabel(
                self.tr("普通诊断检查 Python、FFmpeg、yt-dlp、配置文件、转录、字幕处理和配音参数。"),
                self.introCard,
            )
        )
        introLayout.addWidget(
            CaptionLabel(
                self.tr("深度诊断会在普通诊断基础上尝试真实 API 检查，可能产生少量调用。"),
                self.introCard,
            )
        )

        self.pageLayout.setSpacing(18)
        self.pageLayout.setContentsMargins(36, 10, 36, 0)
        self.pageLayout.addWidget(toolbar)
        self.pageLayout.addWidget(self.introCard)
        self.pageLayout.addWidget(self.resultContainer)
        self.pageLayout.addStretch(1)
        self.runButton.clicked.connect(lambda: self._run(False))
        self.deepRunButton.clicked.connect(lambda: self._run(True))

    def _run(self, check_api: bool):
        if self.thread and self.thread.isRunning():
            return
        self._clear_results()
        self.introCard.hide()
        self.resultLayout.addWidget(self._message_card(self.tr("正在检查"), self.tr("正在检查本机依赖和当前配置...")))
        self.resultContainer.adjustSize()
        self.pageLayout.invalidate()
        self.runButton.setEnabled(False)
        self.deepRunButton.setEnabled(False)
        self.thread = DoctorThread(check_api=check_api)
        self.thread.finished.connect(self._on_finished)
        self.thread.error.connect(self._on_error)
        self.thread.start()

    def _on_finished(self, checks: list[Check]):
        self.runButton.setEnabled(True)
        self.deepRunButton.setEnabled(True)
        self._clear_results()
        errors = sum(1 for c in checks if c.status == "error")
        warnings = sum(1 for c in checks if c.status == "warn")
        for check in checks:
            self.resultLayout.addWidget(self._result_card(check))
        self.resultContainer.adjustSize()
        self.pageLayout.invalidate()
        if errors:
            InfoBar.error(
                self.tr("诊断完成"),
                self.tr("发现 {errors} 个错误，{warnings} 个警告").format(errors=errors, warnings=warnings),
                duration=INFOBAR_DURATION_ERROR,
                parent=self,
            )
        else:
            InfoBar.success(
                self.tr("诊断完成"),
                self.tr("发现 {warnings} 个警告").format(warnings=warnings),
                duration=INFOBAR_DURATION_SUCCESS,
                parent=self,
            )

    def _on_error(self, message: str):
        self.runButton.setEnabled(True)
        self.deepRunButton.setEnabled(True)
        InfoBar.error(self.tr("诊断失败"), message, duration=INFOBAR_DURATION_ERROR, parent=self)

    def _result_card(self, check: Check) -> CardWidget:
        card = CardWidget(self.resultContainer)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        title = BodyLabel(f"{_status_label(check.status)}  {check.name}", card)
        message = CaptionLabel(check.message, card)
        layout.addWidget(title)
        layout.addWidget(message)
        if check.fix:
            fix = CaptionLabel(self.tr("建议：") + check.fix, card)
            layout.addWidget(fix)
        card.setMinimumHeight(86 if check.fix else 62)
        return card

    def _message_card(self, title: str, message: str) -> CardWidget:
        card = CardWidget(self.resultContainer)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.addWidget(BodyLabel(title, card))
        layout.addWidget(CaptionLabel(message, card))
        card.setMinimumHeight(62)
        return card

    def _clear_results(self):
        while self.resultLayout.count():
            item = self.resultLayout.takeAt(0)
            if widget := item.widget():
                widget.deleteLater()


def _status_label(status: str) -> str:
    return {"ok": "OK", "warn": "WARN", "error": "ERROR"}.get(status, status.upper())


def _build_doctor_config() -> dict:
    provider = cfg.dubbing_provider.value
    return {
        "llm": {
            "api_key": _current_llm_api_key(),
            "api_base": _current_llm_api_base(),
            "model": _current_llm_model(),
        },
        "whisper_api": {
            "api_key": cfg.whisper_api_key.value,
            "api_base": cfg.whisper_api_base.value,
            "model": cfg.whisper_api_model.value or "whisper-1",
        },
        "transcribe": {
            "asr": cfg.transcribe_model.value.name.lower().replace("_", "-"),
        },
        "subtitle": {
            "optimize": cfg.need_optimize.value,
            "split": cfg.need_split.value,
        },
        "translate": {
            "service": cfg.translator_service.value.name.lower(),
        },
        "dubbing": {
            "provider": provider,
            "preset": cfg.dubbing_preset.value,
            "api_key": cfg.dubbing_api_key.value,
            "api_base": cfg.dubbing_api_base.value,
            "model": cfg.dubbing_model.value,
            "voice": cfg.dubbing_voice.value,
            "timing": "balanced",
            "audio_mode": "replace",
        },
    }


def _current_llm_api_key() -> str:
    service = cfg.llm_service.value
    return {
        "OPENAI": cfg.openai_api_key.value,
        "SILICON_CLOUD": cfg.silicon_cloud_api_key.value,
        "DEEPSEEK": cfg.deepseek_api_key.value,
        "OLLAMA": cfg.ollama_api_key.value,
        "LM_STUDIO": cfg.lm_studio_api_key.value,
        "GEMINI": cfg.gemini_api_key.value,
        "CHATGLM": cfg.chatglm_api_key.value,
    }.get(service.name, "")


def _current_llm_api_base() -> str:
    service = cfg.llm_service.value
    return {
        "OPENAI": cfg.openai_api_base.value,
        "SILICON_CLOUD": cfg.silicon_cloud_api_base.value,
        "DEEPSEEK": cfg.deepseek_api_base.value,
        "OLLAMA": cfg.ollama_api_base.value,
        "LM_STUDIO": cfg.lm_studio_api_base.value,
        "GEMINI": cfg.gemini_api_base.value,
        "CHATGLM": cfg.chatglm_api_base.value,
    }.get(service.name, "")


def _current_llm_model() -> str:
    service = cfg.llm_service.value
    return {
        "OPENAI": cfg.openai_model.value,
        "SILICON_CLOUD": cfg.silicon_cloud_model.value,
        "DEEPSEEK": cfg.deepseek_model.value,
        "OLLAMA": cfg.ollama_model.value,
        "LM_STUDIO": cfg.lm_studio_model.value,
        "GEMINI": cfg.gemini_model.value,
        "CHATGLM": cfg.chatglm_model.value,
    }.get(service.name, "")
