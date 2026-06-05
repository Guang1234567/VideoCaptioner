# UI Component Audit

Date: 2026-06-04

## Direction

Use qfluentwidgets components for visible app UI by default. Prefer:

- `SettingCardGroup` + `SettingCard` variants for form-like settings.
- `MessageBoxBase` for modal dialogs.
- `ScrollArea` or `SingleDirectionScrollArea` for pages that can exceed one viewport.
- `PrimaryPushButton`, `PushButton`, `PrimaryToolButton`, `HyperlinkButton` instead of hand-styled Qt buttons.
- qfluent labels and controls before manual stylesheet overrides.

Manual stylesheet should be limited to transparent containers, media preview backgrounds, or places where qfluent has no equivalent.

## Fixed In This Pass

- `video_synthesis_interface.py`
  - Replaced hand-built input/output/dubbing cards with qfluent setting groups and setting cards.
  - Added a scrollable content area so advanced dubbing controls remain reachable.
  - Removed custom `LineEdit` border styling.
  - Localized switch text to `开/关`.

- `DubbingVoiceDialog.py`
  - Replaced bare `QDialog` with `MessageBoxBase`.
  - Removed hand-written dialog background, card border, and button color styles.

- `task_creation_interface.py`
  - Replaced hand-styled tool button with `PrimaryToolButton`.
  - Removed custom search input and footer hyperlink styles.
  - Replaced status/copyright labels with qfluent label components.

- `home_interface.py`
  - Removed hard-coded white background from the home page.

## Remaining UI Debt

- `subtitle_style_interface.py`
  - Uses custom `MySettingCard` and many manual styles. This page should be migrated carefully because it has many specialized controls for ASS style editing.
  - Suggested direction: replace simple rows with qfluent `SettingCard` variants, keep custom controls only for the live subtitle preview and truly custom color/font pickers.

- `MySettingCard.py`
  - Custom setting-card implementation based on `QFrame`, `QLabel`, and `QToolButton`.
  - Suggested direction: gradually replace usages with qfluent `SettingCard`, `ComboBoxSettingCard`, `ColorSettingCard`, `CustomColorSettingCard`, and compact spinbox cards.

- `transcription_interface.py`
  - Uses a custom `VideoInfoCard` and thumbnail `QLabel`. This is acceptable for media preview, but the fixed thumbnail background and info layout should be reviewed visually.

- `MyVideoWidget.py`
  - Media rendering naturally needs custom widgets. Keep custom video surface, but avoid styling regular controls manually.

- Whisper setting widgets
  - Mostly use qfluent `SettingCardGroup`; remaining styles are transparent scroll containers and status colors. Low priority.

