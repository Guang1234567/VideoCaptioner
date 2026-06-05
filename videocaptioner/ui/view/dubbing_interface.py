from pathlib import Path

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
from PyQt5.QtWidgets import QFileDialog, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    ExpandLayout,
    InfoBar,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    PushSettingCard,
    ScrollArea,
    SegmentedWidget,
    SettingCard,
    SettingCardGroup,
    setFont,
)
from qfluentwidgets import FluentIcon as FIF

from videocaptioner.core.constant import INFOBAR_DURATION_ERROR, INFOBAR_DURATION_SUCCESS
from videocaptioner.core.dubbing import get_dubbing_preset
from videocaptioner.ui.common.config import cfg
from videocaptioner.ui.common.dubbing_options import (
    DUBBING_PROVIDERS,
    get_provider_option,
    get_provider_voices,
    get_voice_title,
)
from videocaptioner.ui.components.EditComboBoxSettingCard import EditComboBoxSettingCard
from videocaptioner.ui.components.LineEditSettingCard import LineEditSettingCard
from videocaptioner.ui.thread.voice_preview_thread import VoicePreviewThread


class VoiceCard(CardWidget):
    def __init__(self, preset: str, title: str, desc: str, parent=None):
        super().__init__(parent)
        self.preset = preset
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        self.titleLabel = BodyLabel(title, self)
        self.descLabel = CaptionLabel(desc, self)
        self.descLabel.setWordWrap(True)
        self.stateLabel = CaptionLabel("", self)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.playButton = PushButton(self.tr("试听"), self)
        self.useButton = PrimaryPushButton(self.tr("使用"), self)
        self.playButton.setMinimumHeight(34)
        self.useButton.setMinimumHeight(34)
        actions.addWidget(self.playButton, 1)
        actions.addWidget(self.useButton, 1)

        layout.addWidget(self.titleLabel)
        layout.addWidget(self.descLabel)
        layout.addStretch(1)
        layout.addWidget(self.stateLabel)
        layout.addLayout(actions)
        self.setMinimumHeight(136)

    def setCurrent(self, current: bool):
        self.stateLabel.setText(self.tr("当前音色") if current else "")
        self.useButton.setText(self.tr("已选择") if current else self.tr("使用"))
        self.useButton.setEnabled(not current)


class CloneAudioSettingCard(SettingCard):
    def __init__(self, parent=None):
        super().__init__(
            FIF.MICROPHONE,
            "参考音频",
            "SiliconFlow 音色克隆需要一段清晰参考音频",
            parent,
        )
        self.lineEdit = LineEdit(self)
        self.lineEdit.setPlaceholderText(self.tr("选择参考音频文件"))
        self.button = PushButton(self.tr("浏览"), self)
        self.hBoxLayout.addWidget(self.lineEdit, 1, Qt.AlignRight)  # type: ignore
        self.hBoxLayout.addSpacing(8)
        self.hBoxLayout.addWidget(self.button, 0, Qt.AlignRight)  # type: ignore
        self.hBoxLayout.addSpacing(16)
        self.lineEdit.setText(cfg.dubbing_clone_audio.value)
        self.lineEdit.textChanged.connect(lambda text: cfg.set(cfg.dubbing_clone_audio, text))
        self.button.clicked.connect(self._choose_file)

    def _choose_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("选择参考音频"),
            "",
            self.tr("音频文件 (*.wav *.mp3 *.m4a *.flac *.ogg *.opus)"),
        )
        if file_path:
            self.lineEdit.setText(file_path)


class DubbingInterface(ScrollArea):
    """配音音色与提供商配置页。"""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setWindowTitle(self.tr("配音"))
        self.preview_thread: VoicePreviewThread | None = None
        self.player = QMediaPlayer(self)
        self.scrollWidget = QWidget()
        self.expandLayout = ExpandLayout(self.scrollWidget)
        self.titleLabel = QLabel(self.tr("配音"), self)
        self.providerTitleLabel = BodyLabel("", self.scrollWidget)
        self.providerDescLabel = CaptionLabel("", self.scrollWidget)
        self.voice_cards: list[VoiceCard] = []

        self._init_ui()
        self._connect_signals()
        self._on_provider_changed(cfg.dubbing_provider.value)

    def _init_ui(self):
        self.resize(1000, 800)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # type: ignore
        self.setViewportMargins(0, 80, 0, 20)
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)
        self.setObjectName("dubbingInterface")
        self.scrollWidget.setObjectName("scrollWidget")
        self.titleLabel.setObjectName("settingLabel")
        self.titleLabel.move(36, 30)
        self.setStyleSheet(
            """
            DubbingInterface, #scrollWidget { background-color: transparent; }
            QScrollArea { border: none; background-color: transparent; }
            QLabel#settingLabel { font: 33px 'Microsoft YaHei'; background-color: transparent; color: white; }
            """
        )

        self.providerPanel = CardWidget(self.scrollWidget)
        self.providerPanel.setMinimumHeight(118)
        providerLayout = QVBoxLayout(self.providerPanel)
        providerLayout.setContentsMargins(18, 14, 18, 14)
        providerLayout.setSpacing(10)
        self.providerSegment = SegmentedWidget(self.providerPanel)
        for option in DUBBING_PROVIDERS:
            self.providerSegment.addItem(
                routeKey=option.key,
                text=option.title,
                onClick=lambda key=option.key: self._on_provider_changed(key),
            )
        setFont(self.providerSegment, 13)
        providerLayout.addWidget(self.providerSegment)
        providerLayout.addWidget(self.providerTitleLabel)
        providerLayout.addWidget(self.providerDescLabel)

        self.configGroup = SettingCardGroup(self.tr("连接配置"), self.scrollWidget)
        self.apiKeyCard = LineEditSettingCard(
            cfg.dubbing_api_key,
            FIF.FINGERPRINT,
            self.tr("API Key"),
            self.tr("Edge 可留空；Gemini 和 SiliconFlow 必填"),
            "",
            self.configGroup,
        )
        self.apiBaseCard = LineEditSettingCard(
            cfg.dubbing_api_base,
            FIF.LINK,
            self.tr("Base URL"),
            self.tr("需要代理或兼容网关时修改"),
            "https://api.siliconflow.cn/v1",
            self.configGroup,
        )
        self.modelCard = EditComboBoxSettingCard(
            cfg.dubbing_model,
            FIF.ROBOT,  # type: ignore
            self.tr("模型"),
            self.tr("当前提供商的文字转语音模型"),
            [],
            self.configGroup,
        )
        self.testCard = PushSettingCard(
            self.tr("测试配音"),
            FIF.PLAY,
            self.tr("测试当前配置"),
            self.tr("合成一句试听音频并在本页播放"),
            self.configGroup,
        )
        self.configGroup.addSettingCard(self.apiKeyCard)
        self.configGroup.addSettingCard(self.apiBaseCard)
        self.configGroup.addSettingCard(self.modelCard)
        self.configGroup.addSettingCard(self.testCard)

        self.cloneGroup = SettingCardGroup(self.tr("音色克隆"), self.scrollWidget)
        self.cloneAudioCard = CloneAudioSettingCard(self.cloneGroup)
        self.cloneTextCard = LineEditSettingCard(
            cfg.dubbing_clone_text,
            FIF.EDIT,
            self.tr("参考文本"),
            self.tr("参考音频中实际说出的原文，需尽量准确"),
            self.tr("请输入参考音频对应文字"),
            self.cloneGroup,
        )
        self.cloneGroup.addSettingCard(self.cloneAudioCard)
        self.cloneGroup.addSettingCard(self.cloneTextCard)

        self.voiceGroup = QWidget(self.scrollWidget)
        voiceLayout = QVBoxLayout(self.voiceGroup)
        voiceLayout.setContentsMargins(0, 0, 0, 0)
        voiceLayout.setSpacing(12)
        voiceLayout.addWidget(BodyLabel(self.tr("音色库"), self.voiceGroup))
        self.voicePanel = QWidget(self.voiceGroup)
        self.voiceGrid = QGridLayout(self.voicePanel)
        self.voiceGrid.setContentsMargins(0, 0, 0, 0)
        self.voiceGrid.setSpacing(12)
        voiceLayout.addWidget(self.voicePanel)

        self.expandLayout.setSpacing(28)
        self.expandLayout.setContentsMargins(36, 10, 36, 0)
        self.expandLayout.addWidget(self.providerPanel)
        self.expandLayout.addWidget(self.voiceGroup)
        self.expandLayout.addWidget(self.cloneGroup)
        self.expandLayout.addWidget(self.configGroup)

    def _connect_signals(self):
        self.testCard.clicked.connect(self._preview_current)

    def showEvent(self, event):
        super().showEvent(event)
        self._on_provider_changed(cfg.dubbing_provider.value)

    def _on_provider_changed(self, provider: str):
        cfg.set(cfg.dubbing_provider, provider)
        option = get_provider_option(provider)
        self.providerSegment.setCurrentItem(provider)
        if item := self.providerSegment.widget(provider):
            self.providerSegment.slideAni.stop()
            self.providerSegment.slideAni.setValue(item.x())
        self.providerTitleLabel.setText(option.title)
        self.providerDescLabel.setText(option.description)
        presets = get_provider_voices(provider)
        current = cfg.dubbing_preset.value
        if current not in {voice.preset for voice in presets}:
            self._apply_preset(presets[0].preset, show_tip=False)

        needs_api = option.needs_api_key
        self.configGroup.setVisible(True)
        self.apiKeyCard.setVisible(needs_api)
        self.apiBaseCard.setVisible(needs_api)
        self.modelCard.setVisible(needs_api)
        self.testCard.setVisible(True)
        self.modelCard.setItems(list(option.models))
        if not cfg.dubbing_model.value and option.models:
            cfg.set(cfg.dubbing_model, option.models[0])
        if not cfg.dubbing_api_base.value and option.default_base:
            cfg.set(cfg.dubbing_api_base, option.default_base)
        self.cloneGroup.setVisible(option.supports_clone)
        self._render_voice_cards(provider)
        self.configGroup.adjustSize()
        self.cloneGroup.adjustSize()
        self.voiceGroup.adjustSize()
        self.expandLayout.update()

    def _render_voice_cards(self, provider: str):
        while self.voiceGrid.count():
            item = self.voiceGrid.takeAt(0)
            if widget := item.widget():
                widget.setParent(None)
                widget.deleteLater()
        self.voice_cards = []
        voices = get_provider_voices(provider)
        rows = max(1, (len(voices) + 1) // 2)
        self.voicePanel.setMinimumHeight(rows * 146 + (rows - 1) * 12)
        for index, voice in enumerate(voices):
            card = VoiceCard(voice.preset, voice.title, voice.description, self.voicePanel)
            card.playButton.clicked.connect(lambda _=False, p=voice.preset: self._preview(p))
            card.useButton.clicked.connect(lambda _=False, p=voice.preset: self._apply_preset(p))
            card.setCurrent(voice.preset == cfg.dubbing_preset.value)
            self.voiceGrid.addWidget(card, index // 2, index % 2)
            self.voice_cards.append(card)

    def _apply_preset(self, preset_name: str, *, show_tip: bool = True):
        preset = get_dubbing_preset(preset_name)
        cfg.set(cfg.dubbing_provider, preset.provider)
        cfg.set(cfg.dubbing_preset, preset_name)
        cfg.set(cfg.dubbing_voice, preset.voice)
        cfg.set(cfg.dubbing_model, preset.model)
        if preset.api_base and not cfg.dubbing_api_base.value:
            cfg.set(cfg.dubbing_api_base, preset.api_base)
        self.modelCard.comboBox.setCurrentText(preset.model)
        self._render_voice_cards(preset.provider)
        if show_tip:
            InfoBar.success(
                self.tr("已选择音色"),
                self.tr("{name} 已设为默认配音音色").format(name=get_voice_title(preset_name)),
                duration=INFOBAR_DURATION_SUCCESS,
                parent=self,
            )

    def _preview_current(self):
        self._preview(cfg.dubbing_preset.value)

    def _preview(self, preset_name: str):
        if self.preview_thread and self.preview_thread.isRunning():
            return
        self.testCard.button.setEnabled(False)
        self.testCard.button.setText(self.tr("试听中..."))
        self.preview_thread = VoicePreviewThread(preset_name)
        self.preview_thread.finished.connect(self._on_preview_finished)
        self.preview_thread.error.connect(self._on_preview_error)
        self.preview_thread.start()

    def _on_preview_finished(self, path: str):
        self.testCard.button.setEnabled(True)
        self.testCard.button.setText(self.tr("测试配音"))
        self.player.setMedia(QMediaContent(QUrl.fromLocalFile(path)))
        self.player.play()
        InfoBar.success(
            self.tr("开始播放"),
            self.tr("正在播放：{name}").format(name=Path(path).name),
            duration=INFOBAR_DURATION_SUCCESS,
            parent=self,
        )

    def _on_preview_error(self, message: str):
        self.testCard.button.setEnabled(True)
        self.testCard.button.setText(self.tr("测试配音"))
        InfoBar.error(
            self.tr("试听失败"),
            message,
            duration=INFOBAR_DURATION_ERROR,
            parent=self,
        )
