"""대본 정규화 단위 테스트 (기획안 17절)."""

from tubenote.models import TranscriptSegment
from tubenote.transcript import full_text, normalize_segments


def _seg(index, start, end, text):
    return TranscriptSegment(index=index, start=start, end=end, text=text)


def test_removes_empty_segments():
    segs = [
        _seg(0, 0.0, 2.0, "안녕하세요"),
        _seg(1, 2.0, 2.1, "   "),
        _seg(2, 2.1, 5.0, "반갑습니다"),
    ]
    out = normalize_segments(segs)
    assert [s.text for s in out] == ["안녕하세요", "반갑습니다"]


def test_collapses_whitespace():
    out = normalize_segments([_seg(0, 0.0, 3.0, "  여러   공백   정리  ")])
    assert out[0].text == "여러 공백 정리"


def test_merges_short_adjacent_segment():
    segs = [
        _seg(0, 0.0, 3.0, "첫 문장입니다"),
        _seg(1, 3.1, 3.3, "네"),  # 짧고(0.2s) 간격 작음(0.1s) -> 병합
    ]
    out = normalize_segments(segs)
    assert len(out) == 1
    assert out[0].text == "첫 문장입니다 네"
    assert out[0].start == 0.0
    assert out[0].end == 3.3  # 뒤 세그먼트 end 보존


def test_does_not_merge_when_gap_large():
    segs = [
        _seg(0, 0.0, 3.0, "첫 문장"),
        _seg(1, 10.0, 10.2, "네"),  # 짧지만 간격이 큼 -> 병합 안 함
    ]
    out = normalize_segments(segs)
    assert len(out) == 2


def test_reindexes_from_zero():
    segs = [
        _seg(5, 0.0, 2.0, "a"),
        _seg(9, 2.0, 4.0, "b"),
    ]
    out = normalize_segments(segs)
    assert [s.index for s in out] == [0, 1]


def test_full_text():
    segs = [_seg(0, 0.0, 1.0, "줄1"), _seg(1, 1.0, 2.0, "줄2")]
    assert full_text(segs) == "줄1\n줄2"
