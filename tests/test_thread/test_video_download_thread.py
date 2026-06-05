import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from videocaptioner.ui.thread.video_download_thread import VideoDownloadThread


def test_ted_download_retries_with_hls_after_403(tmp_path, monkeypatch, qapp):
    used_formats: list[str] = []

    class FakeYoutubeDL:
        def __init__(self, params):
            self.params = params
            used_formats.append(params["format"])

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, url, download=False):
            return {
                "title": "TED Test",
                "ext": "mp4",
                "language": "en",
                "automatic_captions": {},
            }

        def process_info(self, info_dict):
            if "[ext=mp4]" in self.params["format"]:
                raise Exception("HTTP Error 403: Forbidden")
            home = Path(self.params["paths"]["home"])
            home.mkdir(parents=True, exist_ok=True)
            (home / "TED Test.mp4").write_bytes(b"fake-video")

        def prepare_filename(self, info_dict):
            return str(Path(self.params["paths"]["home"]) / "TED Test.mp4")

    monkeypatch.setattr(
        "videocaptioner.ui.thread.video_download_thread.yt_dlp.YoutubeDL",
        FakeYoutubeDL,
    )

    thread = VideoDownloadThread("https://www.ted.com/talks/example", str(tmp_path))

    video_path, subtitle_path, thumbnail_path, _info = thread.download()

    assert Path(video_path).exists()
    assert subtitle_path is None
    assert thumbnail_path is None
    assert used_formats == [
        "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "bestvideo[protocol^=m3u8]+bestaudio[protocol^=m3u8]/best[protocol^=m3u8]/best",
    ]


def test_friendly_error_for_ted_403(qapp):
    thread = VideoDownloadThread("https://www.ted.com/talks/example", "/tmp")

    message = thread._friendly_error("HTTP Error 403: Forbidden")

    assert "TED" in message
    assert "备用视频流" in message
