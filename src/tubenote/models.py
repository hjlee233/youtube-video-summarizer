"""데이터 모델 정의 (기획안 9절 기준).

파일 기반 JSON 저장을 전제로 하며, pydantic 모델로 직렬화/검증한다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStatus(str, Enum):
    PENDING = "pending"
    METADATA = "metadata"
    DOWNLOADING = "downloading"
    PREPROCESSING = "preprocessing"
    TRANSCRIBING = "transcribing"
    SUMMARIZING = "summarizing"
    RENDERING = "rendering"
    DONE = "done"
    FAILED = "failed"


class VideoMetadata(BaseModel):
    """yt-dlp로 수집한 영상 메타데이터 (기획안 8.2)."""

    video_id: str
    title: str
    channel: str | None = None
    url: str
    duration_seconds: int | None = None
    upload_date: str | None = None  # yt-dlp는 YYYYMMDD 형식 제공
    thumbnail_url: str | None = None
    is_live: bool = False
    fetched_at: str = Field(default_factory=_utcnow_iso)


class TranscriptSegment(BaseModel):
    """STT가 생성한 대본 세그먼트 (기획안 9절)."""

    index: int
    start: float
    end: float
    speaker: str | None = None
    text: str


class JobSettings(BaseModel):
    stt_model: str = "medium"
    language: str = "auto"
    summary_detail: str = "standard"
    keep_audio: bool = False


class Job(BaseModel):
    """작업 상태 (기획안 9절). 단계 완료 시마다 갱신해 재개에 활용."""

    job_id: str
    video_id: str
    status: JobStatus = JobStatus.PENDING
    completed_steps: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_utcnow_iso)
    updated_at: str = Field(default_factory=_utcnow_iso)
    error: str | None = None
    settings: JobSettings = Field(default_factory=JobSettings)

    def mark_step(self, step: str, status: JobStatus) -> None:
        if step not in self.completed_steps:
            self.completed_steps.append(step)
        self.status = status
        self.updated_at = _utcnow_iso()


class Topic(BaseModel):
    """청크/최종 요약의 한 주제 항목 (기획안 8.8)."""

    title: str
    detail: str = ""
    timestamp_seconds: float | None = None


class Claim(BaseModel):
    """근거 시간이 연결된 주장 (기획안 8.8 / 14절)."""

    text: str
    timestamp_seconds: float | None = None


class ChunkSummary(BaseModel):
    """청크 단위 요약 결과 (Map 단계)."""

    chunk_index: int = 0
    summary: str = ""
    topics: list[Topic] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)
    uncertain_points: list[str] = Field(default_factory=list)


class TimelineEntry(BaseModel):
    """시간순 목차 항목 (기획안 8.9)."""

    timestamp_seconds: float
    title: str


class FinalSummary(BaseModel):
    """전체 통합 요약 결과 (Reduce 단계, 기획안 8.9)."""

    three_line_summary: list[str] = Field(default_factory=list)
    key_points: list[str] = Field(default_factory=list)
    timeline: list[TimelineEntry] = Field(default_factory=list)
    # 산문형 서사 요약 (읽기용). 시간순 목차 다음에 렌더링된다.
    narrative: str = ""
    details: list[Topic] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    conclusion: str = ""
    action_items: list[str] = Field(default_factory=list)
    uncertain_points: list[str] = Field(default_factory=list)


class ModelInfo(BaseModel):
    stt: str
    language: str | None = None
    device: str | None = None
    compute_type: str | None = None
    summarizer: str | None = None


class Result(BaseModel):
    """최종 결과 묶음 (기획안 9절)."""

    metadata: VideoMetadata
    transcript: list[TranscriptSegment] = Field(default_factory=list)
    chunk_summaries: list[ChunkSummary] = Field(default_factory=list)
    final_summary: FinalSummary | None = None
    model_info: ModelInfo
