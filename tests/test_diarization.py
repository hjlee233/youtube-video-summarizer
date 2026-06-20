"""화자 배정/이름변경 단위 테스트 (기획안 5단계). pyannote 불필요."""

from tubenote.diarization import (
    SpeakerTurn,
    assign_speakers,
    rename_speakers,
    unique_speakers,
)
from tubenote.models import TranscriptSegment


def _seg(i, start, end, text="x", speaker=None):
    return TranscriptSegment(index=i, start=start, end=end, text=text, speaker=speaker)


def test_assign_by_max_overlap():
    segs = [_seg(0, 0.0, 5.0), _seg(1, 5.0, 10.0)]
    turns = [
        SpeakerTurn(0.0, 4.8, "SPEAKER_00"),
        SpeakerTurn(4.8, 10.0, "SPEAKER_01"),
    ]
    out = assign_speakers(segs, turns)
    assert out[0].speaker == "SPEAKER_00"
    assert out[1].speaker == "SPEAKER_01"


def test_assign_picks_larger_overlap():
    # 세그먼트 0~10이 두 화자에 걸침: 0~3 spk0, 3~10 spk1 → 더 긴 spk1
    segs = [_seg(0, 0.0, 10.0)]
    turns = [SpeakerTurn(0.0, 3.0, "A"), SpeakerTurn(3.0, 10.0, "B")]
    assert assign_speakers(segs, turns)[0].speaker == "B"


def test_assign_no_overlap_keeps_none():
    segs = [_seg(0, 0.0, 5.0)]
    turns = [SpeakerTurn(10.0, 20.0, "A")]
    assert assign_speakers(segs, turns)[0].speaker is None


def test_rename_speakers():
    segs = [_seg(0, 0, 1, speaker="SPEAKER_00"), _seg(1, 1, 2, speaker="SPEAKER_01")]
    out = rename_speakers(segs, {"SPEAKER_00": "진행자", "SPEAKER_01": ""})
    assert out[0].speaker == "진행자"
    assert out[1].speaker == "SPEAKER_01"  # 빈 매핑 → 유지


def test_rename_unmapped_kept():
    segs = [_seg(0, 0, 1, speaker="SPEAKER_00")]
    out = rename_speakers(segs, {"SPEAKER_99": "x"})
    assert out[0].speaker == "SPEAKER_00"


def test_unique_speakers_in_order():
    segs = [
        _seg(0, 0, 1, speaker="B"),
        _seg(1, 1, 2, speaker="A"),
        _seg(2, 2, 3, speaker="B"),
        _seg(3, 3, 4, speaker=None),
    ]
    assert unique_speakers(segs) == ["B", "A"]
