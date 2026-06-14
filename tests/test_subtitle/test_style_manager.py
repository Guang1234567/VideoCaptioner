from videocaptioner.core.subtitle.style_manager import (
    AssSubtitleStyle,
    RoundedSubtitleStyle,
    StyleSource,
    SubtitleRenderer,
    SubtitleStylePreset,
    list_styles,
    load_style,
    normalize_style_id,
    save_user_style,
)


def test_builtin_styles_are_typed_and_grouped_by_renderer():
    ass_styles = list_styles(renderer="ass", include_user=False)
    rounded_styles = list_styles(renderer="rounded", include_user=False)

    assert {style.id for style in ass_styles} >= {
        "ass/default",
        "ass/anime",
        "ass/vertical",
    }
    assert {style.id for style in rounded_styles} >= {"rounded/default"}
    assert all(isinstance(style.style, AssSubtitleStyle) for style in ass_styles)
    assert all(isinstance(style.style, RoundedSubtitleStyle) for style in rounded_styles)


def test_load_style_uses_renderer_to_disambiguate_default():
    ass = load_style("default", renderer=SubtitleRenderer.ASS)
    rounded = load_style("default", renderer=SubtitleRenderer.ROUNDED)

    assert ass is not None
    assert rounded is not None
    assert ass.id == "ass/default"
    assert rounded.id == "rounded/default"
    assert isinstance(ass.style, AssSubtitleStyle)
    assert isinstance(rounded.style, RoundedSubtitleStyle)


def test_save_user_style_does_not_modify_builtin_styles(tmp_path):
    user_preset = SubtitleStylePreset(
        id="rounded/my-style",
        name="my-style",
        renderer=SubtitleRenderer.ROUNDED,
        source=StyleSource.USER,
        style=RoundedSubtitleStyle(font_name="Noto Sans SC", font_size=44),
    )

    saved = save_user_style(user_preset, styles_dir=tmp_path)
    loaded = load_style("rounded/my-style", styles_dir=tmp_path, renderer="rounded")
    builtin = load_style("rounded/default", styles_dir=tmp_path, renderer="rounded")

    assert saved == tmp_path / "rounded" / "my-style.json"
    assert loaded is not None
    assert loaded.source == StyleSource.USER
    assert loaded.to_rounded_dict()["font_size"] == 44
    assert builtin is not None
    assert builtin.source == StyleSource.BUILTIN


def test_normalize_style_id_accepts_legacy_names():
    assert normalize_style_id("default", "ass") == "ass/default"
    assert normalize_style_id("ass-default", "rounded") == "ass/default"
    assert normalize_style_id("rounded-default", "ass") == "rounded/default"
    assert normalize_style_id("rounded/default", "ass") == "rounded/default"
