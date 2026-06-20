"""재개/캐시 계획(plan_resume) 단위 테스트 (기획안 16절 P1)."""

from tubenote.models import (
    FinalSummary,
    ModelInfo,
    Result,
    TranscriptSegment,
    VideoMetadata,
)
from tubenote.pipeline import plan_resume


def _result(*, with_transcript=True, with_summary=False):
    return Result(
        metadata=VideoMetadata(video_id="abc12345678", title="t", url="u"),
        transcript=(
            [TranscriptSegment(index=0, start=0.0, end=1.0, text="안녕")]
            if with_transcript
            else []
        ),
        final_summary=FinalSummary(conclusion="끝") if with_summary else None,
        model_info=ModelInfo(stt="large-v3"),
    )


def test_no_existing_runs_full():
    assert plan_resume(None, summarize_enabled=True, force=False) == (False, True)
    assert plan_resume(None, summarize_enabled=False, force=False) == (False, False)


def test_force_ignores_cache():
    r = _result(with_transcript=True, with_summary=True)
    # 강제 재처리: 대본·요약이 있어도 전체 재실행
    assert plan_resume(r, summarize_enabled=True, force=True) == (False, True)


def test_resume_when_transcript_only():
    # 대본은 있고 요약이 없음 → STT 건너뛰고 요약만 수행 (재개)
    r = _result(with_transcript=True, with_summary=False)
    assert plan_resume(r, summarize_enabled=True, force=False) == (True, True)


def test_cache_hit_when_fully_done():
    # 대본+요약 모두 있음 → 재사용, 요약도 건너뜀 (캐시 히트)
    r = _result(with_transcript=True, with_summary=True)
    assert plan_resume(r, summarize_enabled=True, force=False) == (True, False)


def test_reuse_transcript_without_summary_request():
    # 대본 있음, 요약 비활성 → 재사용하되 요약 안 함
    r = _result(with_transcript=True, with_summary=False)
    assert plan_resume(r, summarize_enabled=False, force=False) == (True, False)


def test_empty_transcript_runs_full():
    r = _result(with_transcript=False)
    assert plan_resume(r, summarize_enabled=True, force=False) == (False, True)
