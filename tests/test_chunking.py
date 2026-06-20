"""청크 분할 단위 테스트 (기획안 17절)."""

from tubenote.chunking import build_chunks
from tubenote.models import TranscriptSegment


def _segs(texts):
    out = []
    t = 0.0
    for i, text in enumerate(texts):
        out.append(TranscriptSegment(index=i, start=t, end=t + 2.0, text=text))
        t += 2.0
    return out


def test_empty_returns_empty():
    assert build_chunks([]) == []


def test_single_chunk_when_small():
    segs = _segs(["가" * 10, "나" * 10])
    chunks = build_chunks(segs, max_chars=1000, overlap_segments=0)
    assert len(chunks) == 1
    assert len(chunks[0].segments) == 2
    assert chunks[0].start == 0.0
    assert chunks[0].end == 4.0


def test_splits_on_char_limit():
    segs = _segs(["가" * 50, "나" * 50, "다" * 50])
    chunks = build_chunks(segs, max_chars=60, overlap_segments=0)
    # 각 세그먼트가 50자, 한도 60 -> 세그먼트 하나씩 별도 청크
    assert len(chunks) == 3
    assert [len(c.segments) for c in chunks] == [1, 1, 1]


def test_overlap_carries_previous_segment():
    segs = _segs(["가" * 50, "나" * 50, "다" * 50])
    chunks = build_chunks(segs, max_chars=60, overlap_segments=1)
    # 두 번째 청크는 직전 마지막 세그먼트로 시작 (중첩)
    assert chunks[1].segments[0].text == chunks[0].segments[-1].text


def test_never_splits_oversized_segment():
    segs = _segs(["가" * 100])  # 단일 세그먼트가 한도보다 큼
    chunks = build_chunks(segs, max_chars=10)
    assert len(chunks) == 1
    assert chunks[0].char_count == 100


def test_chunk_indices_sequential():
    segs = _segs(["가" * 50] * 5)
    chunks = build_chunks(segs, max_chars=60, overlap_segments=0)
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_prompt_text_has_timestamps():
    segs = _segs(["안녕하세요"])
    chunks = build_chunks(segs, max_chars=1000)
    assert chunks[0].to_prompt_text() == "[0s] 안녕하세요"
