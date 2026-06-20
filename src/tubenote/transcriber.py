"""faster-whisper 기반 음성 인식 (기획안 8.5)."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .config import TranscriptionConfig
from .errors import TranscriptionError
from .models import TranscriptSegment

# 진행 콜백: (처리된 초, 전체 초 또는 None) -> None
ProgressCallback = Callable[[float, float | None], None]


def _resolve_compute_type(device: str, compute_type: str = "auto") -> str:
    """compute_type을 결정한다 (기획안 8.5).

    명시값(int8 / float16 등)이 있으면 그대로 사용하고, "auto"이면 장치에 맞게
    GPU -> int8_float16, CPU -> int8을 선택한다.
    """
    if compute_type and compute_type != "auto":
        return compute_type

    resolved = device
    if device == "auto":
        try:
            import ctranslate2

            resolved = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:
            resolved = "cpu"
    return "int8_float16" if resolved == "cuda" else "int8"


def transcribe(
    wav_path: Path,
    config: TranscriptionConfig,
    *,
    progress: ProgressCallback | None = None,
) -> tuple[list[TranscriptSegment], str]:
    """WAV 파일을 받아 세그먼트 목록과 감지된 언어를 반환한다.

    반환: (세그먼트 리스트, 언어 코드)
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:  # pragma: no cover
        raise TranscriptionError(
            "faster-whisper가 설치되어 있지 않습니다."
        ) from exc

    compute_type = _resolve_compute_type(config.device, config.compute_type)
    language = None if config.language == "auto" else config.language

    try:
        model = WhisperModel(
            config.model,
            device=config.device,
            compute_type=compute_type,
        )
    except Exception as exc:
        raise TranscriptionError(f"STT 모델 로딩 실패: {exc}") from exc

    try:
        segments_iter, info = model.transcribe(
            str(wav_path),
            language=language,
            vad_filter=config.vad_filter,
            beam_size=config.beam_size,
        )

        total = getattr(info, "duration", None)
        segments: list[TranscriptSegment] = []
        for i, seg in enumerate(segments_iter):  # 지연 평가 — 실제 디코딩 시점
            segments.append(
                TranscriptSegment(
                    index=i,
                    start=round(seg.start, 3),
                    end=round(seg.end, 3),
                    text=(seg.text or "").strip(),
                )
            )
            if progress is not None:
                progress(seg.end, total)
    except Exception as exc:
        raise TranscriptionError(f"음성 인식 중 오류: {exc}") from exc

    detected_language = getattr(info, "language", None) or (language or "unknown")
    return segments, detected_language
