"""LLM 기반 요약 (기획안 8.8 / 14절).

2단계 Map-Reduce:
  1. 각 청크를 구조화 요약 (Map)
  2. 청크 요약들을 통합해 최종 문서 작성 (Reduce)

OpenAI 호환 API와 Ollama(OpenAI 호환 /v1 엔드포인트)를 모두 지원한다.
API 키/모델이 없으면 SummaryNotConfiguredError로 알려 파이프라인이 대본까지만
저장하도록 한다.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Callable

from pydantic import ValidationError

from .config import Config
from .chunking import TranscriptChunk
from .errors import SummaryError, SummaryNotConfiguredError
from .models import ChunkSummary, FinalSummary, VideoMetadata
from .security import mask_text, secret_values

# 진행 로그 콜백
SummaryLogger = Callable[[str], None]


def _noop(_msg: str) -> None:  # pragma: no cover
    pass


# prompts/ 디렉터리 (프로젝트 루트). 패키지는 src/tubenote/ 이므로 parents[2].
_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"

_OLLAMA_BASE_URL = "http://localhost:11434/v1"
_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)

# 요약 상세도별 지시문 (프롬프트의 {detail_instruction} 자리에 삽입)
_DETAIL_INSTRUCTIONS: dict[str, str] = {
    "simple": (
        "간결하게 작성하세요. 가장 핵심적인 내용만 남기고 항목 수를 최소화하며, "
        "각 설명은 짧게 1문장 이내로 합니다."
    ),
    "standard": (
        "핵심을 균형 있게 정리하세요. 주요 주제와 근거를 빠짐없이 담되 장황하지 않게 작성합니다."
    ),
    "detailed": (
        "최대한 포괄적이고 자세하게 정리하세요. 표준 수준보다 더 많은 항목을 만드세요 — "
        "details, claims, timeline, key_points 항목 수를 늘리고, 어떤 항목도 줄이거나 합치지 마세요. "
        "그러면서 각 항목의 설명도 더 구체적으로(구체적 사례, 수치, 고유명사, 인용 포함) 작성하세요. "
        "영상에 등장한 세부 내용을 빠짐없이 담는 것을 우선하세요. "
        "action_items는 영상에 실제로 언급된 것이 있으면 하나도 빠뜨리지 말고 모두 포함하세요"
        "(단, 영상에 없으면 만들어내지 말고 비워 두세요)."
    ),
}


def _detail_instruction(detail: str) -> str:
    return _DETAIL_INSTRUCTIONS.get(detail, _DETAIL_INSTRUCTIONS["standard"])


def _load_prompt(name: str, replacements: dict[str, str]) -> str:
    """프롬프트 파일을 읽고 `{placeholder}`를 치환한다.

    프롬프트에 JSON 중괄호가 많아 str.format은 쓰지 않고 단순 치환한다.
    """
    path = _PROMPTS_DIR / name
    text = path.read_text(encoding="utf-8")
    for key, value in replacements.items():
        text = text.replace("{" + key + "}", value)
    return text


def is_summary_configured(config: Config) -> bool:
    """요약을 시도할 수 있는 최소 설정이 갖춰졌는지 검사."""
    summary = config.summary
    if not summary.model:
        return False
    if summary.provider == "ollama":
        return True
    # openai_compatible: 키 또는 사용자 지정 base_url 중 하나는 있어야 함
    return bool(config.secrets.openai_api_key or config.secrets.openai_base_url)


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        # 앞뒤 코드펜스 제거
        lines = stripped.splitlines()
        if lines and lines[0].lstrip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines)
    return stripped.strip()


def _extract_json(text: str) -> dict:
    """LLM 응답에서 JSON 객체를 파싱한다 (코드펜스/잡텍스트에 관대)."""
    candidate = _strip_code_fence(text)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    # 본문 중 첫 { ~ 마지막 } 구간을 시도
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(candidate[start : end + 1])
    raise json.JSONDecodeError("JSON 객체를 찾을 수 없습니다.", candidate, 0)


class Summarizer:
    """OpenAI 호환/Ollama 클라이언트를 감싼 요약기."""

    def __init__(self, config: Config, *, log: SummaryLogger = _noop):
        if not is_summary_configured(config):
            raise SummaryNotConfiguredError()

        from openai import OpenAI

        self.config = config
        self.log = log
        self.model = config.summary.model
        self.max_retries = max(1, config.summary.max_retries)

        if config.summary.provider == "ollama":
            base_url = config.secrets.openai_base_url or _OLLAMA_BASE_URL
            api_key = config.secrets.openai_api_key or "ollama"
        else:
            base_url = config.secrets.openai_base_url or None
            api_key = config.secrets.openai_api_key or "not-needed"

        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def _call(self, prompt: str) -> str:
        """지수 백오프로 재시도하며 LLM을 호출하고 응답 텍스트를 반환."""
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    response_format={"type": "json_object"},
                )
                return resp.choices[0].message.content or ""
            except Exception as exc:  # noqa: BLE001 — 다양한 SDK 예외
                last_exc = exc
                # response_format 미지원 서버 대비: 한 번은 옵션 없이 재시도
                if attempt == 0 and "response_format" in str(exc):
                    try:
                        resp = self.client.chat.completions.create(
                            model=self.model,
                            messages=[{"role": "user", "content": prompt}],
                            temperature=0.2,
                        )
                        return resp.choices[0].message.content or ""
                    except Exception as exc2:  # noqa: BLE001
                        last_exc = exc2
                if attempt < self.max_retries - 1:
                    backoff = 2**attempt
                    self.log(f"LLM 호출 실패, {backoff}s 후 재시도 ({attempt + 1}/{self.max_retries})")
                    time.sleep(backoff)
        masked = mask_text(last_exc, *secret_values(self.config))
        raise SummaryError(f"LLM 호출 실패: {masked}") from last_exc

    def summarize_chunk(self, chunk: TranscriptChunk) -> ChunkSummary:
        prompt = _load_prompt(
            "chunk_summary.md",
            {
                "chunk_text": chunk.to_prompt_text(),
                "detail_instruction": _detail_instruction(self.config.summary.detail),
            },
        )
        raw = self._call(prompt)
        try:
            data = _extract_json(raw)
            summary = ChunkSummary.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise SummaryError(f"청크 요약 형식 오류: {exc}") from exc
        summary.chunk_index = chunk.index
        return summary

    def integrate(
        self,
        metadata: VideoMetadata,
        chunk_summaries: list[ChunkSummary],
    ) -> FinalSummary:
        payload = json.dumps(
            [c.model_dump(mode="json") for c in chunk_summaries],
            ensure_ascii=False,
            indent=2,
        )
        prompt = _load_prompt(
            "final_summary.md",
            {
                "title": metadata.title,
                "channel": metadata.channel or "",
                "duration": str(metadata.duration_seconds or ""),
                "chunk_summaries_json": payload,
                "detail_instruction": _detail_instruction(self.config.summary.detail),
            },
        )
        raw = self._call(prompt)
        try:
            data = _extract_json(raw)
            return FinalSummary.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise SummaryError(f"최종 요약 형식 오류: {exc}") from exc


def summarize(
    chunks: list[TranscriptChunk],
    metadata: VideoMetadata,
    config: Config,
    *,
    log: SummaryLogger = _noop,
) -> tuple[list[ChunkSummary], FinalSummary]:
    """청크 목록을 받아 (청크 요약들, 최종 요약)을 반환한다.

    개별 청크 실패는 건너뛰고 계속 진행한다 (기획안 11절 재시도 정책).
    """
    summarizer = Summarizer(config, log=log)

    chunk_summaries: list[ChunkSummary] = []
    for chunk in chunks:
        log(f"청크 {chunk.index + 1}/{len(chunks)} 요약 중 (~{chunk.char_count}자)")
        try:
            chunk_summaries.append(summarizer.summarize_chunk(chunk))
        except SummaryError as exc:
            log(f"청크 {chunk.index + 1} 요약 실패 — 건너뜀: {exc}")

    if not chunk_summaries:
        raise SummaryError("모든 청크 요약에 실패했습니다.")

    log("최종 통합 요약 작성 중")
    final = summarizer.integrate(metadata, chunk_summaries)
    return chunk_summaries, final
