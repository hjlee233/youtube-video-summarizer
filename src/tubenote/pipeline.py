"""파이프라인 오케스트레이션 (기획안 6절).

메타데이터 → 다운로드 → WAV 변환 → STT → 정규화 → (청크 분할 → LLM 요약 →
Markdown 렌더링) → JSON/MD 저장. 요약 자격증명이 없으면 대본까지만 저장한다.

재개/캐시 (기획안 16절 P1): 같은 영상의 result.json에 대본이 이미 있으면
다운로드·STT를 건너뛴다. 대본은 있는데 요약이 없으면(중단) STT 재실행 없이
요약부터 이어간다. force_reprocess로 캐시를 무시할 수 있다.
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
    from_cache: bool = False


def plan_resume(
    existing: Result | None,
    *,
    summarize_enabled: bool,
    force: bool,
) -> tuple[bool, bool]:
    """기존 결과로부터 재개 계획을 결정한다 (순수 함수, 테스트 용이).

    반환: (reuse_transcript, need_summary)
    - reuse_transcript: 다운로드·STT를 건너뛰고 기존 대본을 재사용할지
    - need_summary: 이번 실행에서 요약을 실제로 수행할지
    """
    reuse = (not force) and existing is not None and bool(existing.transcript)
    if reuse:
        need_summary = summarize_enabled and existing.final_summary is None
    else:
        need_summary = summarize_enabled
    return reuse, need_summary


def _summarize_and_render(
    result: Result,
    config: Config,
    *,
    do_summary: bool,
    job: Job,
    jobs_dir: Path,
    log: StepLogger,
) -> tuple[Path, Path, bool]:
    """요약(필요 시) + Markdown 렌더링 (캐시·전체 경로 공용)."""
    summarized = result.final_summary is not None
    if do_summary:
        try:
            notice = security.cloud_transfer_notice(config)  # 기획안 12절
            if notice:
                log("summary", notice)
            chunks = chunking.build_chunks(
                result.transcript, max_chars=config.summary.chunk_chars
            )
            log("summary", f"청크 {len(chunks)}개로 분할, 요약을 시작합니다.")
            job.status = JobStatus.SUMMARIZING
            chunk_summaries, final_summary = summarizer.summarize(
                chunks, result.metadata, config, log=lambda m: log("summary", m)
            )
            result.chunk_summaries = chunk_summaries
            result.final_summary = final_summary
            result.model_info.summarizer = config.summary.model
            storage.save_result(config.paths.result_dir, result)
            job.mark_step("summary", JobStatus.SUMMARIZING)
            summarized = True
            log("summary", "요약 완료.")
        except SummaryNotConfiguredError as exc:
            log("summary", exc.user_message)
        except SummaryError as exc:
            log("summary", f"요약 실패 — 대본은 저장되어 있습니다: {exc}")
    elif not summarized:
        log("summary", "요약을 건너뜁니다.")
    else:
        log("summary", "기존 요약을 재사용합니다 (캐시).")

    markdown = renderer.render_markdown(
        result, include_full_transcript=config.privacy.include_full_transcript
    )
    markdown_path = storage.save_markdown(
        config.paths.result_dir, result.metadata.video_id, markdown
    )
    job.mark_step("render", JobStatus.DONE)
    storage.save_job(jobs_dir, job)
    log("render", f"Markdown 저장: {markdown_path}")
    result_path = (
        storage.result_dir_for(config.paths.result_dir, result.metadata.video_id)
        / "result.json"
    )
    return result_path, markdown_path, summarized


def run_transcription_pipeline(
    url: str,
    config: Config,
    *,
    cookies_from_browser: str | None = None,
    summarize_enabled: bool = True,
    force_reprocess: bool = False,
    log: StepLogger = _noop_log,
) -> PipelineOutcome:
    """URL 하나를 받아 대본 → (요약) → Markdown 까지 생성한다 (재개/캐시 지원)."""
    config.paths.ensure()
    jobs_dir = config.paths.data_dir / "jobs"

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

    existing = (
        None if force_reprocess else storage.load_result(config.paths.result_dir, video_id)
    )
    reuse, need_summary = plan_resume(
        existing, summarize_enabled=summarize_enabled, force=force_reprocess
    )

    # --- 캐시/재개 경로: 기존 대본 재사용 (다운로드·STT 건너뜀) ---
    if reuse:
        assert existing is not None
        log(
            "cache",
            f"기존 대본을 재사용합니다 (세그먼트 {len(existing.transcript)}개). 다운로드·STT 건너뜀.",
        )
        for step in ("metadata", "download", "audio", "transcribe", "transcript_saved"):
            job.mark_step(step, JobStatus.TRANSCRIBING)
        storage.save_job(jobs_dir, job)
        result_path, markdown_path, summarized = _summarize_and_render(
            existing, config, do_summary=need_summary, job=job, jobs_dir=jobs_dir, log=log
        )
        return PipelineOutcome(
            job=job,
            metadata=existing.metadata,
            result=existing,
            result_path=result_path,
            markdown_path=markdown_path,
            summarized=summarized,
            from_cache=True,
        )

    # --- 전체 경로 ---
    audio.find_ffmpeg()  # FFmpeg 사전 점검
    allow_remote = config.youtube.allow_remote_components

    log("metadata", "영상 정보를 조회합니다.")
    metadata = youtube.fetch_metadata(
        url,
        cookies_from_browser=cookies_from_browser,
        allow_remote_components=allow_remote,
    )
    job.mark_step("metadata", JobStatus.METADATA)
    storage.save_job(jobs_dir, job)
    log("metadata", f"제목: {metadata.title}")

    temp_dir = config.paths.temp_dir
    audio_path: Path | None = None
    wav_path: Path | None = None
    try:
        # 오디오 다운로드
        log("download", "오디오를 다운로드합니다.")
        job.status = JobStatus.DOWNLOADING
        audio_path = youtube.download_audio(
            url,
            temp_dir,
            cookies_from_browser=cookies_from_browser,
            allow_remote_components=allow_remote,
        )
        job.mark_step("download", JobStatus.DOWNLOADING)

        # WAV 전처리
        log("audio", "16 kHz mono WAV로 변환합니다.")
        job.status = JobStatus.PREPROCESSING
        wav_path = audio.to_wav_16k_mono(audio_path, temp_dir / f"{video_id}.wav")
        job.mark_step("audio", JobStatus.PREPROCESSING)

        # STT
        log("transcribe", f"음성 인식을 시작합니다 (모델: {config.transcription.model}).")
        job.status = JobStatus.TRANSCRIBING

        def _progress(done: float, total: float | None) -> None:
            if total:
                log("transcribe", f"진행률 {done / total * 100:4.1f}% ({done:.0f}/{total:.0f}s)")

        raw_segments, detected_language = transcribe(
            wav_path, config.transcription, progress=_progress
        )
        job.mark_step("transcribe", JobStatus.TRANSCRIBING)

        # 정규화
        segments = transcript.normalize_segments(raw_segments)
        log("transcribe", f"세그먼트 {len(segments)}개 (감지 언어: {detected_language})")

        # 대본 결과 저장 (요약 전에 먼저 저장해 STT 결과를 보존 → 재개 가능)
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
        storage.save_result(config.paths.result_dir, result)
        job.mark_step("transcript_saved", JobStatus.TRANSCRIBING)
        storage.save_job(jobs_dir, job)
        log("save", "대본 저장 완료.")

        result_path, markdown_path, summarized = _summarize_and_render(
            result, config, do_summary=need_summary, job=job, jobs_dir=jobs_dir, log=log
        )
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
        storage.save_job(jobs_dir, job)
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
