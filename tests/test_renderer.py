"""Markdown 렌더링 단위 테스트 (기획안 17절)."""

from tubenote.models import (
    Claim,
    FinalSummary,
    ModelInfo,
    Result,
    TimelineEntry,
    Topic,
    TranscriptSegment,
    VideoMetadata,
)
from tubenote.renderer import format_hms, render_markdown

VIDEO_ID = "dQw4w9WgXcQ"


def _result(final_summary):
    return Result(
        metadata=VideoMetadata(
            video_id=VIDEO_ID,
            title="테스트 영상",
            channel="테스트 채널",
            url=f"https://www.youtube.com/watch?v={VIDEO_ID}",
            duration_seconds=3725,
            upload_date="20251109",
        ),
        transcript=[
            TranscriptSegment(index=0, start=0.0, end=2.0, text="첫 줄"),
            TranscriptSegment(index=1, start=12.0, end=15.0, text="둘째 줄"),
        ],
        final_summary=final_summary,
        model_info=ModelInfo(stt="large-v3", language="ko"),
    )


def test_format_hms():
    assert format_hms(0) == "0:00"
    assert format_hms(75) == "1:15"
    assert format_hms(3725) == "1:02:05"


def test_renders_metadata_and_default_excludes_transcript():
    md = render_markdown(_result(None))  # 기본값: 대본 미포함
    assert "# 테스트 영상" in md
    assert "채널: 테스트 채널" in md
    assert "길이: 1:02:05" in md
    assert "게시일: 2025-11-09" in md
    # 기본적으로 전체 대본 섹션은 포함하지 않는다
    assert "## 전체 대본" not in md
    assert f"&t=12s" not in md
    # 요약이 없으면 안내 문구
    assert "요약이 생성되지 않았습니다" in md


def test_includes_full_transcript_when_enabled():
    md = render_markdown(_result(None), include_full_transcript=True)
    assert "## 전체 대본" in md
    assert f"https://www.youtube.com/watch?v={VIDEO_ID}&t=12s" in md


def test_renders_full_summary_sections_with_timestamp_links():
    fs = FinalSummary(
        three_line_summary=["요약1", "요약2"],
        key_points=["핵심1"],
        timeline=[TimelineEntry(timestamp_seconds=30, title="도입")],
        details=[Topic(title="주제A", detail="설명A", timestamp_seconds=60)],
        claims=[Claim(text="주장X", timestamp_seconds=90)],
        conclusion="결론입니다.",
        action_items=["할 일1"],
        uncertain_points=["확인 필요1"],
    )
    md = render_markdown(_result(fs))

    for section in [
        "## 세 줄 요약",
        "## 핵심 내용",
        "## 시간순 목차",
        "## 상세 정리",
        "## 주요 주장과 근거",
        "## 결론",
        "## 실행 항목",
        "## 불확실하거나 확인이 필요한 내용",
    ]:
        assert section in md

    assert "요약1" in md
    assert "**주제A**" in md
    assert "주장X" in md
    assert "결론입니다." in md
    # 타임스탬프 링크들
    assert f"&t=30s" in md
    assert f"&t=60s" in md
    assert f"&t=90s" in md


def test_default_excludes_full_transcript_with_summary():
    fs = FinalSummary(three_line_summary=["요약"])
    md = render_markdown(_result(fs))  # 기본값 False
    assert "## 전체 대본" not in md


def test_narrative_section_rendered_between_timeline_and_details():
    fs = FinalSummary(
        timeline=[TimelineEntry(timestamp_seconds=10, title="도입")],
        narrative="첫 문단입니다.\n\n둘째 문단입니다.",
        details=[Topic(title="주제A")],
    )
    md = render_markdown(_result(fs))
    assert "## 서사 요약" in md
    assert "첫 문단입니다." in md
    # 위치: 시간순 목차 다음, 상세 정리 이전
    assert md.index("## 시간순 목차") < md.index("## 서사 요약") < md.index("## 상세 정리")


def test_narrative_section_omitted_when_empty():
    fs = FinalSummary(three_line_summary=["요약"])  # narrative 기본 ""
    md = render_markdown(_result(fs))
    assert "## 서사 요약" not in md
