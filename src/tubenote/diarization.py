"""화자 분리 (기획안 15절 5단계 / 4절 2차).

pyannote.audio로 화자 구간을 얻고, faster-whisper 세그먼트에 시간 겹침 기준으로
화자를 배정한다. WhisperX 대신 pyannote를 직접 써서 기존 STT를 재사용한다.

pyannote는 선택적 의존성이다: `uv sync --extra diarization` + .env의 HF_TOKEN +
모델 라이선스 동의(pyannote/speaker-diarization-3.1, pyannote/segmentation-3.0)가 필요하다.
배정/이름변경 로직은 순수 함수라 의존성 없이 테스트된다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import DiarizationConfig
from .errors import TubeNoteError
from .models import TranscriptSegment

_DIARIZATION_MODEL = "pyannote/speaker-diarization-3.1"


class DiarizationError(TubeNoteError):
    user_message = "화자 분리에 실패했습니다."


@dataclass
class SpeakerTurn:
    start: float
    end: float
    speaker: str


def assign_speakers(
    segments: list[TranscriptSegment],
    turns: list[SpeakerTurn],
) -> list[TranscriptSegment]:
    """각 대본 세그먼트에 시간 겹침이 가장 큰 화자를 배정한다 (순수 함수).

    겹치는 화자 구간이 없으면 speaker는 None으로 둔다.
    """
    out: list[TranscriptSegment] = []
    for seg in segments:
        best_speaker: str | None = None
        best_overlap = 0.0
        for turn in turns:
            overlap = max(0.0, min(seg.end, turn.end) - max(seg.start, turn.start))
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = turn.speaker
        out.append(seg.model_copy(update={"speaker": best_speaker}))
    return out


def rename_speakers(
    segments: list[TranscriptSegment],
    mapping: dict[str, str],
) -> list[TranscriptSegment]:
    """화자 라벨을 사용자 지정 이름으로 치환한다 (순수 함수).

    mapping에 없는 화자는 그대로 둔다. 빈 문자열로 매핑되면 원래 라벨 유지.
    """
    out: list[TranscriptSegment] = []
    for seg in segments:
        new = mapping.get(seg.speaker or "", "").strip()
        if seg.speaker and new:
            out.append(seg.model_copy(update={"speaker": new}))
        else:
            out.append(seg.model_copy())
    return out


def unique_speakers(segments: list[TranscriptSegment]) -> list[str]:
    """대본에 등장하는 화자 라벨을 등장 순서대로 반환."""
    seen: list[str] = []
    for seg in segments:
        if seg.speaker and seg.speaker not in seen:
            seen.append(seg.speaker)
    return seen


def diarize(
    wav_path: Path,
    config: DiarizationConfig,
    *,
    hf_token: str,
) -> list[SpeakerTurn]:
    """pyannote로 화자 구간을 추출한다. (pyannote.audio 필요)"""
    if not hf_token:
        raise DiarizationError(
            "화자 분리에는 HF_TOKEN이 필요합니다 (.env에 설정하고 모델 라이선스에 동의하세요)."
        )
    try:
        from pyannote.audio import Pipeline
    except ImportError as exc:  # pragma: no cover
        raise DiarizationError(
            "pyannote.audio가 설치되어 있지 않습니다. `uv sync --extra diarization`로 설치하세요."
        ) from exc

    try:
        pipeline = Pipeline.from_pretrained(_DIARIZATION_MODEL, use_auth_token=hf_token)
    except Exception as exc:  # 게이트/네트워크/라이선스 등
        raise DiarizationError(
            f"화자 분리 모델 로딩 실패(라이선스 동의·HF_TOKEN 확인): {exc}"
        ) from exc

    # 장치 배치
    resolved = config.device
    try:
        import torch

        if config.device == "auto":
            resolved = "cuda" if torch.cuda.is_available() else "cpu"
        pipeline.to(torch.device(resolved))
    except Exception:  # torch 없거나 배치 실패 시 CPU 기본
        pass

    kwargs: dict = {}
    if config.min_speakers is not None:
        kwargs["min_speakers"] = config.min_speakers
    if config.max_speakers is not None:
        kwargs["max_speakers"] = config.max_speakers

    try:
        annotation = pipeline(str(wav_path), **kwargs)
    except Exception as exc:
        raise DiarizationError(f"화자 분리 실행 실패: {exc}") from exc

    turns = [
        SpeakerTurn(start=round(turn.start, 3), end=round(turn.end, 3), speaker=speaker)
        for turn, _, speaker in annotation.itertracks(yield_label=True)
    ]
    return turns
