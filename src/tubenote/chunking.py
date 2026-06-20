"""대본 청크 분할 (기획안 8.7).

시간이 아니라 텍스트 길이와 문장(세그먼트) 경계를 함께 사용한다.
- 청크당 약 chunk_chars(기본 7,000)자
- 이전 청크와 1~2개 세그먼트 중첩
- 하나의 세그먼트를 중간에서 자르지 않음
- 각 청크에 시작·종료 시간 포함
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .models import TranscriptSegment


class TranscriptChunk(BaseModel):
    index: int
    start: float
    end: float
    segments: list[TranscriptSegment] = Field(default_factory=list)

    @property
    def char_count(self) -> int:
        return sum(len(s.text) for s in self.segments)

    def to_prompt_text(self) -> str:
        """LLM 입력용 텍스트. 각 줄 앞에 시작 초를 붙여 타임스탬프 인용을 돕는다."""
        return "\n".join(f"[{int(s.start)}s] {s.text}" for s in self.segments)


def build_chunks(
    segments: list[TranscriptSegment],
    *,
    max_chars: int = 7000,
    overlap_segments: int = 1,
) -> list[TranscriptChunk]:
    """세그먼트를 청크로 분할한다.

    세그먼트는 절대 쪼개지 않으며, 누적 글자 수가 max_chars를 넘으면 새 청크를
    시작한다. 새 청크는 직전 청크의 마지막 overlap_segments개 세그먼트로 시작해
    문맥을 잇는다. 단일 세그먼트가 max_chars보다 길어도 그대로 한 청크에 담는다.
    """
    if not segments:
        return []
    if max_chars <= 0:
        raise ValueError("max_chars는 양수여야 합니다.")
    overlap_segments = max(0, overlap_segments)

    chunks: list[TranscriptChunk] = []
    current: list[TranscriptSegment] = []
    current_chars = 0

    def flush() -> None:
        nonlocal current, current_chars
        if not current:
            return
        chunks.append(
            TranscriptChunk(
                index=len(chunks),
                start=current[0].start,
                end=current[-1].end,
                segments=list(current),
            )
        )

    for seg in segments:
        seg_len = len(seg.text)
        # 이미 내용이 있고, 추가하면 한도를 넘으면 청크를 닫고 중첩과 함께 새로 시작
        if current and current_chars + seg_len > max_chars:
            flush()
            overlap = current[-overlap_segments:] if overlap_segments else []
            current = list(overlap)
            current_chars = sum(len(s.text) for s in current)

        current.append(seg)
        current_chars += seg_len

    flush()
    return chunks
