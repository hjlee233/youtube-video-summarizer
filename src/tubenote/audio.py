"""FFmpeg 기반 오디오 전처리 (기획안 8.4).

16 kHz / mono / PCM 16-bit WAV로 변환한다. faster-whisper 입력에 적합한 형식.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .errors import AudioProcessingError, FFmpegNotFoundError


def find_ffmpeg() -> str:
    """PATH에서 ffmpeg 실행 파일을 찾는다. 없으면 FFmpegNotFoundError."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise FFmpegNotFoundError()
    return ffmpeg


def to_wav_16k_mono(input_path: Path, output_path: Path) -> Path:
    """입력 오디오를 16 kHz mono PCM 16-bit WAV로 변환한다.

    원본 볼륨은 유지한다. 음량 정규화/잡음 제거는 품질 문제 확인 후 추가.
    """
    ffmpeg = find_ffmpeg()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(input_path),
        "-vn",            # 비디오 스트림 제거
        "-ac",
        "1",              # mono
        "-ar",
        "16000",          # 16 kHz
        "-c:a",
        "pcm_s16le",      # PCM 16-bit
        str(output_path),
    ]

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise AudioProcessingError(f"FFmpeg 실행 실패: {exc}") from exc

    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()[-5:]
        raise AudioProcessingError(
            "오디오 전처리에 실패했습니다.\n" + "\n".join(tail)
        )

    if not output_path.is_file():
        raise AudioProcessingError("변환된 WAV 파일이 생성되지 않았습니다.")

    return output_path
