from dataclasses import dataclass


@dataclass(frozen=True)
class DubbingProviderOption:
    key: str
    title: str
    description: str
    needs_api_key: bool
    supports_clone: bool
    default_base: str
    models: tuple[str, ...]


@dataclass(frozen=True)
class DubbingVoiceOption:
    preset: str
    title: str
    description: str


DUBBING_PROVIDERS: tuple[DubbingProviderOption, ...] = (
    DubbingProviderOption(
        key="edge",
        title="Edge 免费配音",
        description="免 API Key，适合默认快速生成中文或英文配音。",
        needs_api_key=False,
        supports_clone=False,
        default_base="",
        models=("edge-tts",),
    ),
    DubbingProviderOption(
        key="gemini",
        title="Gemini TTS",
        description="Google Gemini 语音模型，适合英文自然表达。",
        needs_api_key=True,
        supports_clone=False,
        default_base="https://generativelanguage.googleapis.com/v1beta",
        models=("gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts"),
    ),
    DubbingProviderOption(
        key="siliconflow",
        title="SiliconFlow CosyVoice",
        description="CosyVoice 中文表现稳定，并支持参考音频克隆。",
        needs_api_key=True,
        supports_clone=True,
        default_base="https://api.siliconflow.cn/v1",
        models=("FunAudioLLM/CosyVoice2-0.5B",),
    ),
)


DUBBING_VOICES: dict[str, tuple[DubbingVoiceOption, ...]] = {
    "edge": (
        DubbingVoiceOption("edge-cn-female", "中文女声", "免费中文女声，适合日常解说"),
        DubbingVoiceOption("edge-cn-male", "中文男声", "免费中文男声，适合旁白"),
        DubbingVoiceOption("edge-en-female", "英文女声", "免费英文女声"),
        DubbingVoiceOption("edge-en-male", "英文男声", "免费英文男声"),
    ),
    "gemini": (
        DubbingVoiceOption("gemini-en-friendly", "友好英文", "亲切自然，不支持音色克隆"),
        DubbingVoiceOption("gemini-en-neutral", "自然英文", "清晰稳定，不支持音色克隆"),
        DubbingVoiceOption("gemini-en-upbeat", "活泼英文", "更有能量，不支持音色克隆"),
    ),
    "siliconflow": (
        DubbingVoiceOption("siliconflow-cn-female", "中文女声 Anna", "自然中文女声，支持参考音频克隆"),
        DubbingVoiceOption("siliconflow-cn-male", "中文男声 Alex", "自然中文男声，支持参考音频克隆"),
        DubbingVoiceOption("siliconflow-cn-deep-male", "低沉男声 Benjamin", "沉稳旁白，支持参考音频克隆"),
    ),
}


def get_provider_option(provider: str) -> DubbingProviderOption:
    for option in DUBBING_PROVIDERS:
        if option.key == provider:
            return option
    return DUBBING_PROVIDERS[0]


def get_provider_titles() -> list[str]:
    return [option.key for option in DUBBING_PROVIDERS]


def get_provider_voices(provider: str) -> tuple[DubbingVoiceOption, ...]:
    return DUBBING_VOICES.get(provider, DUBBING_VOICES["edge"])


def get_voice_title(preset: str) -> str:
    for voices in DUBBING_VOICES.values():
        for voice in voices:
            if voice.preset == preset:
                return voice.title
    return preset
