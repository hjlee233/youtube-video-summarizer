"""YouTube URL 파싱과 메타데이터 조회 (기획안 8.1 ~ 8.3)."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .errors import (
    DownloadError,
    InvalidURLError,
    LiveVideoError,
    MetadataError,
)
from .models import VideoMetadata

# YouTube 영상 ID는 11자 [A-Za-z0-9_-]
_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
# 경로 기반 추출용: /live/<id>, /shorts/<id>, /embed/<id>, /v/<id>
_PATH_ID_RE = re.compile(r"^/(?:live|shorts|embed|v)/([A-Za-z0-9_-]{11})")


def extract_video_id(url: str) -> str:
    """지원하는 YouTube URL에서 11자 영상 ID를 추출한다.

    지원 형식: youtube.com/watch?v=, youtu.be/, youtube.com/live/,
    shorts/embed/v 경로. 추출 실패 시 InvalidURLError.
    """
    if not url or not isinstance(url, str):
        raise InvalidURLError("URL이 비어 있습니다.")

    raw = url.strip()
    # 스킴이 없으면 붙여서 urlparse가 host/path를 인식하게 한다
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", raw):
        raw = "https://" + raw

    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host

    # youtu.be/<id>
    if host == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/")[0]
        if _VIDEO_ID_RE.match(candidate):
            return candidate
        raise InvalidURLError(f"영상 ID를 추출할 수 없습니다: {url}")

    if host in {"youtube.com", "m.youtube.com", "music.youtube.com"}:
        # /watch?v=<id>
        if parsed.path == "/watch":
            qs = parse_qs(parsed.query)
            values = qs.get("v", [])
            if values and _VIDEO_ID_RE.match(values[0]):
                return values[0]
        # /live/<id>, /shorts/<id>, /embed/<id>, /v/<id>
        m = _PATH_ID_RE.match(parsed.path)
        if m:
            return m.group(1)

    raise InvalidURLError(f"지원하지 않는 YouTube 주소입니다: {url}")


def canonical_watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def timestamp_url(video_id: str, seconds: float) -> str:
    """특정 시점으로 이동하는 YouTube 링크 (기획안 8.9)."""
    return f"https://www.youtube.com/watch?v={video_id}&t={int(seconds)}s"


def _apply_access_opts(
    opts: dict,
    *,
    cookies_from_browser: str | None,
    allow_remote_components: bool,
) -> dict:
    """로그인 쿠키와 EJS 원격 컴포넌트(보호 영상 JS 챌린지 해석) 옵션을 적용."""
    if cookies_from_browser:
        opts["cookiesfrombrowser"] = (cookies_from_browser,)
    if allow_remote_components:
        # yt-dlp가 yt-dlp-ejs 솔버 스크립트를 GitHub에서 받아 Deno로 실행 (멤버십/보호 영상)
        opts["remote_components"] = ["ejs:github"]
    return opts


def fetch_metadata(
    url: str,
    *,
    cookies_from_browser: str | None = None,
    allow_remote_components: bool = False,
) -> VideoMetadata:
    """yt-dlp로 메타데이터를 조회한다 (다운로드 없이).

    생방송 중인 영상은 LiveVideoError로 거절한다.
    """
    from yt_dlp import YoutubeDL

    video_id = extract_video_id(url)
    watch_url = canonical_watch_url(video_id)

    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }
    _apply_access_opts(
        opts,
        cookies_from_browser=cookies_from_browser,
        allow_remote_components=allow_remote_components,
    )

    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(watch_url, download=False)
    except Exception as exc:  # yt-dlp는 다양한 예외를 던진다
        raise MetadataError(f"메타데이터 조회 실패: {exc}") from exc

    if info is None:
        raise MetadataError("메타데이터를 가져오지 못했습니다.")

    # 생방송 진행 중 거절 (is_live=True 또는 live_status가 'is_live')
    if info.get("is_live") or info.get("live_status") == "is_live":
        raise LiveVideoError()

    return VideoMetadata(
        video_id=info.get("id", video_id),
        title=info.get("title") or "(제목 없음)",
        channel=info.get("uploader") or info.get("channel"),
        url=watch_url,
        duration_seconds=info.get("duration"),
        upload_date=info.get("upload_date"),
        thumbnail_url=info.get("thumbnail"),
        is_live=bool(info.get("is_live")),
    )


def download_audio(
    url: str,
    temp_dir: Path,
    *,
    cookies_from_browser: str | None = None,
    allow_remote_components: bool = False,
) -> Path:
    """최상의 오디오 스트림만 임시 다운로드한다 (기획안 8.3).

    파일명에는 영상 ID를 사용해 특수문자 문제를 방지한다.
    다운로드된 오디오 파일 경로를 반환한다.
    """
    from yt_dlp import YoutubeDL

    video_id = extract_video_id(url)
    watch_url = canonical_watch_url(video_id)
    temp_dir.mkdir(parents=True, exist_ok=True)

    outtmpl = str(temp_dir / "%(id)s.%(ext)s")
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
    }
    _apply_access_opts(
        opts,
        cookies_from_browser=cookies_from_browser,
        allow_remote_components=allow_remote_components,
    )

    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(watch_url, download=True)
            downloaded = Path(ydl.prepare_filename(info))
    except Exception as exc:
        raise DownloadError(f"오디오 다운로드 실패: {exc}") from exc

    if not downloaded.is_file():
        # prepare_filename이 후처리 전 이름을 줄 수 있으므로 id로 폴백 탐색
        matches = sorted(temp_dir.glob(f"{video_id}.*"))
        if matches:
            return matches[0]
        raise DownloadError("다운로드된 오디오 파일을 찾을 수 없습니다.")

    return downloaded
