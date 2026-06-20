"""요약 오케스트레이션 단위 테스트 (LLM 호출은 모킹)."""

import json

import pytest

from tubenote.chunking import build_chunks
from tubenote.config import Config
from tubenote.errors import SummaryError, SummaryNotConfiguredError
from tubenote.models import TranscriptSegment, VideoMetadata
from tubenote import summarizer as summ


def _configured_config():
    c = Config.load()
    c.summary.provider = "openai_compatible"
    c.summary.model = "test-model"
    c.secrets.openai_api_key = "sk-test"
    return c


def _segments(n):
    return [
        TranscriptSegment(index=i, start=i * 5.0, end=i * 5.0 + 5.0, text="문장" * 30)
        for i in range(n)
    ]


def _metadata():
    return VideoMetadata(
        video_id="abc12345678",
        title="제목",
        channel="채널",
        url="https://www.youtube.com/watch?v=abc12345678",
        duration_seconds=100,
    )


_CHUNK_JSON = json.dumps(
    {
        "summary": "구간 요약",
        "topics": [{"title": "주제", "detail": "설명", "timestamp_seconds": 10}],
        "claims": [{"text": "주장", "timestamp_seconds": 12}],
        "action_items": [],
        "uncertain_points": [],
    }
)

_FINAL_JSON = json.dumps(
    {
        "three_line_summary": ["줄1", "줄2", "줄3"],
        "key_points": ["핵심"],
        "timeline": [{"timestamp_seconds": 0, "title": "도입"}],
        "details": [{"title": "상세", "detail": "내용", "timestamp_seconds": 20}],
        "claims": [{"text": "주장", "timestamp_seconds": 12}],
        "conclusion": "결론",
        "action_items": [],
        "uncertain_points": [],
    }
)


def test_not_configured_raises():
    # 환경(config.yaml/.env)에 의존하지 않도록 명시적으로 미설정 상태 구성
    c = Config.load()
    c.summary.model = ""
    c.secrets.openai_api_key = ""
    c.secrets.openai_base_url = ""
    with pytest.raises(SummaryNotConfiguredError):
        summ.Summarizer(c)


def test_map_reduce_with_mocked_llm(monkeypatch):
    # 청크 프롬프트와 최종 프롬프트를 내용으로 구분해 응답을 분기
    def fake_call(self, prompt):
        if "분석할 대본 구간" in prompt:
            return f"```json\n{_CHUNK_JSON}\n```"
        return _FINAL_JSON

    monkeypatch.setattr(summ.Summarizer, "_call", fake_call)

    config = _configured_config()
    segs = _segments(6)
    chunks = build_chunks(segs, max_chars=150, overlap_segments=0)
    assert len(chunks) >= 2  # 여러 청크가 나오도록

    chunk_summaries, final = summ.summarize(chunks, _metadata(), config)

    assert len(chunk_summaries) == len(chunks)
    # chunk_index가 올바르게 부여되는지
    assert [cs.chunk_index for cs in chunk_summaries] == list(range(len(chunks)))
    assert chunk_summaries[0].summary == "구간 요약"
    assert final.three_line_summary == ["줄1", "줄2", "줄3"]
    assert final.conclusion == "결론"


def test_failed_chunk_is_skipped_not_fatal(monkeypatch):
    calls = {"n": 0}

    def fake_call(self, prompt):
        if "분석할 대본 구간" in prompt:
            calls["n"] += 1
            if calls["n"] == 1:
                return "쓰레기 응답 not json"  # 첫 청크 파싱 실패
            return _CHUNK_JSON
        return _FINAL_JSON

    monkeypatch.setattr(summ.Summarizer, "_call", fake_call)
    # 파싱 실패 시 재시도 없이 바로 SummaryError가 나도록 max_retries=1로
    config = _configured_config()
    config.summary.max_retries = 1

    segs = _segments(6)
    chunks = build_chunks(segs, max_chars=150, overlap_segments=0)
    chunk_summaries, final = summ.summarize(chunks, _metadata(), config)

    # 첫 청크는 건너뛰고 나머지는 성공
    assert len(chunk_summaries) == len(chunks) - 1
    assert final.conclusion == "결론"
