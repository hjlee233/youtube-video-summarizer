"""파이프라인 오케스트레이션 (기획안 6절).

메타데이터 → 다운로드 → WAV 변환 → STT → 정규화 → (청크 분할 → LLM 요약 →
Markdown 렌더링) → JSON/MD 저장. 요약 자격증명이 없으면 대본까지만 저장한다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import audio, chunking, renderer, security, storage, summarizer, transcript, youtube
from .config import Config
from .errors import SummaryError, SummaryNotConfiguredError
from .models import (
    Job,
    JobSettings,
    JobStatus,
    ModelInfo,
    Result,
    VideoMetadata,
)
from .transcriber import _resolve_compute_type, transcribe

# 단계 로그 콜백: (단계 이름, 메시지) -> None
StepLogger = Callable[[str, str], None]


def _noop_log(step: str, message: str) -> None:  # pragma: no cover
    pass


@dataclass
class PipelineOutcome:
    job: Job
    metadata: VideoMetadata
    result: Result
    result_path: Path
    markdown_path: Path | None = None
    summarized: bool = False


def run_transcription_pipeline(
    url: str,
    config: Config,
    *,
    cookies_from_browser: str | None = None,
    summarize_enabled: bool = True,
    log: StepLogger = _noop_log,
) -> PipelineOutcome:
    """URL 하나를 받아 대본 → (요약) → Markdown 까지 생성한다."""
    config.paths.ensure()

    video_id = youtube.extract_video_id(url)
    job = Job(
        job_id=str(uuid.uuid4()),
        video_id=video_id,
        settings=JobSettings(
            stt_model=config.transcription.model,
            language=config.transcription.language,
            keep_audio=config.privacy.keep_audio,
        ),
    )

    # FFmpeg 사전 점검 — 다운로드 전에 빠르게 실패하도록
    audio.find_ffmpeg()

    allow_remote = config.youtube.allow_remote_components

    # 1. 메타데이터
    log("metadata", "영상 정보를 조회합니다.")
    metadata = youtube.fetch_metadata(
        url,
        cookies_from_browser=cookies_from_browser,
        allow_remote_components=allow_remote,
    )
    job.mark_step("metadata", JobStatus.METADATA)
    storage.save_job(config.paths.data_dir / "jobs", job)
    log("metadata", f"제목: {metadata.title}")

    temp_dir = config.paths.temp_dir
    audio_path: Path | None = None
    wav_path: Path | None = None
    try:
        # 2. 오디오 다운로드
        log("download", "오디오를 다운로드합니다.")
        job.status = JobStatus.DOWNLOADING
        audio_path = youtube.download_audio(
            url,
            temp_dir,
            cookies_from_browser=cookies_from_browser,
            allow_remote_components=allow_remote,
        )
        job.mark_step("download", JobStatus.DOWNLOADING)

        # 3. WAV 전처리
        log("audio", "16 kHz mono WAV로 변환합니다.")
        job.status = JobStatus.PREPROCESSING
        wav_path = audio.to_wav_16k_mono(audio_path, temp_dir / f"{video_id}.wav")
        job.mark_step("audio", JobStatus.PREPROCESSING)

        # 4. STT
        log("transcribe", f"음성 인식을 시작합니다 (모델: {config.transcription.model}).")
        job.status = JobStatus.TRANSCRIBING

        def _progress(done: float, total: float | None) -> None:
            if total:
                log("transcribe", f"진행률 {done / total * 100:4.1f}% ({done:.0f}/{total:.0f}s)")

        raw_segments, detected_language = transcribe(
            wav_path, config.transcription, progress=_progress
        )
        job.mark_step("transcribe", JobStatus.TRANSCRIBING)

        # 5. 정규화
        segments = transcript.normalize_segments(raw_segments)
        log("transcribe", f"세그먼트 {len(segments)}개 (감지 언어: {detected_language})")

        # 6. 대본 결과 저장 (요약 전에 먼저 저장해 STT 결과를 보존)
        result = Result(
            metadata=metadata,
            transcript=segments,
            model_info=ModelInfo(
                stt=config.transcription.model,
                language=detected_language,
                device=config.transcription.device,
                compute_type=_resolve_compute_type(
                    config.transcription.device, config.transcription.compute_type
                ),
            ),
        )
        result_path = storage.save_result(config.paths.result_dir, result)
        job.mark_step("transcript_saved", JobStatus.TRANSCRIBING)
        storage.save_job(config.paths.data_dir / "jobs", job)
        log("save", f"대본 저장: {result_path}")

        # 7. 요약 (자격증명 없으면 건너뜀 — 기획안 11절 "대본까지만 저장")
        summarized = False
        if not summarize_enabled:
            log("summary", "요약을 건너뜁니다 (--no-summary).")
        else:
            try:
                # 클라우드 LLM이면 대본 전송 안내 (기획안 12절)
                notice = security.cloud_transfer_notice(config)
                if notice:
                    log("summary", notice)
                chunks = chunking.build_chunks(
                    segments, max_chars=config.summary.chunk_chars
                )
                log("summary", f"청크 {len(chunks)}개로 분할, 요약을 시작합니다.")
                job.status = JobStatus.SUMMARIZING

                def _slog(msg: str) -> None:
                    log("summary", msg)

                chunk_summaries, final_summary = summarizer.summarize(
                    chunks, metadata, config, log=_slog
                )
                result.chunk_summaries = chunk_summaries
                result.final_summary = final_summary
                result.model_info.summarizer = config.summary.model
                result_path = storage.save_result(config.paths.result_dir, result)
                job.mark_step("summary", JobStatus.SUMMARIZING)
                summarized = True
                log("summary", "요약 완료.")
            except SummaryNotConfiguredError as exc:
                log("summary", exc.user_message)
            except SummaryError as exc:
                # 요약 실패가 대본 저장을 무효화하지 않음
                log("summary", f"요약 실패 — 대본은 저장되어 있습니다: {exc}")

        # 8. Markdown 렌더링
        markdown = renderer.render_markdown(
            result,
            include_full_transcript=config.privacy.include_full_transcript,
        )
        markdown_path = storage.save_markdown(
            config.paths.result_dir, video_id, markdown
        )
        job.mark_step("render", JobStatus.DONE)
        storage.save_job(config.paths.data_dir / "jobs", job)
        log("render", f"Markdown 저장: {markdown_path}")

        return PipelineOutcome(
            job=job,
            metadata=metadata,
            result=result,
            result_path=result_path,
            markdown_path=markdown_path,
            summarized=summarized,
        )

    except Exception as exc:
        job.status = JobStatus.FAILED
        # 상태 파일에 비밀이 새지 않도록 마스킹 (기획안 12절)
        job.error = security.mask_text(str(exc), *security.secret_values(config))
        storage.save_job(config.paths.data_dir / "jobs", job)
        raise
    finally:
        # 임시 파일 정리 (기획안 8절 / 12절): keep_audio가 아니면 삭제
        if not config.privacy.keep_audio:
            for p in (audio_path, wav_path):
                if p is not None and p.is_file():
                    try:
                        p.unlink()
                    except OSError:
                        pass
