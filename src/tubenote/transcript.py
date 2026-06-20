"""대본 정규화 (기획안 8.6).

원본 타임스탬프를 보존하면서 공백 정리, 빈 세그먼트 제거, 짧고 인접한
세그먼트 병합을 수행한다. LLM이 대본을 임의로 다시 쓰지 않도록, 이 단계는
순수하게 형식 정리만 담당한다.
"""

from __future__ import annotations

import re

from .models import TranscriptSegment

_WS_RE = re.compile(r"\s+")


def _clean_text(text: str) -> str:
    return _WS_RE.sub(" ", text).strip()


def normalize_segments(
    segments: list[TranscriptSegment],
    *,
    min_duration: float = 0.5,
    max_gap: float = 0.4,
) -> list[TranscriptSegment]:
    """세그먼트를 정규화한다.

    - 텍스트 공백 정리, 빈 세그먼트 제거
    - 매우 짧은(min_duration 미만) 세그먼트를, 시간 간격이 max_gap 이하인
      직전 세그먼트에 병합
    - 병합 시 start는 앞 세그먼트, end는 뒤 세그먼트 값을 사용 (타임스탬프 보존)
    - index는 0부터 재부여
    """
    cleaned: list[TranscriptSegment] = []
    for seg in segments:
        text = _clean_text(seg.text)
        if not text:
            continue
        cleaned.append(seg.model_copy(update={"text": text}))

    if not cleaned:
        return []

    merged: list[TranscriptSegment] = [cleaned[0]]
    for seg in cleaned[1:]:
        prev = merged[-1]
        duration = seg.end - seg.start
        gap = seg.start - prev.end
        if duration < min_duration and gap <= max_gap:
            merged[-1] = prev.model_copy(
                update={"end": seg.end, "text": f"{prev.text} {seg.text}".strip()}
            )
        else:
            merged.append(seg)

    return [seg.model_copy(update={"index": i}) for i, seg in enumerate(merged)]


def full_text(segments: list[TranscriptSegment]) -> str:
    """세그먼트 텍스트를 줄바꿈으로 이어 붙인 전체 대본."""
    return "\n".join(seg.text for seg in segments)
