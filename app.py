"""TubeNote Local — Streamlit UI (기획안 10절 / 15절 3단계).

    uv run streamlit run app.py
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

import streamlit as st

from tubenote import security, storage, youtube
from tubenote.config import Config
from tubenote.errors import TubeNoteError
from tubenote.models import FinalSummary, Result
from tubenote.pipeline import run_transcription_pipeline
from tubenote.renderer import format_hms, render_markdown
from tubenote.summarizer import is_summary_configured
from tubenote.youtube import timestamp_url

st.set_page_config(page_title="TubeNote Local", page_icon="📝", layout="wide")

# 단계별 진행률 기준값 (transcribe는 내부 %로 보간)
_STEP_FRAC = {
    "metadata": 0.05,
    "download": 0.15,
    "audio": 0.22,
    "transcribe": 0.30,
    "save": 0.72,
    "summary": 0.80,
    "render": 0.98,
}


# --------------------------------------------------------------------------- #
# 사이드바 설정
# --------------------------------------------------------------------------- #
def build_config() -> tuple[Config, str | None, bool]:
    base = Config.load()
    st.sidebar.header("⚙️ 설정")

    st.sidebar.subheader("음성 인식 (STT)")
    models = ["small", "medium", "large-v3"]
    stt_model = st.sidebar.selectbox(
        "STT 모델", models, index=models.index(base.transcription.model) if base.transcription.model in models else 1
    )
    langs = ["auto", "ko", "en", "ja"]
    language = st.sidebar.selectbox("언어", langs, index=langs.index(base.transcription.language) if base.transcription.language in langs else 0)
    devices = ["auto", "cuda", "cpu"]
    device = st.sidebar.selectbox("실행 장치", devices, index=devices.index(base.transcription.device) if base.transcription.device in devices else 0)
    ctypes = ["auto", "float16", "int8_float16", "int8", "float32"]
    compute_type = st.sidebar.selectbox("연산 정밀도", ctypes, index=ctypes.index(base.transcription.compute_type) if base.transcription.compute_type in ctypes else 0)

    st.sidebar.subheader("요약 (LLM)")
    do_summary = st.sidebar.checkbox("요약 생성", value=False)
    providers = ["openai_compatible", "ollama"]
    provider = st.sidebar.selectbox("요약 제공자", providers, index=providers.index(base.summary.provider) if base.summary.provider in providers else 0)
    summary_model = st.sidebar.text_input("요약 모델", value=base.summary.model)
    details = ["simple", "standard", "detailed"]
    detail = st.sidebar.selectbox("요약 상세도", details, index=details.index(base.summary.detail) if base.summary.detail in details else 1)

    st.sidebar.subheader("로그인 / 개인정보")
    browsers = ["(사용 안 함)", "chrome", "edge", "firefox"]
    _bdefault = base.youtube.cookies_from_browser
    browser = st.sidebar.selectbox(
        "로그인 브라우저 (비공개 영상용)",
        browsers,
        index=browsers.index(_bdefault) if _bdefault in browsers else 0,
    )
    allow_remote = st.sidebar.checkbox(
        "보호/멤버십 영상 처리 (외부 JS 챌린지 해석)",
        value=base.youtube.allow_remote_components,
        help="yt-dlp가 외부 JS 솔버(yt-dlp-ejs)를 GitHub에서 받아 Deno로 실행합니다. Deno 설치 필요.",
    )
    keep_audio = st.sidebar.checkbox("원본 오디오 보관", value=base.privacy.keep_audio)
    include_transcript = st.sidebar.checkbox(
        "요약 문서에 전체 대본 포함", value=base.privacy.include_full_transcript
    )

    # 설정 반영
    base.transcription.model = stt_model
    base.transcription.language = language
    base.transcription.device = device
    base.transcription.compute_type = compute_type
    base.summary.provider = provider
    base.summary.model = summary_model
    base.summary.detail = detail
    base.youtube.allow_remote_components = allow_remote
    base.privacy.keep_audio = keep_audio
    base.privacy.include_full_transcript = include_transcript

    cookies = None if browser == "(사용 안 함)" else browser

    # 요약 설정 상태 안내
    if do_summary and not is_summary_configured(base):
        st.sidebar.warning("요약 자격증명/모델이 없어 대본까지만 저장됩니다. `.env`와 요약 모델을 확인하세요.")

    # 임시 폴더 정리 (기획안 12절)
    st.sidebar.subheader("정리")
    if st.sidebar.button("🧹 임시 폴더 정리"):
        count, freed = storage.clear_temp(base.paths.temp_dir)
        st.sidebar.success(f"임시 파일 {count}개 삭제 · {freed / 1024 / 1024:.1f} MB 확보")

    return base, cookies, do_summary


# --------------------------------------------------------------------------- #
# 결과 탭 렌더링 헬퍼
# --------------------------------------------------------------------------- #
def _summary_markdown(fs: FinalSummary) -> str:
    out: list[str] = []
    if fs.three_line_summary:
        out.append("### 세 줄 요약")
        out += [f"- {s}" for s in fs.three_line_summary]
    if fs.key_points:
        out.append("\n### 핵심 내용")
        out += [f"- {s}" for s in fs.key_points]
    if fs.narrative.strip():
        out.append("\n### 서사 요약\n")
        out.append(fs.narrative.strip())
    if fs.conclusion:
        out.append("\n### 결론\n")
        out.append(fs.conclusion)
    out.append("\n### 실행 항목")
    out += [f"- {a}" for a in fs.action_items] or ["- (없음)"]
    out.append("\n### 불확실하거나 확인이 필요한 내용")
    out += [f"- {u}" for u in fs.uncertain_points] or ["- (없음)"]
    return "\n".join(out)


def _timeline_markdown(fs: FinalSummary, vid: str) -> str:
    if not fs.timeline:
        return "_(시간순 목차 없음)_"
    lines = []
    for e in fs.timeline:
        link = f"[{format_hms(e.timestamp_seconds)}]({timestamp_url(vid, e.timestamp_seconds)})"
        lines.append(f"- {link} {e.title}")
    return "\n".join(lines)


def _details_markdown(fs: FinalSummary, vid: str) -> str:
    out: list[str] = ["#### 상세 정리"]
    if fs.details:
        for t in fs.details:
            link = f" ([{format_hms(t.timestamp_seconds)}]({timestamp_url(vid, t.timestamp_seconds)}))" if t.timestamp_seconds is not None else ""
            out.append(f"- **{t.title}**{link}")
            if t.detail:
                out.append(f"  - {t.detail}")
    else:
        out.append("- (없음)")
    out.append("\n#### 주요 주장과 근거")
    if fs.claims:
        for c in fs.claims:
            link = f" ([{format_hms(c.timestamp_seconds)}]({timestamp_url(vid, c.timestamp_seconds)}))" if c.timestamp_seconds is not None else ""
            out.append(f"- {c.text}{link}")
    else:
        out.append("- (없음)")
    return "\n".join(out)


def _transcript_markdown(result: Result) -> str:
    vid = result.metadata.video_id
    lines = []
    for seg in result.transcript:
        link = f"[{format_hms(seg.start)}]({timestamp_url(vid, seg.start)})"
        lines.append(f"- {link} {seg.text}")
    return "\n".join(lines)


def show_results(result: Result, result_path: Path, markdown_path: Path | None) -> None:
    md = result.metadata
    st.subheader(md.title)
    cols = st.columns([1, 2])
    if md.thumbnail_url:
        cols[0].image(md.thumbnail_url, use_container_width=True)
    info = cols[1]
    info.markdown(
        f"**채널:** {md.channel or '-'}  \n"
        f"**길이:** {format_hms(md.duration_seconds) if md.duration_seconds else '-'}  \n"
        f"**URL:** {md.url}  \n"
        f"**언어:** {result.model_info.language or '-'} · **STT:** {result.model_info.stt} · "
        f"**요약:** {result.model_info.summarizer or '없음'}"
    )

    # 다운로드 / 폴더 열기
    dl = st.columns(3)
    if markdown_path and markdown_path.is_file():
        dl[0].download_button(
            "⬇️ summary.md 다운로드",
            markdown_path.read_text(encoding="utf-8"),
            file_name=f"{md.video_id}_summary.md",
            mime="text/markdown",
        )
    dl[1].download_button(
        "⬇️ result.json 다운로드",
        result.model_dump_json(indent=2),
        file_name=f"{md.video_id}_result.json",
        mime="application/json",
    )
    if dl[2].button("📂 결과 폴더 열기"):
        try:
            os.startfile(result_path.parent)  # noqa: S606 (로컬 단일 사용자)
        except Exception as exc:  # pragma: no cover
            st.warning(f"폴더를 열 수 없습니다: {exc}")

    tabs = st.tabs(["요약", "시간순 목차", "상세 정리", "전체 대본", "원본 JSON"])
    fs = result.final_summary
    with tabs[0]:
        st.markdown(_summary_markdown(fs) if fs else "_요약이 생성되지 않았습니다._")
    with tabs[1]:
        st.markdown(_timeline_markdown(fs, md.video_id) if fs else "_없음_")
    with tabs[2]:
        st.markdown(_details_markdown(fs, md.video_id) if fs else "_없음_")
    with tabs[3]:
        st.markdown(_transcript_markdown(result))
    with tabs[4]:
        st.json(result.model_dump(mode="json"))


# --------------------------------------------------------------------------- #
# 메인
# --------------------------------------------------------------------------- #
def main() -> None:
    st.title("📝 TubeNote Local")
    st.caption("YouTube 영상을 로컬에서 대본화하고 AI로 요약합니다.")

    config, cookies, do_summary = build_config()

    # 클라우드 LLM 전송 안내 (기획안 12절)
    if do_summary:
        notice = security.cloud_transfer_notice(config)
        if notice:
            st.warning("⚠️ " + notice)

    url = st.text_input("YouTube URL", placeholder="https://www.youtube.com/watch?v=...")
    c1, c2 = st.columns([1, 1])
    preview_clicked = c1.button("🔎 영상 정보 미리보기")
    start_clicked = c2.button("▶️ 분석 시작", type="primary")
    force_reprocess = st.checkbox(
        "강제 재처리 (캐시 무시)",
        value=False,
        help="이미 처리된 영상도 다운로드·STT부터 다시 처리합니다. 기본은 기존 대본 재사용.",
    )

    # 미리보기 + 기존 결과 감지
    if preview_clicked and url.strip():
        try:
            with st.spinner("영상 정보를 조회 중..."):
                meta = youtube.fetch_metadata(
                    url,
                    cookies_from_browser=cookies,
                    allow_remote_components=config.youtube.allow_remote_components,
                )
            st.session_state["preview"] = meta
            existing = storage.load_result(config.paths.result_dir, meta.video_id)
            st.session_state["existing"] = existing is not None
        except TubeNoteError as exc:
            st.error(exc.user_message)

    if "preview" in st.session_state and not start_clicked:
        meta = st.session_state["preview"]
        pc = st.columns([1, 2])
        if meta.thumbnail_url:
            pc[0].image(meta.thumbnail_url, use_container_width=True)
        pc[1].markdown(
            f"**{meta.title}**  \n채널: {meta.channel or '-'}  \n"
            f"길이: {format_hms(meta.duration_seconds) if meta.duration_seconds else '-'}"
        )
        if st.session_state.get("existing"):
            st.info("이미 처리된 영상입니다. 다시 분석하거나 기존 결과를 불러올 수 있습니다.")
            if st.button("📁 기존 결과 불러오기"):
                result = storage.load_result(config.paths.result_dir, meta.video_id)
                rp = storage.result_dir_for(config.paths.result_dir, meta.video_id) / "result.json"
                mp = storage.result_dir_for(config.paths.result_dir, meta.video_id) / "summary.md"
                st.session_state["result"] = result
                st.session_state["result_path"] = rp
                st.session_state["markdown_path"] = mp if mp.is_file() else None

    # 분석 실행
    if start_clicked:
        if not url.strip():
            st.warning("URL을 입력하세요.")
        else:
            progress_bar = st.progress(0.0)
            status = st.empty()
            log_box = st.empty()
            logs: list[str] = []
            t0 = time.time()

            def ui_log(step: str, message: str) -> None:
                logs.append(f"[{step}] {message}")
                frac = _STEP_FRAC.get(step, 0.5)
                if step == "transcribe":
                    m = re.search(r"진행률\s*([\d.]+)%", message)
                    if m:
                        frac = 0.30 + 0.40 * (float(m.group(1)) / 100)
                progress_bar.progress(min(frac, 1.0))
                status.markdown(f"**{step}** · {message}  \n_경과 {time.time() - t0:.0f}s_")
                log_box.code("\n".join(logs[-12:]))

            try:
                outcome = run_transcription_pipeline(
                    url,
                    config,
                    cookies_from_browser=cookies,
                    summarize_enabled=do_summary,
                    force_reprocess=force_reprocess,
                    log=ui_log,
                )
                progress_bar.progress(1.0)
                _cache_note = " · 기존 대본 재사용(캐시)" if outcome.from_cache else ""
                status.success(f"완료! (총 {time.time() - t0:.0f}s){_cache_note}")
                st.session_state["result"] = outcome.result
                st.session_state["result_path"] = outcome.result_path
                st.session_state["markdown_path"] = outcome.markdown_path
                st.session_state.pop("preview", None)
            except TubeNoteError as exc:
                st.error(f"오류: {exc.user_message}")
                if str(exc) != exc.user_message:
                    st.caption(f"상세: {exc}")
            except Exception as exc:  # pragma: no cover
                st.error(f"예상치 못한 오류: {exc}")

    # 결과 표시
    if "result" in st.session_state and st.session_state["result"] is not None:
        st.divider()
        show_results(
            st.session_state["result"],
            st.session_state.get("result_path", Path()),
            st.session_state.get("markdown_path"),
        )


if __name__ == "__main__":
    main()
