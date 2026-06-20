"""Markdown 결과 렌더링 (기획안 8.9)."""

from __future__ import annotations

from .models import Claim, Result, Topic
from .youtube import timestamp_url


def format_hms(seconds: float) -> str:
    """초를 H:MM:SS 또는 M:SS 형태로 변환."""
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _ts_link(video_id: str, seconds: float | None) -> str:
    """타임스탬프를 클릭 가능한 YouTube 링크로. seconds가 None이면 빈 문자열."""
    if seconds is None:
        return ""
    return f"[{format_hms(seconds)}]({timestamp_url(video_id, seconds)})"


def _format_upload_date(raw: str | None) -> str:
    if raw and len(raw) == 8 and raw.isdigit():
        return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"
    return raw or "-"


def _topic_lines(video_id: str, topics: list[Topic]) -> list[str]:
    lines: list[str] = []
    for t in topics:
        link = _ts_link(video_id, t.timestamp_seconds)
        prefix = f"- **{t.title}**"
        if link:
            prefix += f" ({link})"
        lines.append(prefix)
        if t.detail:
            lines.append(f"  - {t.detail}")
    return lines


def _claim_lines(video_id: str, claims: list[Claim]) -> list[str]:
    lines: list[str] = []
    for c in claims:
        link = _ts_link(video_id, c.timestamp_seconds)
        suffix = f" ({link})" if link else ""
        lines.append(f"- {c.text}{suffix}")
    return lines


def render_markdown(result: Result, *, include_full_transcript: bool = False) -> str:
    """Result를 사람이 읽기 좋은 Markdown 문서로 변환."""
    md = result.metadata
    video_id = md.video_id
    out: list[str] = []

    # 헤더 / 메타데이터
    out.append(f"# {md.title}")
    out.append("")
    out.append(f"- 채널: {md.channel or '-'}")
    out.append(f"- 영상 URL: {md.url}")
    duration = format_hms(md.duration_seconds) if md.duration_seconds else "-"
    out.append(f"- 길이: {duration}")
    out.append(f"- 게시일: {_format_upload_date(md.upload_date)}")
    out.append(f"- 처리 일시: {md.fetched_at}")
    out.append("")

    fs = result.final_summary
    if fs is None:
        out.append("> 요약이 생성되지 않았습니다. 대본만 포함됩니다.")
        out.append("")
    else:
        # 세 줄 요약
        out.append("## 세 줄 요약")
        out.append("")
        if fs.three_line_summary:
            out.extend(f"- {line}" for line in fs.three_line_summary)
        else:
            out.append("- (없음)")
        out.append("")

        # 핵심 내용
        out.append("## 핵심 내용")
        out.append("")
        out.extend(f"- {p}" for p in fs.key_points) if fs.key_points else out.append("- (없음)")
        out.append("")

        # 시간순 목차
        out.append("## 시간순 목차")
        out.append("")
        if fs.timeline:
            for entry in fs.timeline:
                link = _ts_link(video_id, entry.timestamp_seconds)
                out.append(f"- {link} {entry.title}" if link else f"- {entry.title}")
        else:
            out.append("- (없음)")
        out.append("")

        # 서사 요약 (산문형, 읽기용) — 시간순 목차 다음
        if fs.narrative.strip():
            out.append("## 서사 요약")
            out.append("")
            out.append(fs.narrative.strip())
            out.append("")

        # 상세 정리
        out.append("## 상세 정리")
        out.append("")
        out.extend(_topic_lines(video_id, fs.details) or ["- (없음)"])
        out.append("")

        # 주요 주장과 근거
        out.append("## 주요 주장과 근거")
        out.append("")
        out.extend(_claim_lines(video_id, fs.claims) or ["- (없음)"])
        out.append("")

        # 결론
        out.append("## 결론")
        out.append("")
        out.append(fs.conclusion or "(없음)")
        out.append("")

        # 실행 항목
        out.append("## 실행 항목")
        out.append("")
        out.extend(f"- {a}" for a in fs.action_items) if fs.action_items else out.append("- (없음)")
        out.append("")

        # 불확실 / 확인 필요
        out.append("## 불확실하거나 확인이 필요한 내용")
        out.append("")
        out.extend(f"- {u}" for u in fs.uncertain_points) if fs.uncertain_points else out.append("- (없음)")
        out.append("")

    # 전체 대본
    if include_full_transcript:
        out.append("## 전체 대본")
        out.append("")
        for seg in result.transcript:
            link = _ts_link(video_id, seg.start)
            out.append(f"- {link} {seg.text}" if link else f"- {seg.text}")
        out.append("")

    return "\n".join(out)
