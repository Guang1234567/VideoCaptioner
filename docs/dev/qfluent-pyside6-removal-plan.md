# qfluentwidgets / PyQt5 Removal Plan

This is the working migration record for removing `PyQt-Fluent-Widgets`,
removing the hidden VLC player path, and moving the desktop UI to PySide6.

## Baseline

- Checkpoint commit before the migration: `55532cf chore: checkpoint shared config and ui refresh`.
- Baseline screenshots:
  - `/tmp/vc-qfluent-baseline-20260609-dark/contact-sheet.png`
  - `/tmp/vc-qfluent-baseline-20260609-dark/settings-contact-sheet.png`
  - `/tmp/vc-qfluent-baseline-20260609-dark/compact-contact-sheet.png`
  - `/tmp/vc-qfluent-baseline-20260609-light/contact-sheet.png`
  - `/tmp/vc-qfluent-baseline-20260609-light/settings-contact-sheet.png`
  - `/tmp/vc-qfluent-baseline-20260609-light/compact-contact-sheet.png`
- Last verified local suite before migration:
  - `126 passed, 1 warning`
  - `ruff check videocaptioner tests scripts` passed.

## Current Dependency Surface

qfluentwidgets is still used in these areas:

- App boot/theme: `videocaptioner/ui/main.py`, `videocaptioner/ui/common/config.py`,
  `videocaptioner/ui/common/theme_tokens.py`.
- Shell/navigation: `videocaptioner/ui/view/main_window.py`,
  `videocaptioner/ui/view/home_interface.py`.
- First-party component layer that still wraps qfluent widgets:
  `videocaptioner/ui/components/settings_controls.py`,
  `videocaptioner/ui/components/form_cards.py`,
  `videocaptioner/ui/components/workflow_widgets.py`,
  `videocaptioner/ui/components/subtitle_style_controls.py`,
  `videocaptioner/ui/components/donate_dialog.py`.
- Main pages: doctor, dubbing, subtitle, subtitle style, transcription, task
  creation, video synthesis, logs, LLM logs, batch process.
- Tooling/packaging: `scripts/ui_smoke_check.py`, `VideoCaptioner.spec`,
  `pyproject.toml`, `uv.lock`.

PyQt5 is still imported across UI views, UI threads, GUI tests, the smoke script,
`pyproject.toml`, and `VideoCaptioner.spec`. PySide6 is not installed in the
current virtual environment yet.

VLC removal has started:

- Removed `videocaptioner/ui/components/video_widget.py`.
- Removed `videocaptioner/ui/common/signal_bus.py`, because it only served the
  hidden VLC player.
- Removed `PYTHON_VLC_MODULE_PATH` setup from `videocaptioner/config.py`.
- Subtitle row clicks now only select rows; they no longer emit hidden playback
  signals.

## Target Architecture

Use PySide6 directly and keep project-owned UI controls in one place:

- `videocaptioner/ui/components/`
  - reusable cards, setting rows, file pickers, pill/tag widgets, buttons,
    progress/status rows, and form controls.
- `videocaptioner/ui/common/`
  - app theme tokens, icon loading, settings state, and Qt-only helpers.
- `videocaptioner/ui/view/`
  - page composition only; avoid local copies of button/card/input styling when
    a reusable component exists.

The UI must not depend on qfluentwidgets for configuration, navigation, theme,
icons, messages, buttons, cards, combo boxes, scroll areas, dialogs, or menus.

## Migration Order

1. Finish dead-code deletion.
   - VLC and the global playback signal bus are removable now.
   - Remove qfluent hidden imports from packaging after all imports are gone.

2. Add PySide6 dependency and update packaging.
   - Replace PyQt5 dependencies with PySide6.
   - Remove `PyQt5-Qt5` overrides.
   - Update `VideoCaptioner.spec` hidden imports to PySide6 modules.

3. Convert Qt imports.
   - `pyqtSignal` -> `Signal`.
   - PySide6 multimedia API differences:
     - `QMediaPlayer.setMedia(QMediaContent(...))` becomes `setSource(QUrl)`.
     - `QMediaContent` is removed.
   - Enum names may need `Qt.AlignmentFlag`, `Qt.ItemDataRole`, etc., if
     strict typing or runtime issues appear.

4. Replace qfluent base widgets with project widgets.
   - `FluentWindow` / `NavigationInterface`: project-owned main shell/sidebar.
   - `PushButton`, `PrimaryPushButton`, `PillPushButton`: themed QPushButton
     subclasses/helpers.
   - `ComboBox`, `EditableComboBox`, `LineEdit`, `TextEdit`, `PlainTextEdit`:
     native Qt widgets styled by theme tokens.
   - `ScrollArea`: styled QScrollArea helper.
   - `InfoBar`: project toast/banner component.
   - `Action`, `RoundMenu`, dropdown buttons: QAction/QMenu-based project
     helpers.
   - `MessageBoxBase`: QDialog-based project dialogs.
   - `TableView`, `ProgressBar`: native Qt widgets styled centrally.

5. Update screenshot smoke tooling.
   - Keep the current qfluent baseline screenshots.
   - Make the smoke script launch PySide6 pages and produce matching contact
     sheets for dark/light/compact states.

6. Run acceptance.
   - Use `docs/dev/e2e-acceptance-checklist.md`.
   - Update that file with pass/fail evidence as each area is validated.

## Acceptance Standard

- `rg "qfluentwidgets|PyQt5|PyQt-Fluent-Widgets|PyQt5-Qt5|python-vlc|\\bvlc\\b"`
  returns no relevant project dependency or import.
- `uv run videocaptioner` starts the GUI with PySide6.
- Baseline pages can be screenshot in dark, light, normal width, and compact
  width.
- Core local tests and ruff pass.
- No hidden VLC player dependency remains.
- Settings values still persist to the shared TOML config and survive page
  switching.
- Provider-specific fields, model loading, connection tests, dubbing preview,
  subtitle processing, subtitle style preview, video synthesis, diagnostics, and
  full flow still behave according to `docs/dev/e2e-acceptance-checklist.md`.
