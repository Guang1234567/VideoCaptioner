#!/usr/bin/env python3
"""Demo realtime transcription + translation through local voxgate.

Examples:
  python scripts/voxgate_realtime_demo.py --input speech.wav --translator bing
  python scripts/voxgate_realtime_demo.py --capture-command 'ffmpeg ... -f s16le -'
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from collections.abc import AsyncIterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.realtime import VoxgateRealtimeClient
from videocaptioner.core.translate.factory import TranslatorFactory
from videocaptioner.core.translate.types import TargetLanguage, TranslatorType

PCM_SAMPLE_RATE = 16000
PCM_CHANNELS = 1
PCM_BYTES_PER_SAMPLE = 2


def main() -> int:
    args = _parse_args()
    if not args.input and not args.capture_command:
        print("error: provide --input or --capture-command", file=sys.stderr)
        return 2
    server = None
    try:
        if args.start_server:
            server = _ensure_voxgate_server(args)
        asyncio.run(_run(args))
        return 0
    finally:
        if server and server.poll() is None:
            server.send_signal(signal.SIGTERM)
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a realtime voxgate transcription demo.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", metavar="FILE", help="Audio/video file to play into voxgate in realtime")
    source.add_argument(
        "--capture-command",
        metavar="CMD",
        help="Command that writes 16 kHz mono PCM16 little-endian audio to stdout",
    )
    parser.add_argument("--voxgate-bin", default="", help="Path to voxgate binary")
    parser.add_argument("--host", default="127.0.0.1", help="voxgate server host")
    parser.add_argument("--port", type=int, default=18088, help="voxgate server port")
    parser.add_argument("--auth-token", default="videocaptioner-local", help="voxgate local bearer token")
    parser.add_argument("--no-start-server", dest="start_server", action="store_false", help="Use an already running server")
    parser.add_argument("--ffmpeg", default="ffmpeg", help="ffmpeg executable")
    parser.add_argument("--fast", action="store_true", help="Do not pace --input as realtime playback")
    parser.add_argument("--chunk-ms", type=int, default=100, help="PCM chunk size sent over WebSocket")
    parser.add_argument("--translator", choices=["none", "bing", "google"], default="bing")
    parser.add_argument("--target", default="zh-Hans", help="Target language code/name, e.g. zh-Hans, en, ja")
    parser.add_argument("--json", action="store_true", help="Print JSONL events only")
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    translator = _create_translator(args.translator, args.target)
    ws_url = f"ws://{args.host}:{args.port}/v1/realtime"
    client = VoxgateRealtimeClient(ws_url, auth_token=args.auth_token)

    if args.capture_command:
        pcm_chunks = _capture_command_pcm(args.capture_command, args.chunk_ms)
    else:
        pcm_chunks = _ffmpeg_file_pcm(Path(args.input), args.ffmpeg, args.fast, args.chunk_ms)

    async for event in client.stream_pcm(pcm_chunks):
        if event.type == "session":
            _emit(args, {"type": "session", "event": event.raw_type})
        elif event.type == "delta":
            _emit(args, {"type": "delta", "text": event.text, "item_id": event.item_id})
        elif event.type == "completed":
            translated = _translate_text(translator, event.text) if translator else ""
            _emit(
                args,
                {
                    "type": "final",
                    "text": event.text,
                    "translation": translated,
                    "item_id": event.item_id,
                },
            )
        elif event.type == "error":
            _emit(args, {"type": "error", "message": event.text, "item_id": event.item_id})


def _ensure_voxgate_server(args: argparse.Namespace) -> subprocess.Popen | None:
    health_url = f"http://{args.host}:{args.port}/health"
    if _health_ok(health_url):
        return None

    voxgate = _resolve_voxgate(args.voxgate_bin)
    cmd = [
        voxgate,
        "serve",
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--auth-token",
        args.auth_token,
        "--quiet",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.time() + 10
    while time.time() < deadline:
        if proc.poll() is not None:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise RuntimeError(f"voxgate serve exited early: {stderr.strip()}")
        if _health_ok(health_url):
            return proc
        time.sleep(0.2)
    proc.terminate()
    raise RuntimeError(f"voxgate serve did not become healthy at {health_url}")


def _resolve_voxgate(explicit: str) -> str:
    if explicit:
        return explicit
    found = shutil.which("voxgate")
    if found:
        return found
    local = Path.home() / "ime-asr" / "bin" / "voxgate"
    if local.exists():
        return str(local)
    raise FileNotFoundError("voxgate binary not found; pass --voxgate-bin")


def _health_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=0.5) as response:
            return response.status == 200
    except Exception:
        return False


async def _ffmpeg_file_pcm(
    input_path: Path,
    ffmpeg: str,
    fast: bool,
    chunk_ms: int,
) -> AsyncIterator[bytes]:
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error"]
    if not fast:
        cmd.append("-re")
    cmd.extend(["-i", str(input_path), "-ac", "1", "-ar", str(PCM_SAMPLE_RATE), "-f", "s16le", "-"])
    async for chunk in _process_stdout_chunks(cmd, chunk_ms):
        yield chunk


async def _capture_command_pcm(command: str, chunk_ms: int) -> AsyncIterator[bytes]:
    async for chunk in _process_stdout_chunks(command, chunk_ms, shell=True):
        yield chunk


async def _process_stdout_chunks(
    cmd: list[str] | str,
    chunk_ms: int,
    *,
    shell: bool = False,
) -> AsyncIterator[bytes]:
    chunk_size = max(
        640,
        int(PCM_SAMPLE_RATE * PCM_CHANNELS * PCM_BYTES_PER_SAMPLE * chunk_ms / 1000),
    )
    if shell:
        proc = await asyncio.create_subprocess_shell(
            str(cmd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    else:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    assert proc.stdout is not None
    while True:
        chunk = await proc.stdout.read(chunk_size)
        if not chunk:
            break
        yield chunk
    stderr = await proc.stderr.read() if proc.stderr else b""
    code = await proc.wait()
    if code != 0:
        raise RuntimeError(f"audio source command failed ({code}): {stderr.decode(errors='replace')}")


def _create_translator(service: str, target: str):
    if service == "none":
        return None
    translator_type = TranslatorType(service)
    return TranslatorFactory.create_translator(
        translator_type,
        thread_num=1,
        batch_num=1,
        target_language=_target_language(target),
    )


def _target_language(raw: str) -> TargetLanguage:
    aliases = {
        "zh": TargetLanguage.SIMPLIFIED_CHINESE,
        "zh-cn": TargetLanguage.SIMPLIFIED_CHINESE,
        "zh-hans": TargetLanguage.SIMPLIFIED_CHINESE,
        "zh-tw": TargetLanguage.TRADITIONAL_CHINESE,
        "zh-hant": TargetLanguage.TRADITIONAL_CHINESE,
        "en": TargetLanguage.ENGLISH,
        "ja": TargetLanguage.JAPANESE,
        "ko": TargetLanguage.KOREAN,
    }
    lowered = raw.lower()
    if lowered in aliases:
        return aliases[lowered]
    for item in TargetLanguage:
        if raw in {item.name, item.value}:
            return item
    raise ValueError(f"unsupported target language: {raw}")


def _translate_text(translator, text: str) -> str:
    if not text.strip():
        return ""
    data = ASRData([ASRDataSeg(text=text, start_time=0, end_time=0)])
    translated = translator.translate_subtitle(data)
    if not translated.segments:
        return ""
    return translated.segments[0].translated_text


def _emit(args: argparse.Namespace, payload: dict) -> None:
    if args.json:
        print(json.dumps(payload, ensure_ascii=False), flush=True)
        return
    kind = payload["type"]
    if kind == "delta":
        print(f"delta: {payload['text']}", flush=True)
    elif kind == "final":
        print(f"final: {payload['text']}", flush=True)
        if payload.get("translation"):
            print(f"  -> {payload['translation']}", flush=True)
    elif kind == "session":
        print(f"session: {payload['event']}", flush=True)
    else:
        print(json.dumps(payload, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
