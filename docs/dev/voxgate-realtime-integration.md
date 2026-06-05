# Voxgate Realtime Integration Plan

## What Voxgate Is

`voxgate` is a local Chinese speech-to-text gateway. It wraps a non-public input-method ASR backend and exposes two app-facing surfaces:

- CLI: `voxgate transcribe <file|->`
- Local server: `voxgate serve`

The useful server endpoints for VideoCaptioner are:

| Endpoint | Protocol | Use |
|---|---|---|
| `/health` | HTTP GET | local readiness check |
| `/v1/models` | HTTP GET | OpenAI-compatible model listing |
| `/v1/audio/transcriptions` | HTTP multipart | file transcription |
| `/v1/realtime` | WebSocket | realtime transcription |

`/v1/audio/translations` intentionally returns 400. Translation must be done in VideoCaptioner after receiving transcript text.

## Realtime Protocol

`/v1/realtime` accepts an OpenAI Realtime-style subset:

- client sends `session.update`
- client sends `input_audio_buffer.append` with base64 16 kHz mono PCM16 audio
- client may send `input_audio_buffer.commit` when the source stops
- server emits:
  - `conversation.item.input_audio_transcription.delta`
  - `conversation.item.input_audio_transcription.completed`
  - error events on failure

The upstream ASR backend is not public API and is documented by voxgate as research-only. It may change or stop working. Product UI must present it as an optional local realtime ASR backend, not as a guaranteed cloud service.

## Feasibility In VideoCaptioner

The current stack can support this feature:

- PyQt5 can run a realtime panel with a background worker thread.
- Existing translation providers can translate finalized utterances.
- FFmpeg can capture/normalize audio to `s16le` PCM.
- The new `videocaptioner.core.realtime.voxgate` module can consume PCM chunks and emit normalized transcript events.

The main missing production pieces are audio capture UX and operating-system-specific device selection.

## Demo Added

This demo adds:

- `videocaptioner.core.realtime.voxgate.VoxgateRealtimeClient`
- `scripts/voxgate_realtime_demo.py`

The demo can start a local voxgate server, play a file into the realtime WebSocket using ffmpeg, and translate completed utterances:

```bash
uv run python scripts/voxgate_realtime_demo.py \
  --input /path/to/speech.wav \
  --translator bing \
  --target zh-Hans
```

For real capture, pass a command that writes 16 kHz mono PCM16 to stdout:

```bash
uv run python scripts/voxgate_realtime_demo.py \
  --capture-command 'ffmpeg -f avfoundation -i ":0" -ac 1 -ar 16000 -f s16le -'
```

Linux microphone example:

```bash
uv run python scripts/voxgate_realtime_demo.py \
  --capture-command 'arecord -f S16_LE -r 16000 -c 1'
```

Windows microphone example:

```powershell
uv run python scripts/voxgate_realtime_demo.py `
  --capture-command 'ffmpeg -f dshow -i audio="Microphone (Realtek Audio)" -ac 1 -ar 16000 -f s16le -'
```

System audio is OS-specific:

- Windows: WASAPI loopback should be preferred once the exact device selector is implemented.
- macOS: users usually need a virtual audio device such as BlackHole.
- Linux: PulseAudio/PipeWire monitor sources can provide loopback capture.

## Proposed UI

Add a new "Realtime" workspace, separate from the existing batch subtitle workflow.

Controls:

- Source selector:
  - microphone
  - system audio
  - custom capture command
- Voxgate status:
  - binary found / missing
  - server running / stopped
  - credentials ok / missing
- Language settings:
  - source language hint, default auto/zh
  - target language
  - translator: Bing, Google, LLM
- Runtime buttons:
  - start
  - pause
  - clear
  - export transcript
  - export bilingual transcript

Main view:

- live partial transcript line
- finalized transcript list
- translated line below each finalized utterance
- connection and latency indicators

For video watching, a compact floating subtitle window would be more useful than embedding this into the existing processing pages. It should support always-on-top, font size, opacity, and source/translation layout.

## Production Architecture

Recommended modules:

- `core.realtime.voxgate`: transport and event normalization
- `core.realtime.audio_capture`: OS-specific ffmpeg/device command builder
- `core.realtime.translation`: small per-utterance translation service with debounce/cache
- `ui.thread.realtime_thread`: PyQt worker thread
- `ui.view.realtime_interface`: full control panel
- `ui.view.floating_caption_window`: compact overlay

The UI should not call `voxgate` internals. It should only talk to the local server or start the binary as a child process.

## Risks And Limits

- Voxgate upstream ASR is non-public and research-only.
- Realtime is best for moderate live sessions; very long single sessions may need rolling item/session behavior.
- Translation on every delta is wasteful; translate only finalized utterances, optionally with a small debounce.
- Computer-audio capture differs by OS and needs explicit device discovery.
- A packaged VideoCaptioner build must either bundle voxgate or provide a doctor/onboarding install path.
